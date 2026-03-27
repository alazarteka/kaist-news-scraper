from __future__ import annotations

import unittest

from herald.archive import merge_articles
from herald.models import Article


class MergeArticlesTests(unittest.TestCase):
    def test_merge_articles_prefers_newer_incoming_record(self) -> None:
        existing = [
            Article(
                id="kr_1",
                title="Old title",
                date="2026.03.20",
                url="https://example.com/1",
                lang="kr",
                source="kr_research",
                preview="",
            )
        ]
        incoming = [
            Article(
                id="kr_1",
                title="New title",
                date="2026.03.20",
                url="https://example.com/1",
                lang="kr",
                source="kr_research",
                preview="",
            )
        ]

        merged = merge_articles(existing, incoming)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].title, "New title")

    def test_merge_preserves_existing_translated_title(self) -> None:
        existing = [
            Article(
                id="kr_1",
                title="Flowers Have a Biological Clock",
                date="2026.03.27",
                url="https://example.com/1",
                lang="kr",
                source="kr_research",
                preview="Longer preview text",
                title_original="꽃은 곤충 맞춰 피고 향기 내는 생체시계",
                title_translated=True,
            )
        ]
        incoming = [
            Article(
                id="kr_1",
                title="꽃은 곤충 맞춰 피고 향기 내는 생체시계",
                date="2026.03.27",
                url="https://example.com/1",
                lang="kr",
                source="kr_research",
                preview="short",
            )
        ]

        merged = merge_articles(existing, incoming)
        self.assertEqual(merged[0].title, "Flowers Have a Biological Clock")
        self.assertEqual(merged[0].title_original, "꽃은 곤충 맞춰 피고 향기 내는 생체시계")
        self.assertTrue(merged[0].title_translated)
        self.assertEqual(merged[0].preview, "Longer preview text")


if __name__ == "__main__":
    unittest.main()
