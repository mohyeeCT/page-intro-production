import re


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
) -> list[str]:
    flags = []
    template = (page_template or "").strip().lower()
    intro_words = _normalise_words(intro_copy)

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
