import unittest

from utils.page_inputs import normalise_input_value, normalise_page_type


class PageInputNormalisationTests(unittest.TestCase):
    def test_normalises_supported_page_type_aliases(self):
        cases = {
            "Product Page": "product",
            "Collection Page": "category",
            "ecommerce category": "category",
            "service_lp": "service",
            "Service Landing Page": "service",
            "LP": "landing_page",
            "location page": "local",
            "city page": "local",
            "blog page": "blog",
            "": "",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalise_page_type(value), expected)

    def test_normalises_spreadsheet_nulls_without_changing_valid_text(self):
        for value in (None, float("nan"), "NaN", "none", "<NA>", "NaT", "null"):
            with self.subTest(value=value):
                self.assertEqual(normalise_input_value(value), "")

        self.assertEqual(
            normalise_input_value("  Summer Running Shoes  "),
            "Summer Running Shoes",
        )
        self.assertEqual(normalise_input_value(0), "0")


if __name__ == "__main__":
    unittest.main()
