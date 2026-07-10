import unittest

from utils import copy_gen


class IntroCopyPromptTests(unittest.TestCase):
    def test_provider_default_models_match_current_recommended_defaults(self):
        self.assertEqual(
            copy_gen.DEFAULT_MODELS,
            {
                "Claude": "claude-sonnet-5",
                "OpenAI": "gpt-5.5",
                "Gemini (free)": "gemini-3.5-flash",
            },
        )

    def test_sonnet_5_request_leaves_thinking_unset(self):
        options = copy_gen._anthropic_request_options("claude-sonnet-5", 600)

        self.assertEqual(options, {"model": "claude-sonnet-5", "max_tokens": 600})
        self.assertNotIn("thinking", options)
        self.assertNotIn("extra_body", options)

    def test_anthropic_text_extractor_skips_non_text_blocks(self):
        class Block:
            def __init__(self, type_, text=None):
                self.type = type_
                self.text = text

        self.assertEqual(
            copy_gen._extract_anthropic_text([
                Block("thinking"),
                Block("text", "Intro copy."),
            ]),
            "Intro copy.",
        )

    def test_openai_gpt5_models_use_completion_token_parameter(self):
        self.assertEqual(
            copy_gen._openai_token_limit("gpt-5.5", 600),
            {"max_completion_tokens": 600},
        )
        self.assertEqual(
            copy_gen._openai_token_limit("gpt-5.4", 600),
            {"max_completion_tokens": 600},
        )

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
