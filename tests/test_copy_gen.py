import unittest

from utils import copy_gen


class IntroCopyPromptTests(unittest.TestCase):
    def test_provider_default_models_match_current_recommended_defaults(self):
        self.assertEqual(copy_gen.DEFAULT_MODELS["Claude"], "claude-sonnet-4-6")
        self.assertEqual(copy_gen.DEFAULT_MODELS["OpenAI"], "gpt-5.5")
        self.assertEqual(copy_gen.DEFAULT_MODELS["Groq (free tier)"], "llama3-70b-8192")

    def test_prompt_blocks_unsupported_risky_claims(self):
        prompt = copy_gen._build_prompt(
            h1="Running Shoes",
            primary_keyword="running shoes",
            supporting_keywords=["trail shoes"],
            business_type="ecommerce",
            page_template="product",
            brand_name="Acme",
            include_brand=True,
            word_count=100,
            paragraph_count=1,
            page_type="Product",
            page_context="Lightweight training shoe.",
        )

        self.assertIn("UNSUPPORTED CLAIM RULES", prompt)
        self.assertIn("Do not state return", prompt)
        self.assertIn("availability", prompt)
        self.assertIn("unless explicitly present", prompt)
        self.assertNotIn("availability, options, variants", prompt)

    def test_scraped_context_is_research_not_exact_claim_permission(self):
        prompt = copy_gen._build_prompt(
            h1="Running Shoes",
            primary_keyword="running shoes",
            supporting_keywords=[],
            business_type="ecommerce",
            page_template="category",
            brand_name="",
            include_brand=False,
            word_count=80,
            paragraph_count=1,
            page_type="Category",
            page_context="Sizes 8, 9, 10. $49.99.",
        )

        self.assertIn("Use scraped page content as grounding context", prompt)
        self.assertIn("Do not turn scraped prices", prompt)


if __name__ == "__main__":
    unittest.main()
