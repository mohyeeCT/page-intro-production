import re
import time


# Business type context injected into every prompt
BUSINESS_TYPE_CONTEXT = {
    "b2b": (
        "This is a B2B page targeting business buyers, procurement teams, or decision-makers. "
        "Tone: professional, factual, and outcome-focused. Avoid consumer-facing language. "
        "No lifestyle language, no urgency gimmicks. Lead with capability and result."
    ),
    "b2c": (
        "This is a B2C page targeting individual consumers. "
        "Tone: approachable, benefit-driven, and clear. Speak directly to the reader's need. "
        "Avoid jargon. Keep it human and specific."
    ),
    "ecommerce": (
        "This is an ecommerce page. Tone: confident and conversion-oriented. "
        "Highlight what the product or category does and why it is worth buying. "
        "Avoid filler. Every sentence should help the reader decide."
    ),
    "service": (
        "This is a service business page. Tone: credible and reassuring. "
        "Focus on what the service delivers and who it is for. "
        "Avoid overpromising. Demonstrate expertise through specificity."
    ),
    "local": (
        "This is a local business page. Tone: direct and community-aware. "
        "Can reference the location naturally if it fits. "
        "Keep it grounded - this is not a national brand page."
    ),
    "general": (
        "Write clear, accurate copy appropriate for the page topic. "
        "Tone: neutral and informative. Avoid hype or filler language."
    ),
}

RATE_LIMITS = {
    "Claude": 0.5,
    "OpenAI": 0.5,
    "Gemini": 5.0,
    "Mistral": 2.0,
    "Groq": 2.0,
}


def _sanitise(text: str, brand_name: str = "") -> str:
    """
    Post-processing sanitiser applied to all AI output.
    - Strips em dashes (replaced with comma or space)
    - Removes surrounding quotes
    - Corrects brand name casing if brand_name is provided
    - Strips leading/trailing whitespace
    """
    # Remove surrounding quotes
    text = text.strip().strip('"').strip("'").strip()

    # Replace em dashes with a comma-space
    text = text.replace("\u2014", ", ").replace("\u2013", ", ")
    text = re.sub(r'\s*--\s*', ", ", text)

    # Fix brand name casing
    if brand_name:
        text = re.sub(re.escape(brand_name), brand_name, text, flags=re.IGNORECASE)

    return text.strip()


def _build_prompt(
    h1: str,
    primary_keyword: str,
    supporting_keywords: list,
    business_type: str,
    brand_name: str,
    include_brand: bool,
    word_count: int,
    paragraph_count: int,
    page_type: str = ""
) -> str:
    biz_context = BUSINESS_TYPE_CONTEXT.get(business_type, BUSINESS_TYPE_CONTEXT["general"])
    supporting_list = ", ".join(supporting_keywords) if supporting_keywords else "none"
    brand_instruction = (
        f'You may include the brand name "{brand_name}" once if it fits naturally. '
        "It must appear in exact casing as written here. Do not force it."
        if include_brand and brand_name
        else "Do not include any brand name in the copy."
    )
    para_instruction = (
        "Write exactly 1 paragraph."
        if paragraph_count == 1
        else f"Write exactly {paragraph_count} short paragraphs."
    )

    return f"""You are writing an SEO page introduction for the following page.

PAGE CONTEXT
H1: {h1}
Page type: {page_type or "not specified"}
Primary keyword: {primary_keyword}
Supporting keywords (weave in naturally, do not list): {supporting_list}

BUSINESS TYPE RULES
{biz_context}

COPY RULES
- {para_instruction}
- Target length: approximately {word_count} words total.
- The primary keyword must appear naturally within the first 40 words.
- Supporting keywords should appear once each where they fit naturally. Do not force them.
- Never produce a keyword list, bullet list, or heading inside the copy.
- This paragraph follows directly from the H1. Do not repeat the H1 verbatim.
- No em dashes anywhere. Use commas or short sentences instead.
- No filler openers: never start with "Welcome to", "In today's", "Are you looking for", "If you're".
- No marketing superlatives: avoid "best", "leading", "world-class", "cutting-edge".
- Write in active voice. Vary sentence length.
- {brand_instruction}

Return only the intro copy. No preamble, no explanation, no markdown."""


def generate_intro(
    h1: str,
    primary_keyword: str,
    supporting_keywords: list,
    business_type: str,
    brand_name: str,
    include_brand: bool,
    word_count: int,
    paragraph_count: int,
    page_type: str,
    provider: str,
    api_key: str,
    model_overrides: dict = None
) -> str:
    """
    Routes copy generation to the selected AI provider.
    Returns the sanitised intro paragraph string.
    """
    prompt = _build_prompt(
        h1=h1,
        primary_keyword=primary_keyword,
        supporting_keywords=supporting_keywords,
        business_type=business_type,
        brand_name=brand_name,
        include_brand=include_brand,
        word_count=word_count,
        paragraph_count=paragraph_count,
        page_type=page_type
    )

    raw = ""

    try:
        if provider == "Claude":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            model = (model_overrides or {}).get("claude", "claude-3-5-haiku-20241022")
            msg = client.messages.create(
                model=model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = msg.content[0].text

        elif provider == "OpenAI":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            model = (model_overrides or {}).get("openai", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600
            )
            raw = resp.choices[0].message.content

        elif provider == "Gemini":
            from google import genai
            client = genai.Client(api_key=api_key)
            model = (model_overrides or {}).get("gemini", "gemini-2.0-flash")
            response = client.models.generate_content(model=model, contents=prompt)
            raw = response.text

        elif provider == "Mistral":
            from mistralai.client import Mistral
            client = Mistral(api_key=api_key)
            model = (model_overrides or {}).get("mistral", "mistral-small-latest")
            resp = client.chat.complete(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = resp.choices[0].message.content

        elif provider == "Groq":
            from groq import Groq
            client = Groq(api_key=api_key)
            model = (model_overrides or {}).get("groq", "llama3-8b-8192")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600
            )
            raw = resp.choices[0].message.content

        else:
            raise ValueError(f"Unknown provider: {provider}")

    except Exception as e:
        raise RuntimeError(f"[{provider}] Generation failed: {e}")

    time.sleep(RATE_LIMITS.get(provider, 1.0))
    return _sanitise(raw, brand_name)
