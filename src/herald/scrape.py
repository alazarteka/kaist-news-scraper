from __future__ import annotations

import time
from datetime import date
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .models import Article
from .sources import SOURCES, SourceConfig
from .utils import DEFAULT_TIMEOUT, USER_AGENT, article_id_from_url, normalize_text, parse_date


def article_priority(article: Article) -> tuple[int, int]:
    source_rank = 1 if SOURCES[article.source].research_host else 0
    preview_rank = len(article.preview)
    return (source_rank, preview_rank)


class KAISTScraper:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self.client.close()

    def fetch_page(self, source: SourceConfig, page: int) -> str:
        url = f"{source.base_url}?mode=L&GotoPage={page}"
        response = self.client.get(url)
        response.raise_for_status()
        return response.text

    def parse_listing_page(self, html: str, source: SourceConfig) -> list[Article]:
        soup = BeautifulSoup(html, "html.parser")
        articles: list[Article] = []
        for link in soup.select("a.lay[href*='mng_no=']"):
            title_tag = link.select_one("strong.tis")
            date_tag = link.select_one("span.date")
            preview_tag = link.select_one("span.tes")
            href = link.get("href")
            if not title_tag or not date_tag or not href:
                continue

            url = urljoin(source.base_url, href)
            articles.append(
                Article(
                    id=article_id_from_url(url, source.lang),
                    title=normalize_text(title_tag.get_text(" ", strip=True)),
                    date=normalize_text(date_tag.get_text(" ", strip=True)),
                    url=url,
                    lang=source.lang,
                    source=source.key,
                    preview=normalize_text(
                        preview_tag.get_text(" ", strip=True) if preview_tag else ""
                    ),
                )
            )
        return articles

    def scrape_source(
        self,
        source: SourceConfig,
        page_limit: int,
        cutoff_date: date | None,
        delay_seconds: float,
    ) -> list[Article]:
        results: list[Article] = []
        for page in range(1, page_limit + 1):
            html = self.fetch_page(source, page)
            items = self.parse_listing_page(html, source)
            if not items:
                break

            results.extend(
                article
                for article in items
                if cutoff_date is None
                or (parse_date(article.date) is not None and parse_date(article.date) >= cutoff_date)
            )

            if cutoff_date is not None:
                oldest = min(
                    (parsed for parsed in (parse_date(item.date) for item in items) if parsed is not None),
                    default=None,
                )
                if oldest is not None and oldest < cutoff_date:
                    break

            if page != page_limit:
                time.sleep(delay_seconds)
        return results

    def scrape(
        self,
        source_keys: list[str],
        page_limit: int,
        cutoff_date: date | None,
        delay_seconds: float,
    ) -> list[Article]:
        deduped: dict[str, Article] = {}
        for key in source_keys:
            source = SOURCES[key]
            for article in self.scrape_source(source, page_limit, cutoff_date, delay_seconds):
                current = deduped.get(article.id)
                if current is None or article_priority(article) > article_priority(current):
                    deduped[article.id] = article

        return sorted(
            deduped.values(),
            key=lambda item: (parse_date(item.date) or date.min, item.id),
            reverse=True,
        )
