from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from .models import ArchiveSnapshot, Article


def load_archive(path: Path) -> ArchiveSnapshot:
    if not path.exists():
        return ArchiveSnapshot(generated_at="", articles=[])

    data = json.loads(path.read_text(encoding="utf-8"))
    return ArchiveSnapshot(
        generated_at=str(data.get("generated_at", "")),
        articles=[Article(**item) for item in data.get("articles", [])],
    )


def merge_articles(existing: Iterable[Article], incoming: Iterable[Article]) -> list[Article]:
    merged: dict[str, Article] = {article.id: article for article in existing}
    for article in incoming:
        current = merged.get(article.id)
        merged[article.id] = article if current is None else merge_article(current, article)
    return sorted(
        merged.values(),
        key=lambda article: (article.date, article.id),
        reverse=True,
    )


def merge_article(existing: Article, incoming: Article) -> Article:
    merged = existing.to_record()
    incoming_record = incoming.to_record()

    for key, value in incoming_record.items():
        if value is None:
            continue
        if key == "preview":
            if len(str(value)) >= len(str(merged.get(key, ""))):
                merged[key] = value
            continue
        if key in {"title", "title_original", "title_translated"}:
            continue
        merged[key] = value

    if incoming.title_translated:
        merged["title"] = incoming.title
        merged["title_original"] = incoming.title_original
        merged["title_translated"] = True
    elif not existing.title_translated:
        merged["title"] = incoming.title
        merged["title_original"] = incoming.title_original
        merged["title_translated"] = incoming.title_translated

    return Article(**merged)


def save_archive(path: Path, articles: list[Article]) -> ArchiveSnapshot:
    snapshot = ArchiveSnapshot(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        articles=articles,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot.to_record(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return snapshot
