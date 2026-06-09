import streamlit as st
import pandas as pd
import json
import time
from utils.sheets import get_gspread_client, load_sheet, write_results_batch
from utils.gsc import get_gsc_client, get_top_queries_for_url
from utils.dfs import get_ranked_keywords_for_url, get_keyword_volume_difficulty, merge_keyword_pools
from utils.keyword import score_keyword_pool
from utils.copy_gen import generate_intro
from utils.niches import get_niche_context, NICHES
from utils.scraper import scrape_page_context, is_ecommerce_collection_page

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

    dfs_login = st.text_input("DataForSEO Login")
    dfs_password = st.text_input("DataForSEO Password", type="password")

    st.divider()
    st.header("Jina Reader")
    jina_key = st.text_input(
        "Jina API Key", type="password",
        help="Free at jina.ai — 10M tokens, no card required. Without a key it still works at 20 RPM."
    )
    enable_scraping = st.toggle(
        "Enable page scraping",
        value=True,
        help="Scrapes each page via Jina Reader and passes the content to the AI to ground copy in actual page detail."
    )

    st.divider()
    st.header("AI Provider")

    provider = st.selectbox("Provider", [
        "Claude",
        "OpenAI",
        "Gemini (free)",
        "Mistral (free tier)",
        "Groq (free tier)",
    ])

    _model_options = {
        "Claude": [
            "Default (claude-sonnet-4-6)",
            "claude-opus-4-5",
            "claude-haiku-3-5",
        ],
        "OpenAI": [
            "Default (gpt-4o-mini)",
            "gpt-4o",
            "gpt-4-turbo",
        ],
        "Gemini (free)": [
            "Default (gemini-2.0-flash)",
            "gemini-2.0-flash-lite",
            "gemini-1.5-pro",
        ],
        "Mistral (free tier)": [
            "Default (mistral-small-latest)",
            "mistral-medium-latest",
            "mistral-large-latest",
        ],
        "Groq (free tier)": [
            "Default (llama3-70b-8192)",
            "llama3-8b-8192",
            "llama-3.1-70b-versatile",
        ],
    }

    selected_model_display = st.selectbox(
        "AI Model Version",
        _model_options.get(provider, ["Default"]),
        help="Choose which model to use. 'Default' uses the recommended model for this provider."
    )
    if selected_model_display.startswith("Default"):
        st.session_state["selected_model"] = None
    else:
        st.session_state["selected_model"] = selected_model_display

    _key_labels = {
        "Claude": "Claude API Key",
        "OpenAI": "OpenAI API Key",
        "Gemini (free)": "Google AI Studio API Key",
        "Mistral (free tier)": "Mistral API Key",
        "Groq (free tier)": "Groq API Key",
    }
    _key_links = {
        "Claude": "Get key: console.anthropic.com",
        "OpenAI": "Get key: platform.openai.com/api-keys",
        "Gemini (free)": "Get key: aistudio.google.com/app/apikey",
        "Mistral (free tier)": "Get key: console.mistral.ai/api-keys",
        "Groq (free tier)": "Get key: console.groq.com/keys",
    }
    api_key = st.text_input(
        _key_labels.get(provider, f"{provider} API Key"),
        type="password",
        help=_key_links.get(provider, "")
    )

    st.divider()
    st.header("Job Config")

    use_gsc = st.toggle(
        "Use GSC for keyword selection",
        value=True,
        help="When enabled, pulls top queries from GSC for keyword selection and brand detection. Disable if you are using manual keywords or H1-derived keywords only."
    )
    gsc_site_url = ""
    if use_gsc:
        gsc_site_url = st.text_input(
            "GSC Site URL",
            help="Match exactly: sc-domain:example.com or https://example.com/"
        )
    else:
        st.caption("GSC disabled. Primary keywords will come from the sheet keyword column or H1-derived phrases.")
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

    st.markdown("---")
    brand_guidelines = st.text_area(
        "Brand & Copy Guidelines (optional)",
        placeholder="Paste brand voice, tone, target audience, USPs, key messages, words to avoid, competitor notes, or any copy guidelines here. The AI will apply this context to every intro generated in this run.",
        height=160,
        help="Free-form brand context injected into every prompt. Paste a brand brief, style notes, or bullet points — any format works."
    )
    st.markdown("---")
    forbidden_phrases = st.text_area(
        "Forbidden Phrases (one per line)",
        placeholder="best in class\nworld-class\namazing",
        height=80,
        help="Phrases the AI must never use. Applied to every intro in this run."
    )
    # Niche selection
    _niche_groups = {}
    for _nk, _nv in NICHES.items():
        _niche_groups.setdefault(_nv["group"], []).append((_nk, _nv["label"]))
    _niche_options = [("none", "No specific niche")]
    for _grp in ["B2B", "Service / Local", "Ecommerce"]:
        for _nk, _nlabel in _niche_groups.get(_grp, []):
            _niche_options.append((_nk, f"{_grp}: {_nlabel}"))
    _niche_keys = [k for k, _ in _niche_options]
    _niche_labels = [l for _, l in _niche_options]
    _niche_idx = st.session_state.get("intro_niche_idx", 0)
    selected_niche_idx = st.selectbox(
        "Niche",
        range(len(_niche_options)),
        format_func=lambda i: _niche_labels[i],
        index=_niche_idx,
        key="intro_niche_select"
    )
    selected_niche = _niche_keys[selected_niche_idx]
    st.session_state["intro_niche_idx"] = selected_niche_idx

    st.markdown("---")

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
    restricted_industry = st.toggle(
        "Restricted Industry Mode",
        value=False,
        help=(
            "Enable for industries where Google/DFS suppress keyword volume data by policy: "
            "firearms, CBD, kratom, dispensaries, adult. "
            "When on, scoring focuses on clicks, impressions, and relevance — "
            "volume filter is disabled and zero-volume keywords compete on equal footing."
        )
    )
    if not restricted_industry:
        min_volume = st.number_input("Min Search Volume", value=10, step=5)
    else:
        min_volume = 0
        st.caption("Min volume filter disabled. Scoring on impressions, clicks, and relevance.")

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
    if use_gsc:
        st.caption(
            "Auto-detect branded GSC queries using CTR, position, and domain word signals. "
            "Detected terms merge with any manually entered terms in the sidebar."
        )
    else:
        st.caption("GSC disabled. Brand auto-detection is unavailable; use manual branded terms in the sidebar if needed.")

    _detect_ready = use_gsc and bool(gsc_site_url)
    if use_gsc and not gsc_site_url:
        st.caption("Enter a GSC Site URL above to enable auto-detection.")
    detect_btn = st.button("Auto-detect Branded Terms", disabled=not _detect_ready)

    if detect_btn:
        if use_gsc and not gsc_site_url:
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
    _missing = []
    if not api_key:
        _missing.append(f"{provider} API key")
    if not dfs_login:
        _missing.append("DataForSEO login")
    if not dfs_password:
        _missing.append("DataForSEO password")
    if _missing:
        st.warning(f"Complete credentials before running: {', '.join(_missing)}.")
    run_btn = st.button("Generate Intros", type="primary", disabled=bool(_missing))

    if run_btn:
        errors = []
        if not api_key:
            errors.append(f"{provider} API key is required.")
        if not dfs_password:
            errors.append("DataForSEO password is required.")
        if not dfs_login:
            errors.append("DataForSEO login is required.")
        if use_gsc and not gsc_site_url:
            errors.append("GSC Site URL is required.")
        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                sa_info = st.session_state.sa_info
                gsc_client = get_gsc_client(sa_info) if use_gsc else None
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
            if branded_terms:
                st.info(f"Branded filter active: {', '.join(sorted(branded_terms))}")

            results = []
            used_primaries = set()  # tracks assigned primary keywords across all rows
            df = st.session_state.input_df.copy()
            progress = st.progress(0, text="Starting...")
            status_area = st.empty()
            partial_placeholder = st.empty()

            def _show_partial(res_list):
                if not res_list:
                    return
                import pandas as _pd
                _partial = _pd.DataFrame(res_list)
                _cols = [c for c in ["url", "primary_keyword", "scrape_status", "word_count", "status"]
                         if c in _partial.columns]
                with partial_placeholder.container():
                    st.caption(f"Partial results — {len(res_list)} row(s) completed so far")
                    st.dataframe(_partial[_cols], use_container_width=True)

            for i, row in df.iterrows():
                url = str(row[url_col]).strip()
                h1 = str(row[h1_col]).strip() if h1_col in row else ""
                page_type = str(row[page_type_col]).strip() if page_type_col != "(none)" and page_type_col in row else ""
                manual_keywords_raw = str(row[keywords_col]).strip() if keywords_col != "(none)" and keywords_col in row else ""
                manual_seeds = [k.strip() for k in manual_keywords_raw.split(",") if k.strip()] if manual_keywords_raw else []

                pct = int((i / len(df)) * 100)
                progress.progress(pct, text=f"Processing {i + 1}/{len(df)}: {url[:60]}")

                if not url or url.lower() == "nan" or not url.startswith("http"):
                    results.append({
                        "url": url,
                        "intro_copy": "",
                        "primary_keyword": "",
                        "runner_up": "",
                        "supporting_keywords": "",
                        "word_count": 0,
                        "primary_volume": "",
                        "primary_difficulty": "",
                        "cluster_source": "",
                        "scrape_status": "skipped",
                        "status": "skipped: invalid URL"
                    })
                    _show_partial(results)
                    continue

                try:
                    import re as _re
                    scrape_status = "disabled"  # updated in step 6 if scraping runs

                    # ── Priority chain for primary keyword selection ───────────────
                    # Tier 1: Manual keyword from sheet — hard override, always primary
                    # Tier 2: H1-derived phrases — primary if no manual keyword
                    # Tier 3: GSC + DFS scoring — primary only if neither tier 1 nor 2 present
                    # GSC and DFS ranked keywords always feed the supporting pool regardless of tier

                    # Step 1: GSC pull (always runs — feeds supporting pool)
                    gsc_error = ""
                    if use_gsc and gsc_client:
                        status_area.info(f"[{i+1}] Pulling GSC queries...")
                        gsc_queries = get_top_queries_for_url(gsc_client, gsc_site_url, url, top_n=10)
                        if gsc_queries and "_error" in gsc_queries[0]:
                            gsc_error = gsc_queries[0]["_error"]
                            gsc_queries = []
                    else:
                        gsc_queries = []
                        gsc_error = "GSC disabled"

                    # Step 2: DFS ranked keywords (always runs — feeds supporting pool)
                    status_area.info(f"[{i+1}] Pulling DFS ranked keywords...")
                    dfs_ranked = get_ranked_keywords_for_url(
                        dfs_login, dfs_password, url,
                        location_code=int(location_code)
                    )
                    dfs_ranked_error = ""
                    if dfs_ranked and "_error" in dfs_ranked[0]:
                        dfs_ranked_error = dfs_ranked[0]["_error"]
                        dfs_ranked = []

                    # Step 3: Determine primary keyword source and enrich accordingly
                    forced_primary = None
                    forced_primary_data = {}

                    if manual_seeds:
                        # TIER 1: Manual keyword — enrich with DFS volume/difficulty, force as primary
                        status_area.info(f"[{i+1}] Enriching manual keyword (Tier 1 primary)...")
                        primary_seed = manual_seeds[0]  # first keyword in cell is primary
                        extra_seeds = manual_seeds[1:]  # any additional are supporting candidates

                        all_to_enrich = [s for s in manual_seeds
                                         if s.lower() not in {item["query"].lower() for item in dfs_ranked}]
                        if all_to_enrich:
                            enriched = get_keyword_volume_difficulty(
                                dfs_login, dfs_password, all_to_enrich,
                                location_code=int(location_code)
                            )
                            if "_error" in enriched:
                                st.warning(f"Row {i+1}: DFS enrichment failed ({enriched['_error']}), continuing with default keyword metrics.")
                                enriched = {}
                        else:
                            enriched = {}

                        # Build primary data from enrichment or DFS ranked match
                        _dfs_map = {item["query"].lower(): item for item in dfs_ranked}
                        _p_key = primary_seed.lower()
                        if _p_key in _dfs_map:
                            _p_item = _dfs_map[_p_key]
                            forced_primary_data = {
                                "keyword": primary_seed,
                                "volume": _p_item.get("volume", 0),
                                "difficulty": _p_item.get("difficulty", 50),
                                "source": "manual"
                            }
                        elif _p_key in enriched:
                            forced_primary_data = {
                                "keyword": primary_seed,
                                "volume": enriched[_p_key].get("volume", 0),
                                "difficulty": enriched[_p_key].get("difficulty", 50),
                                "source": "manual"
                            }
                        else:
                            forced_primary_data = {
                                "keyword": primary_seed,
                                "volume": 0,
                                "difficulty": 50,
                                "source": "manual"
                            }
                        forced_primary = primary_seed

                        # Remaining manual seeds join the supporting pool via DFS ranked
                        for s in extra_seeds:
                            key = s.lower()
                            if key not in _dfs_map:
                                vd = enriched.get(key, {})
                                dfs_ranked.append({
                                    "query": s,
                                    "volume": vd.get("volume", 0),
                                    "difficulty": vd.get("difficulty", 50),
                                    "position": 50,
                                    "impressions": 0,
                                    "clicks": 0,
                                    "ctr": 0,
                                    "source": "manual"
                                })

                    elif h1:
                        # TIER 2: Use full H1 as primary keyword (strip leading articles only)
                        status_area.info(f"[{i+1}] No manual keyword — using H1 as primary keyword (Tier 2)...")
                        _h1_clean = _re.sub(
                            r"^(the|a|an|this|our)\s+", "", h1.strip(), flags=_re.IGNORECASE
                        ).strip().lower()

                        if _h1_clean:
                            _h1_vd = get_keyword_volume_difficulty(
                                dfs_login, dfs_password, [_h1_clean],
                                location_code=int(location_code)
                            )
                            if "_error" in _h1_vd:
                                st.warning(f"Row {i+1}: DFS H1 enrichment failed ({_h1_vd['_error']}), continuing with default keyword metrics.")
                                _h1_vd = {}
                            _best_vd = _h1_vd.get(_h1_clean, {})
                            forced_primary = _h1_clean
                            forced_primary_data = {
                                "keyword": _h1_clean,
                                "volume": _best_vd.get("volume", 0),
                                "difficulty": _best_vd.get("difficulty", 50),
                                "source": "h1_derived"
                            }

                    # Step 4: Merge GSC + DFS ranked into supporting pool
                    # When a forced_primary exists, it is excluded from the pool
                    # so it cannot appear again as a supporting keyword
                    pool = merge_keyword_pools(gsc_queries, dfs_ranked, [])
                    if forced_primary:
                        pool = [k for k in pool if k["query"].lower() != forced_primary.lower()]

                    # Step 5: Score the supporting pool (Tier 3 primary selection runs here
                    # only when forced_primary is None — i.e. no manual keyword and no H1)
                    status_area.info(f"[{i+1}] Scoring keyword pool...")

                    if not pool and not forced_primary:
                        source_errors = " | ".join(
                            e for e in [
                                f"GSC error: {gsc_error}" if gsc_error else "",
                                f"DFS ranked error: {dfs_ranked_error}" if dfs_ranked_error else "",
                            ]
                            if e
                        )
                        results.append({
                            "url": url,
                            "intro_copy": "",
                            "primary_keyword": "",
                            "runner_up": "",
                            "supporting_keywords": "",
                            "word_count": 0,
                            "primary_volume": "",
                            "primary_difficulty": "",
                            "cluster_source": source_errors or "no data",
                            "scrape_status": scrape_status,
                            "status": f"skipped: no keyword data{f' ({source_errors})' if source_errors else ''}"
                        })
                        _show_partial(results)
                        continue

                    if forced_primary:
                        # Score the pool for supporting keywords only
                        cluster = score_keyword_pool(
                            keyword_pool=pool,
                            branded_terms=branded_terms,
                            position_cutoff=float(position_cutoff),
                            min_volume=int(min_volume),
                            h1=h1,
                            max_cluster_size=int(max_cluster_size),
                            used_primaries=used_primaries,
                            restricted_industry=restricted_industry
                        )
                        # Override primary with the forced choice
                        final_primary = forced_primary
                        final_primary_data = forced_primary_data
                        final_supporting = cluster["supporting_keywords"]
                        cluster_tier = forced_primary_data.get("source", "manual")
                    else:
                        # TIER 3: No manual keyword, no H1 — GSC+DFS drives primary selection
                        cluster = score_keyword_pool(
                            keyword_pool=pool,
                            branded_terms=branded_terms,
                            position_cutoff=float(position_cutoff),
                            min_volume=int(min_volume),
                            h1=h1,
                            max_cluster_size=int(max_cluster_size),
                            used_primaries=used_primaries,
                            restricted_industry=restricted_industry
                        )
                        if cluster["fallback_triggered"] or not cluster["primary_keyword"]:
                            results.append({
                                "url": url,
                                "intro_copy": "",
                                "primary_keyword": "",
                                "runner_up": "",
                                "supporting_keywords": "",
                                "word_count": 0,
                                "primary_volume": "",
                                "primary_difficulty": "",
                                "cluster_source": "no scoreable keywords",
                                "scrape_status": scrape_status,
                                "status": "skipped: no scoreable keywords"
                            })
                            _show_partial(results)
                            continue
                        final_primary = cluster["primary_keyword"]
                        final_primary_data = cluster["primary_data"] or {}
                        final_supporting = cluster["supporting_keywords"]
                        cluster_tier = "gsc+dfs"

                    # Register primary to avoid reassignment in subsequent rows
                    used_primaries.add(final_primary.lower().strip())

                    # Step 6: Optionally scrape page for content context
                    page_context = ""
                    if enable_scraping:
                        status_area.info(f"[{i+1}] Scraping page content...")
                        scrape_mode = (
                            "ecommerce_collection"
                            if is_ecommerce_collection_page(business_type, page_type)
                            else "default"
                        )
                        scrape_result = scrape_page_context(jina_key, url, max_chars=10000, mode=scrape_mode)
                        if scrape_result["success"]:
                            page_context = scrape_result["content"]
                            scrape_label = "ecommerce collection" if scrape_mode == "ecommerce_collection" else "default"
                            scrape_status = f"ok {scrape_label} ({len(page_context)} chars)"
                        else:
                            scrape_status = f"failed: {scrape_result['error'][:60]}"
                            # Non-fatal — log and continue without context
                            st.warning(f"Row {i+1}: scrape failed ({scrape_result['error']}), continuing without page context.")

                    # Step 7: Generate intro copy
                    status_area.info(f"[{i+1}] Generating copy with {provider}...")
                    # Merge niche context into brand_guidelines
                    _niche_ctx = get_niche_context(selected_niche)
                    _effective_guidelines = (
                        brand_guidelines + "\n\n" + _niche_ctx
                        if brand_guidelines.strip() and _niche_ctx
                        else _niche_ctx or brand_guidelines
                    )
                    _forbidden_str = "\n".join(
                        p.strip() for p in forbidden_phrases.strip().splitlines() if p.strip()
                    )
                    intro = generate_intro(
                        h1=h1,
                        primary_keyword=final_primary,
                        supporting_keywords=final_supporting,
                        business_type=business_type,
                        page_template=page_template,
                        brand_name=brand_name,
                        include_brand=include_brand,
                        word_count=int(word_count),
                        paragraph_count=int(paragraph_count),
                        page_type=page_type,
                        provider=provider,
                        api_key=api_key,
                        page_context=page_context,
                        model=st.session_state.get("selected_model"),
                        brand_guidelines=_effective_guidelines,
                        forbidden_phrases=_forbidden_str,
                    )

                    actual_word_count = len(intro.split())
                    # Build cluster source label from primary tier + supporting sources
                    _supporting_sources = cluster.get("supporting_data", []) if not forced_primary else []
                    _raw_sources = (
                        [final_primary_data.get("source", cluster_tier)] +
                        [k.get("source", "") for k in _supporting_sources]
                    )
                    _source_parts = []
                    for s in _raw_sources:
                        _source_parts.extend(s.split("+"))
                    cluster_sources = "+".join(dict.fromkeys(p for p in _source_parts if p))

                    # Build full scored pool display for debug (top 10)
                    _all_scored = cluster.get("all_scored", []) if not forced_primary else []
                    _debug_pool = [
                        f"{k['keyword']} | vol:{k['volume']} diff:{k['difficulty']} "
                        f"pos:{k['position']} score:{k['score']} src:{k['source']}"
                        for k in _all_scored[:10]
                    ]

                    runner_up = final_supporting[0] if final_supporting else ""
                    results.append({
                        "url": url,
                        "intro_copy": intro,
                        "primary_keyword": final_primary,
                        "runner_up": runner_up,
                        "supporting_keywords": ", ".join(final_supporting),
                        "word_count": actual_word_count,
                        "primary_volume": final_primary_data.get("volume", ""),
                        "primary_difficulty": final_primary_data.get("difficulty", ""),
                        "cluster_source": cluster_sources,
                        "scrape_status": scrape_status,
                        "status": "ok",
                        # Debug fields — not written to sheet
                        "_debug_tier": cluster_tier,
                        "_debug_gsc_count": len(gsc_queries),
                        "_debug_dfs_count": len(dfs_ranked),
                        "_debug_gsc_error": gsc_error,
                        "_debug_dfs_error": dfs_ranked_error,
                        "_debug_pool_size": len(pool),
                        "_debug_scored_pool": "\n".join(_debug_pool) if _debug_pool else "n/a",
                        "_debug_page_context": page_context,
                        "_debug_scrape_status": scrape_status,
                        "_debug_primary_data": (
                            f"keyword: {final_primary} | "
                            f"vol: {final_primary_data.get('volume','?')} | "
                            f"diff: {final_primary_data.get('difficulty','?')} | "
                            f"source: {final_primary_data.get('source','?')}"
                        ),
                        "_debug_restricted": restricted_industry,
                    })
                    _show_partial(results)

                except Exception as e:
                    results.append({
                        "url": url,
                        "intro_copy": "",
                        "primary_keyword": "",
                        "runner_up": "",
                        "supporting_keywords": "",
                        "word_count": 0,
                        "primary_volume": "",
                        "primary_difficulty": "",
                        "cluster_source": "",
                        "scrape_status": scrape_status,
                        "status": f"error: {e}"
                    })
                    _show_partial(results)

            progress.progress(100, text="Done.")
            status_area.empty()
            partial_placeholder.empty()
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

    # Summary table — clean output columns only, no debug fields
    display_cols = ["url", "primary_keyword", "runner_up", "primary_volume", "primary_difficulty",
                    "supporting_keywords", "word_count", "scrape_status", "intro_copy", "cluster_source", "status"]
    st.dataframe(results_df[display_cols], use_container_width=True)

    # Per-row debug expanders
    st.subheader("Row Debug")
    for _, row in results_df.iterrows():
        row_label = row["url"][:70] + "..." if len(row["url"]) > 70 else row["url"]
        with st.expander(row_label):
            if row["status"] != "ok":
                st.error(f"Status: {row['status']}")
            else:
                # Primary keyword selection
                st.caption("**Primary Keyword Selection**")
                tier_labels = {
                    "manual": "Tier 1 — Manual keyword from sheet",
                    "h1_derived": "Tier 2 — Derived from H1",
                    "gsc+dfs": "Tier 3 — GSC + DFS scoring"
                }
                tier = row.get("_debug_tier", "")
                st.markdown(tier_labels.get(tier, f"Tier: {tier}"))
                st.caption(row.get("_debug_primary_data", ""))

                # Data sources
                st.caption("**Data Sources**")
                st.markdown(
                    f"GSC queries returned: **{row.get('_debug_gsc_count', '?')}** | "
                    f"DFS ranked keywords: **{row.get('_debug_dfs_count', '?')}** | "
                    f"Pool after merge: **{row.get('_debug_pool_size', '?')}** | "
                    f"Restricted industry mode: **{'on' if row.get('_debug_restricted') else 'off'}**"
                )

                # Scored pool
                scored_pool = row.get("_debug_scored_pool", "")
                if scored_pool and scored_pool != "n/a":
                    st.caption("**Top 10 Scored Keywords** (keyword | vol | diff | pos | score | source)")
                    st.text(scored_pool)
                else:
                    st.caption("Scored pool: primary was forced (manual or H1), no pool scoring run.")

                # Supporting keywords
                if row.get("supporting_keywords"):
                    st.caption(f"**Supporting keywords sent to AI:** {row['supporting_keywords']}")

                # Scrape / page context
                st.caption("**Page Scraping**")
                scrape_status = row.get("_debug_scrape_status", "disabled")
                st.markdown(f"Scrape status: `{scrape_status}`")
                page_ctx = row.get("_debug_page_context", "")
                if page_ctx:
                    st.text_area(
                        f"Page content sent to AI ({len(page_ctx)} chars)",
                        value=page_ctx,
                        height=150,
                        disabled=True,
                        key=f"ctx_{row['url']}"
                    )

    if len(skipped) > 0:
        with st.expander(f"Skipped / Errors ({len(skipped)})"):
            st.dataframe(skipped[["url", "status"]], use_container_width=True)

    col_dl, col_xl, col_wb = st.columns(3)

    with col_dl:
        csv = results_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV",
            data=csv,
            file_name="page_intro_results.csv",
            mime="text/csv"
        )

    with col_xl:
        import io as _io
        _export_cols = [c for c in display_cols if c in results_df.columns]
        _xl_buf = _io.BytesIO()
        results_df[_export_cols].to_excel(_xl_buf, index=False, engine="openpyxl")
        st.download_button(
            "Download Excel",
            data=_xl_buf.getvalue(),
            file_name="page_intro_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
                            "runner_up": "Runner-Up Keyword",
                            "primary_volume": "Primary KW Volume",
                            "primary_difficulty": "Primary KW Difficulty",
                            "supporting_keywords": "Supporting Keywords",
                            "word_count": "Word Count",
                            "scrape_status": "Page Scrape Status",
                            "cluster_source": "Cluster Source",
                            "status": "Intro Status"
                        }
                    )
                    st.success("Written to sheet.")
                except Exception as e:
                    st.error(f"Write-back failed: {e}")
