import unittest

from utils.language import (
    find_internal_source_language,
    find_non_us_english_spellings,
)


class LanguageTests(unittest.TestCase):
    def test_finds_internal_source_language(self):
        examples = (
            "The live product page specifically positions the range for teams.",
            "The live product page also offers several useful options.",
            "According to the provided context, the service supports growing teams.",
            "The scraped content shows several product styles.",
            "Google Search Console indicates strong interest in the service.",
            "GSC data indicates strong interest in the service.",
            "According to PAA, shoppers compare several product styles.",
        )

        for example in examples:
            with self.subTest(example=example):
                self.assertTrue(find_internal_source_language(example))

    def test_source_language_check_allows_legitimate_topics_and_official_names(self):
        legitimate_copy = (
            "Product page design services help ecommerce teams create clearer "
            "shopping journeys and stronger product information."
        )
        legitimate_internal_topic = (
            "AI Overview optimization services help brands improve search visibility."
        )
        protected_copy = (
            "The Live Product Page offers practical design support for growing teams."
        )

        self.assertEqual(find_internal_source_language(legitimate_copy), [])
        self.assertEqual(
            find_internal_source_language(legitimate_internal_topic),
            [],
        )
        self.assertEqual(
            find_internal_source_language(protected_copy, ["Live Product Page"]),
            [],
        )

    def test_finds_distinct_non_us_spellings(self):
        matches = find_non_us_english_spellings(
            "The organisation prioritises colour choices for the catalogue."
        )

        self.assertEqual(
            matches,
            ["organisation", "prioritises", "colour", "catalogue"],
        )

    def test_protects_official_names_and_avoids_us_false_positives(self):
        matches = find_non_us_english_spellings(
            "Colour Centre fulfills orders with a fulfilling support team.",
            ["Colour Centre"],
        )

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
