#!/usr/bin/env python3
"""Offline checks for shopping-list coverage and price-evidence handling."""

import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import compare_list as comparison
import epiceries as api


NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


def args(max_products=8, max_details=80):
    return SimpleNamespace(max_products=max_products, max_details=max_details,
                           max_age_days=14, fresh=False, cache_dir=Path(tempfile.gettempdir()))


def product(product_id, prices):
    return {"id": product_id, "name": "Lait 2%", "brand": "Québon", "size": "2 L",
            "url": f"https://epiceries.ca/view?i={product_id}", "updated": "2026-09-22T00:00:00Z",
            "store": "walmart", "price": 1.00, "prices": prices}


class ComparisonTests(unittest.TestCase):
    def test_input_requires_supported_stores_and_unambiguous_items(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "list.json"
            source.write_text(json.dumps({"stores": ["Maxi", "IGA", "maxi"],
                                          "items": [{"label": "milk", "ids": ["Ab12"]}]}))
            _, request = comparison.parse_args(["--input", str(source)])
            self.assertEqual(request["stores"], ["maxi", "iga"])
            source.write_text(json.dumps({"stores": ["costco"],
                                          "items": [{"label": "milk", "query": "lait"}]}))
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                comparison.parse_args(["--input", str(source)])

    def test_per_store_date_overrides_top_level_cheapest_and_updated(self):
        data = product("A1", [
            {"store": "maxi", "price": 4.60, "size": "2 L", "date": "2026-09-22T00:00:00Z",
             "link": "https://www.maxi.ca/p/a"},
            {"store": "iga", "price": 3.00, "size": "2 L", "date": "2025-09-22T00:00:00Z",
             "link": "https://www.iga.ca/p/a"},
            {"store": "walmart", "price": 1.00, "date": "2026-09-22T00:00:00Z"},
        ])
        result = comparison.normalize_product(data, ["maxi", "iga", "superc"], NOW, 14)
        self.assertEqual(result["lowest_recent"]["store"], "maxi")
        self.assertEqual(result["offers"][1]["observation_status"], "old")
        self.assertEqual(result["offers"][1]["retailer_url"], "https://www.iga.ca/p/a")
        self.assertEqual(result["missing_stores"], ["superc"])
        self.assertEqual(len(result["offers"]), 2)

    def test_query_does_not_filter_to_cheapest_store_or_claim_product_match(self):
        calls = []

        def fake_call(command, value, options):
            calls.append((command, value))
            if command == "search":
                return {"results": [{"id": "A1"}], "hasMore": True}
            return product("A1", [{"store": "iga", "price": 4.49,
                                   "date": "2026-09-22T00:00:00Z"}])

        with patch.object(comparison, "call_api", side_effect=fake_call):
            report = comparison.compare({"stores": ["maxi", "iga"],
                                         "items": [{"label": "milk", "query": "lait"}]}, args(), NOW)
        row = report["items"][0]
        self.assertEqual(calls, [("search", "lait"), ("product", "A1")])
        self.assertTrue(row["needs_product_match_review"])
        self.assertTrue(row["search_truncated"])
        self.assertFalse(report["api_retrieval_complete"])
        self.assertFalse(report["all_selected_products_have_recent_store_prices"])
        self.assertEqual(row["products"][0]["offers"][0]["store"], "iga")
        self.assertEqual(row["products"][0]["missing_stores"], ["maxi"])

    def test_detail_budget_round_robins_across_list_and_marks_unfetched(self):
        def fake_call(command, value, options):
            if command == "search":
                return {"results": [{"id": value + "1"}, {"id": value + "2"}], "hasMore": False}
            return product(value, [])

        with patch.object(comparison, "call_api", side_effect=fake_call):
            report = comparison.compare({"stores": ["maxi"], "items": [
                {"label": "milk", "query": "lait"},
                {"label": "eggs", "query": "oeufs"},
            ]}, args(max_details=2), NOW)
        self.assertEqual(report["product_details_requested"], 2)
        self.assertEqual([len(row["products"]) for row in report["items"]], [1, 1])
        self.assertEqual([row["unfetched_product_count"] for row in report["items"]], [1, 1])
        self.assertFalse(report["api_retrieval_complete"])

    def test_error_is_reported_without_silently_using_partial_result(self):
        def fake_call(command, value, options):
            if value == "Bad":
                raise api.ClientError("network_error", "Test outage")
            return product(value, [{"store": "maxi", "price": 5.0,
                                    "date": "2026-09-22T00:00:00Z"}])

        with patch.object(comparison, "call_api", side_effect=fake_call):
            report = comparison.compare({"stores": ["maxi"], "items": [
                {"label": "butter", "ids": ["Good", "Bad"]},
            ]}, args(), NOW)
        self.assertFalse(report["ok"])
        self.assertEqual(report["errors"][0]["product_id"], "Bad")
        self.assertEqual(len(report["items"][0]["products"]), 1)

    def test_retrieval_completion_is_not_recent_store_coverage(self):
        with patch.object(comparison, "call_api", return_value=product("Eggs", [
            {"store": "superc", "price": 2.97, "date": "2025-11-13T00:00:00Z"},
        ])):
            report = comparison.compare({"stores": ["maxi", "superc"], "items": [
                {"label": "eggs", "ids": ["Eggs"]},
            ]}, args(), NOW)
        self.assertTrue(report["api_retrieval_complete"])
        self.assertFalse(report["all_selected_products_have_recent_store_prices"])
        self.assertEqual(report["items"][0]["products"][0]["missing_stores"], ["maxi"])


if __name__ == "__main__":
    unittest.main()
