import re
import requests

JINA_READER_URL = "https://r.jina.ai/"


def scrape_page_context(api_key: str, url: str, max_chars: int = 2000) -> dict:
    """
    Scrape a page via Jina Reader and return truncated topic context.

    Uses POST to https://r.jina.ai/ with the URL in the request body,
    which avoids encoding issues with the GET path-based approach.

    Returns:
        { "content": str, "title": str, "success": bool, "error": str }
    """
    if not url:
        return {"content": "", "title": "", "success": False, "error": "No URL provided"}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Return-Format": "markdown",
        "X-With-Links-Summary": "false",
        "X-With-Images-Summary": "false",
        "X-Target-Selector": (
            "main, #MainContent, #main-content, article, "
            ".page-content, .entry-content, .post-content, [role='main']"
        ),
        "X-Timeout": "30",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.post(
            JINA_READER_URL,
            headers=headers,
            json={"url": url},
            timeout=40
        )
        resp.raise_for_status()

        data = resp.json()
        if not data.get("data"):
            return {"content": "", "title": "", "success": False, "error": "Jina returned no data"}

        text = data["data"].get("content", "") or ""
        title = data["data"].get("title", "") or ""

        if not text:
            return {"content": "", "title": title, "success": False, "error": "Jina returned empty content"}

        # Drop image lines
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

        # Drop pure link-list lines (nav remnants)
        text = re.sub(r"^\s*\*\s+\[.+?\]\(https?://.+?\)\s*$", "", text, flags=re.MULTILINE)

        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if not text:
            return {"content": "", "title": title, "success": False, "error": "No usable content after cleaning"}

        # Take first half of cleaned content, capped at max_chars
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
