from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_CLASSIFICATION_MODEL = "qwen/qwen-2.5-7b-instruct"
DEFAULT_TRANSLATION_MODEL = "openai/gpt-4.1-mini"
DEFAULT_CACHE_PATH = Path(".cache/herald-openrouter-cache.json")
DEFAULT_TIMEOUT = 20.0
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(frozen=True, slots=True)
class SourceConfig:
    key: str
    label: str
    base_url: str
    lang: str
    research_host: bool = False


@dataclass(slots=True)
class Article:
    id: str
    title: str
    date: str
    url: str
    lang: str
    source: str
    preview: str
    is_research: bool | None = None
    classifier: str | None = None
    confidence: float | None = None
    reason: str | None = None
    title_original: str | None = None
    title_translated: bool = False

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ClassificationDecision:
    is_research: bool
    classifier: str
    confidence: float
    reason: str


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

NEGATIVE_SIGNALS = {
    "kr": [
        "입학식",
        "학위수여식",
        "명예박사",
        "mou",
        "협약",
        "협력",
        "기부",
        "장학",
        "총장",
        "선임",
        "취임",
        "행사",
        "워크숍",
        "포럼",
        "교류",
        "개최",
        "수여",
        "졸업식",
        "축사",
        "채용",
        "기념식",
        "박물관",
        "영구 소장",
        "워크숍",
        "펠로우",
    ],
    "en": [
        "commencement",
        "matriculation",
        "honorary doctorate",
        "signs mou",
        "mou",
        "partnership",
        "donation",
        "appointed",
        "appointment",
        "general chair",
        "workshop",
        "ceremony",
        "forum",
        "exchange",
        "knowledge exchange",
        "awarded honorary",
        "fundraising",
        "president",
        "museum",
        "permanent collection",
        "fellow",
        "thesis",
    ],
}

POSITIVE_SIGNALS = {
    "kr": [
        "연구팀",
        "연구 결과",
        "학술지",
        "게재",
        "doi",
        "논문명",
        "제1저자",
        "교신저자",
        "국제학술지",
    ],
    "en": [
        "research team",
        "paper title",
        "published",
        "study",
        "journal",
        "doi",
        "corresponding author",
        "first author",
    ],
}


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def contains_korean(value: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", value))


def parse_date(value: str) -> date | None:
    cleaned = value.strip().replace(".", "-").replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d."):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def article_id_from_url(url: str, lang: str) -> str:
    match = re.search(r"mng_no=(\d+)", url)
    if not match:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        return f"{lang}_{digest}"
    return f"{lang}_{match.group(1)}"


def article_priority(article: Article) -> tuple[int, int]:
    source_rank = 1 if SOURCES[article.source].research_host else 0
    preview_rank = len(article.preview)
    return (source_rank, preview_rank)


class JsonCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, dict[str, Any]] | None = None

    def _load(self) -> None:
        if self._data is not None:
            return
        if not self.path.exists():
            self._data = {}
            return
        self._data = json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, key: str) -> dict[str, Any] | None:
        self._load()
        assert self._data is not None
        return self._data.get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._load()
        assert self._data is not None
        self._data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


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

        ordered = sorted(
            deduped.values(),
            key=lambda item: (parse_date(item.date) or date.min, item.id),
            reverse=True,
        )
        return ordered


class RuleBasedClassifier:
    def classify(self, article: Article) -> ClassificationDecision | None:
        if SOURCES[article.source].research_host:
            return ClassificationDecision(
                is_research=True,
                classifier="rules",
                confidence=1.0,
                reason="researchnews host",
            )

        text = normalize_text(f"{article.title} {article.preview}").lower()
        language = "kr" if article.lang == "kr" else "en"
        positives = [token for token in POSITIVE_SIGNALS[language] if token in text]
        negatives = [token for token in NEGATIVE_SIGNALS[language] if token in text]

        if negatives:
            return ClassificationDecision(
                is_research=False,
                classifier="rules",
                confidence=0.98,
                reason=f"administrative/news signal: {negatives[0]}",
            )

        strong_research = [
            "연구팀",
            "연구 결과",
            "학술지",
            "게재",
            "doi",
            "논문명",
            "research team",
            "published",
            "study",
            "paper title",
            "journal",
        ]
        if any(token in text for token in strong_research):
            return ClassificationDecision(
                is_research=True,
                classifier="rules",
                confidence=0.96,
                reason="strong research wording",
            )

        if len(positives) >= 2:
            return ClassificationDecision(
                is_research=True,
                classifier="rules",
                confidence=0.88,
                reason=f"multiple research signals: {', '.join(positives[:2])}",
            )

        return None


class OpenRouterClassifier:
    def __init__(
        self,
        api_key: str,
        model: str,
        cache: JsonCache,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.cache = cache
        self.client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/openai/codex",
                "X-Title": "herald",
            },
        )

    def close(self) -> None:
        self.client.close()

    def cache_key(self, article: Article) -> str:
        digest = hashlib.sha256(
            f"{article.id}\n{article.title}\n{article.preview}\n{self.model}".encode("utf-8")
        ).hexdigest()
        return digest

    def classify(self, article: Article) -> ClassificationDecision:
        key = self.cache_key(article)
        cached = self.cache.get(key)
        if cached is not None:
            return ClassificationDecision(**cached)

        messages = [
            {
                "role": "system",
                "content": (
                    "Classify whether a KAIST news article is primarily about a specific "
                    "scientific or engineering research result. "
                    "Return true for research discoveries, experiments, methods, papers, "
                    "or research-team results. Return false for ceremonies, appointments, "
                    "donations, MOUs, admin announcements, student life, or general "
                    "institutional news. Reply with JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "source": article.source,
                        "language": article.lang,
                        "title": article.title,
                        "preview": article.preview,
                        "url": article.url,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 180,
            "messages": messages,
        }
        formats = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "research_decision",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "is_research": {"type": "boolean"},
                            "confidence": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["is_research", "confidence", "reason"],
                        "additionalProperties": False,
                    },
                },
            },
            {"type": "json_object"},
        ]

        last_error: Exception | None = None
        for response_format in formats:
            attempt_payload = dict(payload)
            attempt_payload["response_format"] = response_format
            try:
                response = self.client.post(OPENROUTER_URL, json=attempt_payload)
                response.raise_for_status()
                decision = self._parse_response(response.json())
                break
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                last_error = exc
        else:
            raise RuntimeError(f"OpenRouter classification failed: {last_error}")

        self.cache.set(key, asdict(decision))
        return decision

    def translate_title(self, article: Article) -> str:
        key = self.translation_cache_key(article)
        cached = self.cache.get(key)
        if cached is not None:
            return str(cached["title_en"])

        messages = [
            {
                "role": "system",
                "content": (
                    "Translate the given Korean news title into natural, concise English. "
                    "Keep proper nouns accurate. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title_ko": article.title,
                        "source": article.source,
                        "url": article.url,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 120,
            "messages": messages,
        }
        formats = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "title_translation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title_en": {"type": "string"},
                        },
                        "required": ["title_en"],
                        "additionalProperties": False,
                    },
                },
            },
            {"type": "json_object"},
        ]

        last_error: Exception | None = None
        for response_format in formats:
            attempt_payload = dict(payload)
            attempt_payload["response_format"] = response_format
            try:
                response = self.client.post(OPENROUTER_URL, json=attempt_payload)
                response.raise_for_status()
                translated = self._parse_translation_response(response.json())
                break
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                last_error = exc
        else:
            raise RuntimeError(f"OpenRouter title translation failed: {last_error}")

        self.cache.set(key, {"title_en": translated})
        return translated

    def translate_titles(
        self,
        articles: list[Article],
        batch_size: int = 16,
    ) -> int:
        translated_count = 0
        pending: list[Article] = []

        for article in articles:
            key = self.translation_cache_key(article)
            cached = self.cache.get(key)
            if cached is not None:
                translated_title = str(cached["title_en"])
                translated_count += apply_title_translation(article, translated_title)
                continue
            pending.append(article)

        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            try:
                translations = self._translate_batch(chunk)
            except RuntimeError:
                for article in chunk:
                    translated_count += apply_title_translation(
                        article, self.translate_title(article)
                    )
                continue

            for article in chunk:
                translated_title = translations.get(article.id)
                if not translated_title:
                    translated_count += apply_title_translation(
                        article, self.translate_title(article)
                    )
                    continue
                self.cache.set(
                    self.translation_cache_key(article),
                    {"title_en": translated_title},
                )
                translated_count += apply_title_translation(article, translated_title)

        return translated_count

    def translation_cache_key(self, article: Article) -> str:
        digest = hashlib.sha256(
            f"translate\n{article.id}\n{article.title}\n{self.model}".encode("utf-8")
        ).hexdigest()
        return digest

    def _parse_response(self, data: dict[str, Any]) -> ClassificationDecision:
        message = data["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(
                item.get("text", "") for item in message if isinstance(item, dict)
            )
        parsed = parse_model_json(message)
        normalized = normalize_decision_payload(parsed)
        return ClassificationDecision(
            is_research=normalized["is_research"],
            classifier=f"openrouter:{self.model}",
            confidence=normalized["confidence"],
            reason=normalized["reason"],
        )

    def _parse_translation_response(self, data: dict[str, Any]) -> str:
        message = data["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(
                item.get("text", "") for item in message if isinstance(item, dict)
            )
        parsed = parse_model_json(message)
        return normalize_translation_payload(parsed)

    def _translate_batch(self, articles: list[Article]) -> dict[str, str]:
        messages = [
            {
                "role": "system",
                "content": (
                    "Translate each Korean news title into natural, concise English. "
                    "Return JSON only. Preserve ids exactly."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "items": [
                            {
                                "id": article.id,
                                "title_ko": article.title,
                                "source": article.source,
                            }
                            for article in articles
                        ]
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max(200, 40 * len(articles)),
            "messages": messages,
        }
        formats = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "title_translations",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "translations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "title_en": {"type": "string"},
                                    },
                                    "required": ["id", "title_en"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["translations"],
                        "additionalProperties": False,
                    },
                },
            },
            {"type": "json_object"},
        ]

        last_error: Exception | None = None
        for response_format in formats:
            attempt_payload = dict(payload)
            attempt_payload["response_format"] = response_format
            try:
                response = self.client.post(OPENROUTER_URL, json=attempt_payload)
                response.raise_for_status()
                return self._parse_batch_translation_response(response.json())
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                last_error = exc
        raise RuntimeError(f"OpenRouter batch title translation failed: {last_error}")

    def _parse_batch_translation_response(self, data: dict[str, Any]) -> dict[str, str]:
        message = data["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(
                item.get("text", "") for item in message if isinstance(item, dict)
            )
        parsed = parse_model_json(message)
        return normalize_translation_batch_payload(parsed)


def extract_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Model response was not valid JSON: {text!r}")
    return match.group(0)


def parse_model_json(text: str) -> Any:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return json.loads(extract_json_object(stripped))


def normalize_translation_payload(payload: Any) -> str:
    if isinstance(payload, str):
        return normalize_text(payload.strip().strip('"'))

    if isinstance(payload, list):
        if len(payload) != 1:
            raise ValueError(f"Unexpected translation payload list: {payload!r}")
        return normalize_translation_payload(payload[0])

    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected translation payload type: {payload!r}")

    for key in ("title_en", "translation", "translated_title", "english_title", "title"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_text(value.strip())

    raise ValueError(f"Missing translated title in payload: {payload!r}")


def normalize_translation_batch_payload(payload: Any) -> dict[str, str]:
    if isinstance(payload, dict):
        if "translations" in payload and isinstance(payload["translations"], list):
            payload = payload["translations"]
        elif all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
            return {key: normalize_text(value) for key, value in payload.items()}

    if not isinstance(payload, list):
        raise ValueError(f"Unexpected translation batch payload: {payload!r}")

    translated: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"Unexpected translation batch item: {item!r}")
        item_id = item.get("id")
        title_en = first_present(
            item,
            ["title_en", "translation", "translated_title", "english_title", "title"],
        )
        if not isinstance(item_id, str) or not isinstance(title_en, str):
            raise ValueError(f"Invalid translation batch item: {item!r}")
        translated[item_id] = normalize_text(title_en)
    return translated


def normalize_decision_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, bool):
        return {
            "is_research": payload,
            "confidence": 0.5,
            "reason": "Model returned a bare boolean response.",
        }

    if isinstance(payload, str):
        return {
            "is_research": coerce_bool(payload),
            "confidence": 0.5,
            "reason": "Model returned a bare string label.",
        }

    if isinstance(payload, list):
        if len(payload) != 1:
            raise ValueError(f"Unexpected list payload from model: {payload!r}")
        payload = payload[0]

    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected payload type from model: {payload!r}")

    candidate = payload
    if "is_research" not in candidate:
        for key in ("classification", "decision", "result", "output", "data"):
            nested = candidate.get(key)
            if isinstance(nested, dict):
                candidate = nested
                break

    research_value = first_present(
        candidate,
        ["is_research", "isResearch", "research", "label", "classification"],
    )
    confidence_value = first_present(
        candidate,
        ["confidence", "confidence_score", "score", "probability"],
    )
    reason_value = first_present(
        candidate,
        ["reason", "explanation", "rationale"],
    )

    if research_value is None:
        raise ValueError(f"Missing research label in model payload: {payload!r}")

    return {
        "is_research": coerce_bool(research_value),
        "confidence": coerce_confidence(confidence_value),
        "reason": str(reason_value or "No reason provided.").strip(),
    }


def first_present(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "research", "research_article"}:
            return True
        if normalized in {"false", "no", "not_research", "non_research", "general_news"}:
            return False
    raise ValueError(f"Could not coerce research label: {value!r}")


def coerce_confidence(value: Any) -> float:
    if value is None:
        return 0.5
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        if stripped:
            number = float(stripped)
            if value.strip().endswith("%"):
                return number / 100.0
            return number
    raise ValueError(f"Could not coerce confidence: {value!r}")


def apply_decision(article: Article, decision: ClassificationDecision) -> None:
    article.is_research = decision.is_research
    article.classifier = decision.classifier
    article.confidence = decision.confidence
    article.reason = decision.reason


def apply_title_translation(article: Article, translated_title: str) -> int:
    translated_title = normalize_text(translated_title)
    if not translated_title or translated_title == article.title:
        return 0
    if article.title_original is None:
        article.title_original = article.title
    article.title = translated_title
    article.title_translated = True
    return 1


def classify_articles(
    articles: list[Article],
    mode: str,
    model: str,
    cache_path: Path,
    api_key: str | None,
) -> list[Article]:
    rule_classifier = RuleBasedClassifier()
    llm_classifier: OpenRouterClassifier | None = None

    if mode in {"auto", "openrouter"} and api_key:
        llm_classifier = OpenRouterClassifier(
            api_key=api_key,
            model=model,
            cache=JsonCache(cache_path),
        )
    elif mode == "openrouter" and not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for --classifier openrouter")

    try:
        for article in articles:
            rule_decision = rule_classifier.classify(article)
            if mode == "rules":
                apply_decision(
                    article,
                    rule_decision
                    or ClassificationDecision(
                        is_research=False,
                        classifier="rules",
                        confidence=0.6,
                        reason="default conservative fallback",
                    ),
                )
                continue

            if mode == "none":
                apply_decision(
                    article,
                    ClassificationDecision(
                        is_research=SOURCES[article.source].research_host,
                        classifier="none",
                        confidence=1.0 if SOURCES[article.source].research_host else 0.0,
                        reason="host-only classification",
                    ),
                )
                continue

            if rule_decision is not None:
                apply_decision(article, rule_decision)
                continue

            if llm_classifier is not None:
                apply_decision(article, llm_classifier.classify(article))
                continue

            apply_decision(
                article,
                ClassificationDecision(
                    is_research=False,
                    classifier="rules",
                    confidence=0.6,
                    reason="no OpenRouter key; conservative fallback",
                ),
            )
        return articles
    finally:
        if llm_classifier is not None:
            llm_classifier.close()


def translate_selected_titles(
    articles: list[Article],
    model: str,
    cache_path: Path,
    api_key: str | None,
    batch_size: int,
) -> int:
    if not api_key:
        return 0

    translator = OpenRouterClassifier(
        api_key=api_key,
        model=model,
        cache=JsonCache(cache_path),
    )
    try:
        korean_articles = [article for article in articles if contains_korean(article.title)]
        return translator.translate_titles(korean_articles, batch_size=batch_size)
    finally:
        translator.close()


def save_json(articles: list[Article], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([article.to_record() for article in articles], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_csv(articles: list[Article], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not articles:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(articles[0].to_record().keys()))
        writer.writeheader()
        writer.writerows(article.to_record() for article in articles)


def save_markdown(articles: list[Article], path: Path, cutoff_date: date | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    title_suffix = f" (since {cutoff_date.isoformat()})" if cutoff_date else ""
    lines = [f"### KAIST Research Digest{title_suffix}", ""]
    grouped: dict[str, list[Article]] = {}
    for article in articles:
        grouped.setdefault(article.date, []).append(article)

    for article_date in sorted(grouped.keys(), reverse=True):
        lines.append(f"* **{article_date}**")
        for article in grouped[article_date]:
            tag = article.lang.upper()
            lines.append(f"  * [{tag}] [{article.title}]({article.url})")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def default_cutoff(days: int = 30) -> date:
    return date.today() - timedelta(days=days)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape KAIST news feeds and classify research articles."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=list(SOURCES.keys()),
        default=["kr_research", "kr_news", "en_news"],
        help="Feed sources to scrape.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Maximum pages to scrape per source.",
    )
    parser.add_argument(
        "--cutoff-date",
        type=str,
        default=None,
        help="Only keep articles on or after YYYY-MM-DD. Defaults to 30 days ago.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between page fetches from the same source.",
    )
    parser.add_argument(
        "--classifier",
        choices=["auto", "rules", "openrouter", "none"],
        default="auto",
        help="Classification strategy for main news feeds.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Legacy shared OpenRouter model override for both classification and translation.",
    )
    parser.add_argument(
        "--classification-model",
        default=None,
        help=f"OpenRouter model for article classification. Default: {DEFAULT_CLASSIFICATION_MODEL}",
    )
    parser.add_argument(
        "--translation-model",
        default=None,
        help=f"OpenRouter model for title translation. Default: {DEFAULT_TRANSLATION_MODEL}",
    )
    parser.add_argument(
        "--translation-batch-size",
        type=int,
        default=16,
        help="Number of Korean titles to translate per OpenRouter request.",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="Path to the OpenRouter classification cache.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("kaist_research_digest.json"),
        help="Write full results to this JSON file.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional CSV export path.",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=None,
        help="Optional Markdown digest path.",
    )
    parser.add_argument(
        "--research-only",
        action="store_true",
        help="Keep only items classified as research.",
    )
    return parser.parse_args(argv)


def resolve_cutoff(raw_value: str | None) -> date | None:
    if raw_value is None:
        return default_cutoff()
    parsed = parse_date(raw_value)
    if parsed is None:
        raise ValueError(f"Invalid cutoff date: {raw_value}")
    return parsed


def print_summary(all_articles: list[Article], selected_articles: list[Article]) -> None:
    classified = sum(1 for article in all_articles if article.is_research)
    print(
        f"Scraped {len(all_articles)} articles, classified {classified} as research, "
        f"wrote {len(selected_articles)} articles."
    )
    by_classifier: dict[str, int] = {}
    for article in all_articles:
        key = article.classifier or "unknown"
        by_classifier[key] = by_classifier.get(key, 0) + 1
    for classifier, count in sorted(by_classifier.items()):
        print(f"  {classifier}: {count}")

    translated = sum(1 for article in selected_articles if article.title_translated)
    if translated:
        print(f"  translated titles: {translated}")


def run_pipeline(args: argparse.Namespace) -> int:
    api_key = os.getenv("OPENROUTER_API_KEY")
    classification_model = (
        args.classification_model or args.model or DEFAULT_CLASSIFICATION_MODEL
    )
    translation_model = args.translation_model or args.model or DEFAULT_TRANSLATION_MODEL
    cutoff = resolve_cutoff(args.cutoff_date)
    scraper = KAISTScraper()
    try:
        articles = scraper.scrape(
            source_keys=args.sources,
            page_limit=args.pages,
            cutoff_date=cutoff,
            delay_seconds=args.delay,
        )
    finally:
        scraper.close()

    articles = classify_articles(
        articles=articles,
        mode=args.classifier,
        model=classification_model,
        cache_path=args.cache_path,
        api_key=api_key,
    )

    selected = [article for article in articles if article.is_research] if args.research_only else articles
    if args.classifier in {"auto", "openrouter"}:
        translate_selected_titles(
            articles=selected,
            model=translation_model,
            cache_path=args.cache_path,
            api_key=api_key,
            batch_size=args.translation_batch_size,
        )
    save_json(selected, args.output_json)
    if args.output_csv:
        save_csv(selected, args.output_csv)
    if args.output_markdown:
        save_markdown(selected, args.output_markdown, cutoff)

    print_summary(articles, selected)
    print(f"JSON: {args.output_json}")
    if args.output_csv:
        print(f"CSV: {args.output_csv}")
    if args.output_markdown:
        print(f"Markdown: {args.output_markdown}")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        return run_pipeline(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
