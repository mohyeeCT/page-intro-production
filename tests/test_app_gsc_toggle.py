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
        self.assertIn('DEFAULT_MODELS["OpenAI"]', source)


if __name__ == "__main__":
    unittest.main()
