---
name: social-analytics
description: Analyze social media posting activity across Threads, Facebook, Instagram, LinkedIn, and TikTok — fetch engagement data, classify topics, spot patterns, and generate independent per-platform reports plus a cross-platform comparison.
---

# Social Analytics

Fetch and analyze the user's posting activity across Threads, Facebook, Instagram, LinkedIn, and TikTok. You are the analyst — the fetcher script pulls raw data, you do all the thinking.

The tool operates on **optimistic auth**: if a platform's API token is set, we try to fetch from it; if the token is missing or broken, that platform is skipped with a warning and we move on. There is no platform that is "required" — users can configure any subset.

## Arguments

Parse the user's input:
- Bare number → `--days N` (e.g. `30` means last 30 days)
- `--platform <name|all>` → restrict to one platform, or run all configured ones (default: `all`)
  - Valid names: `threads`, `facebook`, `instagram`, `linkedin`, `tiktok`
- `--top N` → show top N posts in rankings (default 5)
- `--no-replies` → skip conversation/reply data (faster, fewer API calls)
- `--refresh` → ignore cached data, re-fetch

Defaults: 30 days, all platforms, top 5, replies included, cache reused.

## Workflow

### 1. Pre-flight checks

Verify before fetching:
- `python3` is available
- `requests` package is installed (`python3 -c "import requests"`)
- **At least one** of these tokens is set (as env var or in `.env`):
  - `THREADS_ACCESS_TOKEN`
  - `FACEBOOK_ACCESS_TOKEN` (optionally with `FACEBOOK_PAGE_ID`)
  - `INSTAGRAM_ACCESS_TOKEN` (optionally with `INSTAGRAM_USER_ID`)
  - `LINKEDIN_ACCESS_TOKEN` (optionally with `LINKEDIN_ORGANIZATION_URN`)
  - `TIKTOK_ACCESS_TOKEN`

If **no** tokens are set, show the user the setup instructions from `${CLAUDE_PLUGIN_ROOT}/skills/social-analytics/references/setup-guide.md` and stop. If `requests` is missing, offer to install: `pip install requests`.

Do **not** block on missing tokens for individual platforms — the fetcher will warn and skip them.

### 2. Cache check

Cache location: `~/.claude/social-analytics/cache/`

File naming:
- Per-platform: `{platform}-{days}d-{YYYY-MM-DD}.json`
- Combined manifest: `combined-{days}d-{YYYY-MM-DD}.json` (always written, even for single-platform runs — it's the index)

If `combined-{days}d-{today}.json` exists AND `--refresh` was NOT passed → use cached data, skip fetching. Otherwise → fetch fresh data.

### 3. Fetch data

Run the fetcher:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/fetch.py \
  --platform <name|all> \
  --days <N> \
  --output-dir ~/.claude/social-analytics/cache \
  [--no-replies] [--top-replies 3]
```

Progress appears on stderr. Skipped platforms are shown as `SKIP <platform>: <reason>` messages — surface them to the user so they know which platforms aren't contributing to the report.

Exit codes:
- `0` → at least one platform succeeded
- `1` → no platforms produced data (all missing tokens or all errored)

### 4. Read and analyze the JSON

Read `combined-{days}d-{today}.json`. Its shape:

```json
{
  "fetched_at": "ISO timestamp",
  "days": 30,
  "since": "ISO timestamp",
  "requested_platforms": ["threads", "facebook", "instagram", "linkedin", "tiktok"],
  "succeeded_platforms": ["threads", "linkedin"],
  "skipped_platforms": ["facebook", "instagram", "tiktok"],
  "platforms": {
    "<platform>": {
      "platform": "<name>",
      "profile": { ... },
      "account_insights": { ... },
      "posts": [
        {
          "platform": "<name>",
          "id": "...",
          "url": "...",
          "text": "...",
          "posted_at": "ISO",
          "media_type": "TEXT|IMAGE|VIDEO|CAROUSEL|LINK|UNKNOWN",
          "metrics": {
            "impressions": int|null,
            "reach": int|null,
            "likes": int|null,
            "comments": int|null,
            "shares": int|null,
            "saves": int|null,
            "clicks": int|null,
            "video_views": int|null
          },
          "replies": [ ... ],
          "raw": { ... platform-specific ... }
        }
      ]
    }
  }
}
```

**Important — `null` metrics are not zero.** A `null` means the platform doesn't expose that metric (e.g. Threads doesn't expose `reach`; TikTok doesn't expose `saves`). In tables, show `—` or `N/A`, not `0`.

### 5. Produce one independent report per succeeded platform

For **each** platform in `succeeded_platforms`, produce a full report with these sections:

#### Overview
- Total posts in period, posts per week average
- Total and average impressions, likes, comments, shares (and saves/reach/clicks where available)
- Overall engagement rate: `(likes + comments + shares + saves) / impressions`
  - Omit terms that are `null` for this platform
  - If impressions is `null`, report engagement as raw interaction totals only
- Follower count (from `account_insights` or `profile.follower_count`)

#### Top & Bottom Posts
- Top N posts by engagement rate (with text preview, date, metrics, URL)
- Bottom N posts by engagement rate
- Top N by raw impressions/views

#### Media Type Breakdown
- Count and average engagement by `media_type` (TEXT, IMAGE, VIDEO, CAROUSEL, LINK)

#### Timing Patterns
- Hour-of-day distribution (in user's apparent timezone, inferred from post timestamps)
- Day-of-week distribution
- Best posting times by engagement rate
- Posting frequency trend: week-over-week post counts

#### Conversation Depth
- Posts with most replies/comments
- Average reply count
- Notable conversations (interesting reply content, if fetched)

#### Topic Classification
Read each post's text and assign 1–2 topic labels from organic categories that emerge from the content. Do not use a fixed taxonomy — let the topics arise naturally. Then aggregate:
- Post count per topic
- Average engagement per topic
- Trending vs declining topics (first half vs second half of period)

#### Per-Platform Recommendations
Generate 3–5 actionable recommendations scoped to this platform, each with:
- **What to do** — specific, concrete action
- **Supporting data** — the numbers backing it
- **Confidence** — high/medium/low based on sample size and signal strength

### 6. Cross-platform comparison (when ≥2 platforms succeeded)

After the per-platform reports, produce a **Cross-Platform Analysis** section:

#### Platform at a Glance
Single table comparing:
- Posts in period
- Follower count
- Average engagement rate (flag when not comparable — e.g. LinkedIn without `impressions`)
- Best-performing media type
- Most active posting day/hour

#### Topic Performance Across Platforms
- Which topics (from classification) show up on multiple platforms?
- Which platform gives the best engagement for each shared topic?
- Topics that are platform-exclusive and why that might be

#### Audience & Timing Divergence
- Do best posting times differ between platforms?
- Any topic that performs on one platform and flops on another?
- Format preferences (e.g. "LinkedIn prefers text, Instagram prefers carousels")

#### Cross-Platform Recommendations
3–5 recommendations that specifically leverage running on multiple platforms:
- Cross-post opportunities (topic X works on both Threads and LinkedIn)
- Platform specialization (put video experiments on TikTok, text on Threads)
- Gaps worth filling (strong engagement on platform A, no presence on platform B)
- Where to stop duplicating effort

### 7. Output format

Present as a well-structured Markdown report:

1. **TL;DR** at the top — the 3 most important findings across everything
2. Platform list with "succeeded" vs "skipped" status (clarify what's missing and why)
3. One section per succeeded platform (step 5)
4. Cross-platform analysis (step 6) when ≥2 platforms succeeded
5. Use tables for tabular data; mark `null` metrics as `—`
6. For each recommendation, include the supporting numbers inline

If only one platform succeeded, skip the cross-platform section entirely and note this at the top of the report.
