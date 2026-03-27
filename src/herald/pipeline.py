from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

from .archive import load_archive, merge_articles, save_archive
from .models import AppConfig, BuildStats
from .render import render_site
from .scrape import KAISTScraper
from .classify import classify_articles
from .translate import translate_selected_titles
from .utils import parse_date


def build_site(config: AppConfig) -> BuildStats:
    stats = BuildStats()
    archive_path = Path(config.archive_path)
    cache_path = Path(config.cache_path)
    snapshot = load_archive(archive_path)
    cutoff = resolve_cutoff(config, snapshot)

    scraper = KAISTScraper()
    try:
        scraped_articles = scraper.scrape(
            source_keys=config.source_keys,
            page_limit=config.page_limit,
            cutoff_date=cutoff,
            delay_seconds=config.request_delay_seconds,
        )
    finally:
        scraper.close()

    api_key = os.getenv("OPENROUTER_API_KEY")
    classified_articles = classify_articles(
        scraped_articles,
        mode=config.classifier_mode,
        model=config.classification_model,
        cache_path=cache_path,
        api_key=api_key,
    )
    selected_articles = [article for article in classified_articles if article.is_research]
    translated_titles = translate_selected_titles(
        selected_articles,
        model=config.translation_model,
        cache_path=cache_path,
        api_key=api_key,
        batch_size=config.translation_batch_size,
    )

    merged_articles = merge_articles(snapshot.articles, selected_articles)
    saved = save_archive(archive_path, merged_articles)
    render_site(saved.articles, config)

    stats.scraped = len(scraped_articles)
    stats.selected = len(selected_articles)
    stats.translated_titles = translated_titles
    stats.archive_articles = len(saved.articles)
    stats.archive_days = len({article.date for article in saved.articles})
    return stats


def resolve_cutoff(config: AppConfig, snapshot) -> date:
    if config.start_date:
        parsed = parse_date(config.start_date)
        if parsed is None:
            raise ValueError(f"Invalid start_date in config: {config.start_date!r}")
        return parsed

    default_cutoff = date.today() - timedelta(days=config.cutoff_days)
    latest_archived = latest_archive_date(snapshot.articles)
    if latest_archived is None:
        return default_cutoff

    overlap_cutoff = latest_archived - timedelta(days=config.catchup_overlap_days)
    return max(default_cutoff, overlap_cutoff)


def latest_archive_date(articles) -> date | None:
    parsed_dates = [parsed for parsed in (parse_date(article.date) for article in articles) if parsed]
    if not parsed_dates:
        return None
    return max(parsed_dates)
