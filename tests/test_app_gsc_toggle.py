import unittest
from pathlib import Path


class IntroGscToggleTests(unittest.TestCase):
    def test_app_exposes_gsc_toggle_and_guards_gsc_client(self):
        source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("Use GSC for keyword selection", source)
        self.assertIn("if use_gsc:", source)
        self.assertIn("gsc_client = get_gsc_client(sa_info) if use_gsc else None", source)
        self.assertIn("if use_gsc and gsc_client:", source)

    def test_app_displays_shared_model_defaults(self):
        source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("from utils.copy_gen import generate_intro, DEFAULT_MODELS", source)
        self.assertIn('DEFAULT_MODELS["Claude"]', source)
        self.assertIn('DEFAULT_MODELS["OpenAI"]', source)
        self.assertIn("claude-sonnet-5", source)
        self.assertIn("claude-sonnet-4-6", source)
        self.assertIn("claude-haiku-4-5-20251001", source)
        self.assertIn("gpt-5.5", source)
        self.assertIn("gpt-5.4", source)
        self.assertIn("gemini-3.5-flash", source)
        self.assertNotIn("Mistral", source)
        self.assertNotIn("Groq", source)
        self.assertNotIn("gemini-2.0-flash", source)
        self.assertNotIn("gpt-4o", source)
        self.assertNotIn("gpt-5.4-mini", source)
        self.assertNotIn("gpt-5.4-nano", source)

    def test_app_wires_intro_qa_flags_to_results_and_sheet_output(self):
        source = Path("app.py").read_text(encoding="utf-8")

        self.assertIn("from utils.intro_qa import", source)
        self.assertIn("build_intro_qa_flags", source)
        self.assertIn('"qa_flags"', source)
        self.assertIn('"Intro QA Flags"', source)
        self.assertIn("previous_openings", source)
        self.assertIn("previous_category_openings", source)


if __name__ == "__main__":
    unittest.main()
