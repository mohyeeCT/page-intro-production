import re
import requests

JINA_BASE = "https://r.jina.ai/"

# Strip known noise elements server-side via Jina's X-Remove-Selector.
# More reliable than X-Target-Selector because we remove known bad elements
# rather than guessing content class names per platform.
_REMOVE_SELECTOR = ", ".join([
    "nav", "header", "footer", "aside",
    "#cart", ".cart", "[class*='cart']",
    "#header", "#footer", "#nav", "#sidebar",
    "[class*='sidebar']", "[class*='navigation']",
    "[class*='breadcrumb']", "[class*='cookie']",
    "[class*='popup']", "[class*='modal']",
    "[class*='newsletter']", "[class*='subscribe']",
    "[class*='related']", "[class*='recommended']",
    "[class*='upsell']", "[class*='cross-sell']",
    "form", "script", "style", "noscript", "iframe",
])

# Line-level noise patterns — catch anything that slipped through
_NOISE_LINE = re.compile(
    r"^\s*("
    r"\$[\d,.]+|"
    r"Add to cart|Sold out|Sale price|Regular price|Unit price|"
    r"Quantity must be|Adding product|"
    r"Please allow \d|"
    r"Pickup available|Usually ready|Check availability|"
    r"Skip to content|Log in|Sign in|Create account|"
    r"Search$|Menu$|Close$|"
    r"You are not old enough|We need to verify your age|"
    r"Are you 18 or older|I AM OVER 18|I AM NOT|"
    r"By entering you agree|Must be \d+ to enter|"
    r"\+?1?[\s\-.]?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
    r")\s*$",
    re.IGNORECASE
)


def _score_paragraph(para: str) -> float:
    """
    Score a paragraph by content quality.
    Returns 0.0 for noise, higher for substantive prose.
    Rewards: sentence-like text, word count, alpha ratio.
    Penalises: short lines, link-heavy lines, non-alpha content.
    """
    words = para.split()
    if len(words) < 8:
        return 0.0

    # Penalise link-heavy lines (nav remnants)
    link_count = len(re.findall(r"\[.+?\]\(https?://", para))
    if link_count > 2:
        return 0.0

    # Penalise lines that are mostly numbers or symbols
    alpha_ratio = sum(c.isalpha() for c in para) / max(len(para), 1)
    if alpha_ratio < 0.5:
        return 0.0

    return len(words) * alpha_ratio


def scrape_page_context(api_key: str, url: str, max_chars: int = 4000) -> dict:
    """
    Scrape a page via Jina Reader and return cleaned topic context.

    Strategy:
    1. X-Remove-Selector strips nav/cart/footer/modals server-side
    2. Line-level noise filter removes age gates, prices, buttons
    3. Paragraph scoring keeps substantive prose, drops boilerplate
    4. Headings are always kept for structural context
    5. Final output trimmed to max_chars at sentence boundary

    Returns:
        { "content": str, "title": str, "success": bool, "error": str }
    """
    if not url:
        return {"content": "", "title": "", "success": False, "error": "No URL provided"}

    headers = {
        "Accept": "application/json",
        "X-Return-Format": "markdown",
        "X-With-Links-Summary": "false",
        "X-With-Images-Summary": "false",
        "X-Remove-Selector": _REMOVE_SELECTOR,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(
            f"{JINA_BASE}{url}",
            headers=headers,
            timeout=40
        )
        resp.raise_for_status()

        data = resp.json()
        page_data = data.get("data", {})
        text = page_data.get("content", "") or ""
        title = page_data.get("title", "") or ""

        if not text:
            return {"content": "", "title": title, "success": False,
                    "error": "Jina returned empty content"}

        # Drop image lines
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

        # Drop pure link-list lines
        text = re.sub(r"^\s*\*\s+\[.+?\]\(https?://.+?\)\s*$", "", text, flags=re.MULTILINE)

        # Drop known noise lines
        lines = text.splitlines()
        lines = [l for l in lines if not _NOISE_LINE.match(l)]
        text = "\n".join(lines)

        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if not text:
            return {"content": "", "title": title, "success": False,
                    "error": "No content found after stripping boilerplate"}

        # Score paragraphs — keep best-scoring ones plus all headings
        paragraphs = re.split(r"\n{2,}", text)
        result_paras = []
        chars_used = 0

        for para in paragraphs:
            if chars_used >= max_chars:
                break
            is_heading = para.strip().startswith("#")
            score = _score_paragraph(para)
            if score > 0 or is_heading:
                result_paras.append(para)
                chars_used += len(para)

        content = "\n\n".join(result_paras).strip()

        if not content:
            return {"content": "", "title": title, "success": False,
                    "error": "No substantive content found after scoring"}

        # Final trim to max_chars at sentence boundary
        if len(content) > max_chars:
            truncated = content[:max_chars]
            last_period = truncated.rfind(".")
            if last_period > max_chars * 0.6:
                content = truncated[:last_period + 1]
            else:
                content = truncated

        return {
            "content": content.strip(),
            "title": title,
            "success": True,
            "error": ""
        }

    except requests.exceptions.Timeout:
        return {"content": "", "title": "", "success": False, "error": "Request timed out"}
    except requests.exceptions.HTTPError as e:
        return {"content": "", "title": "", "success": False, "error": f"HTTP {e.response.status_code}"}
    except requests.exceptions.RequestException as e:
        return {"content": "", "title": "", "success": False, "error": str(e)}
    except Exception as e:
        return {"content": "", "title": "", "success": False, "error": str(e)}
