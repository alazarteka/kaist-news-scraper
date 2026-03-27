# Architecture

## Goal

`herald` is an installable Python application that builds a private KAIST research digest as a static website.

The runtime model is:

1. A nightly job scrapes the KAIST research and news feeds.
2. Articles are classified as research or non-research.
3. Selected Korean titles are translated to English.
4. New articles are merged into a persistent archive.
5. The full archive is rendered into a static HTML site with minimal CSS.

The site is then served privately over the user's existing Tailscale-accessible host.

## Core Design

The digest should be rebuilt from structured state on every run, not edited in place.

That means:

- the archive is the source of truth
- rendering is deterministic
- new releases can change the presentation without damaging history
- duplicate prevention happens at the state layer, not the HTML layer

## Catch-Up Behavior

The build should tolerate missed runs.

Each run calculates its scrape cutoff using:

- a configured lookback window
- the latest archived article date
- a small overlap buffer

That means if the machine is off for a few days, the next successful run will re-fetch recent pages, overlap slightly with the last archived day, and backfill the missed items before rebuilding the site.

The practical limit is still controlled by the configured lookback window and page depth.

## Package Layout

```text
src/herald/
  __init__.py
  cli.py
  config.py
  models.py
  sources.py
  scrape.py
  classify.py
  translate.py
  archive.py
  render.py
  pipeline.py
deploy/
  herald.toml.production.example
  cron/
  systemd/
```

## Responsibilities

### `config.py`

- load a TOML config file
- render an example config file
- define output paths, source selection, OpenRouter models, and runtime defaults

### `models.py`

- typed dataclasses for articles, archive entries, and build results

### `sources.py`

- static KAIST feed definitions

### `scrape.py`

- deterministic list-page scraping only
- extraction of title, preview, date, URL, source

### `classify.py`

- hard-rule classification first
- optional OpenRouter fallback for ambiguous items

### `translate.py`

- translate selected Korean titles into English
- batch requests when possible
- cache by article id and original Korean title

### `archive.py`

- persist structured history as JSON
- merge new items without duplication
- keep newest days first when rendering

### `render.py`

- generate:
  - `site/index.html`
  - `site/feed.json`
  - `site/assets/styles.css`
- use minimal handwritten HTML and CSS

### `pipeline.py`

- orchestrate scrape -> classify -> translate -> archive -> render

### `cli.py`

- expose installable commands:
  - `herald build`
  - `herald init-config`
  - `herald --version`

## State Files

Suggested runtime layout:

```text
var/
  archive.json
  openrouter-cache.json
site/
  index.html
  feed.json
  assets/styles.css
```

These files are runtime artifacts and should not be committed in normal use.

## Release Shape

The repository should be installable from GitHub as a package:

```bash
pip install git+https://github.com/<user>/herald.git
```

or from tagged releases:

```bash
pip install herald
```

The installed CLI should work with a config file and a cron job:

```bash
herald build --config /etc/herald/config.toml
```

Production examples for config and unattended execution live under `deploy/`.

## Static Site Shape

The site should remain intentionally simple:

- top-level page title and last updated timestamp
- newest day first
- each day rendered as a section
- each article shown as:
  - English title
  - optional original Korean title
  - source and date
  - link to KAIST
- minimal CSS only

No client-side JavaScript is required for the first version.

## Current Build Status

The package already supports:

1. installable CLI entry points
2. archive-aware catch-up builds
3. static HTML rendering with minimal CSS
4. production config and unattended-run examples
5. tests around archive merge, cutoff logic, and rendering
