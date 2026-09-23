#!/usr/bin/env python3
"""Compare recorded prices for a shopping list at selected Québec chains.

This is an evidence collector, not a complete store catalogue or a product matcher.
Python 3.9+, standard library only.
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sys

import epiceries as api


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="JSON shopping list; see README")
    source.add_argument("--item", action="append", help="Search term; repeat for each item")
    parser.add_argument("--stores", help="Comma-separated chains; overrides input file stores")
    parser.add_argument("--max-products", type=api.ranged_int(1, 100), default=8,
                        help="Maximum search candidates per item (default: 8)")
    parser.add_argument("--max-details", type=api.ranged_int(1, 200), default=80,
                        help="Maximum distinct product-detail requests per run (default: 80)")
    parser.add_argument("--max-age-days", type=api.ranged_int(0, 365), default=14,
                        help="Flag older observations; heuristic, not sale validity (default: 14)")
    parser.add_argument("--fresh", action="store_true", help="Bypass local cache only")
    parser.add_argument("--cache-dir", type=Path, default=api.parse_args(["info"]).cache_dir)
    args = parser.parse_args(argv)
    try:
        request = load_request(args)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return args, request


def load_request(args):
    if args.input:
        request = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("Input must be a JSON object")
        items = request.get("items")
        stores = args.stores if args.stores is not None else request.get("stores")
    else:
        items = [{"label": term, "query": term} for term in args.item]
        stores = args.stores
    if isinstance(stores, str):
        stores = stores.split(",")
    if not isinstance(stores, list) or not stores:
        raise ValueError("Specify at least one store with --stores or input file stores")
    clean_stores = []
    for store in stores:
        if not isinstance(store, str) or store.strip().lower() not in api.STORES:
            raise ValueError(f"Unsupported store: {store!r}; choose from {', '.join(api.STORES)}")
        normalized = store.strip().lower()
        if normalized not in clean_stores:
            clean_stores.append(normalized)
    if not isinstance(items, list) or not items:
        raise ValueError("Input must contain a nonempty items array")
    if len(items) > 30:
        raise ValueError("Limit each run to 30 items to respect API usage guidance")
    clean_items = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each item must be an object")
        label = item.get("label")
        query = item.get("query")
        ids = item.get("ids")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("Each item needs a nonempty label")
        if (query is None) == (ids is None):
            raise ValueError(f"{label!r}: provide either query or ids, not both")
        if query is not None:
            if not isinstance(query, str) or len(query.strip()) < 2:
                raise ValueError(f"{label!r}: query needs at least two characters")
            clean_items.append({"label": label.strip(), "query": query.strip()})
        else:
            if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
                raise ValueError(f"{label!r}: ids must contain 1–20 product IDs")
            if any(not isinstance(i, str) or not re.fullmatch(r"[A-Za-z0-9]+", i) for i in ids):
                raise ValueError(f"{label!r}: use alphanumeric product IDs from the API")
            clean_items.append({"label": label.strip(), "ids": list(dict.fromkeys(ids))})
    return {"stores": clean_stores, "items": clean_items}


def call_api(command, value, args):
    if command == "search":
        endpoint_args = api.parse_args(["search", "--query", value, "--limit", str(args.max_products)])
    else:
        endpoint_args = api.parse_args(["product", value])
    payload = api.fetch(api.request_url(endpoint_args), args.cache_dir, args.fresh)
    return payload["data"]


def observation_status(raw_date, now, max_age_days):
    if not isinstance(raw_date, str):
        return "unknown", None
    try:
        observed = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return "unknown", None
        age_days = (now - observed.astimezone(timezone.utc)).total_seconds() / 86400
    except (ValueError, OverflowError):
        return "unknown", None
    if age_days < -1 / 24:
        return "future_date", round(age_days, 1)
    if age_days > max_age_days:
        return "old", round(age_days, 1)
    return "recent_observation", round(max(0, age_days), 1)


def normalize_product(data, stores, now, max_age_days):
    if not isinstance(data, dict) or not isinstance(data.get("prices"), list):
        raise api.ClientError("invalid_response", "Product response lacks a prices array")
    offers = []
    for price in data["prices"]:
        if not isinstance(price, dict) or price.get("store") not in stores:
            continue
        status, age_days = observation_status(price.get("date"), now, max_age_days)
        amount = price.get("price")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            status = "invalid_price"
            amount = None
        offers.append({
            "store": price["store"], "price_cad": amount, "size": price.get("size"),
            "unit_price": price.get("unitPrice"), "discounted": price.get("discounted"),
            "observed_at": price.get("date"), "age_days": age_days,
            "observation_status": status, "retailer_url": price.get("link"),
        })
    offers.sort(key=lambda offer: (stores.index(offer["store"]), offer["price_cad"] is None))
    seen = {offer["store"] for offer in offers}
    recent = [offer for offer in offers if offer["observation_status"] == "recent_observation"]
    cheapest = min(recent, key=lambda offer: offer["price_cad"]) if recent else None
    return {
        "id": data.get("id"), "name": data.get("name"), "brand": data.get("brand"),
        "size": data.get("size"), "product_url": data.get("url") or
        (api.BASE_URL.replace("/api", "/view?i=") + data["id"] if isinstance(data.get("id"), str) else None),
        "product_updated_at": data.get("updated"), "offers": offers,
        "missing_stores": [store for store in stores if store not in seen],
        "lowest_recent": ({"store": cheapest["store"], "price_cad": cheapest["price_cad"],
                           "observed_at": cheapest["observed_at"]} if cheapest else None),
    }


def compare(request, args, now=None):
    now = now or datetime.now(timezone.utc)
    output = {
        "ok": True, "source": "epiceries.ca", "started_at": now.isoformat(),
        "stores": request["stores"], "max_age_days": args.max_age_days,
        "coverage": "Tracked products and recorded retailer observations only; not complete catalogues, local inventory or verified flyer prices.",
        "items": [], "errors": [],
    }
    details_cache = {}
    for item in request["items"]:
        row = {"label": item["label"], "mode": "query" if "query" in item else "selected_ids",
               "products": [], "search_truncated": False, "detail_truncated": False}
        if "query" in item:
            row["query"] = item["query"]
            row["needs_product_match_review"] = True
            try:
                found = call_api("search", item["query"], args)
                if not isinstance(found, dict) or not isinstance(found.get("results"), list):
                    raise api.ClientError("invalid_response", "Search response lacks results")
                ids = list(dict.fromkeys(result["id"] for result in found["results"]
                                         if isinstance(result, dict) and isinstance(result.get("id"), str)))
                row["search_truncated"] = bool(found.get("hasMore"))
                row["search_result_count"] = len(ids)
            except api.ClientError as error:
                output["errors"].append({"item": item["label"], "code": error.code, "message": str(error)})
                output["ok"] = False
                output["items"].append(row)
                continue
        else:
            row["requested_ids"] = item["ids"]
            row["needs_product_match_review"] = len(item["ids"]) > 1
            ids = item["ids"]
        row["_pending_ids"] = ids
        output["items"].append(row)
    details_attempted = 0
    while any(row.get("_pending_ids") for row in output["items"]):
        progressed = False
        for row in output["items"]:
            pending = row.get("_pending_ids", [])
            if not pending:
                continue
            product_id = pending[0]
            if product_id not in details_cache and details_attempted >= args.max_details:
                continue
            pending.pop(0)
            progressed = True
            try:
                if product_id not in details_cache:
                    details_attempted += 1
                    try:
                        details_cache[product_id] = call_api("product", product_id, args)
                    except api.ClientError as error:
                        details_cache[product_id] = error
                detail = details_cache[product_id]
                if isinstance(detail, api.ClientError):
                    raise detail
                product = normalize_product(detail, request["stores"], now, args.max_age_days)
                row["products"].append(product)
            except api.ClientError as error:
                output["errors"].append({"item": row["label"], "product_id": product_id,
                                         "code": error.code, "message": str(error)})
                output["ok"] = False
        if not progressed:
            break
    for row in output["items"]:
        pending = row.pop("_pending_ids", [])
        row["detail_truncated"] = bool(pending)
        row["unfetched_product_count"] = len(pending)
    output["product_details_requested"] = details_attempted
    output["api_retrieval_complete"] = all(
        not row["search_truncated"] and not row["detail_truncated"] for row in output["items"]
    ) and not output["errors"]
    output["all_selected_products_have_recent_store_prices"] = output["api_retrieval_complete"] and all(
        not row["needs_product_match_review"] and len(row["products"]) == 1 and
        {offer["store"] for offer in row["products"][0]["offers"]
         if offer["observation_status"] == "recent_observation"} == set(request["stores"])
        for row in output["items"]
    )
    output["completed_at"] = datetime.now(timezone.utc).isoformat()
    return output


def main(argv=None):
    args, request = parse_args(argv)
    report = compare(request, args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
