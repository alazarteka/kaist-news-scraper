import tempfile
import unittest
from pathlib import Path

from herald import (
    Article,
    JsonCache,
    KAISTScraper,
    RuleBasedClassifier,
    SOURCES,
    article_id_from_url,
    classify_articles,
    contains_korean,
    normalize_decision_payload,
    normalize_translation_batch_payload,
    normalize_translation_payload,
    parse_model_json,
)


SAMPLE_HTML = """
<ul>
  <li>
    <a href="?mode=V&amp;mng_no=59870&amp;GotoPage=1" class="lay">
      <span class="midd">
        <strong class="tis">꽃은 곤충 맞춰 피고 향기 내는 ‘생체시계’ 있다</strong>
        <span class="tes">우리 대학 연구팀이 꽃의 개화 시점과 향 분비를 제어하는 메커니즘을 밝혔다.</span>
        <span class="date">2026.03.27</span>
      </span>
    </a>
  </li>
</ul>
"""


class ParsingTests(unittest.TestCase):
    def test_parse_listing_page_extracts_clean_fields(self) -> None:
        scraper = KAISTScraper()
        try:
            items = scraper.parse_listing_page(SAMPLE_HTML, SOURCES["kr_news"])
        finally:
            scraper.close()

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.title, "꽃은 곤충 맞춰 피고 향기 내는 ‘생체시계’ 있다")
        self.assertEqual(item.date, "2026.03.27")
        self.assertEqual(
            item.preview,
            "우리 대학 연구팀이 꽃의 개화 시점과 향 분비를 제어하는 메커니즘을 밝혔다.",
        )
        self.assertEqual(
            item.url,
            "https://news.kaist.ac.kr/news/html/news/?mode=V&mng_no=59870&GotoPage=1",
        )
        self.assertEqual(item.id, article_id_from_url(item.url, "kr"))


class RuleClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = RuleBasedClassifier()

    def test_research_host_is_always_research(self) -> None:
        article = Article(
            id="kr_1",
            title="아무 제목",
            date="2026.03.27",
            url="https://researchnews.kaist.ac.kr/researchnews/html/news/?mode=V&mng_no=1",
            lang="kr",
            source="kr_research",
            preview="",
        )
        decision = self.classifier.classify(article)
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertTrue(decision.is_research)

    def test_admin_announcement_is_not_research(self) -> None:
        article = Article(
            id="en_1",
            title="2026 KAIST Commencement Ceremony Begins",
            date="2026.03.27",
            url="https://news.kaist.ac.kr/newsen/html/news/?mode=V&mng_no=1",
            lang="en",
            source="en_news",
            preview="Students and families gathered for the ceremony.",
        )
        decision = self.classifier.classify(article)
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertFalse(decision.is_research)

    def test_strong_research_wording_is_research(self) -> None:
        article = Article(
            id="en_2",
            title="KAIST Research Team Published New Battery Paper",
            date="2026.03.27",
            url="https://news.kaist.ac.kr/newsen/html/news/?mode=V&mng_no=2",
            lang="en",
            source="en_news",
            preview="The study reports a new catalyst design for batteries.",
        )
        decision = self.classifier.classify(article)
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertTrue(decision.is_research)


class CacheAndFallbackTests(unittest.TestCase):
    def test_auto_classifier_without_api_key_falls_back_conservatively(self) -> None:
        article = Article(
            id="en_3",
            title="KAIST Announces New Campus Space",
            date="2026.03.27",
            url="https://news.kaist.ac.kr/newsen/html/news/?mode=V&mng_no=3",
            lang="en",
            source="en_news",
            preview="The space will support future collaboration.",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = classify_articles(
                articles=[article],
                mode="auto",
                model="unused",
                cache_path=Path(tmpdir) / "cache.json",
                api_key=None,
            )
        self.assertFalse(result[0].is_research)
        self.assertEqual(result[0].reason, "no OpenRouter key; conservative fallback")

    def test_json_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.json"
            cache = JsonCache(path)
            cache.set("key", {"is_research": True})
            self.assertEqual(cache.get("key"), {"is_research": True})


class OpenRouterParsingTests(unittest.TestCase):
    def test_parse_model_json_accepts_boolean_literal(self) -> None:
        self.assertTrue(parse_model_json("true"))

    def test_normalize_decision_payload_accepts_boolean_literal(self) -> None:
        normalized = normalize_decision_payload(True)
        self.assertTrue(normalized["is_research"])
        self.assertEqual(normalized["confidence"], 0.5)

    def test_normalize_decision_payload_accepts_nested_shape(self) -> None:
        payload = {
            "classification": {
                "label": "research",
                "score": "0.91",
                "explanation": "Contains paper and journal details.",
            }
        }
        normalized = normalize_decision_payload(payload)
        self.assertTrue(normalized["is_research"])
        self.assertEqual(normalized["confidence"], 0.91)
        self.assertEqual(normalized["reason"], "Contains paper and journal details.")

    def test_normalize_translation_payload_accepts_nested_shape(self) -> None:
        payload = {"translation": "Flowers Have a Biological Clock That Matches Insects"}
        self.assertEqual(
            normalize_translation_payload(payload),
            "Flowers Have a Biological Clock That Matches Insects",
        )

    def test_normalize_translation_batch_payload_accepts_list_shape(self) -> None:
        payload = {
            "translations": [
                {"id": "kr_1", "title_en": "Flowers Have a Biological Clock"},
                {"id": "kr_2", "translation": "A Catalyst That Does Not Break Down"},
            ]
        }
        self.assertEqual(
            normalize_translation_batch_payload(payload),
            {
                "kr_1": "Flowers Have a Biological Clock",
                "kr_2": "A Catalyst That Does Not Break Down",
            },
        )


class TranslationHelpersTests(unittest.TestCase):
    def test_contains_korean(self) -> None:
        self.assertTrue(contains_korean("꽃은 곤충 맞춰 피고 향기 내는 생체시계"))
        self.assertFalse(contains_korean("Flowers have a biological clock"))


if __name__ == "__main__":
    unittest.main()
