from __future__ import annotations

import unittest

from herald.config import default_config
from herald.models import ArchiveSnapshot, Article
from herald.pipeline import latest_archive_date, resolve_cutoff


class PipelineCutoffTests(unittest.TestCase):
    def test_resolve_cutoff_uses_archive_overlap_when_archive_exists(self) -> None:
        config = default_config()
        snapshot = ArchiveSnapshot(
            generated_at="2026-03-27T00:00:00Z",
            articles=[
                Article(
                    id="kr_1",
                    title="x",
                    date="2026.03.20",
                    url="https://example.com/1",
                    lang="kr",
                    source="kr_research",
                    preview="",
                )
            ],
        )

        cutoff = resolve_cutoff(config, snapshot)
        expected = latest_archive_date(snapshot.articles)
        assert expected is not None
        self.assertEqual((expected - cutoff).days, config.catchup_overlap_days)


if __name__ == "__main__":
    unittest.main()
