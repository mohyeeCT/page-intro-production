import re


_NULL_VALUES = {"<na>", "nan", "nat", "none", "null"}

_PAGE_TYPE_ALIASES = {
    "service lp": "service",
    "service landing page": "service",
    "service landing pages": "service",
    "service page": "service",
    "service pages": "service",
    "landing page": "landing_page",
    "landing pages": "landing_page",
    "lp": "landing_page",
    "category page": "category",
    "category pages": "category",
    "collection": "category",
    "collection page": "category",
    "collection pages": "category",
    "ecommerce category": "category",
    "ecommerce category page": "category",
    "product page": "product",
    "product pages": "product",
    "location": "local",
    "location page": "local",
    "local page": "local",
    "local service": "local",
    "local service page": "local",
    "city page": "local",
    "blog page": "blog",
}


def normalise_input_value(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in _NULL_VALUES:
        return ""
    return text


def normalise_page_type(value, default: str = "") -> str:
    text = normalise_input_value(value).lower()
    cleaned = re.sub(r"[_\-/]+", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return default
    return _PAGE_TYPE_ALIASES.get(cleaned, cleaned.replace(" ", "_"))
