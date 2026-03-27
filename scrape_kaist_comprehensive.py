from herald import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            [
                "--sources",
                "kr_research",
                "kr_news",
                "en_news",
                "--cutoff-date",
                "2026-02-20",
                "--output-json",
                "kaist_news_comprehensive.json",
            ]
        )
    )
