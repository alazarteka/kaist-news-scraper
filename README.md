## Herald

`herald` scrapes KAIST's Korean research feed plus the Korean and English KAIST news feeds, then classifies which items are actual research articles.

The pipeline is deterministic first:

- scrape exact list-page selectors: `a.lay`, `strong.tis`, `span.tes`, `span.date`
- trust the dedicated `researchnews.kaist.ac.kr` host
- reject obvious admin/event items with rules
- send only ambiguous main-news items to OpenRouter when `OPENROUTER_API_KEY` is present
- after selection, translate Korean titles to English when OpenRouter is active
- cache OpenRouter decisions locally so repeated runs are cheap

## Requirements

- Python `3.13`
- dependencies installed through `uv`
- optional: `OPENROUTER_API_KEY` for LLM classification

## Install

```bash
uv sync
```

## Main usage

Recent research digest with automatic classification:

```bash
uv run python main.py --research-only --output-json out/research.json --output-markdown out/research.md
```

Use OpenRouter explicitly with the recommended cheap model:

```bash
export OPENROUTER_API_KEY=...
uv run python main.py \
  --classifier openrouter \
  --classification-model qwen/qwen-2.5-7b-instruct \
  --translation-model openai/gpt-4.1-mini \
  --research-only \
  --output-json out/research.json \
  --output-csv out/research.csv \
  --output-markdown out/research.md
```

Conservative rules-only mode with no API calls:

```bash
uv run python main.py --classifier rules --research-only
```

## Useful options

- `--sources kr_research kr_news en_news`: choose which feeds to scrape
- `--pages 5`: maximum pages per source
- `--cutoff-date YYYY-MM-DD`: keep only newer items
- `--classifier auto|rules|openrouter|none`
- `--classification-model ...`: model used only for ambiguous research classification
- `--translation-model ...`: model used only for Korean title translation
- `--translation-batch-size 16`: number of titles per translation request
- `--cache-path .cache/herald-openrouter-cache.json`
- `--research-only`: drop non-research items from the output

If `--cutoff-date` is omitted, the scraper defaults to the last 30 days.

## Legacy helper scripts

These now call the shared pipeline:

- `uv run python scrape_kaist_news.py`
- `uv run python scrape_kaist_research.py`
- `uv run python scrape_kaist_comprehensive.py`

## Tests

```bash
uv run python -m unittest -v
```
