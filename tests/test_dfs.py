import unittest
from unittest.mock import patch

from utils import dfs


class FakeResponse:
    def __init__(self, items):
        self.items = items

    def raise_for_status(self):
        return None

    def json(self):
        return {"tasks": [{"result": [{"items": self.items}]}]}


class IntroDfsTests(unittest.TestCase):
    def test_volume_difficulty_preserves_zero_difficulty(self):
        response = FakeResponse([
            {
                "keyword": "easy keyword",
                "keyword_info": {"search_volume": 100},
                "keyword_properties": {"keyword_difficulty": 0},
            }
        ])

        with patch("utils.dfs._post_json", return_value=response):
            result = dfs.get_keyword_volume_difficulty(
                "login",
                "password",
                ["easy keyword"],
            )

        self.assertEqual(result["easy keyword"]["difficulty"], 0)

    def test_ranked_keywords_preserve_zero_difficulty(self):
        response = FakeResponse([
            {
                "keyword_data": {
                    "keyword": "easy keyword",
                    "keyword_info": {"search_volume": 100},
                    "keyword_properties": {"keyword_difficulty": 0},
                },
                "ranked_serp_element": {
                    "serp_item": {
                        "rank_absolute": 5,
                    }
                },
            }
        ])

        with patch("utils.dfs._post_json", return_value=response):
            result = dfs.get_ranked_keywords_for_url(
                "login",
                "password",
                "https://example.com/easy",
            )

        self.assertEqual(result[0]["difficulty"], 0)

    def test_ranked_keywords_tries_trailing_slash_variant_when_first_empty(self):
        calls = []

        def fake_post(url, payload, login, password):
            calls.append(payload[0]["filters"][2])
            if len(calls) == 1:
                return FakeResponse([])
            return FakeResponse([
                {
                    "keyword_data": {
                        "keyword": "alpha shoes",
                        "keyword_info": {"search_volume": 100},
                        "keyword_properties": {"keyword_difficulty": 22},
                    },
                    "ranked_serp_element": {"serp_item": {"rank_absolute": 3}},
                }
            ])

        with patch("utils.dfs._post_json", side_effect=fake_post):
            result = dfs.get_ranked_keywords_for_url("login", "password", "https://example.com/shoes")

        self.assertEqual(calls, ["/shoes", "/shoes/"])
        self.assertEqual(result[0]["query"], "alpha shoes")

    def test_ranked_keywords_surfaces_api_error(self):
        with patch("utils.dfs._post_json", side_effect=RuntimeError("bad auth")):
            result = dfs.get_ranked_keywords_for_url("login", "password", "https://example.com/shoes")

        self.assertIn("_error", result[0])
        self.assertIn("bad auth", result[0]["_error"])

    def test_volume_difficulty_surfaces_api_error(self):
        with patch("utils.dfs._post_json", side_effect=RuntimeError("bad auth")):
            result = dfs.get_keyword_volume_difficulty("login", "password", ["alpha"])

        self.assertIn("_error", result)
        self.assertIn("bad auth", result["_error"])


if __name__ == "__main__":
    unittest.main()
