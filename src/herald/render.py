from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .models import AppConfig, Article


SOURCE_LABELS = {
    "kr_research": "KAIST Research News",
    "kr_news": "KAIST News KR",
    "en_news": "KAIST News EN",
}


def render_site(articles: list[Article], config: AppConfig) -> None:
    site_dir = Path(config.site_dir)
    assets_dir = site_dir / "assets"
    site_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    (assets_dir / "styles.css").write_text(STYLES_CSS, encoding="utf-8")
    (site_dir / "feed.json").write_text(
        json.dumps([article.to_record() for article in articles], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (site_dir / "index.html").write_text(
        build_index_html(articles, config),
        encoding="utf-8",
    )


def _format_dateline(raw_date: str) -> str:
    """Turn '2026.03.27' into 'Friday, 27 March 2026'."""
    try:
        parsed = datetime.strptime(raw_date, "%Y.%m.%d")
    except ValueError:
        return raw_date
    return f"{parsed.strftime('%A')}, {parsed.day} {parsed.strftime('%B %Y')}"


def build_index_html(articles: list[Article], config: AppConfig) -> str:
    grouped: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        grouped[article.date].append(article)

    article_count = len(articles)
    day_count = len(grouped)
    latest_date = next(iter(sorted(grouped.keys(), reverse=True)), "No entries yet")
    sections: list[str] = []
    for article_date in sorted(grouped.keys(), reverse=True):
        day_articles = grouped[article_date]
        items = "\n".join(
            build_article_html(article, config.include_original_title)
            for article in day_articles
        )
        dateline = _format_dateline(article_date)
        n = len(day_articles)
        sections.append(
            "<section class=\"day\">"
            f"<header class=\"dateline\"><h2>{html.escape(dateline)}</h2>"
            f"<span class=\"day-n\">{n} piece{'s' if n != 1 else ''}</span></header>"
            f"<ol class=\"stories\">{items}</ol>"
            "</section>"
        )

    updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    body = "\n".join(sections) or "<p class=\"empty\">No research items yet.</p>"
    base_path = html.escape(config.site_base_path, quote=True)
    stylesheet_href = html.escape(f"{config.site_base_path}assets/styles.css", quote=True)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <base href="{base_path}">
    <title>KAIST Research Digest</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..900;1,9..144,300..900&family=Newsreader:ital,opsz,wght@0,6..72,300..700;1,6..72,300..700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{stylesheet_href}">
  </head>
  <body>
    <main class="page">
      <header class="masthead">
        <div class="masthead-rule"></div>
        <p class="flag">Private Tailnet Edition</p>
        <h1>The KAIST<br>Research Digest</h1>
        <p class="folio">{article_count} articles across {day_count} days &middot; Latest {html.escape(latest_date)} &middot; Rebuilt {html.escape(updated_at)}</p>
        <div class="masthead-rule"></div>
      </header>
      {body}
    </main>
  </body>
</html>
"""


def build_article_html(article: Article, include_original_title: bool) -> str:
    original = ""
    if include_original_title and article.title_original:
        original = f"<p class=\"orig\">{html.escape(article.title_original)}</p>"

    source = html.escape(SOURCE_LABELS.get(article.source, article.source.replace("_", " ")))
    lang = "English" if article.lang == "en" else "Korean"
    title = html.escape(article.title)
    url = html.escape(article.url, quote=True)
    preview = ""
    if article.summary:
        preview = f"<p class=\"lede\">{html.escape(' '.join(article.summary.split()))}</p>"
    elif article.preview:
        preview = f"<p class=\"lede\">{html.escape(compact_preview(article.preview, limit=360))}</p>"

    return (
        "<li class=\"item\">"
        "<article>"
        f"<h3><a href=\"{url}\">{title}</a></h3>"
        f"{original}"
        f"{preview}"
        f"<footer class=\"byline\">{source} &middot; {lang}"
        f" &middot; <a href=\"{url}\">Read&nbsp;original&thinsp;&rarr;</a></footer>"
        "</article>"
        "</li>"
    )


def compact_preview(value: str, limit: int = 220) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return trimmed + "..."


STYLES_CSS = """
/* ── Herald — Private Scholarly Broadsheet ── */

:root {
  --ink:       #1a1510;
  --muted:     #756b5e;
  --wine:      #8b2332;
  --gold:      #a67c2e;
  --rule:      rgba(26, 21, 16, 0.22);
  --rule-fine: rgba(26, 21, 16, 0.10);
  --paper:     #f5f0e8;
  --cream:     #faf6ee;
}

*,
*::before,
*::after { box-sizing: border-box; margin: 0; padding: 0; }

html { -webkit-text-size-adjust: 100%; }

body {
  font-family: "Newsreader", "Iowan Old Style", "Palatino Linotype", Georgia, serif;
  font-size: 17px;
  line-height: 1.58;
  color: var(--ink);
  background: var(--paper);
  /* subtle paper grain via SVG noise */
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E");
}

/* ── Page chrome ── */

.page {
  width: min(720px, calc(100vw - 40px));
  margin: 0 auto;
  padding: 56px 0 80px;
}

/* ── Masthead ── */

.masthead {
  text-align: center;
  padding: 0 0 6px;
  margin-bottom: 40px;
}

.masthead-rule {
  height: 0;
  border: none;
  border-top: 2px solid var(--ink);
  margin: 0;
}

/* thin double-rule effect */
.masthead-rule + .flag { margin-top: 18px; }
.masthead-rule:last-child { border-top-width: 1px; margin-top: 16px; }

.flag {
  font-family: "Newsreader", Georgia, serif;
  font-size: 0.72rem;
  font-style: italic;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--muted);
}

h1 {
  font-family: "Fraunces", "Newsreader", Georgia, serif;
  font-optical-sizing: auto;
  font-weight: 900;
  font-size: clamp(2.6rem, 7vw, 4.4rem);
  line-height: 0.92;
  letter-spacing: -0.025em;
  margin: 12px 0 14px;
}

.folio {
  font-size: 0.82rem;
  color: var(--muted);
  letter-spacing: 0.02em;
}

/* ── Day sections ── */

.day { margin-bottom: 36px; }

.dateline {
  display: flex;
  align-items: baseline;
  gap: 14px;
  border-bottom: 1px solid var(--rule);
  padding-bottom: 8px;
  margin-bottom: 20px;
}

.dateline h2 {
  font-family: "Newsreader", Georgia, serif;
  font-weight: 600;
  font-size: 1.05rem;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--gold);
}

.day-n {
  font-size: 0.78rem;
  color: var(--muted);
  font-style: italic;
}

/* ── Article list ── */

.stories {
  list-style: none;
  counter-reset: piece;
}

.item {
  position: relative;
  padding: 0 0 20px 28px;
  counter-increment: piece;
}

.item::before {
  content: counter(piece);
  position: absolute;
  left: 0;
  top: 2px;
  font-family: "Fraunces", Georgia, serif;
  font-weight: 300;
  font-size: 0.92rem;
  color: var(--muted);
  opacity: 0.6;
}

.item + .item {
  border-top: 1px solid var(--rule-fine);
  padding-top: 18px;
}

/* ── Article content ── */

.item h3 {
  font-family: "Newsreader", Georgia, serif;
  font-weight: 600;
  font-size: 1.18rem;
  line-height: 1.32;
  margin-bottom: 4px;
}

.item h3 a {
  color: var(--ink);
  text-decoration: none;
  background-image: linear-gradient(var(--wine), var(--wine));
  background-size: 0% 1px;
  background-position: 0 100%;
  background-repeat: no-repeat;
  transition: background-size 0.3s ease;
}

.item h3 a:hover {
  background-size: 100% 1px;
  color: var(--wine);
}

.orig {
  font-size: 0.88rem;
  font-style: italic;
  color: var(--muted);
  line-height: 1.45;
  margin-bottom: 6px;
}

.lede {
  font-size: 0.94rem;
  line-height: 1.58;
  color: var(--muted);
  max-width: 60ch;
  margin-top: 4px;
}

.byline {
  margin-top: 8px;
  font-size: 0.78rem;
  color: var(--muted);
  letter-spacing: 0.01em;
}

.byline a {
  color: var(--wine);
  text-decoration: none;
  font-style: italic;
}

.byline a:hover {
  text-decoration: underline;
}

/* ── Empty state ── */

.empty {
  padding: 40px 0;
  text-align: center;
  color: var(--muted);
  font-style: italic;
}

/* ── Responsive ── */

@media (max-width: 600px) {
  .page {
    width: calc(100vw - 28px);
    padding: 28px 0 48px;
  }

  h1 {
    font-size: 2.4rem;
    line-height: 0.94;
  }

  .masthead { margin-bottom: 28px; }

  .dateline h2 { font-size: 0.92rem; }

  .item { padding-left: 22px; padding-bottom: 16px; }
  .item + .item { padding-top: 14px; }
}

/* ── Print ── */

@media print {
  body { background: #fff; font-size: 11pt; }
  .page { width: 100%; padding: 0; }
  .masthead-rule { border-color: #000; }
  .item h3 a { color: #000; background: none; }
  .byline a::after { content: " (" attr(href) ")"; font-size: 0.7em; }
}
""".strip() + "\n"
