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

PAGE_TEMPLATE_CONTEXT = {
    "category": (
        "PAGE TEMPLATE: Ecommerce Category\n"
        "Reader mindset: early-stage browsing, not yet ready to buy. They want orientation, not a sales pitch.\n"
        "Rules:\n"
        "- Open by drawing the reader into the range naturally. Lead with a benefit, a use case, or the type of products available. Do not open with 'This collection is', 'This category is', or any variant of that pattern. Vary your opening — do not default to the same word or phrase every time; the right opening depends on what the page content emphasises.\n"
        "- Write about the range and who it is for. Do not focus on a single product.\n"
        "- Reference product types, materials, use cases, or brands from the page content if available.\n"
        "- Breadth over depth. The reader is exploring options, not comparing specs.\n"
        "- No hard CTA. No 'buy now', 'shop now', 'order today', or urgency language of any kind.\n"
        "- No superlatives about the store itself. Describe what the products do.\n"
        "- Keep it tight. This intro sits above a product grid. Every sentence must earn its place."
    ),
    "product": (
        "PAGE TEMPLATE: Product Page\n"
        "Reader mindset: bottom of funnel. They have narrowed their options and want confirmation this is the right choice.\n"
        "Rules:\n"
        "- Lead with the primary use case and one concrete differentiator. Not the category, not the brand story.\n"
        "- Functional language only: what it does, how it performs, who it is built for.\n"
        "- One soft implicit CTA signal is acceptable in the closing sentence, but do not imply availability, variants, delivery, or policy details unless they are explicitly supported.\n"
        "- If page content includes specs, materials, or dimensions, reference the most relevant one specifically.\n"
        "- Do not describe the product category. Describe this specific product."
    ),
    "service_lp": (
        "PAGE TEMPLATE: Service Page / Landing Page\n"
        "Reader mindset: problem-aware and evaluating solutions. They have a need and are checking if this service fits.\n"
        "Rules:\n"
        "- Open with the problem or situation the reader is in, then introduce the service as the resolution.\n"
        "- Outcome-first, not feature-first. What the reader gets, not what the service includes.\n"
        "- One soft CTA signal in the closing sentence is appropriate (e.g. 'get in touch', 'find out how').\n"
        "- B2B: no urgency language, no consumer emotional framing. Capability and result only.\n"
        "- B2C: 'you' language is encouraged. Light emotional framing is acceptable.\n"
        "- Never list service features in the intro. Features belong further down the page."
    ),
    "location": (
        "PAGE TEMPLATE: Location Page\n"
        "Reader mindset: local intent and high urgency. They searched for a service in a specific area.\n"
        "Rules:\n"
        "- The service and location must both appear naturally within the first 15 words. This is the single most important rule for this template.\n"
        "- Ground the copy in the location. Do not write generic service copy with a city name appended at the end.\n"
        "- If page content references specific service areas, neighborhoods, or local context, weave in one specific detail.\n"
        "- Tone is direct and community-aware. Not corporate, not national-scale.\n"
        "- One soft CTA is acceptable (e.g. 'serving [location]', 'contact the [location] team').\n"
        "- Never produce copy that reads like a national page with a city name swapped in."
    ),
    "blog": (
        "PAGE TEMPLATE: Blog / Editorial\n"
        "Reader mindset: informational. They want to learn something, not buy.\n"
        "Rules:\n"
        "- Lead with the question, problem, or topic being addressed. Never use 'In this article we will...'.\n"
        "- The hook can be a counterintuitive statement, the reader's situation framed directly, or a specific question.\n"
        "- Informational tone throughout. No conversion language, no service promotion whatsoever.\n"
        "- No CTA of any kind in the intro.\n"
        "- If placing the primary keyword in the first sentence disrupts the hook, place it in the second sentence instead.\n"
        "- Do not summarise what the article covers. Draw the reader into the topic."
    ),
    "brand": (
        "PAGE TEMPLATE: Brand / About Page\n"
        "Reader mindset: curious and evaluating trust. They want to understand who this company is.\n"
        "Rules:\n"
        "- Lead with what the company stands for or does, not the keyword.\n"
        "- Keyword placement is secondary here. Apply it where it fits naturally, not forced into the first 40 words.\n"
        "- If a brand name is provided, it belongs in the first sentence.\n"
        "- Tone should reflect brand voice. This is the one template where voice matters more than keyword logic.\n"
        "- No CTA of any kind.\n"
        "- No feature or service list. This is positioning copy, not a service description."
    ),
}

RATE_LIMITS = {
    "Claude": 0.5,
    "OpenAI": 0.5,
    "Gemini (free)": 5.0,
}

DEFAULT_MODELS = {
    "Claude": "claude-sonnet-5",
    "OpenAI": "gpt-5.5",
    "Gemini (free)": "gemini-3.5-flash",
}

UNSUPPORTED_CLAIM_GUARDRAIL = (
    "UNSUPPORTED CLAIM RULES\n"
    "- Do not state return, shipping, delivery, warranty, guarantee, refund, exchange, eligibility, "
    "availability, stock, pricing, discount, certification, compliance, safety, legal, medical, or "
    "performance claims unless explicitly present in scraped page content, brand guidelines, or supplied source data.\n"
    "- Treat GSC, DFS, keywords, page template, and business type as strategy signals, not proof of actual policies, "
    "inventory, prices, warranties, guarantees, or shipping terms.\n"
    "- If a risky detail is not confirmed, avoid the claim or keep it general.\n"
)

SCRAPED_CONTEXT_GUARDRAIL = (
    "SCRAPED CONTEXT RULES\n"
    "- Use scraped page content as grounding context for topic, audience, product range, services, materials, "
    "locations, and differentiators.\n"
    "- Do not turn scraped prices, exact sizes, stock levels, product counts, variant counts, discounts, or policy "
    "details into claims unless the user supplied them as approved brand guidance.\n"
    "- Generalize unstable ecommerce details into durable ideas such as available styles, different use cases, "
    "material choices, comparison factors, or shopper needs.\n"
)


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
    page_template: str,
    brand_name: str,
    include_brand: bool,
    word_count: int,
    paragraph_count: int,
    page_type: str = "",
    page_context: str = "",
    brand_guidelines: str = "",
    forbidden_phrases: str = "",
) -> str:
    biz_context = BUSINESS_TYPE_CONTEXT.get(business_type, BUSINESS_TYPE_CONTEXT["general"])
    template_context = PAGE_TEMPLATE_CONTEXT.get(page_template, "")
    supporting_list = ", ".join(supporting_keywords) if supporting_keywords else "none"

    brand_instruction = (
        f'You may include the brand name "{brand_name}" once if it fits naturally. '
        "It must appear in exact casing as written here. Do not force it."
        if include_brand and brand_name
        else "Do not include any brand name in the copy."
    )
    forbidden_line = f"- Never use these phrases: {forbidden_phrases}" if forbidden_phrases.strip() else ""
    brand_guidelines_block = (
        f"\nBRAND & COPY GUIDELINES:\n{brand_guidelines.strip()}"
        if brand_guidelines.strip()
        else ""
    )
    para_instruction = (
        "Write exactly 1 paragraph."
        if paragraph_count == 1
        else f"Write exactly {paragraph_count} short paragraphs."
    )

    # Keyword placement rule varies by template
    if page_template == "brand":
        keyword_rule = "- The primary keyword should appear naturally in the copy. Do not force it into a specific position."
    elif page_template == "blog":
        keyword_rule = "- The primary keyword should appear naturally. If placing it in the first sentence disrupts the hook, use the second sentence instead."
    else:
        keyword_rule = "- The primary keyword must appear naturally within the first 40 words."

    scraped_block = ""
    if page_context and page_context.strip():
        scraped_block = f"""
PAGE CONTENT (scraped from the live page - use it as grounding context, not as permission to invent or overstate risky claims.)
---
{page_context.strip()}
---
"""

    return f"""You are writing an SEO page introduction for the following page.

PAGE DETAILS
H1: {h1}
Page type label: {page_type or "not specified"}
Primary keyword: {primary_keyword}
Supporting keywords (weave in naturally, never list them): {supporting_list}
{scraped_block}
BUSINESS TYPE RULES
{biz_context}

PAGE TEMPLATE RULES
{template_context}

{UNSUPPORTED_CLAIM_GUARDRAIL}
{SCRAPED_CONTEXT_GUARDRAIL if scraped_block else ""}

UNIVERSAL COPY RULES
- {para_instruction}
- Target length: approximately {word_count} words total.
- {keyword_rule}
- Supporting keywords should appear once each where they fit. Do not force any of them.
- Never produce a keyword list, bullet list, or heading inside the copy.
- This intro follows directly from the H1. Do not repeat the H1 verbatim.
- No em dashes anywhere. Use commas or short sentences instead.
- Never start with: "Welcome to", "In today's", "Are you looking for", "If you're", "Whether you're", "This collection", "This category", "This range".
- No marketing superlatives: avoid "best", "leading", "world-class", "cutting-edge", "top-notch".
- Active voice. Vary sentence length.
- {brand_instruction}
{forbidden_line}
{brand_guidelines_block}

The page template rules take priority over the universal copy rules where they conflict.

Return only the intro copy. No preamble, no explanation, no markdown."""


def _extract_anthropic_text(content) -> str:
    text = "\n".join(
        str(block.text)
        for block in (content or [])
        if getattr(block, "type", "text") == "text" and getattr(block, "text", None)
    ).strip()
    if not text:
        raise RuntimeError("AI provider returned an empty text response")
    return text


def _anthropic_request_options(model: str, max_tokens: int) -> dict:
    return {"model": model, "max_tokens": max_tokens}


def _openai_token_limit(model: str, max_tokens: int) -> dict:
    if (model or "").startswith("gpt-5"):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def generate_intro(
    h1: str,
    primary_keyword: str,
    supporting_keywords: list,
    business_type: str,
    page_template: str,
    brand_name: str,
    include_brand: bool,
    word_count: int,
    paragraph_count: int,
    page_type: str,
    provider: str,
    api_key: str,
    page_context: str = "",
    model: str = None,
    brand_guidelines: str = "",
    forbidden_phrases: str = "",
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
        page_template=page_template,
        brand_name=brand_name,
        include_brand=include_brand,
        word_count=word_count,
        paragraph_count=paragraph_count,
        page_type=page_type,
        page_context=page_context,
        brand_guidelines=brand_guidelines,
        forbidden_phrases=forbidden_phrases,
    )

    resolved_model = model or DEFAULT_MODELS.get(provider)
    raw = ""

    try:
        if provider == "Claude":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                **_anthropic_request_options(resolved_model, 600),
                messages=[{"role": "user", "content": prompt}]
            )
            raw = _extract_anthropic_text(msg.content)

        elif provider == "OpenAI":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model=resolved_model,
                messages=[{"role": "user", "content": prompt}],
                **_openai_token_limit(resolved_model, 600)
            )
            raw = resp.choices[0].message.content

        elif provider == "Gemini (free)":
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(model=resolved_model, contents=prompt)
            raw = response.text

        else:
            raise ValueError(f"Unknown provider: {provider}")

    except Exception as e:
        raise RuntimeError(f"[{provider}] Generation failed: {e}")

    time.sleep(RATE_LIMITS.get(provider, 1.0))
    return _sanitise(raw, brand_name)
