from datetime import datetime, timezone
from uuid import uuid4


# DataForSEO public list pricing checked 2026-07-31.
LABS_LIVE_TASK_COST = 0.012
LABS_LIVE_ITEM_COST = 0.00012
RANKED_KEYWORD_LIMIT = 100


def build_run_metadata(
    provider: str,
    model: str,
    now: datetime | None = None,
    run_id: str | None = None,
) -> dict:
    generated_at = now or datetime.now(timezone.utc)
    generated_at = generated_at.astimezone(timezone.utc)
    return {
        "run_id": run_id or str(uuid4()),
        "generated_at": generated_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "provider": provider,
        "model": model or "",
    }


def estimate_intro_run(
    valid_rows: int,
    manual_keyword_rows: int,
    h1_fallback_rows: int,
    manual_seed_count: int,
) -> dict:
    rows = max(int(valid_rows), 0)
    manual_rows = min(max(int(manual_keyword_rows), 0), rows)
    h1_rows = min(max(int(h1_fallback_rows), 0), rows - manual_rows)
    seed_count = max(int(manual_seed_count), 0)

    ranked_min_cost = rows * LABS_LIVE_TASK_COST
    ranked_max_cost = rows * (
        (2 * LABS_LIVE_TASK_COST)
        + (RANKED_KEYWORD_LIMIT * LABS_LIVE_ITEM_COST)
    )
    h1_enrichment_cost = h1_rows * (LABS_LIVE_TASK_COST + LABS_LIVE_ITEM_COST)
    manual_enrichment_max_cost = (
        (manual_rows * LABS_LIVE_TASK_COST)
        + (seed_count * LABS_LIVE_ITEM_COST)
    )

    return {
        "rows": rows,
        "ai_calls": rows,
        "dfs_calls_min": rows + h1_rows,
        "dfs_calls_max": (rows * 2) + h1_rows + manual_rows,
        "dfs_cost_min": ranked_min_cost + h1_enrichment_cost,
        "dfs_cost_max": (
            ranked_max_cost
            + h1_enrichment_cost
            + manual_enrichment_max_cost
        ),
    }
