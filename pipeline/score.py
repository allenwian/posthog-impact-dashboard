"""Critical-Path Impact Score (CPIS) for PostHog/posthog engineers.

Implements docs/metric-spec.md. Input: data/prs.jsonl (fetch_prs.py).
Output: data/impact.json, consumed by the dashboard and the `impact` Cloud Function.

Run: python3 -I score.py
"""
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
WEEKS = 13
WINDOW_DAYS = WEEKS * 7  # 91 days: "at least the last 90 days", split into whole weeks
WINDOW_END = WINDOW_START = None  # set by set_window()


def set_window(end_day):
    """Analyze the WINDOW_DAYS days ending on (and including) end_day, a UTC date."""
    global WINDOW_START, WINDOW_END
    WINDOW_END = datetime(end_day.year, end_day.month, end_day.day, tzinfo=timezone.utc) + timedelta(days=1)
    WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS)


set_window(datetime.now(timezone.utc).date() - timedelta(days=1))

BASE = {
    "weights": {"delivery": 0.40, "review": 0.25, "stewardship": 0.20, "sustained": 0.15},
    "crit_transform": None,  # e.g. lambda c: 0.5 + 0.5 * c for the flattened-criticality variant
    "area_decay": 0.4,
}

# ---------------------------------------------------------------- path tiers
# (prefix, area, layer, criticality). Longest matching prefix wins.
TIERS = [
    ("rust/capture-load-gen/", "Capture load generator", "tests", 0.30),
    ("rust/capture-logs/", "Logs capture (Rust)", "ingestion", 0.75),
    ("rust/capture/", "Event capture endpoint", "ingestion", 1.00),
    ("rust/ingestion-consumer/", "Rust ingestion consumer", "ingestion", 0.95),
    ("rust/kafka-deduplicator/", "Kafka deduplicator", "ingestion", 0.90),
    ("rust/ingestion-control-plane/", "Ingestion control plane", "ingestion", 0.85),
    ("rust/kafka-assigner/", "Kafka partition assigner", "ingestion", 0.80),
    ("rust/batch-import-worker/", "Batch import worker", "ingestion", 0.70),
    ("rust/personhog-", "PersonHog person store", "data-pipeline", 0.95),
    ("rust/persons_migrations/", "Persons DB schema", "data-pipeline", 0.60),
    ("rust/feature-flags/", "Flag evaluation service", "backend-core", 0.95),
    ("rust/flags-consumer/", "Flags read-store consumer", "backend-core", 0.80),
    ("rust/hypercache-server/", "HyperCache server", "backend-core", 0.75),
    ("rust/cymbal/", "Error symbolication & grouping", "data-pipeline", 0.85),
    ("rust/cohort-", "Behavioral cohorts streaming", "data-pipeline", 0.85),
    ("rust/hogql/", "HogQL (Rust)", "query-engine", 0.85),
    ("rust/property-defs-rs/", "Property definitions pipeline", "data-pipeline", 0.70),
    ("rust/usage-ingestion/", "Usage/billing metering", "data-pipeline", 0.70),
    ("rust/deltalite/", "Deltalite (Delta Lake)", "data-pipeline", 0.70),
    ("rust/property-vals-rs/", "Property values pipeline", "data-pipeline", 0.60),
    ("rust/replay-anonymizer", "Replay anonymizer", "data-pipeline", 0.60),
    ("rust/embedding-worker/", "Embedding worker", "data-pipeline", 0.50),
    ("rust/common/", "Rust shared libs", "backend-core", 0.75),
    ("rust/", "Other Rust services", "backend-core", 0.60),
    ("nodejs/src/ingestion/", "Node ingestion pipeline", "ingestion", 1.00),
    ("nodejs/src/session-replay/", "Replay ingestion (Node)", "ingestion", 0.85),
    ("nodejs/src/cdp/", "CDP / Hog functions runtime", "data-pipeline", 0.85),
    ("nodejs/src/logs/", "Logs ingestion (Node)", "ingestion", 0.70),
    ("nodejs/src/ai-observability/", "AI observability ingestion", "ingestion", 0.60),
    ("nodejs/src/messaging/", "Messaging (Node)", "backend-product", 0.55),
    ("nodejs/src/", "Node plugin-server core", "backend-core", 0.75),
    ("nodejs/tests/", "Node tests", "tests", 0.35),
    ("posthog/hogql_queries/", "Query runners", "query-engine", 0.95),
    ("posthog/hogql/", "HogQL engine", "query-engine", 1.00),
    ("common/hogql_parser/", "HogQL C++ parser", "query-engine", 0.90),
    ("common/hogvm/", "HogVM bytecode VM", "query-engine", 0.85),
    ("funnel-udf/", "Funnel UDF (Rust in CH)", "query-engine", 0.85),
    ("clickhouse-udfs/", "ClickHouse UDFs", "query-engine", 0.75),
    ("posthog/clickhouse/", "ClickHouse schema & client", "data-pipeline", 0.90),
    ("posthog/temporal/", "Temporal workflows", "data-pipeline", 0.80),
    ("posthog/models/", "Django core models", "backend-core", 0.75),
    ("posthog/session_recordings/", "Replay backend (Django)", "backend-product", 0.70),
    ("posthog/api/", "Django REST API", "backend-core", 0.65),
    ("posthog/", "Other Django core", "backend-core", 0.60),
    ("ee/clickhouse/", "EE ClickHouse queries", "query-engine", 0.75),
    ("ee/billing/", "Billing integration", "backend-core", 0.70),
    ("ee/hogai/", "PostHog AI agent backend", "backend-product", 0.70),
    ("ee/", "Other EE backend", "backend-product", 0.55),
    ("products/experiments/stats/", "Experiments stats engine", "backend-product", 0.90),
    ("products/product_analytics/", "Product analytics", "query-engine", 0.90),
    ("products/batch_exports/", "Batch exports", "data-pipeline", 0.85),
    ("products/feature_flags/", "Feature flags", "backend-product", 0.80),
    ("products/experiments/", "Experiments", "backend-product", 0.80),
    ("products/data_warehouse/", "Data warehouse", "data-pipeline", 0.80),
    ("products/error_tracking/", "Error tracking", "backend-product", 0.75),
    ("products/data_modeling/", "Data modeling", "data-pipeline", 0.75),
    ("products/revenue_analytics/", "Revenue analytics", "query-engine", 0.65),
    ("products/ai_observability/", "LLM analytics", "backend-product", 0.65),
    ("products/replay/", "Replay product", "backend-product", 0.65),
    ("products/warehouse_sources/", "Warehouse source connectors", "data-pipeline", 0.60),
    ("products/cohorts/", "Cohorts", "backend-product", 0.60),
    ("products/cdp/", "CDP product", "backend-product", 0.60),
    ("products/logs/", "Logs product", "backend-product", 0.60),
    ("frontend/src/queries/nodes/", "Query rendering engine (FE)", "frontend-core", 0.75),
    ("frontend/src/queries/schema/", "Query schema contract", "frontend-core", 0.70),
    ("frontend/src/scenes/session-recordings/player/", "Replay player (FE)", "frontend-product", 0.75),
    ("frontend/src/lib/monaco/", "HogQL editor tooling", "frontend-core", 0.65),
    ("frontend/src/lib/charts/", "Charting engine", "frontend-core", 0.60),
    ("frontend/src/scenes/insights/", "Insights UI", "frontend-product", 0.65),
    ("frontend/src/lib/components/TaxonomicFilter/", "Taxonomic filter", "frontend-core", 0.55),
    *[
        (f"frontend/src/scenes/{s}/", "Flagship product UIs", "frontend-product", 0.55)
        for s in ["experiments", "feature-flags", "session-recordings", "web-analytics", "data-warehouse", "notebooks"]
    ],
    *[
        (f"frontend/src/scenes/{s}/", "Forms & settings UI", "frontend-product", 0.25)
        for s in ["settings", "onboarding", "authentication", "billing"]
    ],
    ("frontend/src/scenes/", "Other product UIs", "frontend-product", 0.40),
    ("frontend/src/lib/lemon-ui/", "Generic UI & app shell", "frontend-core", 0.30),
    ("frontend/src/lib/components/", "Generic UI & app shell", "frontend-core", 0.30),
    ("frontend/src/layout/", "Generic UI & app shell", "frontend-core", 0.30),
    ("frontend/src/lib/", "Frontend core libs", "frontend-core", 0.45),
    ("frontend/", "Other frontend", "frontend-core", 0.35),
    ("common/ingestion/", "Shared ingestion libs", "ingestion", 0.80),
    ("common/replay-shared/", "Shared replay processing", "data-pipeline", 0.70),
    ("common/", "Other common tooling", "infra-ci", 0.35),
    ("livestream/", "Livestream (Go)", "backend-core", 0.60),
    ("proto/", "Protobuf contracts", "backend-core", 0.50),
    ("services/", "Peripheral services", "backend-product", 0.50),
    ("packages/", "Monorepo packages & CLI", "other", 0.40),
    ("cli/", "Monorepo packages & CLI", "other", 0.40),
    ("terraform/", "Terraform", "infra-ci", 0.45),
    (".github/", "CI/CD & Docker", "infra-ci", 0.35),
    ("docker/", "CI/CD & Docker", "infra-ci", 0.35),
    *[(f"{p}/", "E2E tests & dev tooling", "infra-ci", 0.25) for p in ["playwright", "bin", "devenv", "tools"]],
    ("docs/", "Docs", "docs", 0.15),
]
TIERS.sort(key=lambda t: -len(t[0]))
TIER_BY_PREFIX = {t[0]: t for t in TIERS}
DEFAULT_TIER = ("", "Unmapped", "other", 0.30)
LAYERS = ["ingestion", "query-engine", "data-pipeline", "backend-core", "backend-product",
          "frontend-core", "frontend-product", "infra-ci", "tests", "docs", "other"]


def classify(path):
    """Return (area, layer, crit) for a non-noise path."""
    parts = path.split("/")
    if parts[0] == "products" and len(parts) >= 3:
        product, seg = parts[1], parts[2]
        row = None
        # Allow deeper product rows (experiments/stats) to win first.
        for prefix, *rest in TIERS:
            if prefix.startswith("products/") and path.startswith(prefix):
                row = (prefix, *rest)
                break
        label = row[1] if row else product.replace("_", " ").capitalize()
        if seg == "frontend":
            crit = min(0.6, row[3] - 0.2) if row else 0.35
            return f"{label} (frontend)", "frontend-product", crit
        if seg in ("mcp", "skills"):
            return f"{label} ({seg})", "docs", 0.2
        if row:
            return row[1], row[2], row[3]
        if seg in ("backend", "dags"):
            return f"{label} ({seg})", "backend-product", 0.55
        return f"{label} ({seg})", "other", 0.4
    for prefix, area, layer, crit in TIERS:
        if path.startswith(prefix):
            return area, layer, crit
    return DEFAULT_TIER[1:]


# ---------------------------------------------------------------- noise
NOISE_RE = re.compile(
    "|".join(
        [
            r"(^|/)(pnpm-lock\.yaml|uv\.lock|Cargo\.lock|package-lock\.json|yarn\.lock)$", r"\.lock$",
            r"(^|/)migrations/", r"(^|/)max_migration\.txt$", r"^rust/\.sqlx/",
            r"(^|/)__snapshots__/", r"\.(ambr|snap|hoge|stdout)$",
            r"(^|/)generated/", r"\.generated\.", r"_pb\.ts$", r"_pb2\.py$", r"(^|/)generated_configs/",
            r"^frontend/src/queries/(schema|latest-versions)\.json$",
            r"^posthog/(schema|schema_enums|schema_discriminators)\.py$",
            r"^posthog/hogql/grammar/.*(Lexer|Parser|Visitor).*\.py$",
            r"^common/hogql_parser/(?!parser\.cpp$).*(Lexer|Parser|Visitor)",
            r"\.(png|svg|jpe?g|gif|woff2?|ico|webp)$", r"^frontend/public/",
            r"^frontend/src/mocks/", r"(^|/)(fixtures|test_data|evals?)/",
            r"^frontend/src/scenes/session-recordings/mobile-replay/schema/.*\.json$",
            r"^products/desktop/packages/",
            r"^\.(agents|claude|cursor|codex)/", r"(^|/)skills/", r"\.mdx?$",
            r"(^|/)\.test_quarantine\.json$", r"(^|/)snapshots\.yml$",
        ]
    )
)
TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__)/|(^|/)test_[^/]*\.py$|_test\.(py|rs|go)$|\.(test|spec)\.(ts|tsx|js|jsx)$|^playwright/"
)
STORY_RE = re.compile(r"\.stories\.tsx$")
AI_REVIEWERS = {
    "stamphog", "coderabbitai", "greptile-apps", "copilot-pull-request-reviewer", "parameterai",
    "veria-ai", "posthog", "chatgpt-codex-connector", "reviewhog", "graphite-app", "cursor",
    "github-actions", "posthog-security-review-bot", "exe-dev-github-integration", "posthog-local-dev",
}
TYPE_RE = re.compile(r"^(\w+)(\([^)]*\))?!?:\s*", re.I)
REVERT_RE = re.compile(r'^Revert\s+"(.+)"\s*$', re.I)
TYPE_MULT = {"feat": 1.0, "fix": 1.0, "perf": 1.0, "refactor": 0.9, "test": 0.6,
             "chore": 0.4, "ci": 0.4, "build": 0.4, "docs": 0.4, "style": 0.4}


def is_bot(actor):
    if not actor:
        return True
    login = actor.get("login") or ""
    return actor.get("__typename") == "Bot" or login.lower().endswith("[bot]")


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def title_sig(title):
    t = TYPE_RE.sub("", title.lower())
    t = re.sub(r"`[^`]*`|\"[^\"]*\"|'[^']*'", " ", t)
    t = re.sub(r"\d+", " ", t)
    t = re.sub(r"[^a-z]+", " ", t).split()
    return " ".join(t[:5])


def template_sig(pr, files):
    """Template signature, or None.

    The "slot" is the directory named after the PR's subject: a path segment whose words all appear in
    the title, e.g. `sources/cisco_duo/` in "implement cisco_duo source", abstracted to `sources/*`.
    Two PRs are copies of one template if they share the slot and the title minus the subject words:
    "implement cisco_duo source" ~ "implement workday source", even though each connector has its own
    file names. Two different `fix(bigquery): …` bugs keep different titles, so they stay distinct.
    """
    words = set(re.findall(r"[a-z0-9]+", pr["title"].lower()))
    slots, entity = set(), set()
    for path in files:
        segs = path.split("/")
        for i, seg in enumerate(segs[:-1]):
            toks = [t for t in re.split(r"[^a-z0-9]+", seg.lower()) if t]
            if len(seg) >= 3 and toks and all(t in words for t in toks) and seg.lower() not in GENERIC_SEGS:
                slots.add("/".join(segs[:i] + ["*"]))
                entity.update(toks)
                break
    if not slots:
        return None
    title = " ".join(w for w in title_sig(pr["title"]).split() if w not in entity)
    return f"slot:{min(slots)}:{title}"


GENERIC_SEGS = {"posthog", "frontend", "backend", "src", "products", "rust", "nodejs", "api", "sources", "lib",
                "scenes", "components", "temporal", "data", "imports", "hogql", "queries", "tests", "test", "common"}
GENERIC_SEGS |= {seg.lower() for prefix, *_ in TIERS for seg in prefix.strip("/").split("/")}
GENERIC_SEGS |= {"ingestion", "persons", "cdp", "session-replay", "logs", "messaging", "frontend", "dags"}


def review_weight(state, body):
    n = len((body or "").strip())
    if state == "CHANGES_REQUESTED":
        return 1.0
    if state == "COMMENTED":
        return 0.8 if n >= 80 else 0.1
    if state == "APPROVED":
        return 0.6 if n >= 40 else 0.3
    if state == "DISMISSED":
        return 0.2
    return 0.0


def review_bucket(state, body):
    n = len((body or "").strip())
    if state == "CHANGES_REQUESTED":
        return "changesRequested"
    if state == "COMMENTED":
        return "substantiveComments" if n >= 80 else "lightComments"
    if state == "APPROVED":
        return "substantiveApprovals" if n >= 40 else "rubberStamps"
    return "other"


# ---------------------------------------------------------------- per-PR scoring
def score_pr(pr, crit_transform):
    """Return a dict with prScore and its factor breakdown (independent of author context)."""
    files, noise_lines, counted, base_crits = [], 0, 0, {}
    for f in pr["files"]["nodes"]:
        path = f["path"]
        if NOISE_RE.search(path):
            noise_lines += f["additions"] + f["deletions"]
            continue
        area, layer, base_crit = classify(path)
        crit = crit_transform(base_crit) if crit_transform else base_crit
        is_test = bool(TEST_RE.search(path))
        m = 0.3 if is_test or STORY_RE.search(path) else 1.0
        ec = min(f["additions"] + 0.5 * f["deletions"], 400)
        files.append((path, area, layer, crit, m, ec, is_test))
        base_crits[path] = base_crit
        counted += 1
    E = sum(m * ec for *_, m, ec, _t in files)
    m_type = TYPE_RE.match(pr["title"])
    ptype = m_type.group(1).lower() if m_type else None
    out = {"E": round(E, 1), "noiseLines": noise_lines, "filesCounted": counted,
           "filesDropped": len(pr["files"]["nodes"]) - counted, "type": ptype}
    if E < 3:
        out.update(prScore=0.0, critPR=0, size=0, spread=1, testBonus=1, typeMult=TYPE_MULT.get(ptype, 0.8),
                   primaryArea=None, layer=None, areaMass={}, layerMass={})
        return out
    crit_pr = sum(c * m * ec for _p, _a, _l, c, m, ec, _t in files) / E
    size = math.log2(1 + E)
    area_mass, area_crit, area_weighted, layer_mass = defaultdict(float), {}, defaultdict(float), defaultdict(float)
    area_base = {}
    for p_, a, l, c, m, ec, _t in files:
        area_mass[a] += m * ec
        area_crit[a] = max(area_crit.get(a, 0), c)
        area_base[a] = max(area_base.get(a, 0), base_crits[p_])
        area_weighted[a] += c * m * ec
        layer_mass[l] += c * m * ec
    n_areas = sum(1 for a, mass in area_mass.items() if area_base[a] >= 0.6 and mass >= 10)
    spread = 1 + 0.1 * min(max(n_areas - 1, 0), 3)
    has_test = any(t for *_, t in files)
    has_crit_src = any((not t) and base_crits[p_] >= 0.5 for p_, _a, _l, _c, _m, _e, t in files)
    test_bonus = 1.1 if has_test and has_crit_src else 1.0
    type_mult = TYPE_MULT.get(ptype, 0.8)
    pr_score = min(15.0, crit_pr * size * spread * test_bonus * type_mult)
    primary = max(area_weighted, key=area_weighted.get)
    primary_layer = next(l for _p, a, l, *_ in files if a == primary)
    out.update(prScore=pr_score, critPR=round(crit_pr, 3), size=round(size, 2), spread=spread,
               testBonus=test_bonus, typeMult=type_mult, primaryArea=primary, layer=primary_layer,
               areaCrit=area_crit.get(primary), areaBaseCrit=area_base.get(primary), layerMass=dict(layer_mass))
    return out


def load_prs(raw_prs):
    """Keep PRs merged inside the window. raw_prs: iterable of PR dicts from fetch_prs."""
    prs = []
    for pr in raw_prs:
        if not pr or not pr.get("mergedAt"):
            continue
        # GitHub can null out nested connections on partial errors; treat them as empty, not fatal.
        for key in ("files", "reviews", "labels"):
            if not pr.get(key):
                pr[key] = {"totalCount": 0, "nodes": []}
        merged = parse_ts(pr["mergedAt"])
        if WINDOW_START <= merged < WINDOW_END:
            pr["_merged"] = merged
            prs.append(pr)
    return prs


def week_of(ts):
    return min(WEEKS - 1, max(0, (ts - WINDOW_START).days // 7))


# ---------------------------------------------------------------- engine
def run(prs, params, detail=False):
    crit_transform, decay, weights = params["crit_transform"], params["area_decay"], params["weights"]
    human = [p for p in prs if not is_bot(p["author"]) and not any(l["name"] == "self-driving" for l in p["labels"]["nodes"])]
    by_title = defaultdict(list)
    for p in human:
        by_title[p["title"].strip()].append(p)

    scored = {}
    for p in human:
        s = score_pr(p, crit_transform)
        s["raw"] = s["prScore"]
        s["isRevert"] = bool(REVERT_RE.match(p["title"].strip()))
        s["reverted"] = False
        scored[p["number"]] = s
    for p in human:
        m = REVERT_RE.match(p["title"].strip())
        if m:
            cands = [q for q in by_title.get(m.group(1).strip(), []) if q["_merged"] <= p["_merged"]]
            if cands:
                scored[max(cands, key=lambda q: q["_merged"])["number"]]["reverted"] = True
    for s in scored.values():
        if s["isRevert"] or s["reverted"]:
            s["prScore"] = 0.0

    # Template dampening: (author, primaryArea, title signature) -> j-th gets 1/j.
    groups = defaultdict(list)
    for p in sorted(human, key=lambda q: q["_merged"]):
        s = scored[p["number"]]
        if s["prScore"] > 0:
            paths = [f["path"] for f in p["files"]["nodes"] if not NOISE_RE.search(f["path"])]
            sig = template_sig(p, paths) or title_sig(p["title"])
            groups[(p["author"]["login"], s["primaryArea"], sig)].append(p["number"])
    for (author, area, sig), nums in groups.items():
        for j, n in enumerate(nums, start=1):
            scored[n]["tScore"] = scored[n]["prScore"] / j
            scored[n]["templateIndex"] = j
            scored[n]["sig"] = sig

    # Area diminishing returns per (author, primaryArea).
    per_author_area = defaultdict(list)
    for p in human:
        s = scored[p["number"]]
        if s["prScore"] > 0:
            per_author_area[(p["author"]["login"], s["primaryArea"])].append(p["number"])
    D1 = defaultdict(float)
    for (author, area), nums in per_author_area.items():
        for k, n in enumerate(sorted(nums, key=lambda x: -scored[x]["tScore"]), start=1):
            scored[n]["final"] = scored[n]["tScore"] * k ** -decay
            D1[author] += scored[n]["final"]

    # Reviews.
    pr_by_num = {p["number"]: p for p in human}
    credit = {}  # (reviewer, pr) -> credit
    rv_records = defaultdict(list)  # reviewer -> [(pr, state, body, sw, submittedAt)]
    for p in human:
        author = p["author"]["login"]
        eligible = defaultdict(list)
        for rv in p["reviews"]["nodes"]:
            a = rv["author"]
            if is_bot(a) or a["login"].lower() in AI_REVIEWERS or a["login"] == author:
                continue
            eligible[a["login"]].append(rv)
        cx = 0.3 + 0.7 * (scored[p["number"]]["raw"] / 15)
        sole = 1.2 if len(eligible) == 1 else 1.0
        for r, rvs in eligible.items():
            sw = max(review_weight(x["state"], x["body"]) for x in rvs)
            depth = 1 + 0.1 * (min(3, len(rvs)) - 1)
            credit[(r, p["number"])] = sw * depth * cx * sole
            for x in rvs:
                rv_records[r].append((p["number"], x["state"], x["body"], review_weight(x["state"], x["body"]), x["submittedAt"]))
    D2 = defaultdict(float)
    authors_helped = defaultdict(set)
    for (r, n), c in credit.items():
        D2[r] += c
    for r, recs in rv_records.items():
        for n, state, body, sw, _ in recs:
            if sw >= 0.3:
                authors_helped[r].add(pr_by_num[n]["author"]["login"])
    for r in list(D2):
        D2[r] *= 0.5 + 0.5 * min(1, len(authors_helped[r]) / 10)

    # Stewardship.
    area_n, area_crit, area_base_crit = Counter(), {}, {}
    for p in human:
        s = scored[p["number"]]
        if s["prScore"] > 0:
            a = s["primaryArea"]
            area_n[a] += 1
            area_crit[a] = max(area_crit.get(a, 0), s["areaCrit"])
            area_base_crit[a] = max(area_base_crit.get(a, 0), s["areaBaseCrit"])
    contrib = defaultdict(lambda: defaultdict(float))
    authored_in, reviews_in = defaultdict(Counter), defaultdict(Counter)
    for p in human:
        s = scored[p["number"]]
        if s["prScore"] > 0:
            contrib[s["primaryArea"]][p["author"]["login"]] += s["tScore"]
            authored_in[p["author"]["login"]][s["primaryArea"]] += 1
    for (r, n), c in credit.items():
        area = scored[n]["primaryArea"]
        if area and scored[n]["prScore"] > 0:
            contrib[area][r] += 0.5 * c
            reviews_in[r][area] += 1
    D3, steward_detail = defaultdict(float), defaultdict(list)
    for area, people in contrib.items():
        if area_base_crit.get(area, 0) < 0.7 or area_n[area] < 5:
            continue
        total = sum(people.values())
        ranked = sorted(people.items(), key=lambda kv: -kv[1])
        for e, v in people.items():
            if authored_in[e][area] < 3 and reviews_in[e][area] < 6:
                continue
            share = v / total
            val = area_crit[area] * share * math.log2(1 + area_n[area])
            steward_detail[e].append({
                "area": area, "crit": area_crit[area], "nPRs": area_n[area], "share": round(share, 3),
                "authored": authored_in[e][area], "reviews": reviews_in[e][area], "value": round(val, 3),
                "coContributors": [{"login": k, "share": round(x / total, 3)} for k, x in ranked if k != e][:3],
            })
    for e, items in steward_detail.items():
        items.sort(key=lambda d: -d["value"])
        D3[e] = sum(d["value"] for d in items[:3])

    # Sustained & durable.
    weeks = defaultdict(lambda: [False] * WEEKS)
    for p in human:
        if scored[p["number"]]["prScore"] >= 4:
            weeks[p["author"]["login"]][week_of(p["_merged"])] = True
    rv_week = defaultdict(lambda: defaultdict(set))
    for r, recs in rv_records.items():
        for n, state, body, sw, sub in recs:
            if sw >= 0.6 and sub and WINDOW_START <= parse_ts(sub) < WINDOW_END:
                rv_week[r][week_of(parse_ts(sub))].add(n)
    for r, wk in rv_week.items():
        for w, nums in wk.items():
            if len(nums) >= 2:
                weeks[r][w] = True
    substantive, reverted = Counter(), Counter()
    for p in human:
        s = scored[p["number"]]
        if s["E"] >= 3 and not s["isRevert"]:
            substantive[p["author"]["login"]] += 1
            if s["reverted"]:
                reverted[p["author"]["login"]] += 1
    D4 = {}
    for e in set(weeks) | set(substantive):
        rr = reverted[e] / max(1, substantive[e])
        D4[e] = (sum(weeks[e]) / WEEKS) * (1 - min(0.5, 2 * rr))

    # Eligibility + normalization.
    pos_prs = Counter(p["author"]["login"] for p in human if scored[p["number"]]["prScore"] > 0)
    n_reviews = Counter({r: len(recs) for r, recs in rv_records.items()})
    eligible = sorted(e for e in set(pos_prs) | set(n_reviews) if pos_prs[e] >= 5 or n_reviews[e] >= 15)
    dims = {"delivery": D1, "review": D2, "stewardship": D3, "sustained": D4}
    norm = {}
    for key, d in dims.items():
        if key == "sustained":
            norm[key] = {e: d.get(e, 0.0) for e in eligible}
            continue
        mx = max((d.get(e, 0.0) for e in eligible), default=0) or 1
        norm[key] = {e: math.log1p(d.get(e, 0.0)) / math.log1p(mx) for e in eligible}
    cpis = {e: 100 * sum(weights[k] * norm[k][e] for k in weights) for e in eligible}
    ranking = sorted(eligible, key=lambda e: (-cpis[e], -D1.get(e, 0), -D2.get(e, 0)))

    result = {"ranking": ranking, "cpis": cpis}
    if not detail:
        return result
    result.update(human=human, scored=scored, dims=dims, norm=norm, credit=credit, rv_records=rv_records,
                  authors_helped=authors_helped, steward_detail=steward_detail, weeks=weeks,
                  substantive=substantive, reverted=reverted, groups=groups, pos_prs=pos_prs,
                  n_reviews=n_reviews, eligible=eligible)
    return result


def variants():
    w = BASE["weights"]
    out = {"base": BASE, "equal weights": {**BASE, "weights": {k: 0.25 for k in w}}}
    for drop in w:
        rest = {k: v for k, v in w.items() if k != drop}
        tot = sum(rest.values())
        out[f"drop {drop}"] = {**BASE, "weights": {**{k: v / tot for k, v in rest.items()}, drop: 0.0}}
    out["flattened criticality"] = {**BASE, "crit_transform": lambda c: 0.5 + 0.5 * c}
    out["stronger area decay"] = {**BASE, "area_decay": 0.6}
    return out


# ---------------------------------------------------------------- output
DIM_META = [
    {"key": "delivery", "label": "Critical-Path Delivery", "weight": 0.40,
     "summary": "Hard, consequential code landed, weighted by how load-bearing the system is.",
     "formula": "Σ per PR: criticality × log2(1 + effective churn) × cross-area spread × test bonus × change-type; "
                "capped at 15/PR, repeated templated PRs dampened 1/j, and the k-th PR in the same area × k^-0.4."},
    {"key": "review", "label": "Review Leverage", "weight": 0.25,
     "summary": "Being the human gate on other people's hard changes (AI reviewers excluded).",
     "formula": "Σ per reviewed PR: review depth (change request 1.0 … rubber stamp 0.3) × complexity of the PR reviewed "
                "× 1.2 if sole human reviewer; × breadth factor for distinct authors unblocked (saturates at 10)."},
    {"key": "stewardship", "label": "Keystone Stewardship", "weight": 0.20,
     "summary": "Owning a large share of a critical, busy system: the bus-factor question turned into credit.",
     "formula": "Top 3 critical areas (criticality ≥ 0.7, ≥ 5 PRs): criticality × engineer's share of area work "
                "(authored + ½ review credit) × log2(1 + PRs in area)."},
    {"key": "sustained", "label": "Sustained & Durable", "weight": 0.15,
     "summary": "Meaningful contribution across the quarter, and work that isn't reverted.",
     "formula": "Share of the 13 weeks with a substantive PR (score ≥ 4) or ≥ 2 substantive reviews, "
                "× (1 − min(0.5, 2 × revert rate))."},
]


def template_label(sig):
    """Human-readable template group: '"<title words>" in <slot dir>'."""
    if not sig.startswith("slot:"):
        return f'"{sig}"'
    path, _, title = sig[len("slot:"):].rpartition(":")
    return f'"{title}" in {path}' if title else path


def pct_rank(values, v):
    return round(100 * sum(1 for x in values if x <= v) / len(values))


def verdict(e, r, stew, rvs):
    """One plain-English sentence built from the engineer's largest contributions."""
    by_area, n_area, templated, total = defaultdict(float), Counter(), 0, 0
    for p in r["human"]:
        if p["author"]["login"] != e:
            continue
        s = r["scored"][p["number"]]
        total += 1
        if s["prScore"] > 0:
            by_area[s["primaryArea"]] += s["final"]
            n_area[s["primaryArea"]] += 1
            templated += s.get("templateIndex", 1) > 1
    parts = []
    if by_area:
        top = sorted(by_area, key=by_area.get, reverse=True)[:2]
        parts.append("Most critical-path work in " + " and ".join(f"{a} ({n_area[a]} PRs)" for a in top))
    big = stew[0] if stew else None  # highest stewardship value, matching the evidence panel order
    if big:
        parts.append(f"anchors {round(big['share'] * 100)}% of {big['area']}")
    subst = rvs["changesRequested"] + rvs["substantiveComments"] + rvs["substantiveApprovals"]
    if subst >= 10:
        parts.append(f"{subst} substantive reviews for {len(r['authors_helped'][e])} teammates")
    if total and templated / total > 0.2:
        parts.append(f"{templated:,} of {total:,} PRs discounted as templated repeats")
    return "; ".join(parts) + "."


def build(raw_prs):
    prs = load_prs(raw_prs)
    base = run(prs, BASE, detail=True)
    scored, human = base["scored"], base["human"]
    elig, rank = base["eligible"], base["ranking"]

    # Robustness across variants.
    var_tops = {}
    for name, params in variants().items():
        res = base if name == "base" else run(prs, params)
        var_tops[name] = res["ranking"][:7]
    stable_count = {e: sum(e in t[:5] for t in var_tops.values()) for e in rank[:10]}

    # Naive baselines.
    pr_count = Counter(p["author"]["login"] for p in human)
    loc = Counter()
    for p in human:
        loc[p["author"]["login"]] += p["additions"] + p["deletions"]
    rv_count = Counter(r for r, recs in base["rv_records"].items() for _ in recs)

    def naive(counter):
        return [{"login": l, "value": v, "cpisRank": rank.index(l) + 1 if l in rank else None} for l, v in counter.most_common(5)]

    stamphog_only = Counter()
    for p in human:
        approvers = {rv["author"]["login"] for rv in p["reviews"]["nodes"] if rv["author"] and rv["state"] == "APPROVED"}
        if approvers and approvers <= {"stamphog"}:
            stamphog_only[p["author"]["login"]] += 1

    def engineer(e, i, full):
        prs_e = [p for p in human if p["author"]["login"] == e]
        row = {
            "rank": i + 1, "login": e, "avatar": f"https://github.com/{e}.png?size=120",
            "score": round(base["cpis"][e], 1),
            "dims": {d["key"]: {"raw": round(base["dims"][d["key"]].get(e, 0), 2),
                                "norm": round(base["norm"][d["key"]][e], 3),
                                "pct": pct_rank([base["dims"][d["key"]].get(x, 0) for x in elig], base["dims"][d["key"]].get(e, 0))}
                     for d in DIM_META},
            "mergedPRs": len(prs_e),
            "scoredPRs": base["pos_prs"][e],
        }
        layer = defaultdict(float)
        for p in prs_e:
            s = scored[p["number"]]
            if s["prScore"] > 0:
                tot = sum(s["layerMass"].values()) or 1
                for l, m in s["layerMass"].items():
                    layer[l] += s["final"] * m / tot
        row["layerMix"] = {l: round(layer[l], 2) for l in LAYERS if layer[l] > 0}
        if not full:
            return row
        top_prs = sorted((p for p in prs_e if scored[p["number"]]["prScore"] > 0), key=lambda p: -scored[p["number"]]["prScore"])[:5]
        row["topPRs"] = [{
            "number": p["number"], "title": p["title"], "url": f"https://github.com/PostHog/posthog/pull/{p['number']}",
            "mergedAt": p["mergedAt"][:10], **{k: scored[p["number"]][k] for k in
                                               ("prScore", "critPR", "size", "spread", "testBonus", "typeMult", "primaryArea", "layer", "E", "filesCounted", "filesDropped")},
            "changedFiles": p["changedFiles"], "truncated": p["files"]["totalCount"] > 100,
        } for p in top_prs]
        for t in row["topPRs"]:
            t["prScore"] = round(t["prScore"], 2)
        stew = base["steward_detail"].get(e, [])[:3]
        for s in stew:
            s["silo"] = s["share"] > 0.6 and (not s["coContributors"] or s["coContributors"][0]["share"] < 0.15)
        row["stewardship"] = stew
        buckets = Counter(review_bucket(st, b) for _n, st, b, _sw, _ in base["rv_records"].get(e, []))
        rvs = {k: buckets[k] for k in ("changesRequested", "substantiveComments", "substantiveApprovals", "rubberStamps", "lightComments")}
        sole = sum(1 for (r, n), c in base["credit"].items() if r == e and
                   len({rv["author"]["login"] for rv in next(p for p in human if p["number"] == n)["reviews"]["nodes"]
                        if not is_bot(rv["author"]) and rv["author"]["login"].lower() not in AI_REVIEWERS
                        and rv["author"]["login"] != next(p for p in human if p["number"] == n)["author"]["login"]}) == 1)
        best = sorted(((base["credit"][(e, n)], n, st, b) for n, st, b, sw, _ in base["rv_records"].get(e, []) if len((b or "").strip()) >= 40),
                      key=lambda x: -x[0])
        seen, excerpts = set(), []
        for c, n, st, b in best:
            if n in seen:
                continue
            seen.add(n)
            p = next(p for p in human if p["number"] == n)
            excerpts.append({"number": n, "title": p["title"], "author": p["author"]["login"], "state": st,
                             "url": f"https://github.com/PostHog/posthog/pull/{n}", "prScore": round(scored[n]["raw"], 1),
                             "body": re.sub(r"\s+", " ", b.strip())[:220]})
            if len(excerpts) == 3:
                break
        row["reviews"] = {**rvs, "authorsUnblocked": len(base["authors_helped"][e]), "soleGate": sole,
                          "prsReviewed": len({n for (r, n) in base["credit"] if r == e}), "excerpts": excerpts}
        row["weeks"] = base["weeks"][e]
        damp = [(k[2], len(v), round(sum(1 / j for j in range(1, len(v) + 1)), 1))
                for k, v in base["groups"].items() if k[0] == e and len(v) >= 3]
        damp.sort(key=lambda x: -x[1])
        reverted_prs = [p["number"] for p in prs_e if scored[p["number"]]["reverted"]]
        row["adjustments"] = {
            "templated": [{"sig": template_label(s), "count": c, "countedAs": a} for s, c, a in damp[:4]],
            "noiseLinesRemoved": sum(scored[p["number"]]["noiseLines"] for p in prs_e),
            "revertedPRs": reverted_prs,
            "revertRate": round(len(reverted_prs) / max(1, base["substantive"][e]), 3),
            "stamphogOnlyShare": round(stamphog_only[e] / max(1, len(prs_e)), 2),
            "zeroScorePRs": len(prs_e) - base["pos_prs"][e],
        }
        row["robustness"] = {"top5In": stable_count.get(e, 0), "of": len(var_tops),
                             "badge": "Stable" if stable_count.get(e, 0) >= 6 else "Weight-sensitive"}
        row["naiveRanks"] = {
            "prCount": sorted(pr_count, key=lambda x: -pr_count[x]).index(e) + 1 if e in pr_count else None,
            "linesChanged": sorted(loc, key=lambda x: -loc[x]).index(e) + 1 if e in loc else None,
            "reviewCount": sorted(rv_count, key=lambda x: -rv_count[x]).index(e) + 1 if e in rv_count else None,
        }
        row["verdict"] = verdict(e, base, stew, rvs)
        return row

    top_n = 5
    tie = len(rank) > top_n and base["cpis"][rank[top_n - 1]] - base["cpis"][rank[top_n]] < 1.0
    bots = {(p["author"] or {}).get("login") for p in prs if is_bot(p["author"])}
    out = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": "PostHog/posthog",
        "window": {"start": WINDOW_START.date().isoformat(),
                   "end": (WINDOW_END - timedelta(days=1)).date().isoformat(), "days": WINDOW_DAYS},
        "totals": {
            "mergedPRs": len(prs), "humanPRs": len(human), "botPRs": len(prs) - len(human),
            "scoredPRs": sum(1 for s in scored.values() if s["prScore"] > 0),
            "engineers": len({p["author"]["login"] for p in human}), "eligible": len(elig),
            "botAccounts": len(bots),
            "aiReviews": sum(1 for p in prs for rv in p["reviews"]["nodes"]
                             if rv["author"] and (is_bot(rv["author"]) or rv["author"]["login"].lower() in AI_REVIEWERS)),
            "humanReviews": sum(len(v) for v in base["rv_records"].values()),
        },
        "dimensions": DIM_META,
        "top": [engineer(e, i, True) for i, e in enumerate(rank[:top_n + (1 if tie else 0)])],
        "tieAtCutoff": tie,
        "leaderboard": [engineer(e, i, False) for i, e in enumerate(rank[:25])],
        "robustness": {"variants": {k: v[:5] for k, v in var_tops.items()},
                       "baseTop5InTop7Everywhere": sum(all(e in t for t in var_tops.values()) for e in rank[:5])},
        "naive": {"prCount": naive(pr_count), "linesChanged": naive(loc), "reviewCount": naive(rv_count)},
        "tiers": [{"prefix": p, "area": a, "layer": l, "crit": c} for p, a, l, c in sorted(TIERS, key=lambda t: -t[3])],
    }
    return out


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--end", help="last day of the window, YYYY-MM-DD (default: yesterday UTC)")
    args = ap.parse_args()
    if args.end:
        set_window(date.fromisoformat(args.end))
    with (HERE / "data" / "prs.jsonl").open() as f:
        o = build(json.loads(line) for line in f)
    payload = json.dumps(o, separators=(",", ":"))
    # The bundled copies are the fallback served when the scheduled refresh has not run yet.
    for target in (HERE / "data" / "impact.json", HERE.parent / "functions" / "impact.json",
                   HERE.parent / "web" / "public" / "impact.json"):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload)
    return o


if __name__ == "__main__":
    o = main()
    print(json.dumps(o["totals"], indent=1))
    for r in o["leaderboard"][:12]:
        print(r["rank"], r["login"], r["score"], {k: v["norm"] for k, v in r["dims"].items()}, r["mergedPRs"])
    print("robustness", json.dumps(o["robustness"], indent=0))
    print("naive", json.dumps(o["naive"]))
