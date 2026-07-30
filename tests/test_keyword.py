import unittest

from utils.keyword import score_keyword_pool


class IntroKeywordScoringTests(unittest.TestCase):
    def test_zero_difficulty_is_clamped_to_one_for_scoring(self):
        result = score_keyword_pool(
            keyword_pool=[
                {
                    "query": "easy running shoes",
                    "impressions": 100,
                    "clicks": 5,
                    "ctr": 0.05,
                    "position": 5.0,
                    "volume": 100,
                    "difficulty": 0,
                }
            ],
            branded_terms=[],
            h1="Easy Running Shoes",
            restricted_industry=False,
        )

        self.assertEqual(result["primary_data"]["difficulty"], 1)

    def test_standard_zero_volume_scoring_uses_position_and_h1_relevance(self):
        keyword_pool = [
            {
                "query": "random shoes",
                "impressions": 10000,
                "clicks": 200,
                "ctr": 0.15,
                "position": 80.0,
                "volume": 0,
                "difficulty": 50,
            },
            {
                "query": "running shoes",
                "impressions": 1000,
                "clicks": 30,
                "ctr": 0.05,
                "position": 5.0,
                "volume": 0,
                "difficulty": 50,
            },
        ]

        result = score_keyword_pool(
            keyword_pool=keyword_pool,
            branded_terms=[],
            h1="Running Shoes",
            restricted_industry=False,
        )

        self.assertEqual(result["primary_keyword"], "running shoes")


if __name__ == "__main__":
    unittest.main()
