Brief: impact frameworks and PostHog facts for 2026-07-08..2026-10-06

**1) Frameworks, turned into signals we can compute from PR data**

- **SPACE (Forsgren et al.) and DORA.** Both treat activity as only one part of output, next to performance, collaboration and flow. DORA's lead time works per PR as `mergedAt − createdAt`. Pitfall: lead time measures how fast the process moves, not the person's skill, so use it only as a small factor.
- **Weave's own approach.** Weave estimates "Weave Hours": how long an experienced engineer would need to make a change. They built it to resist gaming, and they also separate AI-assisted work from human work and score code reviews. Our version would be an expert-effort or complexity score per PR, built from files touched, how many subsystems it crosses, test files added, and how deep the paths are, rather than LOC. Pitfall: generated, scaffolded or vendored files inflate the size of a PR.
- **Leverage through review.** Count reviews given on *other people's* PRs. Weight CHANGES_REQUESTED and reviews with a substantive `body` higher, and weight by how complex the reviewed PR was. Pitfall: rubber-stamp approvals, and bot reviewers (listed below) must be removed.
- **Unblocking others.** Count distinct authors a person reviewed for, and how quickly they reviewed (`submittedAt − createdAt`).
- **Spread of knowledge and bus factor.** For each product or area, measure how concentrated its authors are. Someone who is one of only 1–2 contributors to a critical path is high-leverage. Pitfall: heavy concentration can also mean a silo.
- **Breadth across teams.** Count the distinct `products/*` folders, or owning teams from `product.yaml`, that a person touched or reviewed.
- **Weighting by criticality (the user's idea).** Weight each path by tier. Ingestion (`rust/`, `nodejs/`, `products/ingestion`), the query engine (`posthog/hogql/**`, `posthog/clickhouse/**`), persons, CDP, feature flags and billing are high. Generic frontend (`frontend/src/lib/components`, storybook) is low. CODEOWNERS already marks the true critical paths, which supports this weighting.
- **Durability.** We can't compute line survival without blame data. A substitute: penalize PRs whose title starts with `revert` or that are reverted later (match the title). We can also give credit for `fix(...)` PRs that land in areas other people wrote.
- **Other quality signals.** Test files changed alongside source, PRs that close issues (`closingIssuesReferences`), and type mix from conventional-commit prefixes (feat/fix/perf/refactor vs chore).

**2) Facts about PostHog in this window**

- **Volume.** 16,374 PRs were merged in the window, far more than expected. The search API returns at most 1,000 results per query, so fetch the GraphQL search in slices of a day or a few days (`merged:2026-07-08..2026-07-09`).
- **Bot authors to exclude:**
  - `posthog[bot]` (app/posthog): 1,434 PRs, including 199 labeled `self-driving` from branches `posthog-self-driving/*`
  - `posthog-js-upgrader[bot]`: 191
  - `scheduled-actions-posthog[bot]`: 128
  - dependabot, renovate and copilot-swe-agent each authored 0 merged PRs here.
  - Filter generally on `__typename == "Bot"` or a login ending in `[bot]`.
- **Bot reviewers to exclude.** These are the bigger risk:
  - `stamphog` is an AI approval agent. 6,355 merged PRs carry the `stamphog` label, so many PRs have no human reviewer at all.
  - Also exclude `coderabbitai`, `greptile-apps`, `copilot-pull-request-reviewer`, `parameterai`, `veria-ai`, and `posthog` acting as a reviewer.
  - Self-reviews: authors comment on their own PRs (for example Gilbert09). Drop any review where reviewer == author.
- **AI-authored work under human accounts.** This is widespread. Branch prefixes `codex/*` and `posthog/*` (agent sessions), plus `AI_POLICY.md` and an "Agent context" section in the PR template, show that most human PRs are written with an agent. Conclusion: raw throughput is badly inflated. Example: Gilbert09 has about 275 of the latest 1,000 merged PRs, many of them templated "scaffold N warehouse sources" or "add X tables" connector PRs. Dampen this with diminishing returns per area and a penalty for repetitive or templated work (similar titles, same directory pattern).
- **Labels.** `stamphog` (approved by AI), `skip-agent-review`, `skip-inkeep-docs`, `self-driving`, `run-ci-frontend`. Titles follow Conventional Commits, `type(scope): ...`, so the scope gives the area.
- **Ownership.** CODEOWNERS is kept small on purpose ("anti-posthog-values"). It covers only `posthog/hogql/**` (@hogql), ClickHouse migrations, `rust/persons_migrations` (ingestion), and auth/CI (security). Real ownership comes from `owners.yaml` plus `products/<name>/product.yaml` (`owners: [team-...]`). There are about 100 `products/*` folders.
- **Merge method.** The repo API returns null for the merge settings because we lack admin access. PR titles map one-to-one to master commits, and PostHog has historically squash-merged, so treat one PR as one unit. Commit counts inside a PR don't carry meaning.
- **Notable high-signal backend contributors seen in the sample.** pl (ingestion consumer, Rust perf), rorylshanks (ClickHouse), jose-sequeira (ingestion), haacked (deletes), georgemunyoro (trends/HogQL). This supports weighting by path tier over counting PRs.

Sources: [Weave YC launch](https://www.ycombinator.com/launches/Mjm-weave-ai-to-quantify-engineering-work), [Weave overview](https://www.promptloop.com/directory/what-does-workweave-dev-do), [Larridin on AI impact measurement](https://larridin.com/blog/measuring-ais-impact-on-engineering-output). Repo facts come from `gh api` and `gh search prs` against PostHog/posthog, run on 2026-10-06.