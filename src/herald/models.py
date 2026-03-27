from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Article:
    id: str
    title: str
    date: str
    url: str
    lang: str
    source: str
    preview: str
    summary: str | None = None
    is_research: bool | None = None
    classifier: str | None = None
    confidence: float | None = None
    reason: str | None = None
    title_original: str | None = None
    title_translated: bool = False

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BuildStats:
    scraped: int = 0
    selected: int = 0
    translated_titles: int = 0
    archive_days: int = 0
    archive_articles: int = 0


@dataclass(slots=True)
class ClassificationDecision:
    is_research: bool
    classifier: str
    confidence: float
    reason: str


@dataclass(slots=True)
class AppConfig:
    source_keys: list[str]
    page_limit: int
    cutoff_days: int
    catchup_overlap_days: int
    request_delay_seconds: float
    classifier_mode: str
    classification_model: str
    translation_model: str
    summary_model: str
    translation_batch_size: int
    archive_path: str
    cache_path: str
    site_dir: str
    start_date: str | None = None
    site_base_path: str = "/"
    include_original_title: bool = True


@dataclass(slots=True)
class ArchiveSnapshot:
    generated_at: str
    articles: list[Article] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "articles": [article.to_record() for article in self.articles],
        }
