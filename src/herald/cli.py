from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import DEFAULT_CONFIG_PATH, load_config, render_config_toml
from .pipeline import build_site


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="herald",
        description="Build a static KAIST research digest site.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Build the archive and static site.")
    build.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the herald TOML config file.",
    )

    init_config = subparsers.add_parser(
        "init-config",
        help="Write an example config file.",
    )
    init_config.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Where to write the example config.",
    )
    init_config.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    return parser


def run_build(config_path: Path) -> int:
    config = load_config(config_path)
    stats = build_site(config)
    print(f"Scraped articles: {stats.scraped}")
    print(f"Selected articles: {stats.selected}")
    print(f"Translated titles: {stats.translated_titles}")
    print(f"Archive articles: {stats.archive_articles}")
    print(f"Archive days: {stats.archive_days}")
    print(f"Site directory: {config.site_dir}")
    return 0


def run_init_config(output_path: Path, force: bool) -> int:
    if output_path.exists() and not force:
        raise FileExistsError(
            f"{output_path} already exists. Use --force to overwrite it."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_config_toml(), encoding="utf-8")
    print(f"Wrote config template to {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            return run_build(args.config)
        if args.command == "init-config":
            return run_init_config(args.output, args.force)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
