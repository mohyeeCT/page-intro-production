import re

from utils.language import (
    find_internal_source_language,
    find_non_us_english_spellings,
)


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "our", "that", "the",
    "this", "to", "with", "you", "your",
}

_PRODUCT_GENERIC_WORDS = {
    "best", "built", "category", "collection", "designed", "everyday",
    "item", "option", "product", "range", "simple", "solution", "style",
    "use", "uses",
}

_LOCATION_GENERIC_WORDS = {
    "available", "company", "emergency", "local", "near", "repair",
    "service", "services", "specialist", "support", "team",
}

_BLOG_CTA_PHRASES = (
    "book a",
    "book an",
    "book now",
    "browse our",
    "buy now",
    "call us",
    "contact us",
    "get a quote",
    "get in touch",
    "order today",
    "request a quote",
    "schedule",
    "shop now",
    "shop the range",
    "talk to an expert",
)


def _normalise_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def intro_opening_signature(intro_copy: str, words: int = 6) -> str:
    return " ".join(_normalise_words(intro_copy)[:words])


def _significant_terms(*values: str) -> set[str]:
    terms = set()
    for value in values:
        for word in _normalise_words(value):
            if len(word) <= 2 or word in _STOPWORDS or word in _PRODUCT_GENERIC_WORDS:
                continue
            terms.add(word)
    return terms


def _location_terms(primary_keyword: str = "", h1: str = "", page_type: str = "") -> set[str]:
    terms = set()
    source = " ".join(v for v in [h1, primary_keyword, page_type] if v)
    for match in re.finditer(
        r"\b(?:in|near|around|serving)\s+([a-zA-Z][a-zA-Z]*(?:\s+[a-zA-Z][a-zA-Z]*){0,2})",
        source,
        flags=re.IGNORECASE,
    ):
        for word in _normalise_words(match.group(1)):
            if word not in _STOPWORDS and word not in _LOCATION_GENERIC_WORDS:
                terms.add(word)

    if not terms:
        words = _normalise_words(primary_keyword)
        if len(words) >= 2:
            candidate = words[-1]
            if candidate not in _STOPWORDS and candidate not in _LOCATION_GENERIC_WORDS:
                terms.add(candidate)
    return terms


def _contains_sales_cta(intro_copy: str) -> bool:
    normalised = " ".join(_normalise_words(intro_copy))
    return any(phrase in normalised for phrase in _BLOG_CTA_PHRASES)


def _phrase_occurrences(text: str, phrase: str) -> int:
    normalised_text = " ".join(_normalise_words(text))
    normalised_phrase = " ".join(_normalise_words(phrase))
    if not normalised_phrase:
        return 0
    pattern = rf"(?:^| ){re.escape(normalised_phrase)}(?: |$)"
    return len(re.findall(pattern, normalised_text))


def _forbidden_phrase_list(forbidden_phrases: str | list[str]) -> list[str]:
    if isinstance(forbidden_phrases, str):
        candidates = forbidden_phrases.splitlines()
    else:
        candidates = forbidden_phrases or []
    return list(dict.fromkeys(p.strip() for p in candidates if p and p.strip()))


def _shares_opening_prefix(signature: str, previous_signatures: set[str], words: int = 3) -> bool:
    prefix = " ".join(signature.split()[:words])
    if not prefix:
        return False
    return any(" ".join(previous.split()[:words]) == prefix for previous in previous_signatures)


def build_intro_qa_flags(
    intro_copy: str,
    page_template: str,
    primary_keyword: str = "",
    h1: str = "",
    page_type: str = "",
    previous_openings: set[str] | None = None,
    previous_category_openings: set[str] | None = None,
    forbidden_phrases: str | list[str] = "",
    target_word_count: int | None = None,
    protected_phrases: list[str] | None = None,
) -> list[str]:
    flags = []
    template = (page_template or "").strip().lower()
    intro_words = _normalise_words(intro_copy)

    primary_mentions = _phrase_occurrences(intro_copy, primary_keyword)
    if primary_keyword and primary_mentions == 0:
        flags.append("primary keyword missing")
    elif primary_mentions > 2:
        flags.append("primary keyword used more than twice")

    normalised_h1 = " ".join(_normalise_words(h1))
    normalised_primary = " ".join(_normalise_words(primary_keyword))
    if (
        normalised_h1
        and normalised_h1 != normalised_primary
        and _phrase_occurrences(intro_copy, h1)
    ):
        flags.append("H1 repeated verbatim")

    for phrase in _forbidden_phrase_list(forbidden_phrases):
        if _phrase_occurrences(intro_copy, phrase):
            flags.append(f'forbidden phrase used: "{phrase}"')

    non_us_spellings = find_non_us_english_spellings(
        intro_copy,
        protected_phrases or [],
    )
    if non_us_spellings:
        flags.append(
            "Non-U.S. English spelling detected: "
            + ", ".join(non_us_spellings[:5])
            + ". Use U.S. English."
        )

    internal_source_language = find_internal_source_language(
        intro_copy,
        protected_phrases or [],
    )
    if internal_source_language:
        flags.append(
            "Internal source language detected: "
            + ", ".join(internal_source_language[:5])
            + ". Rewrite as customer-facing copy."
        )

    if target_word_count:
        target = max(int(target_word_count), 1)
        lower_bound = int(target * 0.8)
        upper_bound = int(target * 1.2)
        if len(intro_words) < lower_bound:
            flags.append("intro shorter than recommended range")
        elif len(intro_words) > upper_bound:
            flags.append("intro longer than recommended range")

    opening = intro_opening_signature(intro_copy)
    if opening and opening in (previous_openings or set()):
        flags.append("repeated intro opening")

    if template == "category":
        category_opening = intro_opening_signature(intro_copy, words=4)
        if category_opening and _shares_opening_prefix(
            category_opening,
            previous_category_openings or set(),
        ):
            flags.append("category opening too similar")

    if template == "product":
        terms = _significant_terms(primary_keyword, h1)
        matched_terms = terms & set(intro_words)
        if len(terms) >= 3 and len(matched_terms) < 2:
            flags.append("product intro may be too generic")

    if template == "location":
        terms = _location_terms(primary_keyword=primary_keyword, h1=h1, page_type=page_type)
        first_15_words = set(intro_words[:15])
        if terms and not (terms & first_15_words):
            flags.append("location missing in first 15 words")

    if template == "blog" and _contains_sales_cta(intro_copy):
        flags.append("blog intro includes sales CTA")

    return flags
