---
name: threads-analytics
description: Analyze Threads (Meta) posting activity — fetch engagement data, classify topics, spot patterns, and generate actionable posting recommendations.
---

# Threads Analytics

Fetch and analyze the user's Threads posting activity. You are the analyst — the fetcher script pulls raw data, you do all the thinking.

## Arguments

Parse the user's input:
- Bare number → `--days N` (e.g. `30` means last 30 days)
- `--top N` → show top N posts in rankings (default 5)
- `--no-replies` → skip conversation/reply data
- `--refresh` → ignore cached data, re-fetch

Defaults: 30 days, top 5, replies included, cache reused.

## Workflow

### 1. Pre-flight checks

Verify before fetching:
- `THREADS_ACCESS_TOKEN` exists (env var or `.env` file). If missing, show the user setup instructions from `${CLAUDE_PLUGIN_ROOT}/skills/threads-analytics/references/setup-guide.md` and stop.
- `python3` is available
- `requests` package is installed (`python3 -c "import requests"`)

If `requests` is missing, offer to install: `pip install requests`

### 2. Cache check

Cache location: `~/.claude/threads-analytics/cache/threads-data-{days}d-{YYYY-MM-DD}.json`

- If a cache file exists for today's date + same day count AND `--refresh` was NOT passed → use cached data, skip fetching
- Otherwise → fetch fresh data

### 3. Fetch data

Run the fetcher:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/fetch.py --days <N> --output <cache_path> [--no-replies] [--top-replies 3]
```

Progress appears on stderr. If it fails:
- Exit code 1 → profile/auth error → show setup guide
- Exit code 2 → rate limit → tell user to wait and retry later
- Exit code 3 → token expired → show refresh instructions from setup guide

### 4. Read and analyze the JSON

Read the cached JSON file. Then compute and present:

#### Overview
- Total posts in period, posts per week average
- Total and average views, likes, replies, reposts, quotes, shares
- Overall engagement rate: `(likes + replies + reposts + quotes + shares) / views`
- Follower count (from user insights)

#### Top & Bottom Posts
- Top N posts by engagement rate (with text preview, date, metrics)
- Bottom N posts by engagement rate
- Top N by raw views

#### Media Type Breakdown
- Count and average engagement by media_type (TEXT_POST, IMAGE, VIDEO, CAROUSEL, etc.)

#### Timing Patterns
- Hour-of-day distribution (in user's apparent timezone, inferred from post timestamps)
- Day-of-week distribution
- Best posting times by engagement rate
- Posting frequency trend: week-over-week post counts

#### Conversation Depth
- Posts with most replies
- Average reply count
- Notable conversations (interesting reply content, if fetched)

### 5. Topic Classification

Read each post's text and assign 1-2 topic labels from organic categories that emerge from the content. Do not use a fixed taxonomy — let the topics arise naturally.

Then aggregate:
- Post count per topic
- Average engagement per topic
- Trending vs declining topics (compare first half vs second half of the period)

### 6. Recommendations

Generate 5-7 actionable recommendations, each with:
- **What to do** — specific, concrete action
- **Supporting data** — the numbers backing it
- **Confidence** — high/medium/low based on sample size and signal strength

Cover:
- Best-performing topics to double down on
- Optimal posting times
- Format guidance (media type insights)
- Declining topics to potentially retire or reinvent
- Rising topics to explore further
- One experimental suggestion based on gaps in the data

### 7. Output format

Present as a well-structured markdown report with clear sections, tables for data, and a TL;DR at the top summarizing the 3 most important findings.
