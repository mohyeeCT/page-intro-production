from pathlib import Path
import unittest


APP_SOURCE = Path(__file__).resolve().parents[1] / "app.py"


class AppRunInfoTests(unittest.TestCase):
    def test_app_wires_extended_qa_inputs(self):
        source = APP_SOURCE.read_text(encoding="utf-8")

        self.assertIn("forbidden_phrases=_forbidden_str", source)
        self.assertIn("target_word_count=int(word_count)", source)

    def test_app_displays_run_preview_and_persists_run_metadata(self):
        source = APP_SOURCE.read_text(encoding="utf-8")

        self.assertIn("estimate_intro_run(", source)
        self.assertIn('st.subheader("Run Preview")', source)
        self.assertIn("run_metadata = build_run_metadata(", source)
        for column in ["run_id", "generated_at", "provider", "model"]:
            self.assertIn(f'"{column}":', source)


if __name__ == "__main__":
    unittest.main()
