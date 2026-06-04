from urllib.parse import urlparse


def _auth(login: str, password: str):
    from requests.auth import HTTPBasicAuth

    return HTTPBasicAuth(login, password)


def _post_json(url: str, payload: list, login: str, password: str):
    import requests

    return requests.post(url, json=payload, auth=_auth(login, password), timeout=30)


def get_keyword_volume_difficulty(
    login: str,
    password: str,
    keywords: list,
    location_code: int = 2840,
    language_code: str = "en"
) -> dict:
    """
    Returns { keyword: { volume, difficulty } } for a list of keywords.
    Used to enrich manual seed keywords that are not in the ranked keywords response.
    """
    if not keywords:
        return {}

    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_overview/live"
    payload = [{
        "keywords": keywords,
        "location_code": location_code,
        "language_code": language_code
    }]

    try:
        resp = _post_json(url, payload, login, password)
        resp.raise_for_status()
        data = resp.json()
        result = {}
        items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])
        for item in items:
            kw = item.get("keyword", "")
            volume = item.get("keyword_info", {}).get("search_volume") or 0
            difficulty = item.get("keyword_properties", {}).get("keyword_difficulty") or 50
            result[kw.lower()] = {"volume": volume, "difficulty": difficulty}
        return result
    except Exception as e:
        return {"_error": str(e)}


def _relative_url_variants(relative_url: str) -> list:
    if not relative_url:
        relative_url = "/"
    variants = [relative_url]
    if relative_url == "/":
        return variants
    if relative_url.endswith("/"):
        variants.append(relative_url.rstrip("/"))
    else:
        variants.append(relative_url + "/")
    return list(dict.fromkeys(variants))


def get_ranked_keywords_for_url(
    login: str,
    password: str,
    page_url: str,
    location_code: int = 2840,
    language_code: str = "en",
    limit: int = 100
) -> list:
    """
    Returns ranked keywords for a specific URL using the DFS Labs ranked_keywords endpoint.
    The endpoint takes a domain in `target` and filters to the specific URL path via filters.

    Each returned item: { query, volume, difficulty, position, source: "dfs_ranked" }

    Note: DFS ranked keywords data updates weekly, not real-time.
    Trailing slash on relative_url matters - try both if results are empty.
    """
    parsed = urlparse(page_url)
    domain = parsed.netloc.replace("www.", "")
    relative_url = parsed.path
    if parsed.query:
        relative_url += f"?{parsed.query}"

    url = "https://api.dataforseo.com/v3/dataforseo_labs/google/ranked_keywords/live"
    last_error = ""
    try:
        for relative_variant in _relative_url_variants(relative_url):
            payload = [{
                "target": domain,
                "location_code": location_code,
                "language_code": language_code,
                "limit": limit,
                "filters": [
                    "ranked_serp_element.serp_item.relative_url", "=", relative_variant
                ],
                "order_by": ["keyword_data.keyword_info.search_volume,desc"]
            }]
            resp = _post_json(url, payload, login, password)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("tasks", [{}])[0].get("result", [{}])[0].get("items", [])

            results = []
            for item in items:
                kw_data = item.get("keyword_data", {})
                kw = kw_data.get("keyword", "")
                volume = kw_data.get("keyword_info", {}).get("search_volume") or 0
                difficulty = kw_data.get("keyword_properties", {}).get("keyword_difficulty") or 50

                serp_el = item.get("ranked_serp_element", {}).get("serp_item", {})
                position = serp_el.get("rank_absolute") or serp_el.get("rank_group") or 50

                if kw:
                    results.append({
                        "query": kw.lower(),
                        "volume": volume,
                        "difficulty": difficulty,
                        "position": float(position),
                        "impressions": 0,
                        "clicks": 0,
                        "ctr": 0,
                        "source": "dfs_ranked"
                    })
            if results:
                return results
        return []
    except Exception as e:
        last_error = str(e)
    return [{"_error": last_error}]


def merge_keyword_pools(gsc_queries: list, dfs_ranked: list, manual_seeds: list = None) -> list:
    """
    Merges GSC queries, DFS ranked keywords, and optional manual seeds into one
    deduplicated pool. GSC data enriches any keyword that appears in both lists.

    Returns a flat list of keyword dicts ready for scoring.
    Each item has: query, volume, difficulty, impressions, clicks, ctr, position, source
    """
    pool = {}

    # Add DFS ranked keywords first as base
    for item in dfs_ranked:
        if "_error" in item:
            continue
        key = item["query"].lower().strip()
        pool[key] = item.copy()

    # Enrich with GSC data where keywords overlap, GSC wins on engagement signals
    for item in gsc_queries:
        if "_error" in item:
            continue
        key = item["query"].lower().strip()
        if key in pool:
            # Keyword exists in DFS - enrich with real engagement data
            pool[key]["impressions"] = item.get("impressions", 0)
            pool[key]["clicks"] = item.get("clicks", 0)
            pool[key]["ctr"] = item.get("ctr", 0)
            pool[key]["position"] = item.get("position", pool[key]["position"])
            pool[key]["source"] = "gsc+dfs"
        else:
            # GSC-only keyword - add it, volume/difficulty will be 0 unless enriched
            pool[key] = {
                "query": item["query"],
                "volume": 0,
                "difficulty": 50,
                "impressions": item.get("impressions", 0),
                "clicks": item.get("clicks", 0),
                "ctr": item.get("ctr", 0),
                "position": item.get("position", 99),
                "source": "gsc"
            }

    # Add manual seeds, flagged separately
    for kw in (manual_seeds or []):
        key = kw.lower().strip()
        if key and key not in pool:
            pool[key] = {
                "query": kw.strip(),
                "volume": 0,
                "difficulty": 50,
                "impressions": 0,
                "clicks": 0,
                "ctr": 0,
                "position": 50,
                "source": "manual"
            }

    return list(pool.values())
