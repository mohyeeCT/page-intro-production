from pathlib import Path
import unittest


APP_SOURCE = Path(__file__).resolve().parents[1] / "app.py"


class AppPageInputTests(unittest.TestCase):
    def test_app_normalises_all_spreadsheet_text_inputs_before_processing(self):
        source = APP_SOURCE.read_text(encoding="utf-8")

        self.assertIn(
            "from utils.page_inputs import normalise_input_value, normalise_page_type",
            source,
        )
        self.assertIn("url = normalise_input_value(row[url_col])", source)
        self.assertIn("h1 = normalise_input_value(row[h1_col])", source)
        self.assertIn("page_type = normalise_page_type(row[page_type_col])", source)
        self.assertIn(
            "manual_keywords_raw = normalise_input_value(row[keywords_col])",
            source,
        )
        self.assertIn("normalise_input_value(value)", source)
        self.assertIn("if url.startswith(\"http\")", source)
        self.assertNotIn('url.lower() == "nan"', source)


if __name__ == "__main__":
    unittest.main()
