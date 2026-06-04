import unittest

from utils.gsc import get_top_queries_for_url


class FailingClient:
    def searchanalytics(self):
        return self

    def query(self, siteUrl, body):
        return self

    def execute(self):
        raise RuntimeError("property denied")


class IntroGscTests(unittest.TestCase):
    def test_gsc_errors_are_returned_for_app_visibility(self):
        result = get_top_queries_for_url(FailingClient(), "sc-domain:example.com", "https://example.com")

        self.assertIn("_error", result[0])
        self.assertIn("property denied", result[0]["_error"])


if __name__ == "__main__":
    unittest.main()
