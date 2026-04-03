# Page Intro Production

Streamlit app for generating page intro paragraphs at scale using keyword clusters built from GSC + DataForSEO ranked keyword data.

Part of the Copy Automation Suite.

---

## What it does

For each URL in your Google Sheet:

1. Pulls top 10 GSC queries for the URL (impressions, CTR, position)
2. Pulls DFS ranked keywords for that specific URL path via `dataforseo_labs/google/ranked_keywords/live`
3. Merges both into a deduplicated keyword pool, enriched with manual seeds if provided
4. Scores every keyword using the standard suite formula
5. Selects a primary keyword (highest score) and up to N supporting keywords
6. Generates 1-2 intro paragraphs with the cluster woven in naturally
7. Writes results back to the sheet via batch API calls

---

## Input Sheet Format

| URL | H1 | Keywords (optional) | Page Type (optional) |
|-----|-----|---------------------|----------------------|
| https://example.com/page | Your H1 Text | keyword one, keyword two | product |

- **URL**: Required. Full URL including https://
- **H1**: Required. Current or planned page H1. Used as topical relevance signal.
- **Keywords**: Optional. Comma-separated manual seeds. If blank, cluster is built entirely from GSC + DFS data.
- **Page Type**: Optional. Passed to the AI as context (e.g. product, category, blog, landing).

---

## Output Columns Written Back

| Column | Description |
|--------|-------------|
| Intro Copy | Generated paragraph(s) |
| Primary Keyword | Highest-scoring keyword used to anchor the copy |
| Supporting Keywords | Comma-separated supporting cluster keywords |
| Word Count | Actual word count of generated copy |
| Cluster Source | Where the cluster came from: gsc, dfs_ranked, gsc+dfs, manual |
| Intro Status | ok / skipped / error |

---

## Setup

### 1. Service Account

Same service account used across all apps in the suite.

1. Go to Google Cloud Console > IAM > Service Accounts
2. Create or reuse existing service account, download JSON key
3. Share your Google Sheet with the service account email (Editor access)
4. Add the service account email as a verified user in GSC (Search Console > Settings > Users and permissions)

### 2. GSC Site URL

Must match the property format exactly:
- Domain property: `sc-domain:example.com`
- URL prefix property: `https://example.com/`

Mismatch here is the most common cause of empty GSC results.

### 3. DFS Location Codes

Common codes:
- 2840 = United States
- 2826 = United Kingdom
- 2036 = Australia
- 2124 = Canada

Full list: https://docs.dataforseo.com/v3/appendix/locations/

### 4. DFS Ranked Keywords Note

The ranked keywords endpoint uses DFS's indexed data, updated weekly. It is not real-time. If a URL was recently published or significantly updated, DFS may not yet have data for it. In that case the cluster will fall back to GSC + manual seeds only.

### 5. Install and run

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Keyword Scoring Formula

```
score = (volume / difficulty) * log1p(impressions) * (1 + CTR) * position_score * relevance_score
```

- `position_score`: positions 1-20 score 1.0; beyond 20 drops off. Only position <= cutoff (default 1.0) is hard-filtered.
- `relevance_score`: word overlap between keyword and H1 using basic stemming. Range 0.5 to 1.5.
- GSC-only fallback: if DFS volume is 0 but GSC shows impressions, keyword is scored on engagement proxy only.
