from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import Article
from .openrouter import OpenRouterClient
from .utils import JsonCache, normalize_text, parse_model_json


SUMMARY_RESPONSE_FORMATS = [
    {
        "type": "json_schema",
        "json_schema": {
            "name": "article_summary",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "summary_en": {"type": "string"},
                },
                "required": ["summary_en"],
                "additionalProperties": False,
            },
        },
    },
    {"type": "json_object"},
]


class OpenRouterArticleSummarizer:
    def __init__(self, api_key: str, model: str, cache_path: Path) -> None:
        self.model = model
        self.cache = JsonCache(cache_path)
        self.client = OpenRouterClient(api_key=api_key, model=model)

    def close(self) -> None:
        self.client.close()

    def summarize(self, article: Article, article_text: str) -> str:
        key = self._cache_key(article, article_text)
        cached = self.cache.get(key)
        if cached is not None:
            return str(cached["summary_en"])

        messages = [
            {
                "role": "system",
                "content": (
                    "Summarize the provided KAIST article in clear, natural English using "
                    "2 to 5 sentences. Focus on the main finding, method, and significance. "
                    "Do not use bullet points. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "title": article.title_original or article.title,
                        "language": article.lang,
                        "source": article.source,
                        "article_text": article_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        summary = self.client.request_with_fallback_formats(
            messages=messages,
            max_tokens=220,
            response_formats=SUMMARY_RESPONSE_FORMATS,
            parser=self._parse_summary_response,
        )
        self.cache.set(key, {"summary_en": summary})
        return summary

    def _cache_key(self, article: Article, article_text: str) -> str:
        return hashlib.sha256(
            f"summarize\n{article.id}\n{article_text}\n{self.model}".encode("utf-8")
        ).hexdigest()

    def _parse_summary_response(self, data: dict[str, Any]) -> str:
        message = data["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(
                item.get("text", "") for item in message if isinstance(item, dict)
            )
        parsed = parse_model_json(message)
        if isinstance(parsed, dict):
            value = parsed.get("summary_en") or parsed.get("summary")
            if isinstance(value, str) and value.strip():
                return normalize_text(value)
        if isinstance(parsed, str) and parsed.strip():
            return normalize_text(parsed)
        raise ValueError(f"Missing article summary in payload: {parsed!r}")


def summarize_selected_articles(
    articles: list[Article],
    *,
    article_texts: dict[str, str],
    model: str,
    cache_path: Path,
    api_key: str | None,
) -> int:
    if not api_key:
        return 0

    summarizer = OpenRouterArticleSummarizer(api_key, model, cache_path)
    summarized = 0
    try:
        for article in articles:
            if article.summary:
                continue
            article_text = article_texts.get(article.id, "").strip()
            if not article_text:
                continue
            article.summary = summarizer.summarize(article, article_text)
            summarized += 1
    finally:
        summarizer.close()
    return summarized
