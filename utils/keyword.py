import math
import re


def _stem(word: str) -> str:
    """
    Minimal stemmer: strips common suffixes so plurals and verb forms match roots.
    No external libs needed.
    flavors -> flavor, beverages -> beverage, extracts -> extract
    """
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3 and not word.endswith("ss"):
        return word[:-1]
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    if word.endswith("ed") and len(word) > 4:
        return word[:-2]
    return word


def _relevance_score(query: str, h1: str) -> float:
    """
    Measures topical overlap between a query and the page H1.
    Returns a multiplier between 0.5 and 1.5.
    Uses basic stemming so plurals match roots.
    """
    STOP_WORDS = {
        "a", "an", "the", "and", "or", "for", "of", "in", "on", "at", "to", "with",
        "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
        "it", "its", "this", "that", "these", "those", "we", "our", "your", "their"
    }

    def tokenise(text):
        words = re.findall(r'[a-z]+', text.lower())
        return set(_stem(w) for w in words if w not in STOP_WORDS and len(w) > 2)

    if not h1:
        return 1.0

    h1_words = tokenise(h1)
    query_words = tokenise(query)

    if not h1_words:
        return 1.0

    overlap = len(h1_words & query_words)
    ratio = overlap / len(h1_words)
    return round(0.5 + ratio, 3)


def score_keyword_pool(
    keyword_pool: list,
    branded_terms: list = None,
    position_cutoff: float = 1.0,
    min_volume: int = 10,
    h1: str = "",
    max_cluster_size: int = 5
) -> dict:
    """
    Scores a merged keyword pool and returns a ranked cluster.

    Instead of returning a single winner, this returns:
    - primary_keyword: highest-scoring keyword (str)
    - supporting_keywords: next N keywords (list of str), up to max_cluster_size
    - all_scored: full ranked list with scores for UI display
    - skipped_branded: count of branded terms filtered out
    - skipped_volume: count of keywords below min_volume

    Scoring formula:
        score = (volume / difficulty) * log1p(impressions) * (1 + ctr) * position_score * relevance_score

    position_score:
        Positions 1-20 all score 1.0. Only position exactly <= position_cutoff is hard-filtered.
        Beyond 20, score drops: 1 / (1 + max(0, position - 20) * 0.1)

    relevance_score:
        Word overlap between query and H1 using basic stemming.
        Range 0.5 (no overlap) to 1.5 (full overlap).

    GSC-fallback for keywords with 0 DFS volume:
        Uses impressions * (1 + ctr) as a proxy score so the keyword
        can still compete if GSC shows strong engagement.
    """
    branded_terms = [t.lower().strip() for t in (branded_terms or [])]
    scored = []
    skipped_branded = 0
    skipped_volume = 0

    for row in keyword_pool:
        query = row.get("query", "").lower().strip()
        if not query:
            continue

        # Filter: branded
        if any(term in query for term in branded_terms):
            skipped_branded += 1
            continue

        position = row.get("position", 99)

        # Hard filter: only exclude if position is at or better than cutoff
        if position <= position_cutoff:
            continue

        volume = row.get("volume", 0)
        difficulty = row.get("difficulty", 50) or 50
        impressions = row.get("impressions", 0)
        clicks = row.get("clicks", 0)
        ctr = row.get("ctr", 0)

        # GSC-only fallback: if DFS volume is 0, use GSC engagement as proxy
        if volume == 0:
            if impressions > 0:
                # Proxy score using engagement only - will rank below any keyword with volume
                proxy_score = math.log1p(impressions) * (1 + ctr) * 0.1
                scored.append({
                    "keyword": row.get("query"),
                    "volume": 0,
                    "difficulty": difficulty,
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": round(ctr * 100, 2),
                    "position": position,
                    "position_score": 1.0,
                    "relevance_score": _relevance_score(query, h1),
                    "score": round(proxy_score, 4),
                    "source": row.get("source", "gsc"),
                    "scoring_mode": "gsc_fallback"
                })
            else:
                skipped_volume += 1
            continue

        if volume < min_volume:
            skipped_volume += 1
            continue

        # Position score: 1-20 all equal, penalty beyond 20
        position_score = 1 / (1 + max(0, position - 20) * 0.1)

        # CTR boost
        ctr_boost = 1 + ctr

        # H1 topical relevance
        relevance = _relevance_score(query, h1)

        score = (volume / difficulty) * math.log1p(impressions) * ctr_boost * position_score * relevance

        scored.append({
            "keyword": row.get("query"),
            "volume": volume,
            "difficulty": difficulty,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(ctr * 100, 2),
            "position": position,
            "position_score": round(position_score, 3),
            "relevance_score": round(relevance, 3),
            "score": round(score, 4),
            "source": row.get("source", "unknown"),
            "scoring_mode": "full"
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    primary = scored[0] if scored else None
    supporting = scored[1:max_cluster_size + 1] if len(scored) > 1 else []

    return {
        "primary_keyword": primary["keyword"] if primary else None,
        "primary_data": primary,
        "supporting_keywords": [k["keyword"] for k in supporting],
        "supporting_data": supporting,
        "all_scored": scored,
        "cluster_size": len(supporting) + (1 if primary else 0),
        "skipped_branded": skipped_branded,
        "skipped_volume": skipped_volume,
        "fallback_triggered": primary is None
    }
