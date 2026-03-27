from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 20.0
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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
