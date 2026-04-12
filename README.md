# social-analytics

Claude Code plugin that fetches your posting activity across **Threads**,
**Facebook** Pages, **Instagram**, **LinkedIn**, and **TikTok**, then produces
per-platform engagement analysis plus a cross-platform comparison report.

The plugin operates on **optimistic auth** — configure tokens for the
platforms you care about, and the rest are quietly skipped. Parity across
platforms is not required; each provider exposes whatever metrics its API
supports and the skill clearly marks what's unavailable.

## Setup

1. **Python 3.8+** with `requests` (and optionally `python-dotenv`):
   ```bash
   pip install requests python-dotenv
   ```

2. **Platform tokens** — follow the per-platform sections in
   [setup-guide.md](skills/social-analytics/references/setup-guide.md).
   You only need to set up the platforms you want analyzed.

3. **Store the tokens** as environment variables or in a `.env` file:
   ```bash
   export THREADS_ACCESS_TOKEN="..."
   export FACEBOOK_ACCESS_TOKEN="..."
   export FACEBOOK_PAGE_ID="..."
   export INSTAGRAM_ACCESS_TOKEN="..."
   export LINKEDIN_ACCESS_TOKEN="..."
   export TIKTOK_ACCESS_TOKEN="..."
   ```

## Usage

In Claude Code:

```
/social-analytics 30                     # Last 30 days, all configured platforms
/social-analytics 7 --platform linkedin  # Last 7 days, LinkedIn only
/social-analytics --platform all --top 10 # All platforms, top 10 rankings
/social-analytics --refresh              # Force re-fetch (ignore cache)
/social-analytics --no-replies           # Skip conversation data (faster)
```

## What you get

For **each** configured platform, independently:

- **Engagement overview** — impressions/reach, likes, comments, shares, saves
  (whichever the platform exposes), plus engagement rates
- **Top/bottom posts** — ranked by engagement rate and raw reach
- **Media type breakdown** — which formats perform best
- **Timing patterns** — best hours and days to post
- **Topic classification** — Claude reads your posts and clusters them by topic
- **Per-platform recommendations** — 3–5 actionable items with supporting data

Then, when **two or more platforms** produced data:

- **Cross-platform comparison** — at-a-glance platform table
- **Topic performance across platforms** — which topics travel, which don't
- **Audience & timing divergence** — where audiences differ
- **Cross-platform recommendations** — cross-post opportunities,
  specialization guidance, gaps worth filling

## How it works

The plugin has one real script (`scripts/fetch.py`) that dispatches to
per-platform providers under `scripts/providers/`. Each provider fetches its
data and maps it onto a shared `NormalizedPost` schema, so the skill can
reason across platforms without caring about underlying API differences.

Claude does all the analysis — topic classification, pattern detection, and
recommendations are pure LLM reasoning over the fetched JSON. No ML libraries
needed.

Data is cached at `~/.claude/social-analytics/cache/` as one file per
platform plus a `combined-*.json` manifest to avoid redundant API calls
within the same day.

### Adding a new platform

1. Create a new file under `scripts/providers/`
2. Subclass `Provider` and implement `fetch_profile`, `fetch_posts`,
   `fetch_post_insights`, `fetch_conversation`, `fetch_account_insights`,
   and `normalize`
3. Register the class in `scripts/providers/__init__.py` under `PROVIDERS`
4. Add a section to `setup-guide.md`

The `Provider` base class handles retries, exponential backoff, rate-limit
tracking, optimistic-auth (missing-token → skip), and the shared
`run()` orchestration.

## Dependencies

- Python 3.8+
- `requests`
- `python-dotenv` (optional, for `.env` file support)

## License

MIT
