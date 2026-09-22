# Épiceries.ca API skill

[![Tests](https://github.com/plcharbonneau/epiceries-ca-skill/actions/workflows/tests.yml/badge.svg)](https://github.com/plcharbonneau/epiceries-ca-skill/actions/workflows/tests.yml)

An agent skill for researching Québec grocery prices through the public [épiceries.ca developer API](https://www.epiceries.ca/developers). Search products, compare recorded retailer prices, find discounts, resolve barcodes and examine price history.

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
and Super C. Include package sizes, observation dates and source links.
```

```text
Utilise $epiceries-api pour comparer ma liste d'épicerie chez Metro
et Provigo. Signale les produits manquants et les prix anciens.
```

The skill teaches the agent to match product variants and quantities, check observation dates, and distinguish a partial basket from a complete comparison. It also explains a subtle API behavior: the search `store` filter selects products whose **cheapest recorded retailer** is that chain, rather than everything that chain carries.

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

The seven commands are `info`, `categories`, `search`, `product`, `history`, `barcode` and `storeproduct`. Product IDs and retailer codes should come from actual responses. See the [API reference](references/api.md) for parameters, pagination and identifier handling.

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
```

The 11 offline tests cover parameter validation, query encoding, leading-zero barcodes, cache behavior, structured errors and retry limits. GitHub Actions runs them on Python 3.9 and 3.14 without contacting the grocery API.

All seven commands were also exercised successfully against the public API on **2026-09-22**. This is dated integration evidence, not an ongoing guarantee of API availability or price accuracy. See [verification notes](references/api.md#live-verification-notes).

## License

The skill instructions, helper code and repository documentation are available under the [MIT License](LICENSE). The license does not grant rights to third-party API data, retailer content, trademarks or product images; their respective terms still apply.
