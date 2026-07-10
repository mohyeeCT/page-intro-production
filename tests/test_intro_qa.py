import unittest

from utils.intro_qa import build_intro_qa_flags, intro_opening_signature


class IntroQaTests(unittest.TestCase):
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
