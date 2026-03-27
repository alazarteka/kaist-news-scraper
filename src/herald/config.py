from __future__ import annotations

import tomllib
from pathlib import Path

from .models import AppConfig


DEFAULT_CONFIG_PATH = Path("herald.toml")


def default_config() -> AppConfig:
    return AppConfig(
        source_keys=["kr_research", "kr_news", "en_news"],
        page_limit=5,
        cutoff_days=30,
        start_date=None,
        catchup_overlap_days=3,
        request_delay_seconds=0.5,
        classifier_mode="auto",
        classification_model="qwen/qwen-2.5-7b-instruct",
        translation_model="openai/gpt-4.1-mini",
        translation_batch_size=16,
        archive_path="var/archive.json",
        cache_path="var/openrouter-cache.json",
        site_dir="site",
        site_base_path="/",
        include_original_title=True,
    )


def normalize_site_base_path(value: str) -> str:
    cleaned = "/" + value.strip().strip("/")
    if cleaned == "/":
        return "/"
    return cleaned + "/"


def render_config_toml(config: AppConfig | None = None) -> str:
    current = config or default_config()
    source_keys = ", ".join(f'"{key}"' for key in current.source_keys)
    include_original_title = str(current.include_original_title).lower()
    return f"""# Herald configuration.
# Copy this file into place and adjust paths for the target machine.

[app]
source_keys = [{source_keys}]
page_limit = {current.page_limit}
cutoff_days = {current.cutoff_days}
start_date = "{current.start_date or ""}"
catchup_overlap_days = {current.catchup_overlap_days}
request_delay_seconds = {current.request_delay_seconds}
classifier_mode = "{current.classifier_mode}"
classification_model = "{current.classification_model}"
translation_model = "{current.translation_model}"
translation_batch_size = {current.translation_batch_size}
archive_path = "{current.archive_path}"
cache_path = "{current.cache_path}"
site_dir = "{current.site_dir}"
site_base_path = "{current.site_base_path}"
include_original_title = {include_original_title}
"""


def load_config(path: Path | None) -> AppConfig:
    config = default_config()
    if path is None or not path.exists():
        return config

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    app = data.get("app", {})
    return AppConfig(
        source_keys=list(app.get("source_keys", config.source_keys)),
        page_limit=int(app.get("page_limit", config.page_limit)),
        cutoff_days=int(app.get("cutoff_days", config.cutoff_days)),
        start_date=str(app.get("start_date", config.start_date or "")).strip() or None,
        catchup_overlap_days=int(
            app.get("catchup_overlap_days", config.catchup_overlap_days)
        ),
        request_delay_seconds=float(
            app.get("request_delay_seconds", config.request_delay_seconds)
        ),
        classifier_mode=str(app.get("classifier_mode", config.classifier_mode)),
        classification_model=str(
            app.get("classification_model", config.classification_model)
        ),
        translation_model=str(app.get("translation_model", config.translation_model)),
        translation_batch_size=int(
            app.get("translation_batch_size", config.translation_batch_size)
        ),
        archive_path=str(app.get("archive_path", config.archive_path)),
        cache_path=str(app.get("cache_path", config.cache_path)),
        site_dir=str(app.get("site_dir", config.site_dir)),
        site_base_path=normalize_site_base_path(
            str(app.get("site_base_path", config.site_base_path))
        ),
        include_original_title=bool(
            app.get("include_original_title", config.include_original_title)
        ),
    )
