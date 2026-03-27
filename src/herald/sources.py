from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceConfig:
    key: str
    label: str
    base_url: str
    lang: str
    research_host: bool = False


SOURCES: dict[str, SourceConfig] = {
    "kr_research": SourceConfig(
        key="kr_research",
        label="KAIST Research News (KR)",
        base_url="https://researchnews.kaist.ac.kr/researchnews/html/news/",
        lang="kr",
        research_host=True,
    ),
    "kr_news": SourceConfig(
        key="kr_news",
        label="KAIST News (KR)",
        base_url="https://news.kaist.ac.kr/news/html/news/",
        lang="kr",
    ),
    "en_news": SourceConfig(
        key="en_news",
        label="KAIST News (EN)",
        base_url="https://news.kaist.ac.kr/newsen/html/news/",
        lang="en",
    ),
}
