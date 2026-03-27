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
        sections.append(
            "<section class=\"day\">"
            "<div class=\"day-header\">"
            f"<div><p class=\"day-label\">Research Day</p><h2>{html.escape(article_date)}</h2></div>"
            f"<p class=\"day-count\">{len(day_articles)} item{'s' if len(day_articles) != 1 else ''}</p>"
            "</div>"
            f"<ul class=\"stories\">{items}</ul>"
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
    <link rel="stylesheet" href="{stylesheet_href}">
  </head>
  <body>
    <main class="page">
      <header class="hero">
        <p class="eyebrow">Private Tailnet Digest</p>
        <h1>KAIST Research Digest</h1>
        <p class="lede">A quiet, private archive of KAIST research coverage. Newest days stay on top, older items remain browseable, and Korean headlines can be translated into English during the nightly build.</p>
        <dl class="hero-stats">
          <div>
            <dt>Articles</dt>
            <dd>{article_count}</dd>
          </div>
          <div>
            <dt>Days</dt>
            <dd>{day_count}</dd>
          </div>
          <div>
            <dt>Latest</dt>
            <dd>{html.escape(latest_date)}</dd>
          </div>
        </dl>
        <p class="meta">Last rebuilt {html.escape(updated_at)}</p>
      </header>
      {body}
    </main>
  </body>
</html>
"""


def build_article_html(article: Article, include_original_title: bool) -> str:
    original = ""
    if include_original_title and article.title_original:
        original = f"<p class=\"original\">Original: {html.escape(article.title_original)}</p>"

    source = html.escape(SOURCE_LABELS.get(article.source, article.source.replace("_", " ")))
    lang = "EN" if article.lang == "en" else "KR"
    title = html.escape(article.title)
    url = html.escape(article.url, quote=True)
    body_text = article.summary or article.preview
    preview = ""
    if body_text:
        preview = f"<p class=\"preview\">{html.escape(compact_preview(body_text, limit=360))}</p>"

    return (
        "<li class=\"story\">"
        "<article class=\"story-card\">"
        "<div class=\"story-topline\">"
        f"<span class=\"badge source\">{source}</span>"
        f"<span class=\"badge lang\">{lang}</span>"
        "</div>"
        f"<a class=\"title\" href=\"{url}\">{title}</a>"
        f"{original}"
        f"{preview}"
        f"<p class=\"details\"><a class=\"story-link\" href=\"{url}\">Open original article</a></p>"
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
:root {
  --bg: #f2ede3;
  --surface: rgba(255, 252, 246, 0.96);
  --surface-strong: #fffaf2;
  --ink: #1c1712;
  --muted: #6c6256;
  --accent: #145f59;
  --accent-soft: rgba(20, 95, 89, 0.1);
  --border: rgba(28, 23, 18, 0.12);
  --shadow: 0 18px 48px rgba(43, 32, 21, 0.08);
  --shadow-soft: 0 10px 24px rgba(43, 32, 21, 0.05);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(20, 95, 89, 0.12), transparent 28%),
    radial-gradient(circle at right 20%, rgba(168, 126, 45, 0.08), transparent 24%),
    linear-gradient(180deg, #faf6ee 0%, var(--bg) 100%);
}

.page {
  width: min(980px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 48px 0 72px;
}

.hero,
.day {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 24px;
  box-shadow: var(--shadow);
}

.hero {
  padding: 34px 32px 28px;
  margin-bottom: 24px;
}

.eyebrow,
.meta,
.original,
.lede {
  margin: 0;
}

.eyebrow {
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.76rem;
  margin-bottom: 10px;
}

h1,
h2 {
  margin: 0;
  font-weight: 600;
}

h1 {
  font-size: clamp(2.2rem, 5vw, 3.7rem);
  line-height: 0.98;
  letter-spacing: -0.03em;
  margin-bottom: 16px;
}

.lede {
  color: var(--muted);
  max-width: 65ch;
  font-size: 1.02rem;
  line-height: 1.55;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 22px 0 0;
}

.hero-stats div {
  background: var(--surface-strong);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 14px 16px;
  box-shadow: var(--shadow-soft);
}

.hero-stats dt {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.hero-stats dd {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
}

.meta {
  margin-top: 18px;
  color: var(--muted);
  font-size: 0.92rem;
}

.day {
  padding: 22px 24px 24px;
  margin-bottom: 18px;
}

.day-header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.day-label {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.day h2 {
  font-size: 1.45rem;
  line-height: 1.05;
}

.day-count {
  margin: 0;
  color: var(--muted);
  font-size: 0.92rem;
}

.stories {
  list-style: none;
  margin: 0;
  padding: 0;
}

.story + .story {
  border-top: 1px solid var(--border);
  margin-top: 16px;
  padding-top: 16px;
}

.story-card {
  background: var(--surface-strong);
  border: 1px solid rgba(28, 23, 18, 0.08);
  border-radius: 18px;
  padding: 16px 16px 14px;
  box-shadow: var(--shadow-soft);
}

.story-topline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 0.78rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.badge.source {
  background: var(--accent-soft);
  color: var(--accent);
}

.badge.lang {
  background: rgba(28, 23, 18, 0.06);
  color: var(--muted);
}

.title {
  color: var(--ink);
  text-decoration: none;
  font-size: 1.14rem;
  line-height: 1.35;
  font-weight: 600;
}

.title:hover {
  color: var(--accent);
}

.original {
  margin-top: 8px;
  color: var(--muted);
  font-size: 0.93rem;
  line-height: 1.45;
}

.preview {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 0.96rem;
  line-height: 1.55;
}

.details {
  margin: 12px 0 0;
}

.story-link {
  color: var(--accent);
  text-decoration: none;
  font-size: 0.92rem;
}

.story-link:hover {
  text-decoration: underline;
}

.empty {
  padding: 32px 12px;
  color: var(--muted);
  font-size: 0.98rem;
}

@media (max-width: 640px) {
  .page {
    width: min(100vw - 20px, 920px);
    padding-top: 22px;
  }

  .hero,
  .day {
    border-radius: 18px;
  }

  .hero {
    padding: 22px 18px;
  }

  .day {
    padding: 18px;
  }

  .hero-stats {
    grid-template-columns: 1fr;
  }

  .day-header {
    align-items: start;
    flex-direction: column;
  }

  .story-card {
    padding: 14px;
  }
}
""".strip() + "\n"
