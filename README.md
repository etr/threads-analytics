# threads-analytics

Claude Code plugin that fetches your Threads (Meta) posting activity and produces engagement analysis, topic classification, and posting recommendations.

## Setup

1. **Python 3.8+** with `requests` and optionally `python-dotenv`:
   ```bash
   pip install requests python-dotenv
   ```

2. **Threads API token** — follow [the setup guide](skills/threads-analytics/references/setup-guide.md) to create a Meta app, configure permissions, and generate a long-lived access token.

3. **Store the token**:
   ```bash
   export THREADS_ACCESS_TOKEN="your-token"
   ```
   Or add it to a `.env` file.

## Usage

In Claude Code:

```
/threads-analytics 30          # Last 30 days
/threads-analytics 7 --top 10  # Last 7 days, top 10 rankings
/threads-analytics --refresh   # Force re-fetch (ignore cache)
/threads-analytics --no-replies # Skip conversation data (faster)

/recommend-threads                          # Posts you may find interesting
/recommend-threads --seeds "ai, climbing"   # Bias toward specific topics
/recommend-threads --recent                 # Use RECENT instead of TOP search
```

`/recommend-threads` requires the optional `threads_keyword_search` permission on your Meta app — see the [setup guide](skills/threads-analytics/references/setup-guide.md). It approximates "follows" and "communities" via the accounts you @-mention and the hashtags you use, since the Threads API does not expose those signals directly.

## What you get

- **Engagement overview** — views, likes, replies, reposts, engagement rates
- **Top/bottom posts** — ranked by engagement rate and raw views
- **Media type breakdown** — which formats perform best
- **Timing patterns** — best hours and days to post
- **Topic classification** — Claude reads your posts and clusters by topic
- **Posting recommendations** — 5-7 actionable items with supporting data
- **Content recommendations** — Threads posts to read, ranked by topical fit to your history and seeds

## How it works

The plugin has two fetcher scripts (`scripts/fetch.py` for history, `scripts/recommend.py` for discovery) that call the Threads API and output structured JSON. Claude does all analysis — topic classification, pattern detection, scoring, and ranking are pure LLM reasoning over the fetched data. No ML libraries needed.

Data is cached at `~/.claude/threads-analytics/cache/` to avoid redundant API calls.

## Dependencies

- Python 3.8+
- `requests`
- `python-dotenv` (optional, for .env file support)
