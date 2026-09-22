# API contract and usage

Source: [official developer documentation](https://www.epiceries.ca/developers), checked 2026-09-22. The live [API entrypoint](https://epiceries.ca/api) lists supported stores and endpoints. This is a compact operational reference; the provider's current contract takes precedence.

## Transport and responses

- Base: `https://epiceries.ca/api`; query parameters select an endpoint. Only GET is documented. No authentication, API key or postal-code parameter.
- The store identifiers are `maxi`, `iga`, `superc`, `metro`, `provigo`, `walmart`.
- Success: `{"ok":true,"data":...}`. Failure: `{"ok":false,"error":{"code":...,"message":...}}`, normally with HTTP 400, 404, 405 or 500. Missing products are not evidence of missing inventory.
- Provider guidance: cache responses, avoid request bursts, remain below a few calls per second. The documented response cache is five minutes; price collection is described as weekly. Fetch time and observation time are different.
- Public responses are JSON and permit browser CORS. Direct callers should identify their client and request JSON. A descriptive User-Agent worked in live Python testing; the default urllib User-Agent received 403. Stop on persistent 403 rather than attempting access-control workarounds.
- The bundled helper waits one second before each network attempt, uses a 20-second request timeout and retries at most twice for 429, 502, 503 or 504. It honors `Retry-After` up to 30 seconds; longer delays are reported as an error for a later retry. It does not retry other HTTP errors, timeouts or malformed responses, and never substitutes expired cached data after a failure.

## Endpoints

| Helper command / API endpoint | Parameters and semantics |
| --- | --- |
| `info` / bare `/api` | API version, supported retailers and endpoint URLs. |
| `categories` / `endpoint=categories` | Current category IDs and labels. Resolve IDs here; documentation examples are illustrative. |
| `search` / `endpoint=search` | At least one of `q` (2+ characters), `category` (integer), `discounted=true`, `store`. Optional `sort`: `updated_desc`, `price_asc`, `price_desc`; `limit`: 1–100 (default 20); `offset`: 0+. |
| `product ID` / `endpoint=product&id=ID` | Product summary plus `prices`, containing available retailer offers. Top-level `price`/`store` represent the cheapest recorded retailer. Omitted retailers have no returned price. |
| `history ID` / `endpoint=history&id=ID` | Optional `store`, `from`, `to`, `limit` (1–500, default 100). Bounds accept ISO dates or Unix seconds. Returns the most recent limited observations in chronological order. No documented history offset. |
| `barcode CODE` / `endpoint=barcode&code=CODE` | UPC/EAN, 8–14 ASCII digits; pass as text to preserve leading zeroes. Resolves to the service's product ID and summary. |
| `storeproduct STORE CODE` / `endpoint=storeproduct&store=STORE&code=CODE` | Retailer's product identifier, distinct from the service ID and not necessarily a UPC. For supported retailer links, use the code after `/p/`. Returns mapped product, available prices, requested retailer history and possibly `deal`. |

**Search `store` is a cheapest-retailer filter.** It does not return every item carried by that chain. `history.store` instead selects observations for that retailer. The helper deliberately exposes search's filter as `--cheapest-store`.

## CLI examples

Run from the skill folder, or use the script's resolved absolute path:

```bash
python3 scripts/epiceries.py search --query 'lait' --sort price_asc --limit 5
python3 scripts/epiceries.py search --cheapest-store maxi --discounted --limit 10
python3 scripts/epiceries.py search --query 'lait' --limit 5 --offset 5
```

After obtaining a real ID or code, the command shapes are:

```text
python3 scripts/epiceries.py product PRODUCT_ID
python3 scripts/epiceries.py history PRODUCT_ID --store iga --from 2026-08-01 --limit 50
python3 scripts/epiceries.py barcode UPC_OR_EAN
python3 scripts/epiceries.py storeproduct maxi RETAILER_CODE
python3 scripts/epiceries.py --fresh product PRODUCT_ID
```

Replace uppercase placeholders with observed values. Use `--help` or `COMMAND --help` for arguments. `--cache-dir PATH` before a subcommand selects a different local cache location. Successful responses include `_client.url`, `_client.retrieved_at` (UTC fetch time), `_client.cache_hit` and `_client.cache_ttl_seconds`. Cache files contain only public API responses and request URLs. Removing that cache is safe; no credentials are stored.

An AI without a Python runtime can perform the same GET requests with its HTTP tool. Example:

```bash
curl --get --max-time 20 --header 'Accept: application/json' \
  --user-agent 'epiceries-api-skill/1.0' \
  --data-urlencode 'endpoint=search' --data-urlencode 'q=lait' \
  --data-urlencode 'limit=5' 'https://epiceries.ca/api'
```

The helper does not crawl, automatically exhaust pagination, normalize prices or choose substitutions. Those decisions remain with the agent and the user's shopping constraints.

## Data fields that affect comparisons

Search results expose service `id`, `name`, `brand`, `size`, lowest `price`, `store`, `discounted`, `category`, `unitPrice`, product `url`, retailer `link`, image and `updated`. Some fields may be null. Detail `prices` and `history` entries include retailer-specific values and observation `timestamp`/`date`.

`unitPrice` contains `value`, `unit`, `raw`; compare against price and package quantity when possible. Do not assume the parsed value is authoritative when it disagrees with the raw value or arithmetic. Historical records may include different sizes; inspect before treating them as a single comparable series.

`storeproduct.deal` is the provider's assessment, possibly null. Published scores: 3 price floor, 2 good discount, 1 ordinary discount, 0 false discount; null means insufficient history. Keep this attributed and examine `sampleCount` and returned time coverage before making a stronger conclusion.

## Live verification notes

2026-09-22: all seven helper commands (`info`, `categories`, `search`, `product`, `history`, `barcode`, `storeproduct`) returned successful JSON without credentials. The product/retailer/barcode chain resolved the same observed product ID. A repeated detail request hit the local cache; an unknown product returned a structured 404 and exit 1. Eleven offline tests passed, including bounded retry behavior and refusal to serve an expired cached result after an API failure.

Category examples in the website documentation differed from the live mapping: the live `Lait` category was 7 and `Beurre` was 10. Always resolve the current mapping.

Observed searches returned missing package sizes, non-food keyword matches, and inconsistent unit-price fields. A single product detail also contained retailer observations roughly two weeks apart. Category filtering improved relevance but did not make all products equivalent. These are reasons for the comparison checks in `SKILL.md`, not evidence that every record is defective. No specific branch's checkout price or inventory was verified.
