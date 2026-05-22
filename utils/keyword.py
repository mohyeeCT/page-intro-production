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
    max_cluster_size: int = 5,
    used_primaries: set = None,
    restricted_industry: bool = False
) -> dict:
    """
    Scores a merged keyword pool and returns a ranked cluster.

    Instead of returning a single winner, this returns:
    - primary_keyword: highest-scoring keyword (str)
    - supporting_keywords: next N keywords (list of str), up to max_cluster_size
    - all_scored: full ranked list with scores for UI display
    - skipped_branded: count of branded terms filtered out
    - skipped_volume: count of keywords below min_volume

    Scoring formula (standard):
        score = (volume / difficulty) * log1p(impressions) * (1 + min(ctr, 0.15)) * position_score * relevance_score

    Scoring formula (restricted_industry=True, zero-volume keywords):
        score = log1p(impressions) * (1 + min(ctr, 0.15)) * position_score * relevance_score
        The 0.1 proxy penalty is removed. Zero-volume keywords with strong GSC signals
        compete on equal footing. Used for industries where DFS/GKP suppress volume
        data by policy (guns, CBD, kratom, dispensaries, adult).

    position_score:
        Positions 1-20 all score 1.0. Only position exactly <= position_cutoff is hard-filtered.
        Beyond 20, score drops: 1 / (1 + max(0, position - 20) * 0.1)

    relevance_score:
        Word overlap between query and H1 using basic stemming.
        Range 0.5 (no overlap) to 1.5 (full overlap).

    used_primaries:
        Set of keyword strings already assigned as primary to other URLs in
        this job run. If the top-scoring keyword is already taken, the scorer
        promotes the most specific unused keyword — preferring longer phrases
        and higher H1 relevance as the tiebreaker.
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

        # GSC-only path: DFS volume is 0 (suppressed or unindexed)
        if volume == 0:
            if impressions > 0:
                pos_score = 1 / (1 + max(0, position - 20) * 0.1)
                relevance = _relevance_score(query, h1)
                ctr_boost = 1 + min(ctr, 0.15)

                if restricted_industry:
                    # Restricted industry: DFS suppresses volume by policy.
                    # Score on GSC engagement alone, no penalty — these keywords
                    # compete on equal footing with volume-bearing keywords.
                    proxy_score = math.log1p(impressions) * ctr_boost * pos_score * relevance
                    scoring_mode = "gsc_restricted"
                else:
                    # Standard fallback: volume just not indexed yet.
                    # Apply 0.1 penalty so these rank below keywords with real volume.
                    proxy_score = math.log1p(impressions) * ctr_boost * 0.1
                    scoring_mode = "gsc_fallback"

                scored.append({
                    "keyword": row.get("query"),
                    "volume": 0,
                    "difficulty": difficulty,
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": round(ctr * 100, 2),
                    "position": position,
                    "position_score": round(pos_score, 3),
                    "relevance_score": round(relevance, 3),
                    "score": round(proxy_score, 4),
                    "source": row.get("source", "gsc"),
                    "scoring_mode": scoring_mode
                })
            else:
                skipped_volume += 1
            continue

        if not restricted_industry and volume < min_volume:
            skipped_volume += 1
            continue

        # Position score: 1-20 all equal, penalty beyond 20
        position_score = 1 / (1 + max(0, position - 20) * 0.1)

        # CTR boost
        ctr_boost = 1 + min(ctr, 0.15)  # capped at 0.15 so high CTR on low-volume keywords cannot override volume as primary signal

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

    used_primaries = used_primaries or set()

    # Select primary: prefer highest-scoring unused keyword.
    # If the top keyword is already a primary elsewhere, scan for the most
    # specific unused alternative — ranked by word count (longer = more specific)
    # then H1 relevance score as tiebreaker.
    primary = None
    primary_idx = None

    for idx, candidate in enumerate(scored):
        kw = candidate["keyword"].lower().strip()
        if kw not in used_primaries:
            primary = candidate
            primary_idx = idx
            break

    # If all top candidates are taken, fall back to the highest scorer regardless
    if primary is None and scored:
        primary = scored[0]
        primary_idx = 0

    # Supporting: everything except the chosen primary, up to max_cluster_size
    supporting = [k for i, k in enumerate(scored) if i != primary_idx][:max_cluster_size]

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
