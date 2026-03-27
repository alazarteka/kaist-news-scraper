# Herald

`herald` builds a private KAIST research digest as a static site.

Each run:

1. scrapes KAIST research and news feeds
2. classifies research items with rules and optional OpenRouter fallback
3. translates selected Korean titles into English
4. generates short English summaries from article bodies
5. merges new items into a persistent archive
6. renders a single static HTML page and JSON feed

The output is intentionally simple: minimal CSS, no client-side JavaScript, newest days first. It is designed to sit behind your Tailscale-accessible host and rebuild unattended every night.

## Catch-Up Behavior

The build is archive-aware. If the machine is off for a few days, the next run uses the latest archived date plus an overlap window to backfill missed items before rebuilding the site.

For longer outages, raise `cutoff_days` and `page_limit` in your config.

If you want to rebuild from a fixed historical point, set `start_date` in the config. When set, it overrides the rolling cutoff logic.

## Repository Layout

```text
src/herald/     application package
tests/          unit tests
docs/           architecture, deployment, release notes
deploy/         production examples for config, cron, and systemd
prototype/      preserved untracked snapshot of the original prototype
```

See `docs/architecture.md`, `docs/deployment.md`, and `docs/release.md`.

## Install

For local development:

```bash
uv sync
uv pip install -e .
```

From GitHub:

```bash
pip install git+https://github.com/alazarteka/kaist-news-scraper.git
```

From a built wheel:

```bash
pip install herald-0.3.0-py3-none-any.whl
```

## Quick Start

Create a config:

```bash
herald init-config --output herald.toml
```

Or start from the repo example:

```bash
cp herald.toml.example herald.toml
```

Run a build:

```bash
herald build --config herald.toml
```

For local repo development:

```bash
uv run python -m herald.cli build --config herald.toml
```

If `OPENROUTER_API_KEY` is present, Herald will use it for ambiguous classification and Korean title translation. Without it, the pipeline still runs in rules-only mode.

## Runtime Outputs

By default the application writes:

- `var/archive.json`
- `var/openrouter-cache.json`
- `site/index.html`
- `site/feed.json`
- `site/assets/styles.css`

These are runtime artifacts and should stay out of git.

If Herald is mounted under a path prefix such as `/herald`, set `site_base_path` in the config so browsers resolve assets correctly.

When `OPENROUTER_API_KEY` is available, Herald prefers AI-generated article summaries over the short list-page teaser text.

## Operations

Production-oriented examples live in `deploy/`:

- `deploy/herald.toml.production.example`
- `deploy/systemd/herald.service`
- `deploy/systemd/herald.timer`
- `deploy/cron/herald.cron`

The recommended flow is:

1. install Herald into its own virtual environment
2. place config under `/etc/herald/herald.toml`
3. store `OPENROUTER_API_KEY` in an environment file if needed
4. run `herald build` from a nightly timer or cron job
5. serve the rendered `site/` directory privately over Tailscale

## Tests

```bash
uv run python -m unittest discover -s tests -v
```
