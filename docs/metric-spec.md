## Thesis

**How the candidates scored** (each criterion out of 5: explainability / robustness / impact over activity / can it be built in 30 minutes):
- **LBEI:** 4 / 4 / 5 / 3. Its stewardship idea and discount ledger are strong. It applies two decays plus a P99 cap, which is hard to explain.
- **CPLS-A:** 4 / 4 / 4 / 4. It has a cadence dimension and a clean review-complexity factor. Its file-sum mass can be inflated by renames that touch many files.
- **CPLS-B:** 4 / 3 / 4 / 4. The churn-weighted mean criticality multiplied by log size is the easiest to explain ("how critical × how big") and resists file-count inflation. It also has the sole-gate review bonus. Ranking by percentile throws away magnitude, and its stateW values reward rubber stamps too much (0.8).

**Synthesis: the Critical-Path Impact Score (CPIS).** An impactful PostHog engineer, over the quarter, does four things:
1. Lands substantive, non-templated changes on the systems that customers' data, numbers and money depend on. These are capture and ingestion, the HogQL engine and query runners, the person store, flag evaluation, ClickHouse, batch exports and pipelines. Deep backend work weighs more than easily spun-up UI.
2. Acts as the human gate on other people's hard changes. This matters because stamphog, an AI, approves about 6.3k PRs.
3. Carries an outsized share of a critical area, which makes them load-bearing.
4. Does this steadily, and the work holds.

Raw lines, commits, PR counts and review counts never enter the score directly. Each one passes through criticality weights, log size, caps, template dampening and diminishing returns, because AI agents and scaffolding make raw throughput meaningless in this repo. Every point traces back to clickable PRs and reviews.

**Unit of work.** One merged PR = one unit (PostHog squash-merges). The window is mergedAt in [2026-07-08T00:00Z, 2026-10-07T00:00Z).

**Definitions used below:**
- **Human PR:** the author's `__typename != "Bot"`, the login does not end in `[bot]`, and the PR has no `self-driving` label.
- **Files:** only the first 100 files of each PR are used (`files.nodes`).
- **Effective churn of a file:** `ec_f = min(additions_f + 0.5·deletions_f, 400)`.
- **File kind multiplier `m_f`:**
  - 0.3 for tests. A test file is a path matching `/(^|\/)(tests?|__tests__)\//`, `/(^|\/)test_[^\/]*\.py$/`, `/_test\.(py|rs|go)$/`, `/\.(test|spec)\.(ts|tsx|js|jsx)$/`, or starting with `playwright/`.
  - 0.3 for `*.stories.tsx`.
  - 1.0 otherwise.
- **crit_f, area_f, layer_f:** taken from the longest matching prefix in the path tier table, after the products rule. Noise files are removed before anything else.
- **Conventional-commit type:** `/^(\w+)(\([^)]*\))?!?:/i` on the title gives `type` and `scope`.
- **Revert pairing:**
  - If a title matches `/^Revert\s+"(.+)"\s*$/i`, its captured text X marks the in-window human PR whose title is exactly X as **reverted**.
  - The revert PR itself is marked **isRevert**.
  - If two PRs share title X, pick the latest one merged before the revert.

## Dimensions

| key | label | exact formula | weight | why it matters |
|---|---|---|---|---|
| `delivery` | Critical-Path Delivery | **Per human PR p.** Let F be the non-noise files.<br>• `E = Σ_f m_f·ec_f`. If E < 3, or p isRevert, or p was reverted, then prScore = 0.<br>• `critPR = Σ_f crit_f·m_f·ec_f / E` (churn-weighted mean criticality).<br>• `size = log2(1 + E)`.<br>• `nAreas` = distinct area_f with crit_f ≥ 0.6 and Σ m_f·ec_f in that area ≥ 10. `spread = 1 + 0.1·min(max(nAreas−1, 0), 3)`.<br>• `testBonus = 1.1` if p has ≥ 1 test file and ≥ 1 non-test file with crit ≥ 0.5, else 1.0.<br>• `typeMult`: feat/fix/perf = 1.0, refactor = 0.9, test = 0.6, chore/ci/build/docs/style = 0.4, missing or unknown = 0.8.<br>• `prScore = min(15, critPR·size·spread·testBonus·typeMult)`.<br>• `primaryArea(p)` = the area with the largest Σ crit_f·m_f·ec_f.<br>**Template dampening.**<br>• sig = the lowercased title with the leading `type(scope)!:` removed, every `` `…` ``, `"…"` and `'…'` token removed, digits removed, and non-alphanumerics collapsed to spaces. Keep the first 5 words.<br>• Group by (author, primaryArea, sig). Order by mergedAt. The j-th PR gets ×1/j: `tScore = prScore/j`.<br>**Area diminishing returns.** For each (author, primaryArea), sort tScore descending. The k-th gets ×k^-0.4.<br>**`D1 = Σ_p tScore_p · k_p^-0.4`** | 0.40 | Measures how much hard, consequential engineering a person landed: critical × big, with size on a log scale. A 300-line change to the HogQL printer scores ≈ 8.2. The same change to a settings form scores ≈ 2.1. Fourteen "add X warehouse source" PRs count as about 3.3 PRs, not 14. |
| `review` | Review Leverage (Human Gate) | **Eligible review.** The reviewer is human (`__typename != Bot`, login does not end in `[bot]`, login not in the AI reviewer list), and the reviewer is not the PR author. The PR is a human PR.<br>**stateW per review:**<br>• CHANGES_REQUESTED = 1.0<br>• COMMENTED with len(body.trim()) ≥ 80 = 0.8<br>• APPROVED with body ≥ 40 = 0.6<br>• APPROVED with an empty or shorter body = 0.3<br>• DISMISSED = 0.2<br>• COMMENTED with a shorter body = 0.1<br>**Per (reviewer r, PR p):**<br>• `sw` = the maximum stateW of r's reviews on p.<br>• `rounds = min(3, count of r's eligible reviews on p)`; `depth = 1 + 0.1·(rounds−1)`.<br>• `cx = 0.3 + 0.7·(prScore_p/15)`, using the undampened prScore. A reverted PR uses the prScore it would have had.<br>• `sole = 1.2` if r is the only eligible human reviewer on p, else 1.0.<br>• `credit(r,p) = sw·depth·cx·sole`.<br>**Breadth.** `Dauth` = distinct authors for whom r had sw ≥ 0.3. `unblock = 0.5 + 0.5·min(1, Dauth/10)`.<br>**`D2 = unblock · Σ_p credit(r,p)`** | 0.25 | Senior engineers multiply others by catching problems in hard changes. Where an AI approves a third of PRs, the human who reads and pushes back on deep backend PRs is the safety net. Rubber stamps on trivial PRs earn about 0.09 each. A change request on a 12-point ingestion PR earns about 0.86. |
| `stewardship` | Keystone Stewardship | **Candidate areas** A have crit_A ≥ 0.7 and `n_A ≥ 5` human PRs with prScore > 0 and primaryArea = A.<br>`contrib(e,A) = Σ tScore_p` over e's PRs with primaryArea = A (after template dampening, before the k-decay) `+ 0.5·Σ credit(e,p)` over PRs p with primaryArea = A.<br>`share(e,A) = contrib(e,A) / Σ_e' contrib(e',A)`.<br>A qualifies for e if e authored ≥ 3 PRs in A or has ≥ 6 credited reviews in A.<br>**`D3 = Σ` over e's top 3 qualifying A by value of `crit_A · share(e,A) · log2(1 + n_A)`** | 0.20 | This is the bus-factor question turned into credit: which critical system would stall without this person as its main builder and gatekeeper (personhog, capture, the HogQL engine, batch exports)? Busy critical areas count more than obscure ones that one person could monopolize. |
| `sustained` | Sustained & Durable | Split the window into 13 seven-day buckets from 2026-07-08, bucketing authored PRs by mergedAt and reviews by submittedAt. Bucket 13 also takes the remaining day.<br>A week is **meaningful** if e merged ≥ 1 PR with prScore ≥ 4, or gave ≥ 2 eligible reviews with sw ≥ 0.6 on distinct PRs.<br>`substantive` = e's PRs with E ≥ 3 that are not reverts, counting reverted PRs by their would-be score. `revertRate = reverted / max(1, substantive)`.<br>**`D4 = (meaningfulWeeks/13) · (1 − min(0.5, 2·revertRate))`** | 0.15 | Impact is a property of the whole quarter, not one heroic week or one scaffolding spree, and work has to stick. The small weight means it breaks ties among strong engineers but cannot carry a weak one. |

## Path tier table

**Matching rules:**
- Apply the noise filter first.
- Then take the **longest matching prefix** (the rows are ordered most-specific first within each group).
- Layers: `ingestion`, `query-engine`, `data-pipeline`, `backend-core`, `backend-product`, `frontend-core`, `frontend-product`, `infra-ci`, `tests`, `docs`, `other`.
- Frontend criticality is set about 10–15% below the mapper suggestions. This is deliberate, to apply the user's rule that core backend weighs more than frontend.

**Products rule.** For `products/<x>/<seg>/…`:
- If `<seg>/` + next = `frontend/generated/`, the file is noise.
- If a `products/<x>/` row exists below:
  - `<seg>` ∈ {backend, dags, stats, or any other non-frontend segment} uses the row's crit and layer.
  - `<seg>` = frontend uses `min(0.6, rowCrit − 0.2)` with layer `frontend-product`.
  - `<seg>` ∈ {mcp, skills} uses 0.2 with layer `docs`.
- If no row exists:
  - backend or dags: 0.55, backend-product.
  - frontend: 0.35, frontend-product.
  - mcp or skills: 0.2, docs.
  - anything else: 0.4, other.
- The area label is "products/<x> (<seg>)".

| # | pathPrefix | area | layer | crit |
|---|---|---|---|---|
| 1 | `rust/capture-load-gen/` | Capture load generator | tests | 0.30 |
| 2 | `rust/capture-logs/` | Logs capture (Rust) | ingestion | 0.75 |
| 3 | `rust/capture/` | Event capture endpoint | ingestion | 1.00 |
| 4 | `rust/ingestion-consumer/` | Rust ingestion consumer | ingestion | 0.95 |
| 5 | `rust/kafka-deduplicator/` | Kafka deduplicator | ingestion | 0.90 |
| 6 | `rust/ingestion-control-plane/` | Ingestion control plane | ingestion | 0.85 |
| 7 | `rust/kafka-assigner/` | Kafka partition assigner | ingestion | 0.80 |
| 8 | `rust/batch-import-worker/` | Batch import worker | ingestion | 0.70 |
| 9 | `rust/personhog-` | PersonHog person store | data-pipeline | 0.95 |
| 10 | `rust/persons_migrations/` | Persons DB schema | data-pipeline | 0.60 |
| 11 | `rust/feature-flags/` | Flag evaluation service | backend-core | 0.95 |
| 12 | `rust/flags-consumer/` | Flags read-store consumer | backend-core | 0.80 |
| 13 | `rust/hypercache-server/` | HyperCache server | backend-core | 0.75 |
| 14 | `rust/cymbal/` | Error symbolication & grouping | data-pipeline | 0.85 |
| 15 | `rust/cohort-` | Behavioral cohorts streaming | data-pipeline | 0.85 |
| 16 | `rust/hogql/` | HogQL (Rust) | query-engine | 0.85 |
| 17 | `rust/property-defs-rs/` | Property definitions pipeline | data-pipeline | 0.70 |
| 18 | `rust/usage-ingestion/` | Usage/billing metering | data-pipeline | 0.70 |
| 19 | `rust/deltalite/` | Deltalite (Delta Lake) | data-pipeline | 0.70 |
| 20 | `rust/property-vals-rs/` | Property values pipeline | data-pipeline | 0.60 |
| 21 | `rust/replay-anonymizer` | Replay anonymizer | data-pipeline | 0.60 |
| 22 | `rust/embedding-worker/` | Embedding worker | data-pipeline | 0.50 |
| 23 | `rust/common/` | Rust shared libs | backend-core | 0.75 |
| 24 | `rust/` | Other Rust services | backend-core | 0.60 |
| 25 | `nodejs/src/ingestion/` | Node ingestion pipeline | ingestion | 1.00 |
| 26 | `nodejs/src/session-replay/` | Replay ingestion (Node) | ingestion | 0.85 |
| 27 | `nodejs/src/cdp/` | CDP / Hog functions runtime | data-pipeline | 0.85 |
| 28 | `nodejs/src/logs/` | Logs ingestion (Node) | ingestion | 0.70 |
| 29 | `nodejs/src/ai-observability/` | AI observability ingestion | ingestion | 0.60 |
| 30 | `nodejs/src/messaging/` | Messaging (Node) | backend-product | 0.55 |
| 31 | `nodejs/src/` | Node plugin-server core | backend-core | 0.75 |
| 32 | `nodejs/tests/` | Node tests | tests | 0.35 |
| 33 | `posthog/hogql_queries/` | Query runners | query-engine | 0.95 |
| 34 | `posthog/hogql/` | HogQL engine | query-engine | 1.00 |
| 35 | `common/hogql_parser/` | HogQL C++ parser | query-engine | 0.90 |
| 36 | `common/hogvm/` | HogVM bytecode VM | query-engine | 0.85 |
| 37 | `funnel-udf/` | Funnel UDF (Rust in CH) | query-engine | 0.85 |
| 38 | `clickhouse-udfs/` | ClickHouse UDFs | query-engine | 0.75 |
| 39 | `posthog/clickhouse/` | ClickHouse schema/client/preagg | data-pipeline | 0.90 |
| 40 | `posthog/temporal/` | Temporal workflows | data-pipeline | 0.80 |
| 41 | `posthog/models/` | Django core models | backend-core | 0.75 |
| 42 | `posthog/session_recordings/` | Replay backend (Django) | backend-product | 0.70 |
| 43 | `posthog/api/` | Django REST API | backend-core | 0.65 |
| 44 | `posthog/` | Other Django core | backend-core | 0.60 |
| 45 | `ee/clickhouse/` | EE ClickHouse queries | query-engine | 0.75 |
| 46 | `ee/billing/` | Billing integration | backend-core | 0.70 |
| 47 | `ee/hogai/` | PostHog AI agent backend | backend-product | 0.70 |
| 48 | `ee/` | Other EE backend | backend-product | 0.55 |
| 49 | `products/experiments/stats/` | Experiments stats engine | backend-product | 0.90 |
| 50 | `products/product_analytics/` | Product analytics | query-engine | 0.90 |
| 51 | `products/batch_exports/` | Batch exports | data-pipeline | 0.85 |
| 52 | `products/feature_flags/` | Feature flags product | backend-product | 0.80 |
| 53 | `products/experiments/` | Experiments | backend-product | 0.80 |
| 54 | `products/data_warehouse/` | Data warehouse | data-pipeline | 0.80 |
| 55 | `products/error_tracking/` | Error tracking | backend-product | 0.75 |
| 56 | `products/data_modeling/` | Data modeling (DAG/matviews) | data-pipeline | 0.75 |
| 57 | `products/revenue_analytics/` | Revenue analytics | query-engine | 0.65 |
| 58 | `products/ai_observability/` | LLM analytics | backend-product | 0.65 |
| 59 | `products/replay/` | Replay product package | backend-product | 0.65 |
| 60 | `products/warehouse_sources/` | Warehouse source connectors (templated) | data-pipeline | 0.60 |
| 61 | `products/cohorts/` / `products/cdp/` / `products/logs/` | Cohorts / CDP / Logs products | backend-product | 0.60 |
| 62 | `frontend/src/queries/nodes/` | Query rendering engine | frontend-core | 0.75 |
| 63 | `frontend/src/queries/schema/` | Query schema contract (hand-written TS) | frontend-core | 0.70 |
| 64 | `frontend/src/scenes/session-recordings/player/` | Replay player | frontend-product | 0.75 |
| 65 | `frontend/src/lib/monaco/` | HogQL editor tooling | frontend-core | 0.65 |
| 66 | `frontend/src/lib/charts/` | Charting engine | frontend-core | 0.60 |
| 67 | `frontend/src/scenes/insights/` | Insights UI | frontend-product | 0.65 |
| 68 | `frontend/src/lib/components/TaxonomicFilter/` | Taxonomic filter | frontend-core | 0.55 |
| 69 | `frontend/src/scenes/experiments/` / `feature-flags/` / `session-recordings/` / `web-analytics/` / `data-warehouse/` / `notebooks/` | Flagship product UIs | frontend-product | 0.55 |
| 70 | `frontend/src/scenes/settings/` / `onboarding/` / `authentication/` / `billing/` | Forms and settings UI | frontend-product | 0.25 |
| 71 | `frontend/src/scenes/` | Other scenes | frontend-product | 0.40 |
| 72 | `frontend/src/lib/lemon-ui/` / `frontend/src/lib/components/` / `frontend/src/layout/` | Generic UI, design system, app shell | frontend-core | 0.30 |
| 73 | `frontend/src/lib/` | Frontend core libs/api | frontend-core | 0.45 |
| 74 | `frontend/` | Other frontend | frontend-core | 0.35 |
| 75 | `common/ingestion/` | Shared ingestion libs | ingestion | 0.80 |
| 76 | `common/replay-shared/` | Shared replay processing | data-pipeline | 0.70 |
| 77 | `common/` | Other common tooling | infra-ci | 0.35 |
| 78 | `livestream/` | Livestream (Go) | backend-core | 0.60 |
| 79 | `proto/` | Protobuf contracts | backend-core | 0.50 |
| 80 | `services/` | Peripheral services (incl. mcp, hogql-language-service) | backend-product | 0.50 |
| 81 | `packages/` / `cli/` | Monorepo packages, CLI | other | 0.40 |
| 82 | `terraform/` | Terraform | infra-ci | 0.45 |
| 83 | `.github/` / `docker/` | CI/CD, docker | infra-ci | 0.35 |
| 84 | `playwright/` / `bin/` / `devenv/` / `tools/` | E2E tests, scripts, dev tooling | infra-ci | 0.25 |
| 85 | `docs/` | Docs | docs | 0.15 |
| 86 | *(default)* | Unmapped | other | 0.30 |

**Implementation notes on the table:**
- Rows that use `/` list several sibling prefixes that share the same tier. Implement each prefix as its own row with the same values. The table has about 60 distinct tier groups.
- `products/web_analytics/` is deliberately omitted because the two maps disagreed on whether it exists. Web analytics backend logic is covered by `posthog/hogql_queries/` at 0.95.

## Noise / exclusions

**Noise files.** These are dropped before scoring and counted in the ledger as "noise churn". Use glob semantics, where `**` means any depth:
- **Lockfiles:** `**/pnpm-lock.yaml`, `**/uv.lock`, `**/Cargo.lock`, `**/package-lock.json`, `**/yarn.lock`, `**/*.lock`
- **Migrations:** `**/migrations/**`, `**/max_migration.txt`, `rust/.sqlx/**`
- **Snapshots:** `**/__snapshots__/**`, `**/*.ambr`, `**/*.snap`, `**/*.hoge`, `**/*.stdout`
- **Generated code:** `**/generated/**` (includes `frontend/src/generated/**`, `products/*/frontend/generated/**`, `nodejs/src/common/generated/**`, `posthog/usage_ingestion/generated/**`), `**/*.generated.*`, `**/*_pb.ts`, `**/*_pb2.py`, `**/generated_configs/**`
- **Query schema outputs:** `frontend/src/queries/schema.json`, `frontend/src/queries/latest-versions.json`, `posthog/schema.py`, `posthog/schema_enums.py`, `posthog/schema_discriminators.py`
- **ANTLR outputs:** `posthog/hogql/grammar/*Lexer*.py`, `*Parser*.py`, `*Visitor*.py`, and generated grammar files under `common/hogql_parser/` that match `*Lexer*`, `*Parser*` or `*Visitor*` (excluding `parser.cpp`, the hand-written converter)
- **Assets:** `**/*.png`, `**/*.svg`, `**/*.jpg`, `**/*.gif`, `**/*.woff*`, `frontend/public/**`
- **Fixtures and evals:** `frontend/src/mocks/**`, `**/fixtures/**`, `**/test_data/**`, `**/eval/**`, `**/evals/**`, `products/review_hog/eval/**`
- **Mobile replay schema JSON:** `frontend/src/scenes/session-recordings/mobile-replay/schema/**/*.json`
- **Vendored desktop packages:** `products/desktop/packages/**`
- **Agent configs, skills and docs:** `.agents/**`, `.claude/**`, `.cursor/**`, `.codex/**`, `**/skills/**`, `**/*.md`, `**/*.mdx`, `CHANGELOG.md`
- **Other:** `.test_quarantine.json`

**Author exclusions** (the PR is dropped entirely):
- `author.__typename == "Bot"`, or the login matches `/\[bot\]$/i`. This covers posthog[bot], posthog-js-upgrader[bot], scheduled-actions-posthog[bot], dependabot, renovate and copilot-swe-agent.
- The author is null (a deleted account).
- The PR has the label `self-driving`.

**Reviewer exclusions** (the review is dropped):
- `__typename == "Bot"`.
- The login matches `/\[bot\]$/i`.
- The login (lowercased) is in {`stamphog`, `coderabbitai`, `greptile-apps`, `copilot-pull-request-reviewer`, `parameterai`, `veria-ai`, `posthog`}.
- The reviewer equals the PR author (self-review).
- The PR is not a human PR.

**PR-level scoring rules:**
- Revert PRs get 0.
- Reverted originals get 0 in delivery and stewardship, but count in revertRate.
- PRs with E < 3 after noise removal get 0 (pure lockfile, snapshot, codegen or migration PRs).
- A PR gated only by stamphog still credits its author, but credits no reviewer.

**Never used:** commits.totalCount (squash merges), comments.totalCount (chatter is not impact), raw additions/deletions totals, lead time, closingIssuesReferences (linked inconsistently; shown as evidence text only).

## Normalization & final score

1. **Eligibility.** A human login with ≥ 5 merged human PRs with prScore > 0, or ≥ 15 eligible reviews, in the window.
2. **Normalizing D1, D2 and D3.** `x' = log1p(x) / log1p(max over eligible of x)`, giving a value in [0, 1].
   - Normalize to the max, not to P95 or P99. With about 300 eligible engineers, a P95 anchor would clip roughly 15 people to 1.0 and erase the resolution among the top 5, which is exactly where we need it.
   - The log already compresses outliers, so one extreme value cannot flatten everyone else.
3. **D4** is already in [0, 1].
4. **Composite.** `CPIS = 100 · (0.40·D1' + 0.25·D2' + 0.20·D3' + 0.15·D4')`. Ties are broken by raw D1, then raw D2.
5. **Percentiles.** Show each dimension's percentile rank among eligible engineers for display only.
6. **Ties at the cutoff.** If CPIS(#5) − CPIS(#6) < 1.0, label #5 and #6 as "statistical tie" and show both.
7. **Robustness.** Rerun the top 5 under 8 variants:
   - (a) base
   - (b) equal weights 0.25 each
   - (c)–(f) drop one dimension at a time, renormalizing the rest proportionally
   - (g) crit flattened to `0.5 + 0.5·crit`
   - (h) area-decay exponent 0.6 instead of 0.4

   Badge **Stable** if the engineer stays in the top 5 in ≥ 6 of 8 variants, **Weight-sensitive** otherwise. Also report how many of the base top 5 stay in the top 7 under every variant.
8. **Naive baselines** for contrast, computed over human PRs: rank by raw merged-PR count, by raw additions + deletions, and by raw eligible-review count.

## Per-engineer evidence to display

For each top-5 engineer (and on hover in the full leaderboard):
1. **Verdict.** One sentence generated from the two largest weighted contributions. Example: "Carried 41% of Rust ingestion-consumer work (12 PRs) and was the only human reviewer on 9 deep query-engine PRs for 7 teammates."
2. **Score breakdown.** The composite CPIS, a 4-segment stacked bar (weight × normalized value), the raw value and percentile per dimension, and the Stable or Weight-sensitive badge.
3. **Top 5 PRs by prScore.** Each shows a GitHub link, title, mergedAt, primaryArea, layer and crit, and E. It also shows the factor breakdown `critPR × size × spread × test × type = prScore`, the files counted vs. dropped as noise, and `changedFiles` (with a truncation flag when > 100).
4. **Layer mix.** A bar of Σ prScore by layer (ingestion, query-engine, data-pipeline, backend-core, backend-product, frontend-core, frontend-product, infra and tests).
5. **Stewardship areas.** For each qualifying area: area, crit, n_A, the engineer's share %, authored PRs and reviews in the area, and the top 3 co-contributors with their shares. Add a "silo" flag when share > 60% and the next contributor is below 15%.
6. **Review evidence.** Counts by state bucket (change requests, substantive comments, substantive approvals, rubber stamps), distinct authors unblocked, and sole-gate count. Show 2–3 excerpts from the highest-credit reviews: PR link, reviewed prScore, and the first 200 characters of the body.
7. **Cadence strip.** 13 cells, one per week, marked meaningful or not.
8. **Adjustments ledger.**
   - Template-dampened PRs, with their sigs. Example: "feat warehouse add source ×14 → counted as 3.3".
   - Area-decay loss.
   - Noise churn removed (lines, and the top noise patterns hit).
   - Reverted PRs, with links.
   - Revert rate.
   - Share of the engineer's PRs whose only approval was stamphog.
9. **Naive vs. CPIS.** Rank by PR count, by lines changed and by review count, next to the CPIS rank.
10. **Global methodology panel.** The full path tier table with rationale, all formulas and the noise list, plus a "why not LOC/commits" comparison of the naive top 5 against the CPIS top 5.

## Known limitations (honest)

- **Missing files.** Only the first 100 files per PR are visible, so huge PRs are under-measured. The changedFiles count is displayed to show this.
- **Missing inline review comments.** Review `body` excludes inline review comments, which are not in our data. A reviewer who leaves 20 inline comments with an empty summary body is scored as a short COMMENTED (0.1) or APPROVED (0.3). This is the largest known bias against thorough reviewers. Fetching `reviews.comments.totalCount` would fix it if the data scope allowed.
- **AI assistance is not separated** from human effort. Agent-written code under a human account is only partly handled, through template dampening, the log size scale, caps and area decay.
- **Splitting is still rewarded.** log2 size is concave, so many small distinct PRs can outscore one large PR. Area decay and template dampening only blunt this.
- **The criticality tiers are judgment calls.** They come from repo structure and the PR sample, not from incident or runtime data. They are published so leaders can contest them, and variant (g) tests sensitivity to them.
- **Revert detection is title-based** and window-bound. Reverts with custom titles, partial reverts, fix-forwards and reverts after 2026-10-06 are missed. There is no line-survival or blame data.
- **Stewardship can reward silos.** The silo flag mitigates this but does not resolve it. Leaders must interpret it.
- **No data outside merged PRs.** Design docs, incident response, mentoring, unmerged or abandoned work, issue triage and on-call are invisible. People on leave lose D4.
- **Window edge effects.** PRs opened before 2026-07-08 count when merged in the window. Reviews count by the window of the PR they belong to (mergedAt), and only the D4 bucketing uses submittedAt.
- **Conventional-commit types are self-reported.** A mislabeled type moves a PR by at most 2.5× (0.4 vs. 1.0).
- **products/web_analytics/** was not verified and is not tiered. If it exists, it falls through to the products default rule.