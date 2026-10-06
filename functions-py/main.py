"""Daily refresh of the PostHog impact analysis.

Keeps a rolling store of raw merged PRs in Cloud Storage. Each run it:
  1. re-fetches the last REFETCH_DAYS days from GitHub (catches new merges and late reviews),
  2. drops PRs older than the analysis window, so the window slides forward,
  3. re-scores everyone and publishes impact/latest.json for the `impact` HTTP function.
On the very first run (empty store) it backfills the full window.
"""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from firebase_admin import initialize_app, storage
from firebase_functions import logger, scheduler_fn
from firebase_functions.options import MemoryOption
from firebase_functions.params import SecretParam

import fetch_prs
import score

initialize_app()
GITHUB_TOKEN = SecretParam("GITHUB_TOKEN")
RAW_BLOB = "raw/prs.jsonl.gz"
META_BLOB = "raw/meta.json"
OUT_BLOB = "impact/latest.json"
BUCKET = "weave-impact-ia26-data"  # private bucket; the `impact` HTTP function reads OUT_BLOB from it
REFETCH_DAYS = 7


def load_raw(bucket):
    blob = bucket.blob(RAW_BLOB)
    if not blob.exists():
        return {}
    lines = gzip.decompress(blob.download_as_bytes()).decode().splitlines()
    return {pr["number"]: pr for pr in map(json.loads, filter(None, lines))}


def save_raw(bucket, prs):
    # Drop scorer-internal keys (e.g. `_merged` datetimes) so only the raw GitHub payload is stored.
    rows = ({k: v for k, v in p.items() if not k.startswith("_")} for p in prs.values())
    body = gzip.compress("\n".join(json.dumps(r) for r in rows).encode())
    bucket.blob(RAW_BLOB).upload_from_string(body, content_type="application/gzip")


def read_last_day(meta_blob):
    """Last successfully refreshed day, or None (forces a full backfill) if meta is missing or unreadable."""
    try:
        return date.fromisoformat(json.loads(meta_blob.download_as_bytes())["lastDay"])
    except Exception as exc:  # NotFound, bad JSON, missing key, bad date
        logger.warn("meta unreadable, backfilling", error=str(exc))
        return None


def refresh():
    os.environ["GITHUB_TOKEN"] = GITHUB_TOKEN.value
    bucket = storage.bucket(BUCKET)
    end = datetime.now(timezone.utc).date() - timedelta(days=1)  # last complete UTC day
    score.set_window(end)

    store = load_raw(bucket)
    meta_blob = bucket.blob(META_BLOB)
    last_day = read_last_day(meta_blob)
    if not store or last_day is None:
        span = score.WINDOW_DAYS  # first run: backfill the whole window
    else:
        # Re-fetch at least a week (late reviews), and back to the last successful run so outages leave no gap.
        span = min(score.WINDOW_DAYS, max(REFETCH_DAYS, (end - last_day).days + 1))
    fresh = fetch_prs.fetch_days([end - timedelta(days=i) for i in range(span + 1)])
    for pr in fresh:
        store[pr["number"]] = pr
    cutoff = score.WINDOW_START.isoformat().replace("+00:00", "Z")
    store = {n: p for n, p in store.items() if p["mergedAt"] >= cutoff}

    # Score before persisting anything, so a PR that breaks scoring is never committed to the store.
    out = score.build(store.values())
    save_raw(bucket, store)
    meta_blob.upload_from_string(json.dumps({"lastDay": end.isoformat()}), content_type="application/json")
    bucket.blob(OUT_BLOB).upload_from_string(
        json.dumps(out, separators=(",", ":")), content_type="application/json"
    )
    logger.info("impact refreshed", window=out["window"], prs=out["totals"]["mergedPRs"],
                top=[e["login"] for e in out["top"]], refetched=len(fresh))


@scheduler_fn.on_schedule(
    schedule="every day 06:00",
    timezone=scheduler_fn.Timezone("Etc/UTC"),
    secrets=[GITHUB_TOKEN],
    memory=MemoryOption.GB_2,
    timeout_sec=1800,
    max_instances=1,
)
def refresh_impact(event: scheduler_fn.ScheduledEvent) -> None:
    refresh()
