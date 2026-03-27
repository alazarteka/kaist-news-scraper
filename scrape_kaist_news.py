from herald import main


if __name__ == "__main__":
    raise SystemExit(
        main(
            [
                "--sources",
                "kr_news",
                "en_news",
                "--classifier",
                "none",
                "--output-json",
                "kaist_news.json",
                "--output-csv",
                "kaist_news.csv",
            ]
        )
    )
