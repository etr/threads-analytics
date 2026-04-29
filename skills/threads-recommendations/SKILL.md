---
name: threads-recommendations
description: Surface Threads posts the user may find interesting, based on their posting history (topics, hashtags, who they mention) plus optional seed topics. Claude scores and ranks the candidates.
---

# Threads Recommendations

Recommend public Threads posts that match the user's interests. The fetcher script collects raw candidates via the Threads `keyword_search` endpoint; you do all the scoring and ranking.

## Arguments

Parse the user's input:
- Bare number → `--days N` for the history window (default 30)
- `--seeds "topic1, topic2"` → user-supplied keywords that bias recommendations
- `--recent` → use `RECENT` search type instead of `TOP`
- `--refresh` → ignore cached history, re-fetch
- `--top N` → number of recommendations to surface in the final report (default 10)

## Workflow

### 1. Pre-flight checks

- `THREADS_ACCESS_TOKEN` exists. If missing, show setup instructions from `${CLAUDE_PLUGIN_ROOT}/skills/threads-analytics/references/setup-guide.md` and stop.
- `python3` and `requests` are available.
- The `threads_keyword_search` permission is required. If the fetcher exits with code 4, tell the user this permission must be added to their Meta app and link them to the setup guide. Do not retry.

### 2. Make sure history is available

Recommendations need a history dossier to derive interest signals.

Cache location: `~/.claude/threads-analytics/cache/threads-data-{days}d-{YYYY-MM-DD}.json`

- If a cache file for today + the requested day count exists and `--refresh` was not passed, reuse it.
- Otherwise, run the history fetcher first:
  ```bash
  python3 ${CLAUDE_PLUGIN_ROOT}/scripts/fetch.py --days <N> --output <history_cache_path> --no-replies
  ```
  `--no-replies` is fine here — recommendations don't need conversation depth.

### 3. Fetch candidate posts

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/recommend.py \
  --history <history_cache_path> \
  --output <reco_cache_path> \
  [--seeds "topic1, topic2"] \
  [--search-type RECENT]
```

Cache output at: `~/.claude/threads-analytics/cache/threads-recos-{YYYY-MM-DD}.json`

Exit codes:
- 1 → input/auth error → show setup guide or run history fetcher first
- 2 → rate limit → tell user to wait
- 3 → token expired → show refresh instructions
- 4 → **missing `threads_keyword_search` permission** → tell user to add it in their Meta app dashboard (Threads API → Permissions), then re-authorize and regenerate the token. Link to setup guide.

### 4. Read and analyze the JSON

The dossier contains:
- `signals` — extracted hashtags and mentions from the user's history
- `queries_run` — the actual searches issued
- `candidates_by_query` — public posts returned per query, deduped, with the user's own posts filtered out

For each candidate, score against:
- **Topical fit** — does the post text actually relate to the user's interest signals, or did it just happen to contain a keyword? (Read the text — don't just trust the match.)
- **Quality signals** — does the post look substantive (not spam, not engagement bait)? Length, specificity, presence of a real point.
- **Recency** — newer posts are more actionable.
- **Seed alignment** — if the user supplied seeds, weight matches against them more heavily.

### 5. Output format

Present a markdown report with:

#### TL;DR
Three sentences: which themes dominate the recommendations, any surprises, and your top pick.

#### Interest signals (what we used)
- Top hashtags from history
- Top mentions/reply targets from history (proxy for follows — the API doesn't expose follows directly)
- Seeds, if supplied

#### Recommended posts (top N)
For each: username, permalink, ~200-char snippet, why it's relevant to this user, your confidence (high/medium/low).

#### Themes that emerged
Cluster the top recommendations into 2-4 themes and name each one.

#### Caveats
- The Threads API has no follows or communities endpoint, so those signals are approximated from the user's own @-mentions and hashtags.
- `keyword_search` returns public posts only.
- If the user wants different recommendations, suggest re-running with explicit `--seeds`.
