from __future__ import annotations

import unittest

from herald.config import default_config
from herald.models import Article
from herald.render import build_index_html


class RenderTests(unittest.TestCase):
    def test_build_index_html_renders_original_title(self) -> None:
        config = default_config()
        article = Article(
            id="kr_1",
            title="Flowers Have a Biological Clock",
            date="2026.03.27",
            url="https://example.com/story",
            lang="kr",
            source="kr_research",
            preview="",
            title_original="꽃은 곤충 맞춰 피고 향기 내는 생체시계 있다",
            title_translated=True,
        )
        html = build_index_html([article], config)
        self.assertIn("KAIST Research Digest", html)
        self.assertIn("Private Tailnet Edition", html)
        self.assertIn("Flowers Have a Biological Clock", html)
        self.assertIn("꽃은 곤충 맞춰 피고 향기 내는 생체시계 있다", html)
        self.assertIn("<ol class=\"stories\">", html)
        self.assertIn("Friday, 27 March 2026", html)

    def test_build_index_html_uses_base_path(self) -> None:
        config = default_config()
        config.site_base_path = "/herald/"
        article = Article(
            id="kr_1",
            title="Flowers Have a Biological Clock",
            date="2026.03.27",
            url="https://example.com/story",
            lang="kr",
            source="kr_research",
            preview="",
        )
        html = build_index_html([article], config)
        self.assertIn('<base href="/herald/">', html)
        self.assertIn('<link rel="stylesheet" href="/herald/assets/styles.css">', html)
        self.assertIn("fonts.googleapis.com", html)

    def test_build_index_html_prefers_summary_over_preview(self) -> None:
        config = default_config()
        article = Article(
            id="kr_1",
            title="Flowers Have a Biological Clock",
            date="2026.03.27",
            url="https://example.com/story",
            lang="kr",
            source="kr_research",
            preview="This preview should not be shown.",
            summary="This is the generated summary.",
        )
        html = build_index_html([article], config)
        self.assertIn("This is the generated summary.", html)
        self.assertNotIn("This preview should not be shown.", html)
        self.assertIn("KAIST Research News &middot; Korean", html)

    def test_build_index_html_does_not_truncate_generated_summary(self) -> None:
        config = default_config()
        summary = (
            "Sentence one explains the finding in plain language. "
            "Sentence two adds the method. "
            "Sentence three gives the result. "
            "Sentence four adds context. "
            "Sentence five explains why it matters. "
            "Sentence six confirms the full summary should still appear."
        )
        article = Article(
            id="kr_1",
            title="Flowers Have a Biological Clock",
            date="2026.03.27",
            url="https://example.com/story",
            lang="kr",
            source="kr_research",
            preview="",
            summary=summary,
        )
        html = build_index_html([article], config)
        self.assertIn("Sentence six confirms the full summary should still appear.", html)


if __name__ == "__main__":
    unittest.main()
