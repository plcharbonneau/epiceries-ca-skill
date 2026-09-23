# Épiceries.ca API skill

[![Tests](https://github.com/plcharbonneau/epiceries-ca-skill/actions/workflows/tests.yml/badge.svg)](https://github.com/plcharbonneau/epiceries-ca-skill/actions/workflows/tests.yml)

An agent skill for comparing a shopping list across chosen Québec grocers through the public [épiceries.ca developer API](https://www.epiceries.ca/developers). Search products, compare each selected chain's recorded price and observation date, find discounts, resolve barcodes and examine price history.

The skill covers **Maxi, IGA, Super C, Metro, Provigo and Walmart**. Its Python client requires no API key and no third-party Python packages.

This is an independent integration, unaffiliated with épiceries.ca or the retailers. It provides price research and shopping-list planning; the API does not support cart updates or checkout.

## Install

With Node.js and npm available, use the [Skills CLI](https://skills.sh/docs):

```bash
npx skills add plcharbonneau/epiceries-ca-skill
```

Select `epiceries-api` and your agent in the installer. For a global installation, add `-g`:

```bash
npx skills add plcharbonneau/epiceries-ca-skill -g
```

The helper requires Python 3.9 or newer and network access to `epiceries.ca`. An agent with an HTTP tool can also follow the documented requests directly without Python. This repository uses the `SKILL.md` format and includes Codex UI metadata in `agents/openai.yaml`.

## Ask your agent

```text
Use $epiceries-api to compare milk, eggs and butter across Maxi, IGA
and Super C. Review product matches and include package sizes,
observation dates, missing prices and source links.
```

```text
Utilise $epiceries-api pour comparer ma liste d'épicerie chez Metro
et Provigo. Signale les produits manquants et les prix anciens.
```

The skill teaches the agent to match product variants and quantities, check observation dates, and distinguish a partial basket from a complete comparison. It also explains a subtle API behavior: the search `store` filter selects products whose **cheapest recorded retailer** is that chain, rather than everything that chain carries.

## Compare a shopping list

For quick discovery, repeat `--item` and choose one or more supported chains:

```bash
python3 scripts/compare_list.py --stores maxi,iga,superc \
  --item 'lait 2%' --item 'oeufs 12' --item 'beurre 454'
```

This returns JSON for up to eight search candidates per item by default. Each candidate includes every recorded price returned for the chosen chains, its store-specific observation date and retailer link, and any stores with no returned price. **The candidates still need product review.** For example, a butter search can include butter cookies. A recent observation is not a confirmed current flyer promotion or a branch's checkout price.

For a precise comparison, first use `search` to identify matching products, then put their real API IDs in a JSON file:

```json
{
  "stores": ["maxi", "iga", "superc"],
  "items": [
    {"label": "Québon 2% milk, 2 L", "ids": ["REPLACE_WITH_LIVE_ID"]},
    {"label": "eggs, 12", "query": "oeufs 12"}
  ]
}
```

```bash
python3 scripts/compare_list.py --input /path/to/list.json
```

Replace the placeholder ID before running. The `ids` form fetches exact tracked products; the `query` form discovers possible matches. If several IDs appear under one item, the agent must decide whether they are genuinely interchangeable. The output reports `search_truncated`, `detail_truncated`, API errors and missing store records. `api_retrieval_complete` only means the requested API records were fetched; `all_selected_products_have_recent_store_prices` additionally requires one selected ID per item and a recent price at every chosen chain. Neither confirms a branch's checkout price. `lowest_recent` is calculated **within a single product ID**, not across different sizes or varieties. `--max-age-days` sets a review threshold (default 14 days); it does not establish whether a special is still valid. `--max-products` and `--max-details` control request volume. Run `--help` for details.

The API has no bulk shopping-list endpoint, store-branch selector or complete inventory feed. This comparison covers tracked products at six chains, not every item or every Québec grocer. For a chain outside the API, the agent can inspect accessible official product pages or a flyer supplied by the user and label that evidence separately. Flyer-only evidence covers advertised offers, not all regular prices. The agent should not claim a complete basket where a requested price is missing.

## Use the client directly

```bash
git clone https://github.com/plcharbonneau/epiceries-ca-skill.git
cd epiceries-ca-skill

python3 scripts/epiceries.py info
python3 scripts/epiceries.py categories
python3 scripts/epiceries.py search --query 'lait' --limit 5
python3 scripts/epiceries.py search --query 'beurre' --discounted --limit 10
python3 scripts/epiceries.py --help
```

The seven low-level commands are `info`, `categories`, `search`, `product`, `history`, `barcode` and `storeproduct`. Product IDs and retailer codes should come from actual responses. See the [API reference](references/api.md) for parameters, pagination and identifier handling.

Responses are JSON. The client keeps the provider's fields intact and adds `_client` metadata for the request URL, fetch time and cache status. It caches successful responses for five minutes, spaces serial network requests by one second and uses bounded retries. Use `--fresh` before a command to bypass the local cache; this does not refresh the provider's underlying observations.

## What the data can establish

- Prices are observations from retailer websites, not guaranteed prices or stock at a particular branch.
- A recorded discount is not proof of a flyer offer, expiry date, loyalty condition or purchase limit.
- Package sizes may be missing and unit prices can be inconsistent. Comparable quantities need checking before ranking offers.
- Missing retailer records are unknown prices, not zero-price items. An incomplete basket must be reported as incomplete.
- Fetch time is separate from the date a retailer price was observed. Prices within one comparison can have different ages.

Attribute results to [épiceries.ca](https://www.epiceries.ca/) and retain product links and observation dates. Use its API reasonably and consult its [developer documentation](https://www.epiceries.ca/developers) for current conditions.

## Tests

```bash
python3 scripts/test_epiceries.py
python3 scripts/test_compare_list.py
```

The offline tests cover parameter validation, query encoding, leading-zero barcodes, cache behavior, structured errors and retry limits, plus shopping-list coverage, stale prices and incomplete results. GitHub Actions runs them on Python 3.9 and 3.14 without contacting the grocery API.

All seven commands were also exercised successfully against the public API on **2026-09-22**. This is dated integration evidence, not an ongoing guarantee of API availability or price accuracy. See [verification notes](references/api.md#live-verification-notes).

## License

The skill instructions, helper code and repository documentation are available under the [MIT License](LICENSE). The license does not grant rights to third-party API data, retailer content, trademarks or product images; their respective terms still apply.
