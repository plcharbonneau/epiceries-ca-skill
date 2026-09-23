---
name: epiceries-api
description: "Compare a Québec shopping list across selected grocers using dated épiceries.ca price observations, product matching and source links. Also search products, discounts, barcodes and history; explain coverage gaps and use official flyer evidence when supplied. Read-only; no carts or checkout."
---

# Épiceries.ca API

Use the documented JSON API at `https://epiceries.ca/api`. No account or API key is required. It covers Maxi, IGA, Super C, Metro, Provigo and Walmart. These are recorded retailer prices, not guaranteed branch prices, inventory, or a complete feed of flyer conditions.

For shopping-list requests, accept the user's chosen stores and items. The user may name any Québec grocer, but the API only supports the six chains above and has no postal-code or branch selector. For other stores, use accessible official retailer product pages or a flyer the user provides, identify that source separately, and say when no reliable price source is available. Never describe these observations as *all* products or prices in a store: the API covers tracked products, and flyers cover advertised offers.

## Access

Use the bundled Python 3 client when shell access is available. It uses only the standard library, verified HTTPS and GET requests. Resolve `scripts/epiceries.py` relative to this skill directory; examples below assume that directory is the working directory.

```bash
python3 scripts/epiceries.py info
python3 scripts/epiceries.py categories
python3 scripts/epiceries.py search --query 'lait' --limit 5
python3 scripts/epiceries.py search --query 'beurre' --discounted --limit 10
python3 scripts/compare_list.py --stores maxi,iga,superc --item 'lait 2%' --item 'oeufs 12'
```

For endpoint parameters, identifiers, pagination and direct HTTP alternatives, read [references/api.md](references/api.md). Use IDs returned by current responses, not illustrative IDs in documentation. Check the live developer documentation when a response contradicts the reference; do not substitute unrelated library documentation.

The batch helper searches up to eight candidates per item by default, fetches their per-retailer price rows, and returns JSON with size, observation date/status, retailer link, product link, missing stores, and explicit search/detail truncation. `api_retrieval_complete` only says requested API records were fetched; `all_selected_products_have_recent_store_prices` requires one selected ID per item and a recent observation at every chosen chain. Neither confirms a branch's checkout price. Use `--max-products` to widen a query and `--max-details` to bound total detail calls. Its 14-day `--max-age-days` threshold only flags older observations; it never proves a sale is active. The helper does **not** decide whether different candidate products are equivalent. A broad query can include unrelated items, and `lowest_recent` is only within one product ID across the selected stores. For a vetted list, pass a JSON file to `--input`:

```json
{"stores":["maxi","iga","superc"],"items":[{"label":"Québon 2% 2 L","ids":["ID_FROM_LIVE_SEARCH"]},{"label":"eggs, 12","query":"oeufs 12"}]}
```

The `ids` form compares exact tracked products across stores; the `query` form discovers candidates that require match review. Run `python3 scripts/compare_list.py --help` for limits and switches. Do not place example IDs into real calls.

The low-level `epiceries.py` helper preserves the API's `ok`/`data` envelope and adds `_client` with request URL, fetch time and cache status. Both scripts use its five-minute local cache and one-second spacing for network requests. Run calls serially. `--fresh` bypasses only that local cache; it does not force the provider to collect new prices. The batch helper reports per-item errors and exits 1 if any API call fails; invalid CLI arguments exit 2. Inspect both the exit status and `ok`.

## Find and compare suitable products

1. Preserve requested brands, quantities, package sizes, food forms, dietary needs and retailer preferences. Match the user's response language. French search terms are often useful for this catalogue; translate meaning without changing the requested product.
2. Search a small candidate set. For ambiguous words, fetch `categories` and use the current category ID. Keyword matches can include unrelated products, and even the butter category includes plant-based spreads and flavoured butter.
3. Inspect the name, brand and size before comparing. Fetch `product` for each suitable candidate to get its available `prices` entries. **The search `store` parameter filters by the cheapest retailer, not by availability at that retailer.** The helper names this option `--cheapest-store`. To compare IGA versus Maxi, search without that filter, then select IGA and Maxi entries from each product's `prices`.
4. Follow search pagination only as far as needed, using `hasMore`, `offset` and `limit`. Say “lowest among the matching offers checked” unless the evidence supports a broader claim. An omitted retailer or empty result means no matching record, not zero cost or proven unavailability.
   If the batch result says `search_truncated`, refine the query or increase its candidate limit before claiming that a requested match is absent.
5. For a known UPC/EAN use `barcode`, retaining leading zeroes. For a retailer product URL, use its actual retailer-specific code with `storeproduct`. That response can include a retailer's historical deal assessment; attribute the assessment to épiceries.ca.

## Interpret prices and build a shopping comparison

- Show observation dates (`updated` or each offer's `date`) separately from the client's fetch time. Product-level freshness does not establish freshness for all retailer offers. Compare dates with the user's planned shopping date; do not call an old observation a verified current special.
- `discounted=true` is a recorded discount flag. It does not establish flyer inclusion, sale expiry, membership eligibility, minimum quantities or stock. If these conditions matter and are absent, report them as unknown or verify the linked retailer offer within the user's task.
- Check the quantity basis. Fixed packages, variable-weight estimates, multipacks, $/kg and $/each cannot be compared as the same unit. When price and package quantity are clear, calculate a comparable unit price and label it calculated. Null sizes and inconsistent `unitPrice.value`/`raw` occur; preserve the source value and flag discrepancies rather than silently correcting the record or inventing a size.
- For a specified amount, use whole required packages and report surplus. A store basket with missing items is a partial subtotal; do not rank it as the cheapest complete basket. Present single-store and split-store totals only for comparable, matched products and the user's allowed substitutions. Label estimates and exclude unknown fees explicitly when relevant.
- History contains observations, not proof that a price held between dates. Inspect returned coverage before saying “lowest this year”; a limited history response or null deal score is insufficient for that claim. If numeric and ISO dates disagree, flag the inconsistency before time-based analysis.
- Attribute results to épiceries.ca and link returned product and retailer pages. A compact result normally includes product/size, retailer, recorded CAD price, comparable unit price when supported, observation date, and relevant qualifications.
- For a shopping-list comparison, show every requested store as a column or row, using “no tracked price” when its offer is absent. Review query candidates for actual product, brand, size, dietary form and unit. Do not rank unrelated candidates or use a partial basket as a complete total. Treat `search_truncated`, `detail_truncated`, API errors or unknown dates as explicit coverage gaps.
- When asked for *all prices*, return every relevant, comparable offer found for the requested items at the selected stores, not only a cheapest-price summary. Give price, package size, unit price if reliable, observation date and both retailer/product source links. State the search bounds and any unrepresented stores or items.
- If current official flyers or retailer pages are supplied or accessible, inspect the relevant offer and record its store/branch, validity window, package size, conditions and link or flyer page. For image/PDF flyers, check that the extracted price, product and conditions belong to the same offer panel; flag uncertain reading for review. Keep flyer evidence separate from API observations; resolve conflicts against the retailer's current store-specific offer when possible. Never infer flyer inclusion or validity from `discounted=true`.

The API has no documented cart, list-writing, order, payment or alert-subscription endpoints. Support requests for price research and planning through this skill; use the appropriate separate shopping workflow if the user also requests retailer actions.

## Validation and maintenance

Run `python3 scripts/test_epiceries.py` and `python3 scripts/test_compare_list.py` for offline checks of request handling and shopping-list coverage. Live smoke tests and observed limitations are recorded in [references/api.md](references/api.md). Refresh the API contract if endpoints, filters or returned fields change.
