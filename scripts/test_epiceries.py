#!/usr/bin/env python3
"""Offline behavioral checks; no network access or third-party packages."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

sys.dont_write_bytecode = True
import epiceries as api


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def http_error(status, headers=None):
    body = {"ok": False, "error": {"code": "not_found" if status == 404 else "upstream_error", "message": "Test failure"}}
    return HTTPError(api.BASE_URL, status, "Test failure", headers or {}, response(body))


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.sleep = patch.object(api.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def test_unicode_and_reserved_characters_are_encoded_as_one_query(self):
        query = 'crème & café #1'
        args = api.parse_args(["search", "--query", query, "--cheapest-store", "iga"])
        params = parse_qs(urlsplit(api.request_url(args)).query)
        self.assertEqual(params["q"], [query])
        self.assertEqual(params["store"], ["iga"])
        self.assertNotIn("discounted", params)

    def test_barcode_preserves_leading_zeroes(self):
        args = api.parse_args(["barcode", "0059749870054"])
        self.assertEqual(parse_qs(urlsplit(api.request_url(args)).query)["code"], ["0059749870054"])

    def test_bad_arguments_stop_before_network(self):
        cases = [["search"], ["search", "--query", "x"], ["search", "--query", "lait", "--limit", "101"],
                 ["barcode", "https://example.com"], ["barcode", "１２３４５６７８"],
                 ["history", "abc123", "--from", "2026-02-30"],
                 ["history", "abc123", "--from", "2026-09-22", "--to", "2026-09-01"]]
        with patch.object(api, "urlopen") as network, contextlib.redirect_stderr(io.StringIO()):
            for args in cases:
                with self.subTest(args=args), self.assertRaises(SystemExit) as error:
                    api.main(args)
                self.assertEqual(error.exception.code, 2)
            network.assert_not_called()

    def test_discount_only_search(self):
        params = parse_qs(urlsplit(api.request_url(api.parse_args(["search", "--discounted"]))).query)
        self.assertEqual(params["discounted"], ["true"])
        self.assertNotIn("store", params)

    def test_cache_preserves_raw_fields_and_original_fetch_time(self):
        payload = {"ok": True, "data": {"size": None, "price": 3.49, "unitPrice": {"value": 2.23, "raw": "2.79/100g"}}}
        with patch.object(api, "urlopen", return_value=response(payload)) as network:
            first = api.fetch(api.BASE_URL, self.cache)
            second = api.fetch(api.BASE_URL, self.cache)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(first["data"], payload["data"])
        self.assertEqual(second["data"], payload["data"])
        self.assertFalse(first["_client"]["cache_hit"])
        self.assertTrue(second["_client"]["cache_hit"])
        self.assertEqual(first["_client"]["retrieved_at"], second["_client"]["retrieved_at"])
        request = network.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("User-agent"), "epiceries-api-skill/1.0")

    def test_fresh_bypasses_cache(self):
        with patch.object(api, "urlopen", side_effect=[response({"ok": True, "data": 1}), response({"ok": True, "data": 2})]) as network:
            api.fetch(api.BASE_URL, self.cache)
            result = api.fetch(api.BASE_URL, self.cache, fresh=True)
        self.assertEqual(network.call_count, 2)
        self.assertEqual(result["data"], 2)
        self.assertFalse(result["_client"]["cache_hit"])

    def test_expired_cache_is_not_used_when_api_fails(self):
        with patch.object(api, "urlopen", return_value=response({"ok": True, "data": "old"})):
            api.fetch(api.BASE_URL, self.cache)
        file = next(self.cache.glob("*.json"))
        record = json.loads(file.read_text())
        record["cached_at"] = 0
        file.write_text(json.dumps(record))
        with patch.object(api, "urlopen", side_effect=[http_error(503) for _ in range(3)]) as network, self.assertRaises(api.ClientError):
            api.fetch(api.BASE_URL, self.cache)
        self.assertEqual(network.call_count, 3)

    def test_404_has_structured_nonzero_exit_without_retry(self):
        output = io.StringIO()
        with patch.object(api, "urlopen", side_effect=http_error(404)) as network, contextlib.redirect_stdout(output):
            code = api.main(["--cache-dir", str(self.cache), "product", "missing"])
        self.assertEqual(code, 1)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(json.loads(output.getvalue())["error"]["http_status"], 404)
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_429_obeys_retry_after(self):
        with patch.object(api, "urlopen", side_effect=[http_error(429, {"Retry-After": "3"}), response({"ok": True, "data": []})]) as network:
            self.assertTrue(api.fetch(api.BASE_URL, self.cache)["ok"])
        self.assertEqual(network.call_count, 2)
        self.sleep.assert_any_call(3.0)

    def test_long_retry_after_stops_without_early_retry(self):
        with patch.object(api, "urlopen", side_effect=http_error(429, {"Retry-After": "120"})) as network, self.assertRaises(api.ClientError) as error:
            api.fetch(api.BASE_URL, self.cache)
        self.assertEqual(error.exception.code, "retry_later")
        self.assertEqual(network.call_count, 1)

    def test_invalid_and_api_error_responses_are_not_cached(self):
        for raw in [b'<html>unavailable</html>', b'{"ok":true}', b'[]', b'{"ok":false,"error":{"code":"not_found","message":"missing"}}']:
            with self.subTest(raw=raw), patch.object(api, "urlopen", return_value=io.BytesIO(raw)), self.assertRaises(api.ClientError):
                api.fetch(api.BASE_URL, self.cache)
            self.assertEqual(list(self.cache.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
