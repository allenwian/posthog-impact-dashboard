# Who carries PostHog's critical path?

An interactive dashboard naming the **top 5 most impactful engineers** in [`PostHog/posthog`](https://github.com/PostHog/posthog) over the last 91 days, with the evidence behind each pick.

**Live:** https://weave-impact-ia26.web.app

## Methodology (short version)

Counting PRs, lines or reviews measures tooling, not impact. That is especially true here: AI agents let one engineer merge 2,200+ PRs in a quarter, and AI reviewers (stamphog, CodeRabbit, Greptile and others) left nearly 4 of every 5 reviews. So every count first goes through a model of *what the work touched* and *whether a human judged it*.

**Critical-Path Impact Score (CPIS)** = weighted blend of four dimensions. Each is log-scaled against the top engineer, 0–100.

| Dimension | Weight | What it measures |
|---|---|---|
| Critical-Path Delivery | 40% | Per PR: `criticality × log2(1 + effective churn) × cross-area spread × test bonus × change type`, capped at 15. Criticality comes from a published 100-row path map: capture, HogQL and ingestion = 1.0; generic UI = 0.3; tests 0.3×. Templated repeats (same file skeleton with the entity name swapped) are dampened 1/j. The k-th PR in the same area is × k^-0.4. |
| Review Leverage | 25% | Being the **human** gate: change requests > substantive comments > approvals with feedback > rubber stamps, × complexity of the reviewed PR, × 1.2 if sole human reviewer, × breadth of teammates unblocked. AI reviewers and self-reviews are excluded. |
| Keystone Stewardship | 20% | Share of a critical, busy area's work (authored + ½ review credit): the bus-factor question turned into credit. A silo flag warns when ownership is too concentrated. |
| Sustained & Durable | 15% | Weeks out of 13 with meaningful work, × a penalty for reverted PRs. |

**Removed as noise:** lockfiles, migrations, snapshots, generated code (schema.json, ANTLR, protobuf), assets, fixtures and evals, agent and skill markdown, bot authors and the `self-driving` label.

**Validation shown on the page:**
- Naive leaderboards, side by side with each person's CPIS rank.
- 7 alternative weightings / criticality / decay assumptions, with a Stable or Weight-sensitive badge.
- A tie flag at the #5 cutoff.
- A per-engineer adjustment ledger and PR-level factor breakdowns that link to GitHub.

The full spec is in [`docs/metric-spec.md`](docs/metric-spec.md). It was designed by a multi-agent workflow: architecture mapping, three independent designs, then a judge/synthesis step. Its honest limitations section is worth reading. The biggest gaps are that inline review comments aren't fetched, and that design work, incidents and mentoring are invisible in PR data.

## Architecture

```
GitHub GraphQL ──► functions-py: refresh_impact (Cloud Scheduler, daily 06:00 UTC)
                    • rolling raw PR store: gs://<bucket>/raw/prs.jsonl.gz
                    • re-fetches last 7 days (new merges + late reviews), drops PRs older than the window
                    • scores with pipeline/score.py ──► gs://<bucket>/impact/latest.json
                                                        │
React (Vite) on Firebase Hosting ──► /api/impact ──► functions: impact (Node; 10-min memory cache,
   falls back to the bundled /impact.json            CDN s-maxage=1h; bundled snapshot fallback)
```

Page loads never touch GitHub. The payload is a ~57 KB JSON served from CDN or memory, so loading is effectively instant, and the data is at most about a day stale.

- `pipeline/fetch_prs.py`: day-sliced GraphQL search, which stays under the 1000-result search cap.
- `pipeline/score.py`: the scoring engine, shared by the CLI and the scheduled function.
- `functions-py/main.py`: the scheduled refresh. `pipeline/*.py` is copied in at predeploy.
- `functions/index.js`: the HTTP API.
- `web/`: the dashboard.

## Run locally

```bash
python3 -I pipeline/fetch_prs.py --end 2026-10-06      # ~5 min, writes pipeline/data/prs.jsonl
python3 -I pipeline/score.py --end 2026-10-06          # ~20 s, writes impact.json (+ bundled copies)
cd web && npm i && npm run dev
```

## Deploy

```bash
# one-time: the project must be on the Blaze plan (Cloud Functions + Scheduler)
firebase functions:secrets:set GITHUB_TOKEN   # fine-grained PAT, public-repo read only
cd web && npm run build && cd ..
firebase deploy                                # hosting + both function codebases
```

The first scheduled run backfills the full window; after that each run is incremental (~1–2 min). To trigger one immediately, use `gcloud scheduler jobs run firebase-schedule-refresh_impact-us-central1 --location us-central1`.
