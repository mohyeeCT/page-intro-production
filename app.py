import streamlit as st
import pandas as pd
import json
import time
from utils.sheets import get_gspread_client, load_sheet, write_results_batch
from utils.gsc import get_gsc_client, get_top_queries_for_url
from utils.dfs import get_ranked_keywords_for_url, get_keyword_volume_difficulty, merge_keyword_pools
from utils.keyword import score_keyword_pool
from utils.copy_gen import generate_intro

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

    sa_json_raw = st.text_area(
        "Service Account JSON",
        height=120,
        help="Paste the full service account JSON. Used for both Sheets and GSC."
    )

    dfs_login = st.text_input("DataForSEO Login", value="mo@brandvoxx.com")
    dfs_password = st.text_input("DataForSEO Password", type="password")

    st.divider()
    st.header("AI Provider")

    provider = st.selectbox("Provider", ["Claude", "OpenAI", "Gemini", "Mistral", "Groq"])
    api_key = st.text_input(f"{provider} API Key", type="password")

    st.divider()
    st.header("Job Config")

    sheet_url = st.text_input("Google Sheet URL")
    worksheet_name = st.text_input("Worksheet name (blank = first sheet)", value="")
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
    include_brand = st.toggle("Append brand name", value=False)
    brand_name = st.text_input("Brand Name (exact casing)") if include_brand else ""
    full_brand_name = st.text_input(
        "Full Brand Name (for abbreviation expansion)",
        help="e.g. if brand is DSB, enter Dayson Shalabi Burkert to expand filter words"
    )
    position_cutoff = st.number_input(
        "Position cutoff (exclude <= this)",
        value=1.0, step=0.5,
        help="Only hard-excludes keywords at this position or better. Default 1.0."
    )
    min_volume = st.number_input("Min Search Volume", value=10, step=5)

# ── Column mapping ──────────────────────────────────────────────────────────
st.subheader("1. Load Sheet")
load_btn = st.button("Load Sheet")

if load_btn:
    errors = []
    if not sa_json_raw:
        errors.append("Service account JSON is required.")
    if not sheet_url:
        errors.append("Sheet URL is required.")
    if errors:
        for e in errors:
            st.error(e)
    else:
        try:
            sa_info = json.loads(sa_json_raw)
            gc = get_gspread_client(sa_info)
            df, ws = load_sheet(gc, sheet_url, worksheet_name or None)
            st.session_state.input_df = df
            st.session_state.ws = ws
            st.success(f"Loaded {len(df)} rows.")
        except Exception as e:
            st.error(f"Sheet load failed: {e}")

if st.session_state.input_df is not None:
    df_preview = st.session_state.input_df
    cols = df_preview.columns.tolist()

    st.subheader("2. Map Columns")
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

    st.subheader("3. Run")
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
                sa_info = json.loads(sa_json_raw)
                gsc_client = get_gsc_client(sa_info)
            except Exception as e:
                st.error(f"GSC client init failed: {e}")
                st.stop()

            # Build branded terms filter list
            branded_terms = []
            if brand_name:
                branded_terms.append(brand_name.lower())
            if full_brand_name:
                branded_terms.extend([
                    w.lower() for w in full_brand_name.split()
                    if len(w) > 2
                ])

            results = []
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
                        max_cluster_size=int(max_cluster_size)
                    )

                    if cluster["fallback_triggered"] or not cluster["primary_keyword"]:
                        results.append({
                            "url": url,
                            "intro_copy": "",
                            "primary_keyword": "",
                            "supporting_keywords": "",
                            "word_count": 0,
                            "cluster_source": "no scoreable keywords",
                            "status": "skipped: no scoreable keywords"
                        })
                        continue

                    # Step 6: Generate intro copy
                    status_area.info(f"[{i+1}] Generating copy with {provider}...")
                    intro = generate_intro(
                        h1=h1,
                        primary_keyword=cluster["primary_keyword"],
                        supporting_keywords=cluster["supporting_keywords"],
                        business_type=business_type,
                        brand_name=brand_name,
                        include_brand=include_brand,
                        word_count=int(word_count),
                        paragraph_count=int(paragraph_count),
                        page_type=page_type,
                        provider=provider,
                        api_key=api_key
                    )

                    actual_word_count = len(intro.split())
                    cluster_sources = list(set(
                        [cluster["primary_data"].get("source", "")] +
                        [k.get("source", "") for k in cluster["supporting_data"]]
                    ))

                    results.append({
                        "url": url,
                        "intro_copy": intro,
                        "primary_keyword": cluster["primary_keyword"],
                        "supporting_keywords": ", ".join(cluster["supporting_keywords"]),
                        "word_count": actual_word_count,
                        "cluster_source": "+".join(cluster_sources),
                        "status": "ok"
                    })

                except Exception as e:
                    results.append({
                        "url": url,
                        "intro_copy": "",
                        "primary_keyword": "",
                        "supporting_keywords": "",
                        "word_count": 0,
                        "cluster_source": "",
                        "status": f"error: {e}"
                    })

            progress.progress(100, text="Done.")
            status_area.empty()
            st.session_state.results_df = pd.DataFrame(results)

# ── Results (outside run block so buttons survive reruns) ───────────────────
if st.session_state.results_df is not None:
    results_df = st.session_state.results_df

    st.subheader("4. Results")

    ok = results_df[results_df["status"] == "ok"]
    skipped = results_df[results_df["status"] != "ok"]

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Generated", len(ok))
    col_b.metric("Skipped / Error", len(skipped))
    col_c.metric("Avg Word Count", int(ok["word_count"].mean()) if len(ok) > 0 else 0)

    st.dataframe(
        results_df[["url", "primary_keyword", "supporting_keywords", "word_count", "intro_copy", "cluster_source", "status"]],
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
                            "supporting_keywords": "Supporting Keywords",
                            "word_count": "Word Count",
                            "cluster_source": "Cluster Source",
                            "status": "Intro Status"
                        }
                    )
                    st.success("Written to sheet.")
                except Exception as e:
                    st.error(f"Write-back failed: {e}")
