from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import Article, ClassificationDecision
from .openrouter import OpenRouterClient
from .sources import SOURCES
from .utils import JsonCache, normalize_decision_payload, normalize_text, parse_model_json


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

JSON_RESPONSE_FORMATS = [
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


class OpenRouterResearchClassifier:
    def __init__(self, api_key: str, model: str, cache_path: Path) -> None:
        self.model = model
        self.cache = JsonCache(cache_path)
        self.client = OpenRouterClient(api_key=api_key, model=model)

    def close(self) -> None:
        self.client.close()

    def classify(self, article: Article) -> ClassificationDecision:
        key = self._cache_key(article)
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

        decision = self.client.request_with_fallback_formats(
            messages=messages,
            max_tokens=180,
            response_formats=JSON_RESPONSE_FORMATS,
            parser=self._parse_response,
        )
        self.cache.set(key, asdict(decision))
        return decision

    def _cache_key(self, article: Article) -> str:
        return hashlib.sha256(
            f"{article.id}\n{article.title}\n{article.preview}\n{self.model}".encode("utf-8")
        ).hexdigest()

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


def apply_decision(article: Article, decision: ClassificationDecision) -> None:
    article.is_research = decision.is_research
    article.classifier = decision.classifier
    article.confidence = decision.confidence
    article.reason = decision.reason


def classify_articles(
    articles: list[Article],
    *,
    mode: str,
    model: str,
    cache_path: Path,
    api_key: str | None,
) -> list[Article]:
    rule_classifier = RuleBasedClassifier()
    llm_classifier: OpenRouterResearchClassifier | None = None

    if mode in {"auto", "openrouter"} and api_key:
        llm_classifier = OpenRouterResearchClassifier(api_key, model, cache_path)
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
