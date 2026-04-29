#!/usr/bin/env python3
"""Threads recommendation fetcher.

Pulls signal from the user's own posting history (topics, hashtags, mentions,
reply targets) and uses the Threads keyword_search endpoint to surface public
posts that may be of interest. The output is a JSON dossier; ranking and final
selection are left to Claude.

The Threads API does not expose a public "who I follow" or "communities"
endpoint, so this script approximates those signals from the user's own
activity (people they @-mention or reply to, plus hashtags they use).
Additional seeds can be supplied via --seeds.
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
    home_env = Path.home() / ".env"
    if home_env.exists():
        load_dotenv(home_env)
except ImportError:
    pass

BASE_URL = "https://graph.threads.net/v1.0"
RATE_WARN = 900
RATE_ABORT = 950
PERMISSION_ERROR_EXIT = 4
api_call_count = 0


def log(msg):
    print(msg, file=sys.stderr)


def api_get(endpoint, params=None, token=None):
    """GET request with rate-limit tracking and exponential backoff retries.

    Distinguishes a missing-permission failure (exit 4) from a generic API
    error so the caller can surface a clear message about
    threads_keyword_search.
    """
    global api_call_count

    if api_call_count >= RATE_ABORT:
        log(f"ABORT: Approaching rate limit ({api_call_count} calls). Stopping to avoid 24h block.")
        sys.exit(2)
    if api_call_count >= RATE_WARN:
        log(f"WARNING: {api_call_count} API calls made (limit ~1000/24h)")

    url = f"{BASE_URL}/{endpoint}" if not endpoint.startswith("http") else endpoint
    if params is None:
        params = {}
    params["access_token"] = token

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
            api_call_count += 1
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                log(f"Request error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
                continue
            log(f"ERROR: Request failed after {max_retries} attempts: {e}")
            return None

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429:
            wait = 2 ** (attempt + 2)
            log(f"Rate limited (429). Waiting {wait}s before retry...")
            time.sleep(wait)
            continue

        try:
            err = resp.json().get("error", {})
            code = err.get("code")
            msg = err.get("message", "")
            if code == 190:
                log("ERROR: Access token expired or invalid. Generate a new token.")
                log("See: setup-guide.md for token refresh instructions.")
                sys.exit(3)
            if code == 10 or "permission" in msg.lower() or resp.status_code == 403:
                log(f"ERROR: Missing permission. API said: {msg}")
                log("The recommendation feature requires the 'threads_keyword_search' permission.")
                log("See setup-guide.md → 'Configure Permissions' to add it to your Meta app.")
                sys.exit(PERMISSION_ERROR_EXIT)
            log(f"API error: {resp.status_code} — {msg or resp.text[:200]}")
        except (ValueError, KeyError):
            log(f"API error: {resp.status_code} — {resp.text[:200]}")

        if attempt < max_retries - 1:
            time.sleep(2 ** (attempt + 1))
        else:
            return None

    return None


HASHTAG_RE = re.compile(r"#(\w{2,40})")
MENTION_RE = re.compile(r"@([A-Za-z0-9_.]{2,40})")


def extract_signals(threads):
    """Pull hashtags, mentions, and per-post text snippets from history."""
    hashtags = Counter()
    mentions = Counter()
    snippets = []
    for t in threads:
        text = (t.get("text") or "").strip()
        if not text:
            continue
        for tag in HASHTAG_RE.findall(text):
            hashtags[tag.lower()] += 1
        for handle in MENTION_RE.findall(text):
            mentions[handle.lower()] += 1
        snippets.append({
            "id": t.get("id"),
            "text": text[:280],
            "timestamp": t.get("timestamp"),
            "engagement": t.get("insights", {}),
        })
    return {
        "hashtags": hashtags.most_common(25),
        "mentions": mentions.most_common(25),
        "snippets": snippets,
    }


def keyword_search(query, token, search_type="TOP", limit=25):
    """Threads keyword_search endpoint. Returns [] on failure (non-permission)."""
    fields = "id,text,timestamp,username,permalink,media_type,has_replies"
    data = api_get(
        "keyword_search",
        {"q": query, "search_type": search_type, "fields": fields, "limit": limit},
        token,
    )
    if not data:
        return []
    return data.get("data", [])


def load_history(history_path):
    """Load a cached fetch.py output file."""
    p = Path(history_path).expanduser()
    if not p.exists():
        log(f"ERROR: History file not found: {p}")
        log("Run /threads-analytics first, or pass --history <path> to a cached file.")
        sys.exit(1)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        log(f"ERROR: Could not parse history JSON: {e}")
        sys.exit(1)


def parse_seeds(raw):
    if not raw:
        return []
    parts = [s.strip() for s in re.split(r"[,;\n]", raw)]
    return [s for s in parts if s]


def build_queries(signals, seeds, max_queries):
    """Merge user-supplied seeds with auto-extracted hashtags/mentions.

    Seeds always come first (explicit user intent beats heuristics). Hashtags
    are next (strong topical signal). Mentions are last and prefixed with @.
    """
    queries = []
    seen = set()

    def add(q):
        key = q.lower().strip()
        if key and key not in seen:
            seen.add(key)
            queries.append(q.strip())

    for s in seeds:
        add(s)
    for tag, _ in signals["hashtags"]:
        add(f"#{tag}")
    for handle, _ in signals["mentions"]:
        add(f"@{handle}")

    return queries[:max_queries]


def main():
    parser = argparse.ArgumentParser(
        description="Fetch candidate Threads posts that may interest the user, based on their history."
    )
    parser.add_argument(
        "--history", type=str, required=True,
        help="Path to a cached fetch.py JSON file (history dossier)."
    )
    parser.add_argument(
        "--seeds", type=str, default=None,
        help="Optional comma-separated topics/keywords to bias recommendations (e.g. \"ai, climbing\")."
    )
    parser.add_argument(
        "--max-queries", type=int, default=10,
        help="Maximum number of distinct keyword queries to issue (default: 10)."
    )
    parser.add_argument(
        "--per-query", type=int, default=15,
        help="Number of candidate posts to fetch per query (default: 15)."
    )
    parser.add_argument(
        "--search-type", type=str, default="TOP", choices=["TOP", "RECENT"],
        help="Threads keyword_search type (default: TOP)."
    )
    parser.add_argument(
        "--since-days", type=int, default=14,
        help="Drop candidates older than this many days (default: 14)."
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output file path (default: stdout)."
    )
    args = parser.parse_args()

    token = os.environ.get("THREADS_ACCESS_TOKEN")
    if not token:
        log("ERROR: THREADS_ACCESS_TOKEN not set.")
        log("Set it as an environment variable or in a .env file.")
        sys.exit(1)

    history = load_history(args.history)
    profile = history.get("profile", {})
    threads = history.get("threads", [])
    if not threads:
        log("ERROR: History has no threads. Cannot derive interest signals.")
        sys.exit(1)

    log(f"Loaded {len(threads)} historical posts for @{profile.get('username', 'user')}")

    signals = extract_signals(threads)
    log(f"Extracted {len(signals['hashtags'])} hashtags, {len(signals['mentions'])} mentions")

    seeds = parse_seeds(args.seeds)
    if seeds:
        log(f"User seeds: {seeds}")

    queries = build_queries(signals, seeds, args.max_queries)
    if not queries:
        log("ERROR: No queries to run — history has no hashtags/mentions and no seeds were provided.")
        log("Pass --seeds \"topic1, topic2\" to seed the recommendation.")
        sys.exit(1)

    log(f"Running {len(queries)} keyword searches: {queries}")

    own_username = (profile.get("username") or "").lower()
    own_post_ids = {t.get("id") for t in threads if t.get("id")}
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.since_days)

    candidates_by_query = {}
    seen_ids = set()
    total_candidates = 0
    for q in queries:
        results = keyword_search(q, token, args.search_type, args.per_query)
        kept = []
        for r in results:
            rid = r.get("id")
            if not rid or rid in seen_ids or rid in own_post_ids:
                continue
            if (r.get("username") or "").lower() == own_username:
                continue
            ts = r.get("timestamp")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                except ValueError:
                    pass
            seen_ids.add(rid)
            kept.append(r)
        candidates_by_query[q] = kept
        total_candidates += len(kept)
        log(f"  '{q}': {len(results)} returned, {len(kept)} kept")

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "seeds": seeds,
        "signals": {
            "hashtags": signals["hashtags"],
            "mentions": signals["mentions"],
            "history_post_count": len(threads),
        },
        "queries_run": queries,
        "search_type": args.search_type,
        "since_days": args.since_days,
        "candidates_by_query": candidates_by_query,
        "candidate_count": total_candidates,
        "api_calls_made": api_call_count,
        "notes": [
            "Threads API does not expose a 'follows' or 'communities' endpoint.",
            "Mentions and hashtags from the user's own posts are used as proxies.",
            "Ranking is left to the Claude analyst — this script only collects.",
        ],
    }

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json, encoding="utf-8")
        log(f"Output written to {args.output}")
    else:
        print(output_json)

    log(f"Done. {total_candidates} candidates across {len(queries)} queries. {api_call_count} API calls.")


if __name__ == "__main__":
    main()
