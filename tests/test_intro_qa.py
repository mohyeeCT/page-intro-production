import unittest

from utils.intro_qa import build_intro_qa_flags, intro_opening_signature


class IntroQaTests(unittest.TestCase):
    def test_internal_source_language_is_flagged(self):
        flags = build_intro_qa_flags(
            intro_copy=(
                "The live product page specifically positions these running shoes "
                "for mixed road and trail use."
            ),
            page_template="product",
            primary_keyword="running shoes",
        )

        self.assertTrue(
            any(flag.startswith("Internal source language detected:") for flag in flags)
        )

    def test_non_us_spelling_is_flagged_but_official_names_are_protected(self):
        flags = build_intro_qa_flags(
            intro_copy=(
                "The organisation prioritises clear guidance for teams comparing "
                "service options and practical next steps."
            ),
            page_template="service_lp",
        )
        protected_flags = build_intro_qa_flags(
            intro_copy=(
                "Colour Centre helps teams compare practical service options and "
                "implementation needs."
            ),
            page_template="service_lp",
            protected_phrases=["Colour Centre"],
        )

        self.assertTrue(
            any(flag.startswith("Non-U.S. English spelling detected:") for flag in flags)
        )
        self.assertFalse(
            any(
                flag.startswith("Non-U.S. English spelling detected:")
                for flag in protected_flags
            )
        )

    def test_missing_primary_keyword_is_flagged(self):
        flags = build_intro_qa_flags(
            intro_copy="Find practical footwear for daily training, weekend miles, and recovery walks.",
            page_template="category",
            primary_keyword="running shoes",
        )

        self.assertIn("primary keyword missing", flags)

    def test_primary_keyword_used_more_than_twice_is_flagged(self):
        flags = build_intro_qa_flags(
            intro_copy=(
                "Running shoes support daily miles. These running shoes balance comfort "
                "and grip, while our running shoes range covers road and trail needs."
            ),
            page_template="category",
            primary_keyword="running shoes",
        )

        self.assertIn("primary keyword used more than twice", flags)

    def test_verbatim_h1_repetition_is_flagged_unless_h1_is_the_primary_keyword(self):
        repeated_flags = build_intro_qa_flags(
            intro_copy="Summer Running Shoes bring breathable comfort to warm-weather training.",
            page_template="category",
            primary_keyword="breathable running shoes",
            h1="Summer Running Shoes",
        )
        primary_h1_flags = build_intro_qa_flags(
            intro_copy="Summer Running Shoes bring breathable comfort to warm-weather training.",
            page_template="category",
            primary_keyword="Summer Running Shoes",
            h1="Summer Running Shoes",
        )

        self.assertIn("H1 repeated verbatim", repeated_flags)
        self.assertNotIn("H1 repeated verbatim", primary_h1_flags)

    def test_configured_forbidden_phrase_is_flagged_case_insensitively(self):
        flags = build_intro_qa_flags(
            intro_copy="Explore a Best in Class range designed for practical everyday use.",
            page_template="category",
            forbidden_phrases="best in class\nworld-class",
        )

        self.assertIn('forbidden phrase used: "best in class"', flags)

    def test_word_count_outside_twenty_percent_target_range_is_flagged(self):
        short_flags = build_intro_qa_flags(
            intro_copy=" ".join(["word"] * 79),
            page_template="service_lp",
            target_word_count=100,
        )
        long_flags = build_intro_qa_flags(
            intro_copy=" ".join(["word"] * 121),
            page_template="service_lp",
            target_word_count=100,
        )
        within_range_flags = build_intro_qa_flags(
            intro_copy=" ".join(["word"] * 80),
            page_template="service_lp",
            target_word_count=100,
        )

        self.assertIn("intro shorter than recommended range", short_flags)
        self.assertIn("intro longer than recommended range", long_flags)
        self.assertNotIn("intro shorter than recommended range", within_range_flags)
        self.assertNotIn("intro longer than recommended range", within_range_flags)

    def test_repeated_intro_opening_is_flagged_across_rows(self):
        prior = {
            intro_opening_signature(
                "Discover durable running shoes designed for daily miles and gym sessions."
            )
        }

        flags = build_intro_qa_flags(
            intro_copy="Discover durable running shoes designed for trail routes and wet weather.",
            page_template="category",
            previous_openings=prior,
        )

        self.assertIn("repeated intro opening", flags)

    def test_category_page_starting_too_similarly_is_flagged(self):
        prior_category = {
            intro_opening_signature(
                "Explore practical storage boxes for tidy homes and busy family spaces.",
                words=4,
            )
        }

        flags = build_intro_qa_flags(
            intro_copy="Explore practical storage baskets for shelves, wardrobes, and utility rooms.",
            page_template="category",
            previous_category_openings=prior_category,
        )

        self.assertIn("category opening too similar", flags)

    def test_product_intro_without_specific_terms_is_flagged_as_generic(self):
        flags = build_intro_qa_flags(
            intro_copy="This product is built for everyday use with a simple design that works in many situations.",
            page_template="product",
            primary_keyword="Nike Air Zoom Pegasus 41",
            h1="Nike Air Zoom Pegasus 41 Running Shoes",
        )

        self.assertIn("product intro may be too generic", flags)

    def test_location_page_missing_location_in_first_15_words_is_flagged(self):
        flags = build_intro_qa_flags(
            intro_copy="Fast plumbing support helps homeowners solve leaks, blocked drains, and urgent repair issues.",
            page_template="location",
            primary_keyword="emergency plumber chicago",
            h1="Emergency Plumber in Chicago",
        )

        self.assertIn("location missing in first 15 words", flags)

    def test_blog_intro_with_sales_cta_is_flagged(self):
        flags = build_intro_qa_flags(
            intro_copy="Learn how winter tyres work, then contact us today to book a fitting.",
            page_template="blog",
        )

        self.assertIn("blog intro includes sales CTA", flags)


if __name__ == "__main__":
    unittest.main()
