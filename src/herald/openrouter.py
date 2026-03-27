from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from .utils import OPENROUTER_URL, DEFAULT_TIMEOUT


class OpenRouterClient:
    def __init__(self, api_key: str, model: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key = api_key
        self.model = model
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

    def request_with_fallback_formats(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
        response_formats: list[dict[str, Any]],
        parser: Callable[[dict[str, Any]], Any],
    ) -> Any:
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        last_error: Exception | None = None
        for response_format in response_formats:
            attempt_payload = dict(payload)
            attempt_payload["response_format"] = response_format
            try:
                response = self.client.post(OPENROUTER_URL, json=attempt_payload)
                response.raise_for_status()
                return parser(response.json())
            except (httpx.HTTPError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
        raise RuntimeError(f"OpenRouter request failed: {last_error}")
