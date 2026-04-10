#!/usr/bin/env python3
"""Threads API fetcher — pulls posts, insights, and conversations."""

import argparse
import json
import os
import sys
import time
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
    pass  # python-dotenv optional; env var must be set directly

BASE_URL = "https://graph.threads.net/v1.0"
RATE_WARN = 900
RATE_ABORT = 950
api_call_count = 0


def log(msg):
    print(msg, file=sys.stderr)


def api_get(endpoint, params=None, token=None):
    """GET request with rate-limit tracking and exponential backoff retries."""
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
            if err.get("code") == 190:
                log("ERROR: Access token expired or invalid. Generate a new token.")
                log("See: setup-guide.md for token refresh instructions.")
                sys.exit(3)
            log(f"API error: {resp.status_code} — {err.get('message', resp.text[:200])}")
        except (ValueError, KeyError):
            log(f"API error: {resp.status_code} — {resp.text[:200]}")

        if attempt < max_retries - 1:
            time.sleep(2 ** (attempt + 1))
        else:
            return None

    return None


def fetch_user_profile(token):
    """GET /me — user ID and profile info."""
    log("Fetching user profile...")
    data = api_get("me", {"fields": "id,username,name,threads_profile_picture_url,threads_biography"}, token)
    if not data or "id" not in data:
        log("ERROR: Could not fetch user profile. Check your access token.")
        sys.exit(1)
    log(f"User: @{data.get('username', 'unknown')} (ID: {data['id']})")
    return data


def fetch_threads(user_id, token, since_date):
    """Fetch all threads with cursor pagination, filtered by date."""
    log(f"Fetching threads since {since_date.strftime('%Y-%m-%d')}...")
    fields = "id,text,timestamp,media_type,permalink,shortcode,is_quote_post"
    all_threads = []
    params = {
        "fields": fields,
        "limit": 50,
        "since": int(since_date.timestamp()),
    }
    url = f"{user_id}/threads"

    while url:
        data = api_get(url, params, token)
        if not data:
            break

        all_threads.extend(data.get("data", []))
        log(f"  Fetched {len(all_threads)} threads so far...")

        next_url = data.get("paging", {}).get("next")
        if next_url:
            url = next_url
            params = {}  # params embedded in next URL
        else:
            url = None

    log(f"Total threads fetched: {len(all_threads)}")
    return all_threads


def fetch_post_insights(media_id, token):
    """GET /{media_id}/insights — engagement metrics for a single post."""
    metrics = "views,likes,replies,reposts,quotes,shares"
    data = api_get(f"{media_id}/insights", {"metric": metrics}, token)
    if not data:
        return {}

    insights = {}
    for item in data.get("data", []):
        name = item.get("name")
        values = item.get("values", [])
        if values:
            insights[name] = values[0].get("value", 0)
        elif "total_value" in item:
            insights[name] = item["total_value"].get("value", 0)
    return insights


def fetch_conversation(media_id, token, top_n=5):
    """GET /{media_id}/conversation — top replies."""
    fields = "id,text,timestamp,username,has_replies"
    data = api_get(f"{media_id}/conversation", {"fields": fields, "limit": top_n}, token)
    if not data:
        return []
    return data.get("data", [])


def fetch_user_insights(user_id, token):
    """GET /{user_id}/threads_insights — account-level metrics."""
    log("Fetching user-level insights...")
    metrics = "views,likes,replies,reposts,quotes,followers_count"
    data = api_get(f"{user_id}/threads_insights", {"metric": metrics}, token)
    if not data:
        return {}

    insights = {}
    for item in data.get("data", []):
        name = item.get("name")
        values = item.get("values", [])
        if values:
            insights[name] = values[0].get("value", 0)
        elif "total_value" in item:
            insights[name] = item["total_value"].get("value", 0)
    return insights


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Threads posting activity and engagement data."
    )
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days of history to fetch (default: 30)"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output file path (default: stdout)"
    )
    parser.add_argument(
        "--no-replies", action="store_true",
        help="Skip fetching conversation/reply data"
    )
    parser.add_argument(
        "--top-replies", type=int, default=3,
        help="Number of top replies to fetch per post (default: 3)"
    )
    args = parser.parse_args()

    token = os.environ.get("THREADS_ACCESS_TOKEN")
    if not token:
        log("ERROR: THREADS_ACCESS_TOKEN not set.")
        log("Set it as an environment variable or in a .env file.")
        log("See setup-guide.md for instructions on obtaining a token.")
        sys.exit(1)

    since_date = datetime.now(timezone.utc) - timedelta(days=args.days)

    profile = fetch_user_profile(token)
    user_id = profile["id"]

    user_insights = fetch_user_insights(user_id, token)

    threads = fetch_threads(user_id, token, since_date)

    log("Fetching per-post insights...")
    for i, thread in enumerate(threads):
        thread["insights"] = fetch_post_insights(thread["id"], token)
        if (i + 1) % 10 == 0:
            log(f"  Insights: {i + 1}/{len(threads)}")

    if not args.no_replies:
        log("Fetching conversations...")
        for i, thread in enumerate(threads):
            replies_count = thread.get("insights", {}).get("replies", 0)
            if replies_count and replies_count > 0:
                thread["conversation"] = fetch_conversation(
                    thread["id"], token, args.top_replies
                )
            else:
                thread["conversation"] = []
            if (i + 1) % 10 == 0:
                log(f"  Conversations: {i + 1}/{len(threads)}")
    else:
        for thread in threads:
            thread["conversation"] = []

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "since": since_date.isoformat(),
        "profile": profile,
        "user_insights": user_insights,
        "threads": threads,
        "api_calls_made": api_call_count,
    }

    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json, encoding="utf-8")
        log(f"Output written to {args.output}")
    else:
        print(output_json)

    log(f"Done. {api_call_count} API calls made.")


if __name__ == "__main__":
    main()
