---
name: epiceries-api
description: "Use the public épiceries.ca developer API to search Québec grocery products, compare recorded prices across retailers, find discounts, look up barcodes or retailer product codes, and examine price history. Use for épiceries.ca data and grocery-list price research; the API is read-only and does not manage carts or checkout."
---

# Épiceries.ca API

Use the documented JSON API at `https://epiceries.ca/api`. No account or API key is required. It covers Maxi, IGA, Super C, Metro, Provigo and Walmart. These are recorded retailer prices, not guaranteed branch prices, inventory, or a complete feed of flyer conditions.

## Access

Use the bundled Python 3 client when shell access is available. It uses only the standard library, verified HTTPS and GET requests. Resolve `scripts/epiceries.py` relative to this skill directory; examples below assume that directory is the working directory.

```bash
python3 scripts/epiceries.py info
python3 scripts/epiceries.py categories
python3 scripts/epiceries.py search --query 'lait' --limit 5
python3 scripts/epiceries.py search --query 'beurre' --discounted --limit 10
```

For endpoint parameters, identifiers, pagination and direct HTTP alternatives, read [references/api.md](references/api.md). Use IDs returned by current responses, not illustrative IDs in documentation. Check the live developer documentation when a response contradicts the reference; do not substitute unrelated library documentation.

The helper preserves the API's `ok`/`data` envelope and adds `_client` with request URL, fetch time and cache status. It caches successful responses for five minutes in the operating system's temporary directory and spaces network requests by one second. Run calls serially. `--fresh` before the subcommand bypasses the local cache; it does not force the provider to collect new prices or bypass its cache. Network/API failures return JSON and exit 1; invalid CLI arguments print usage to stderr and exit 2. Inspect both the exit status and `ok`.

## Find and compare suitable products

1. Preserve requested brands, quantities, package sizes, food forms, dietary needs and retailer preferences. Match the user's response language. French search terms are often useful for this catalogue; translate meaning without changing the requested product.
2. Search a small candidate set. For ambiguous words, fetch `categories` and use the current category ID. Keyword matches can include unrelated products, and even the butter category includes plant-based spreads and flavoured butter.
3. Inspect the name, brand and size before comparing. Fetch `product` for each suitable candidate to get its available `prices` entries. **The search `store` parameter filters by the cheapest retailer, not by availability at that retailer.** The helper names this option `--cheapest-store`. To compare IGA versus Maxi, search without that filter, then select IGA and Maxi entries from each product's `prices`.
4. Follow search pagination only as far as needed, using `hasMore`, `offset` and `limit`. Say “lowest among the matching offers checked” unless the evidence supports a broader claim. An omitted retailer or empty result means no matching record, not zero cost or proven unavailability.
5. For a known UPC/EAN use `barcode`, retaining leading zeroes. For a retailer product URL, use its actual retailer-specific code with `storeproduct`. That response can include a retailer's historical deal assessment; attribute the assessment to épiceries.ca.

## Interpret prices and build a shopping comparison

- Show observation dates (`updated` or each offer's `date`) separately from the client's fetch time. Product-level freshness does not establish freshness for all retailer offers. Compare dates with the user's planned shopping date; do not call an old observation a verified current special.
- `discounted=true` is a recorded discount flag. It does not establish flyer inclusion, sale expiry, membership eligibility, minimum quantities or stock. If these conditions matter and are absent, report them as unknown or verify the linked retailer offer within the user's task.
- Check the quantity basis. Fixed packages, variable-weight estimates, multipacks, $/kg and $/each cannot be compared as the same unit. When price and package quantity are clear, calculate a comparable unit price and label it calculated. Null sizes and inconsistent `unitPrice.value`/`raw` occur; preserve the source value and flag discrepancies rather than silently correcting the record or inventing a size.
- For a specified amount, use whole required packages and report surplus. A store basket with missing items is a partial subtotal; do not rank it as the cheapest complete basket. Present single-store and split-store totals only for comparable, matched products and the user's allowed substitutions. Label estimates and exclude unknown fees explicitly when relevant.
- History contains observations, not proof that a price held between dates. Inspect returned coverage before saying “lowest this year”; a limited history response or null deal score is insufficient for that claim. If numeric and ISO dates disagree, flag the inconsistency before time-based analysis.
- Attribute results to épiceries.ca and link returned product and retailer pages. A compact result normally includes product/size, retailer, recorded CAD price, comparable unit price when supported, observation date, and relevant qualifications.

The API has no documented cart, list-writing, order, payment or alert-subscription endpoints. Support requests for price research and planning through this skill; use the appropriate separate shopping workflow if the user also requests retailer actions.

## Validation and maintenance

Run `python3 scripts/test_epiceries.py` for offline checks of request validation, caching and error handling. Live smoke tests and observed limitations are recorded in [references/api.md](references/api.md). Refresh the API contract if endpoints, filters or returned fields change.
