#!/usr/bin/env python3
"""Small read-only épiceries.ca client. Python 3.9+, standard library only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://epiceries.ca/api"
STORES = ("maxi", "iga", "superc", "metro", "provigo", "walmart")
CACHE_TTL = 300
RETRY_CODES = {429, 502, 503, 504}
MAX_RETRIES = 2


class ClientError(Exception):
    def __init__(self, code, message, status=None):
        super().__init__(message)
        self.code, self.status = code, status


def ranged_int(low, high=None):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("Expected an integer")
        if number < low or (high is not None and number > high):
            raise argparse.ArgumentTypeError(f"Expected {low}..{high or 'unbounded'}")
        return number
    return parse


def date_bound(value):
    if re.fullmatch(r"[0-9]+", value):
        try:
            datetime.fromtimestamp(int(value), timezone.utc)
            return value
        except (ValueError, OverflowError, OSError):
            pass
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError("Use an ISO date/datetime or Unix seconds")
    return value


def bound_seconds(value):
    if value.isdigit():
        return int(value)
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (date if date.tzinfo else date.replace(tzinfo=timezone.utc)).timestamp()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fresh", action="store_true", help="Bypass local cache only")
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) /
                        f"epiceries-api-{os.getuid() if hasattr(os, 'getuid') else 'user'}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("info", help="API metadata")
    commands.add_parser("categories", help="Current category IDs")
    search = commands.add_parser("search", help="Search recorded product prices")
    search.add_argument("--query", dest="q")
    search.add_argument("--category", type=ranged_int(1))
    search.add_argument("--discounted", action="store_true")
    search.add_argument("--cheapest-store", dest="store", choices=STORES,
                        help="Only products cheapest at this retailer; NOT its catalogue")
    search.add_argument("--sort", choices=("updated_desc", "price_asc", "price_desc"), default="updated_desc")
    search.add_argument("--limit", type=ranged_int(1, 100), default=20)
    search.add_argument("--offset", type=ranged_int(0), default=0)
    product = commands.add_parser("product", help="Product and offers across retailers")
    product.add_argument("id")
    history = commands.add_parser("history", help="Dated price observations")
    history.add_argument("id")
    history.add_argument("--store", choices=STORES)
    history.add_argument("--from", dest="from_date", type=date_bound)
    history.add_argument("--to", dest="to_date", type=date_bound)
    history.add_argument("--limit", type=ranged_int(1, 500), default=100)
    barcode = commands.add_parser("barcode", help="Resolve UPC/EAN, preserving leading zeroes")
    barcode.add_argument("code")
    storeproduct = commands.add_parser("storeproduct", help="Resolve a retailer product code")
    storeproduct.add_argument("store", choices=STORES)
    storeproduct.add_argument("code")
    args = parser.parse_args(argv)
    if args.command == "search":
        if args.q is not None:
            args.q = args.q.strip()
            if len(args.q) < 2:
                parser.error("--query requires at least two characters")
        if not any((args.q, args.category, args.discounted, args.store)):
            parser.error("search requires a query, category, discount or cheapest-store filter")
    if args.command == "barcode" and not re.fullmatch(r"[0-9]{8,14}", args.code):
        parser.error("barcode must contain 8–14 ASCII digits; retain leading zeroes")
    if args.command in {"product", "history"} and not re.fullmatch(r"[A-Za-z0-9]+", args.id):
        parser.error("Use the alphanumeric product ID returned by the API")
    if args.command == "storeproduct" and (not args.code.strip() or len(args.code) > 200):
        parser.error("Use the retailer's product code, not its full URL")
    if args.command == "history" and args.from_date and args.to_date:
        if bound_seconds(args.from_date) > bound_seconds(args.to_date):
            parser.error("--from must not be later than --to")
    return args


def request_url(args):
    if args.command == "info":
        return BASE_URL
    fields = {
        "categories": (), "search": ("q", "category", "store", "sort", "limit", "offset"),
        "product": ("id",), "history": ("id", "store", "limit"),
        "barcode": ("code",), "storeproduct": ("store", "code"),
    }
    params = {"endpoint": args.command}
    for name in fields[args.command]:
        value = getattr(args, name, None)
        if value is not None:
            params[name] = value
    if args.command == "search" and args.discounted:
        params["discounted"] = "true"
    if args.command == "history":
        for name, value in (("from", args.from_date), ("to", args.to_date)):
            if value is not None:
                params[name] = value
    return BASE_URL + "?" + urlencode(params)


def retry_delay(header, attempt):
    if not header:
        return 2 ** (attempt + 1)
    try:
        delay = float(header)
    except ValueError:
        try:
            date = parsedate_to_datetime(header)
            delay = date.timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return 2 ** (attempt + 1)
    if not 0 <= delay <= 30:
        if delay < 0:
            return 0
        raise ClientError("retry_later", "Retry-After exceeds the 30-second retry budget; retry later")
    return delay


def decode_payload(raw):
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ClientError("invalid_response", "API did not return valid JSON")
    if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
        raise ClientError("invalid_response", "Response lacks the documented ok envelope")
    if not payload["ok"]:
        error = payload.get("error") or {}
        if not isinstance(error, dict):
            error = {}
        raise ClientError(error.get("code", "api_error"), error.get("message", "API reported failure"))
    if "data" not in payload:
        raise ClientError("invalid_response", "Successful response is missing data")
    return payload


def fetch(url, cache_dir, fresh=False):
    cache_file = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if not fresh:
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            age = time.time() - cached["cached_at"]
            if cached["url"] == url and 0 <= age < CACHE_TTL:
                payload = decode_payload(json.dumps(cached["payload"]))
                return result(payload, url, cached["retrieved_at"], True)
        except (OSError, ValueError, KeyError, TypeError, ClientError):
            pass
    request = Request(url, headers={"User-Agent": "epiceries-api-skill/1.0", "Accept": "application/json"}, method="GET")
    for attempt in range(MAX_RETRIES + 1):
        time.sleep(1)
        try:
            with urlopen(request, timeout=20) as response:
                payload = decode_payload(response.read())
            break
        except HTTPError as error:
            if error.code in RETRY_CODES and attempt < MAX_RETRIES:
                header = error.headers.get("Retry-After")
                error.close()
                time.sleep(retry_delay(header, attempt))
                continue
            try:
                decode_payload(error.read())
            except ClientError as detail:
                if detail.code != "invalid_response":
                    raise ClientError(detail.code, str(detail), error.code)
            finally:
                error.close()
            raise ClientError("http_error", f"API returned HTTP {error.code}", error.code)
        except (URLError, TimeoutError, OSError) as error:
            raise ClientError("network_error", str(error))
    retrieved_at = datetime.now(timezone.utc).isoformat()
    record = {"url": url, "cached_at": time.time(), "retrieved_at": retrieved_at, "payload": payload}
    temporary = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_dir, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False)
        temporary.replace(cache_file)
    except OSError:
        print("Warning: could not write local cache", file=sys.stderr)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return result(payload, url, retrieved_at, False)


def result(payload, url, retrieved_at, cache_hit):
    return {**payload, "_client": {"url": url, "retrieved_at": retrieved_at,
                                  "cache_hit": cache_hit, "cache_ttl_seconds": CACHE_TTL}}


def main(argv=None):
    args = parse_args(argv)
    url = request_url(args)
    try:
        payload = fetch(url, args.cache_dir, args.fresh)
    except ClientError as error:
        payload = {"ok": False, "error": {"code": error.code, "message": str(error)}, "_client": {"url": url}}
        if error.status is not None:
            payload["error"]["http_status"] = error.status
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
