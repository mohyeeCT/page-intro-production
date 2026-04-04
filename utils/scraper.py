import re
import requests

JINA_BASE = "https://r.jina.ai/"


def scrape_page_context(api_key: str, url: str, max_chars: int = 2000) -> dict:
    """
    Scrape a page via Jina Reader and return truncated topic context.

    Uses GET https://r.jina.ai/{url} with Accept: application/json.
    No X-Target-Selector — Jina's built-in Readability handles content
    extraction and nav/footer stripping server-side. The selector was
    causing 422 on any page where the CSS selectors didn't match.

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
            return {"content": "", "title": title, "success": False, "error": "Jina returned empty content"}

        # Drop image lines
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

        # Drop pure link-list lines
        text = re.sub(r"^\s*\*\s+\[.+?\]\(https?://.+?\)\s*$", "", text, flags=re.MULTILINE)

        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if not text:
            return {"content": "", "title": title, "success": False, "error": "No usable content after cleaning"}

        # First half of content, capped at max_chars
        cutoff = min(max_chars, len(text) // 2 + 1)
        truncated = text[:cutoff]

        # Cut at last sentence boundary
        last_period = truncated.rfind(".")
        if last_period > cutoff * 0.6:
            truncated = truncated[:last_period + 1]

        return {
            "content": truncated.strip(),
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
