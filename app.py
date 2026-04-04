import streamlit as st
import pandas as pd
import json
import time
from utils.sheets import get_gspread_client, load_sheet, write_results_batch
from utils.gsc import get_gsc_client, get_top_queries_for_url
from utils.dfs import get_ranked_keywords_for_url, get_keyword_volume_difficulty, merge_keyword_pools
from utils.keyword import score_keyword_pool
from utils.copy_gen import generate_intro
from utils.scraper import scrape_page_context

st.set_page_config(page_title="Page Intro Production", layout="wide")
st.title("Page Intro Production")
st.caption("Generates page intro paragraphs from GSC + DFS keyword clusters")

# ── Session state init ──────────────────────────────────────────────────────
if "results_df" not in st.session_state:
    st.session_state.results_df = None
if "input_df" not in st.session_state:
    st.session_state.input_df = None
if "ws" not in st.session_state:
    st.session_state.ws = None

# ── Sidebar: credentials & config ──────────────────────────────────────────
with st.sidebar:
    st.header("Credentials")

    sa_file = st.file_uploader(
        "Service Account JSON", type=["json"],
        help="Same service account used for Google Sheets and GSC access."
    )

    dfs_login = st.text_input("DataForSEO Login", value="mo@brandvoxx.com")
    dfs_password = st.text_input("DataForSEO Password", type="password")

    st.divider()
    st.header("Jina Reader")
    jina_key = st.text_input(
        "Jina API Key", type="password",
        help="Free at jina.ai — 10M tokens, no card required. Without a key it still works at 20 RPM."
    )
    enable_scraping = st.toggle(
        "Enable page scraping",
        value=False,
        help="Scrapes each page via Jina Reader and passes the content to the AI to ground copy in actual page detail."
    )

    st.divider()
    st.header("AI Provider")

    provider = st.selectbox("Provider", ["Claude", "OpenAI", "Gemini", "Mistral", "Groq"])
    api_key = st.text_input(f"{provider} API Key", type="password")

    st.divider()
    st.header("Job Config")

    gsc_site_url = st.text_input(
        "GSC Site URL",
        help="Match exactly: sc-domain:example.com or https://example.com/"
    )
    location_code = st.number_input("DFS Location Code", value=2840, step=1)

    st.divider()
    st.header("Copy Settings")

    business_type = st.selectbox(
        "Business Type",
        ["b2b", "b2c", "ecommerce", "service", "local", "general"]
    )
    page_template = st.selectbox(
        "Page Template",
        ["category", "product", "service_lp", "location", "blog", "brand"],
        format_func=lambda x: {
            "category": "Category (ecommerce)",
            "product": "Product Page",
            "service_lp": "Service / Landing Page",
            "location": "Location Page",
            "blog": "Blog / Editorial",
            "brand": "Brand / About",
        }[x],
        help="Controls structural intent, keyword placement, and CTA rules for the intro."
    )
    word_count = st.select_slider(
        "Target Word Count",
        options=[60, 80, 100, 120, 150, 180],
        value=120
    )
    paragraph_count = st.radio("Paragraph Count", [1, 2], horizontal=True)
    max_cluster_size = st.slider(
        "Max Supporting Keywords",
        min_value=2,
        max_value=8,
        value=4,
        help="Number of supporting keywords passed to the AI alongside the primary keyword"
    )
    st.divider()
    st.header("Brand")

    brand_name = st.text_input(
        "Brand Name (exact casing)",
        placeholder="Acme Inc.",
        help="Used for copy casing correction and branded term filtering."
    )
    full_brand_name = st.text_input(
        "Full Brand Name (optional)",
        placeholder="Dayson Shalabi Burkert",
        help="If the brand is an abbreviation (e.g. DSB), enter the full name. Each word is added to the branded filter."
    )
    include_brand = st.toggle("Include brand name in copy", value=False)
    branded_terms_input = st.text_area(
        "Additional Branded Terms to Exclude (one per line)",
        placeholder="acme\nacme inc",
        height=60,
        help="Partial match. 'acme' excludes any query containing 'acme'. Merges with auto-detected terms."
    )

    st.divider()
    st.header("Keyword Filters")

    position_cutoff = st.number_input(
        "Position cutoff (exclude <= this)",
        value=1.0, step=0.5,
        help="Only hard-excludes keywords at this position or better. Default 1.0."
    )
    min_volume = st.number_input("Min Search Volume", value=10, step=5)

# ── Section 1: Connect to Google Sheet ─────────────────────────────────────
st.header("1. Connect to Google Sheet")

col1, col2 = st.columns([3, 1])
with col1:
    sheet_url = st.text_input(
        "Google Sheet URL",
        placeholder="https://docs.google.com/spreadsheets/d/..."
    )
with col2:
    worksheet_name = st.text_input("Worksheet name", placeholder="Leave blank for first sheet")

if sheet_url and sa_file:
    try:
        sa_info = json.load(sa_file)
        sa_email = sa_info.get("client_email", "unknown")
        st.info(f"Service account: **{sa_email}** — confirm this has Editor access to the sheet.")
        gc = get_gspread_client(sa_info)
        df, ws = load_sheet(gc, sheet_url, worksheet_name or None)
        st.session_state.input_df = df
        st.session_state.ws = ws
        st.session_state.sa_info = sa_info
        st.success(f"Connected. {len(df)} rows loaded.")
    except Exception as e:
        st.error(f"Sheet load failed: {e}")
        st.caption(
            "Common causes: sheet not shared with the service account, "
            "wrong URL, or Sheets API not enabled in Cloud Console."
        )

if st.session_state.input_df is not None:
    df_preview = st.session_state.input_df
    cols = df_preview.columns.tolist()

    st.header("2. Map Columns")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        url_col = st.selectbox("URL column", cols)
    with col2:
        h1_col = st.selectbox("H1 column", cols)
    with col3:
        page_type_col = st.selectbox("Page Type column (optional)", ["(none)"] + cols)
    with col4:
        keywords_col = st.selectbox("Keywords column (optional, comma-sep)", ["(none)"] + cols)

    st.dataframe(df_preview.head(5), use_container_width=True)

    # ── Section 3: Brand Detection ──────────────────────────────────────────
    st.header("3. Brand Detection")
    st.caption(
        "Auto-detect branded GSC queries using CTR, position, and domain word signals. "
        "Detected terms merge with any manually entered terms in the sidebar."
    )

    detect_btn = st.button("Auto-detect Branded Terms")

    if detect_btn:
        if not gsc_site_url:
            st.error("Enter your GSC Site URL in the sidebar first.")
        else:
            try:
                import re as _re
                sa_info = st.session_state.sa_info
                _gsc = get_gsc_client(sa_info)
                _df = st.session_state.input_df
                _urls = _df[url_col].dropna().astype(str).tolist()[:10]

                _all_queries = {}
                with st.spinner("Sampling GSC queries for brand detection..."):
                    for _u in _urls:
                        _rows = get_top_queries_for_url(_gsc, gsc_site_url, _u.strip(), top_n=20)
                        for _r in _rows:
                            _q = _r["query"].lower().strip()
                            if _q not in _all_queries:
                                _all_queries[_q] = _r

                # Build domain word set + full brand name expansion
                _domain_raw = _re.sub(r"https?://|www\.|sc-domain:", "", gsc_site_url).rstrip("/")
                _domain_parts = set(_re.findall(r"[a-z]+", _domain_raw.lower()))
                _domain_parts -= {"com", "net", "org", "co", "uk", "io", "house", "app",
                                   "law", "firm", "group", "inc", "llc", "ltd"}

                _full_name_parts = set(
                    w.lower() for w in _re.findall(r"[a-zA-Z]+", full_brand_name)
                    if len(w) >= 3
                ) if full_brand_name else set()
                _domain_parts = _domain_parts | _full_name_parts

                _detected = {}
                for _q, _r in _all_queries.items():
                    _imp = _r.get("impressions", 0)
                    _clk = _r.get("clicks", 0)
                    _pos = _r.get("position", 99)
                    _ctr = _clk / _imp if _imp > 0 else 0
                    _reasons = []

                    if _ctr >= 0.15 and _imp >= 10:
                        _reasons.append(f"CTR {round(_ctr * 100)}%")
                    if _pos <= 2.0 and _clk >= 5:
                        _reasons.append(f"pos {round(_pos, 1)}")

                    _q_words = set(_re.findall(r"[a-z]+", _q))
                    _dom_match = _domain_parts & _q_words
                    if _dom_match:
                        _reasons.append(f"domain word: {', '.join(sorted(_dom_match))}")

                    if _reasons:
                        _root = sorted(_dom_match, key=len)[0] if _dom_match else _q.split()[0]
                        if _root not in _detected:
                            _detected[_root] = {"queries": [], "reasons": set()}
                        _detected[_root]["queries"].append(_q)
                        _detected[_root]["reasons"].update(_reasons)

                st.session_state.detected_branded = _detected

                if not _detected:
                    st.info("No branded terms detected. Use manual entry in the sidebar if needed.")

            except Exception as e:
                st.error(f"Brand detection failed: {e}")

    if st.session_state.get("detected_branded"):
        st.caption("Checked terms will be excluded from keyword scoring.")
        _confirmed = {}
        for _root, _data in st.session_state.detected_branded.items():
            _reason_str = " | ".join(sorted(_data["reasons"]))
            _sample = ", ".join(_data["queries"][:5])
            _checked = st.checkbox(
                f"`{_root}` — {_reason_str}",
                value=True,
                key=f"brand_chk_{_root}",
                help=f"Excludes queries: {_sample}"
            )
            if _checked:
                _confirmed[_root] = _data
        st.session_state.confirmed_branded = list(_confirmed.keys())
    elif "detected_branded" not in st.session_state:
        st.caption("Run auto-detect above, or enter terms manually in the sidebar.")

    # ── Section 4: Run ──────────────────────────────────────────────────────
    st.header("4. Run")
    run_btn = st.button("Generate Intros", type="primary")

    if run_btn:
        errors = []
        if not api_key:
            errors.append(f"{provider} API key is required.")
        if not dfs_password:
            errors.append("DataForSEO password is required.")
        if not gsc_site_url:
            errors.append("GSC Site URL is required.")
        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                sa_info = st.session_state.sa_info
                gsc_client = get_gsc_client(sa_info)
            except Exception as e:
                st.error(f"GSC client init failed: {e}")
                st.stop()

            # Build branded terms filter list: auto-detected + manual sidebar + brand name words
            branded_terms = []
            # Auto-detected (confirmed via checkboxes)
            branded_terms.extend(st.session_state.get("confirmed_branded", []))
            # Manual sidebar entries
            if branded_terms_input:
                branded_terms.extend([
                    t.strip().lower() for t in branded_terms_input.splitlines() if t.strip()
                ])
            # Brand name itself
            if brand_name:
                branded_terms.append(brand_name.lower())
            # Full brand name expansion words
            if full_brand_name:
                branded_terms.extend([
                    w.lower() for w in full_brand_name.split() if len(w) > 2
                ])
            branded_terms = list(set(branded_terms))

            results = []
            used_primaries = set()  # tracks assigned primary keywords across all rows
            df = st.session_state.input_df.copy()
            progress = st.progress(0, text="Starting...")
            status_area = st.empty()

            for i, row in df.iterrows():
                url = str(row[url_col]).strip()
                h1 = str(row[h1_col]).strip() if h1_col in row else ""
                page_type = str(row[page_type_col]).strip() if page_type_col != "(none)" and page_type_col in row else ""
                manual_keywords_raw = str(row[keywords_col]).strip() if keywords_col != "(none)" and keywords_col in row else ""
                manual_seeds = [k.strip() for k in manual_keywords_raw.split(",") if k.strip()] if manual_keywords_raw else []

                pct = int((i / len(df)) * 100)
                progress.progress(pct, text=f"Processing {i + 1}/{len(df)}: {url[:60]}")

                if not url or url.lower() == "nan":
                    results.append({
                        "url": url,
                        "intro_copy": "",
                        "primary_keyword": "",
                        "supporting_keywords": "",
                        "word_count": 0,
                        "primary_volume": "",
                        "primary_difficulty": "",
                        "cluster_source": "",
                        "status": "skipped: no URL"
                    })
                    continue

                try:
                    # Step 1: GSC pull
                    status_area.info(f"[{i+1}] Pulling GSC queries...")
                    gsc_queries = get_top_queries_for_url(gsc_client, gsc_site_url, url, top_n=10)

                    # Step 2: DFS ranked keywords for this specific URL
                    status_area.info(f"[{i+1}] Pulling DFS ranked keywords...")
                    dfs_ranked = get_ranked_keywords_for_url(
                        dfs_login, dfs_password, url,
                        location_code=int(location_code)
                    )

                    # Step 3: Enrich manual seeds with DFS volume/difficulty if needed
                    if manual_seeds:
                        status_area.info(f"[{i+1}] Enriching manual seeds...")
                        known_keywords = {item["query"].lower() for item in dfs_ranked}
                        seeds_needing_enrichment = [s for s in manual_seeds if s.lower() not in known_keywords]
                        if seeds_needing_enrichment:
                            enriched = get_keyword_volume_difficulty(
                                dfs_login, dfs_password,
                                seeds_needing_enrichment,
                                location_code=int(location_code)
                            )
                            # Inject enriched data back into manual seeds before merge
                            enriched_seeds_dfs = []
                            for s in manual_seeds:
                                key = s.lower()
                                if key in enriched:
                                    enriched_seeds_dfs.append({
                                        "query": s,
                                        "volume": enriched[key].get("volume", 0),
                                        "difficulty": enriched[key].get("difficulty", 50),
                                        "position": 50,
                                        "impressions": 0,
                                        "clicks": 0,
                                        "ctr": 0,
                                        "source": "manual"
                                    })
                            # Add enriched manual items to dfs_ranked so merge picks them up
                            dfs_ranked.extend(enriched_seeds_dfs)
                            manual_seeds_for_merge = []  # already injected
                        else:
                            manual_seeds_for_merge = manual_seeds
                    else:
                        manual_seeds_for_merge = []

                    # Step 4: Merge all keyword sources
                    pool = merge_keyword_pools(gsc_queries, dfs_ranked, manual_seeds_for_merge)

                    # Step 4b: H1 fallback — if pool is empty, extract phrases from H1
                    # and look them up in DFS so the row isn't skipped entirely
                    if not pool and h1:
                        import re as _re
                        status_area.info(f"[{i+1}] No GSC/DFS data — using H1 as keyword fallback...")
                        _stop = {"a","an","the","and","or","for","of","in","on","at","to",
                                 "with","by","from","as","is","are","was","were","this","that"}
                        _h1_words = [w.lower() for w in _re.findall(r"[a-zA-Z]+", h1)
                                     if w.lower() not in _stop and len(w) > 2]
                        # Build 1-2 word phrase seeds from H1
                        _seeds = list(dict.fromkeys(
                            [" ".join(_h1_words[j:j+2]) for j in range(len(_h1_words)-1)] +
                            _h1_words
                        ))[:6]
                        if _seeds:
                            _fallback_vd = get_keyword_volume_difficulty(
                                dfs_login, dfs_password, _seeds,
                                location_code=int(location_code)
                            )
                            for _s in _seeds:
                                _vd = _fallback_vd.get(_s.lower(), {})
                                pool.append({
                                    "query": _s,
                                    "volume": _vd.get("volume", 0),
                                    "difficulty": _vd.get("difficulty", 50),
                                    "position": 50,
                                    "impressions": 0,
                                    "clicks": 0,
                                    "ctr": 0,
                                    "source": "h1_fallback"
                                })

                    if not pool:
                        results.append({
                            "url": url,
                            "intro_copy": "",
                            "primary_keyword": "",
                            "supporting_keywords": "",
                            "word_count": 0,
                            "cluster_source": "no data",
                            "status": "skipped: no keyword data"
                        })
                        continue

                    # Step 5: Score and build cluster
                    status_area.info(f"[{i+1}] Scoring keyword cluster...")
                    cluster = score_keyword_pool(
                        keyword_pool=pool,
                        branded_terms=branded_terms,
                        position_cutoff=float(position_cutoff),
                        min_volume=int(min_volume),
                        h1=h1,
                        max_cluster_size=int(max_cluster_size),
                        used_primaries=used_primaries
                    )

                    if cluster["fallback_triggered"] or not cluster["primary_keyword"]:
                        results.append({
                            "url": url,
                            "intro_copy": "",
                            "primary_keyword": "",
                            "supporting_keywords": "",
                            "word_count": 0,
                            "primary_volume": "",
                            "primary_difficulty": "",
                            "cluster_source": "no scoreable keywords",
                            "status": "skipped: no scoreable keywords"
                        })
                        continue

                    # Register this primary so subsequent rows avoid it
                    used_primaries.add(cluster["primary_keyword"].lower().strip())

                    # Step 6: Optionally scrape page for content context
                    page_context = ""
                    if enable_scraping:
                        status_area.info(f"[{i+1}] Scraping page content...")
                        scrape_result = scrape_page_context(jina_key, url, max_chars=2000)
                        if scrape_result["success"]:
                            page_context = scrape_result["content"]
                        else:
                            # Non-fatal — log and continue without context
                            st.warning(f"Row {i+1}: scrape failed ({scrape_result['error']}), continuing without page context.")

                    # Step 7: Generate intro copy
                    status_area.info(f"[{i+1}] Generating copy with {provider}...")
                    intro = generate_intro(
                        h1=h1,
                        primary_keyword=cluster["primary_keyword"],
                        supporting_keywords=cluster["supporting_keywords"],
                        business_type=business_type,
                        page_template=page_template,
                        brand_name=brand_name,
                        include_brand=include_brand,
                        word_count=int(word_count),
                        paragraph_count=int(paragraph_count),
                        page_type=page_type,
                        provider=provider,
                        api_key=api_key,
                        page_context=page_context
                    )

                    actual_word_count = len(intro.split())
                    # Flatten all source strings, split on "+", deduplicate, rejoin
                    _raw_sources = (
                        [cluster["primary_data"].get("source", "")] +
                        [k.get("source", "") for k in cluster["supporting_data"]]
                    )
                    _source_parts = []
                    for s in _raw_sources:
                        _source_parts.extend(s.split("+"))
                    cluster_sources = "+".join(dict.fromkeys(p for p in _source_parts if p))

                    _pdata = cluster["primary_data"] or {}
                    results.append({
                        "url": url,
                        "intro_copy": intro,
                        "primary_keyword": cluster["primary_keyword"],
                        "supporting_keywords": ", ".join(cluster["supporting_keywords"]),
                        "word_count": actual_word_count,
                        "primary_volume": _pdata.get("volume", ""),
                        "primary_difficulty": _pdata.get("difficulty", ""),
                        "cluster_source": cluster_sources,
                        "status": "ok"
                    })

                except Exception as e:
                    results.append({
                        "url": url,
                        "intro_copy": "",
                        "primary_keyword": "",
                        "supporting_keywords": "",
                        "word_count": 0,
                        "primary_volume": "",
                        "primary_difficulty": "",
                        "cluster_source": "",
                        "status": f"error: {e}"
                    })

            progress.progress(100, text="Done.")
            status_area.empty()
            st.session_state.results_df = pd.DataFrame(results)

# ── Results (outside run block so buttons survive reruns) ───────────────────
if st.session_state.results_df is not None:
    results_df = st.session_state.results_df

    st.header("4. Results")

    ok = results_df[results_df["status"] == "ok"]
    skipped = results_df[results_df["status"] != "ok"]

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Generated", len(ok))
    col_b.metric("Skipped / Error", len(skipped))
    col_c.metric("Avg Word Count", int(ok["word_count"].mean()) if len(ok) > 0 else 0)

    st.dataframe(
        results_df[["url", "primary_keyword", "primary_volume", "primary_difficulty", "supporting_keywords", "word_count", "intro_copy", "cluster_source", "status"]],
        use_container_width=True
    )

    if len(skipped) > 0:
        with st.expander(f"Skipped / Errors ({len(skipped)})"):
            st.dataframe(skipped[["url", "status"]], use_container_width=True)

    col_dl, col_wb = st.columns(2)

    with col_dl:
        csv = results_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv,
            file_name="page_intro_results.csv",
            mime="text/csv"
        )

    with col_wb:
        wb_btn = st.button("Write Back to Sheet")
        if wb_btn:
            if st.session_state.ws is None:
                st.error("Sheet not loaded. Load sheet first.")
            else:
                try:
                    write_results_batch(
                        ws=st.session_state.ws,
                        df=results_df,
                        result_col_map={
                            "intro_copy": "Intro Copy",
                            "primary_keyword": "Primary Keyword",
                            "primary_volume": "Primary KW Volume",
                            "primary_difficulty": "Primary KW Difficulty",
                            "supporting_keywords": "Supporting Keywords",
                            "word_count": "Word Count",
                            "cluster_source": "Cluster Source",
                            "status": "Intro Status"
                        }
                    )
                    st.success("Written to sheet.")
                except Exception as e:
                    st.error(f"Write-back failed: {e}")
