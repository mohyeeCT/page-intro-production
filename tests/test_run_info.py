import unittest
from datetime import datetime, timezone

from utils.run_info import build_run_metadata, estimate_intro_run


class RunMetadataTests(unittest.TestCase):
    def test_build_run_metadata_uses_one_utc_timestamp_and_run_id(self):
        metadata = build_run_metadata(
            provider="Claude",
            model="claude-sonnet-5",
            now=datetime(2026, 7, 31, 12, 30, tzinfo=timezone.utc),
            run_id="intro-run-1",
        )

        self.assertEqual(
            metadata,
            {
                "run_id": "intro-run-1",
                "generated_at": "2026-07-31T12:30:00Z",
                "provider": "Claude",
                "model": "claude-sonnet-5",
            },
        )


class IntroRunEstimateTests(unittest.TestCase):
    def test_estimate_includes_ranked_keyword_variants_and_keyword_enrichment(self):
        estimate = estimate_intro_run(
            valid_rows=4,
            manual_keyword_rows=1,
            h1_fallback_rows=2,
            manual_seed_count=3,
        )

        self.assertEqual(estimate["rows"], 4)
        self.assertEqual(estimate["ai_calls"], 4)
        self.assertEqual(estimate["dfs_calls_min"], 6)
        self.assertEqual(estimate["dfs_calls_max"], 11)
        self.assertAlmostEqual(estimate["dfs_cost_min"], 0.07224)
        self.assertAlmostEqual(estimate["dfs_cost_max"], 0.1806)


if __name__ == "__main__":
    unittest.main()
