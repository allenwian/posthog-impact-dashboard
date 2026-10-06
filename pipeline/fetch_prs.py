"""Fetch merged PRs for PostHog/posthog over the analysis window via GitHub GraphQL.

Search results are capped at 1000 per query, so we query one day at a time.
CLI output: data/prs.jsonl (one PR per line). The scheduled refresh imports fetch_days().
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

REPO = "PostHog/posthog"
OUT = Path(__file__).parent / "data" / "prs.jsonl"
_token = None


def token():
    """GITHUB_TOKEN env var (Cloud Function secret), else the local gh CLI login."""
    global _token
    if _token is None:
        _token = os.environ.get("GITHUB_TOKEN") or subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    return _token

QUERY = """
query($q: String!, $cursor: String) {
  search(query: $q, type: ISSUE, first: 40, after: $cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number title createdAt mergedAt additions deletions changedFiles
        author { login __typename }
        labels(first: 15) { nodes { name } }
        files(first: 100) { totalCount nodes { path additions deletions } }
        reviews(first: 40) { nodes { author { login __typename } state submittedAt body } }
        comments { totalCount }
        closingIssuesReferences { totalCount }
        commits { totalCount }
      }
    }
  }
  rateLimit { remaining cost }
}
"""


def gql(variables, attempt=0):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.load(resp)
        if "errors" in body and not (body.get("data") or {}).get("search"):
            raise RuntimeError(body["errors"])
        return body["data"]
    except Exception as exc:  # retry transient / secondary rate limit errors
        if attempt >= 5:
            raise
        wait = 5 * (attempt + 1)
        print(f"retry {variables.get('q')} in {wait}s: {exc}", file=sys.stderr)
        time.sleep(wait)
        return gql(variables, attempt + 1)


def fetch_day(day):
    q = f"repo:{REPO} is:pr is:merged merged:{day.isoformat()}"
    cursor, prs = None, []
    while True:
        data = gql({"q": q, "cursor": cursor})
        search = data["search"]
        prs.extend(n for n in search["nodes"] if n)
        if search["issueCount"] > 1000:
            print(f"WARNING {day} has {search['issueCount']} PRs (>1000 cap)", file=sys.stderr)
        if not search["pageInfo"]["hasNextPage"]:
            break
        cursor = search["pageInfo"]["endCursor"]
    print(f"{day}: {len(prs)} PRs (rate remaining {data['rateLimit']['remaining']})", file=sys.stderr)
    return prs


def fetch_days(days, workers=4):
    """Fetch merged PRs for each date in days; returns PR dicts de-duplicated by number."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch_day, days))
    by_number = {}
    for prs in results:
        for pr in prs:
            by_number[pr["number"]] = pr
    return list(by_number.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default=date.today().isoformat(), help="last merge day to fetch, YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=91)
    args = ap.parse_args()
    end = date.fromisoformat(args.end)
    prs = fetch_days([end - timedelta(days=i) for i in range(args.days + 1)])
    with OUT.open("w") as f:
        for pr in prs:
            f.write(json.dumps(pr) + "\n")
    print(f"wrote {len(prs)} PRs to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
