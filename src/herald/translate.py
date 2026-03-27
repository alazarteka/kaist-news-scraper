from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import Article
from .openrouter import OpenRouterClient
from .utils import (
    JsonCache,
    contains_korean,
    normalize_text,
    normalize_translation_batch_payload,
    normalize_translation_payload,
    parse_model_json,
)


TRANSLATION_RESPONSE_FORMATS = [
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

TRANSLATION_BATCH_RESPONSE_FORMATS = [
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


class OpenRouterTitleTranslator:
    def __init__(self, api_key: str, model: str, cache_path: Path) -> None:
        self.model = model
        self.cache = JsonCache(cache_path)
        self.client = OpenRouterClient(api_key=api_key, model=model)

    def close(self) -> None:
        self.client.close()

    def translate_titles(self, articles: list[Article], batch_size: int = 16) -> int:
        translated_count = 0
        pending: list[Article] = []

        for article in articles:
            key = self.translation_cache_key(article)
            cached = self.cache.get(key)
            if cached is not None:
                translated_count += apply_title_translation(article, str(cached["title_en"]))
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
                self.cache.set(self.translation_cache_key(article), {"title_en": translated_title})
                translated_count += apply_title_translation(article, translated_title)

        return translated_count

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

        translated = self.client.request_with_fallback_formats(
            messages=messages,
            max_tokens=120,
            response_formats=TRANSLATION_RESPONSE_FORMATS,
            parser=self._parse_translation_response,
        )
        self.cache.set(key, {"title_en": translated})
        return translated

    def translation_cache_key(self, article: Article) -> str:
        return hashlib.sha256(
            f"translate\n{article.id}\n{article.title}\n{self.model}".encode("utf-8")
        ).hexdigest()

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

        return self.client.request_with_fallback_formats(
            messages=messages,
            max_tokens=max(200, 40 * len(articles)),
            response_formats=TRANSLATION_BATCH_RESPONSE_FORMATS,
            parser=self._parse_batch_translation_response,
        )

    def _parse_translation_response(self, data: dict[str, Any]) -> str:
        message = data["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(
                item.get("text", "") for item in message if isinstance(item, dict)
            )
        parsed = parse_model_json(message)
        return normalize_translation_payload(parsed)

    def _parse_batch_translation_response(self, data: dict[str, Any]) -> dict[str, str]:
        message = data["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(
                item.get("text", "") for item in message if isinstance(item, dict)
            )
        parsed = parse_model_json(message)
        return normalize_translation_batch_payload(parsed)


def apply_title_translation(article: Article, translated_title: str) -> int:
    translated_title = normalize_text(translated_title)
    if not translated_title or translated_title == article.title:
        return 0
    if article.title_original is None:
        article.title_original = article.title
    article.title = translated_title
    article.title_translated = True
    return 1


def translate_selected_titles(
    articles: list[Article],
    *,
    model: str,
    cache_path: Path,
    api_key: str | None,
    batch_size: int,
) -> int:
    if not api_key:
        return 0

    korean_articles = [article for article in articles if contains_korean(article.title)]
    if not korean_articles:
        return 0

    translator = OpenRouterTitleTranslator(api_key, model, cache_path)
    try:
        return translator.translate_titles(korean_articles, batch_size=batch_size)
    finally:
        translator.close()
