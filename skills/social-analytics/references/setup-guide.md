# Social Analytics Setup Guide

This plugin supports five platforms. You only need to configure the ones you
actually want analyzed — the fetcher runs on **optimistic auth**: if the token
for a platform is set, it's used; otherwise that platform is skipped and we
move on.

All tokens can be set as environment variables or in a `.env` file (project
directory or `~/.env`).

## Table of contents

- [Threads](#threads)
- [Facebook Pages](#facebook-pages)
- [Instagram](#instagram)
- [LinkedIn](#linkedin)
- [TikTok](#tiktok)
- [Token storage](#token-storage)
- [Troubleshooting](#troubleshooting)

---

## Threads

**Environment variable:** `THREADS_ACCESS_TOKEN`

### 1. Create a Meta App
1. Go to [Meta for Developers](https://developers.facebook.com/)
2. **My Apps** → **Create App**
3. Use case: **Other** → App type: **Business**
4. Name it (e.g. "Social Analytics") and fill in the contact email
5. **Create App**

### 2. Add the Threads API product
In your app dashboard, scroll to **Add Products**, find **Threads API**, click **Set Up**.

### 3. Configure permissions
Under **Threads API** → **Permissions**, enable:

| Permission | Purpose |
|---|---|
| `threads_basic` | Read user profile and posts |
| `threads_manage_insights` | Access post and user-level insights |
| `threads_read_replies` | Read conversation threads and replies |

### 4. Add yourself as a test user
- **App Roles** → **Roles** → **Add People**
- Accept the invite from the Threads app: Settings → Account → Website Permissions → Tester Invites

### 5. Generate a long-lived token
1. **Threads API** → **API Setup with Access Tokens** → **Generate Token**
2. Exchange the short-lived token for a long-lived one (60 days):
   ```bash
   curl -s "https://graph.threads.net/access_token?\
   grant_type=th_exchange_token&\
   client_secret=YOUR_APP_SECRET&\
   access_token=YOUR_SHORT_LIVED_TOKEN" | python3 -m json.tool
   ```
3. Refresh before expiry:
   ```bash
   curl -s "https://graph.threads.net/refresh_access_token?\
   grant_type=th_refresh_token&\
   access_token=YOUR_LONG_LIVED_TOKEN" | python3 -m json.tool
   ```

### 6. Rate limits
Threads API enforces ~250 calls/user/hour and ~1000/24h. The provider tracks
the call count and warns/aborts as limits approach.

---

## Facebook Pages

**Environment variables:**
- `FACEBOOK_ACCESS_TOKEN` (required)
- `FACEBOOK_PAGE_ID` (optional — falls back to `/me` on a Page access token)

> **This only works for Facebook Pages you manage**, not personal profiles. The Graph API does not expose analytics for personal Facebook profiles.

### 1. Create a Meta App
Same as Threads step 1 (you can reuse the same Meta app).

### 2. Add the Facebook Login product
**Add Products** → **Facebook Login** → **Set Up**.

### 3. Required permissions
| Permission | Purpose |
|---|---|
| `pages_read_engagement` | Read posts, comments, and reactions |
| `pages_show_list` | List Pages you manage |
| `read_insights` | Per-post and Page-level insights |

### 4. Generate a Page access token
1. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select your app, then generate a **User Access Token** with the three permissions above
3. Query `/me/accounts` to get your Pages and their access tokens
4. Use the **Page access token** from the response (it's long-lived by default)

### 5. Optional: set the Page ID explicitly
```bash
export FACEBOOK_ACCESS_TOKEN="your-page-token"
export FACEBOOK_PAGE_ID="123456789012345"
```
If `FACEBOOK_PAGE_ID` is unset, the fetcher calls `/me` which on a Page access token resolves to the Page itself.

---

## Instagram

**Environment variables:**
- `INSTAGRAM_ACCESS_TOKEN` (required)
- `INSTAGRAM_USER_ID` (optional if `FACEBOOK_PAGE_ID` is set — we resolve the linked Instagram Business account automatically)

> **Instagram analytics require a Business or Creator account linked to a Facebook Page.** Personal Instagram accounts are not supported by the Graph API.

### 1. Link your Instagram account to a Facebook Page
On desktop Facebook: **Page Settings** → **Linked Accounts** → **Instagram**.

### 2. Use the same Meta app as Facebook
You can share the same app you set up for Facebook Pages.

### 3. Required permissions
| Permission | Purpose |
|---|---|
| `instagram_basic` | Read profile and media |
| `instagram_manage_insights` | Per-post and account-level insights |
| `pages_show_list` | Needed to discover the linked IG account |

### 4. Generate a token
Use the Graph API Explorer exactly as in the Facebook section above, adding the three permissions listed here. The resulting Page access token also authorizes Instagram calls for the linked IG Business account.

You can typically reuse `FACEBOOK_ACCESS_TOKEN` as `INSTAGRAM_ACCESS_TOKEN` when the same Page/IG link is involved:
```bash
export INSTAGRAM_ACCESS_TOKEN="$FACEBOOK_ACCESS_TOKEN"
```

### 5. Find your Instagram user ID (optional)
```bash
curl -s "https://graph.facebook.com/v19.0/$FACEBOOK_PAGE_ID?fields=instagram_business_account&access_token=$INSTAGRAM_ACCESS_TOKEN"
```
Set it explicitly if you want to skip the auto-resolution:
```bash
export INSTAGRAM_USER_ID="17841400000000000"
```

---

## LinkedIn

**Environment variables:**
- `LINKEDIN_ACCESS_TOKEN` (required)
- `LINKEDIN_ORGANIZATION_URN` (optional — enables Organization mode)

> **Heads up:** LinkedIn's richer analytics endpoints (share statistics, organizational reach) require **Marketing Developer Platform** approval. Without approval, member-level fetches will still return posts and aggregated social actions (likes/comments/shares) but not impression counts.

### 1. Create a LinkedIn app
1. Go to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/)
2. **Create app**, fill in name, company page, and logo
3. In **Products**, add:
   - **Share on LinkedIn** (basic)
   - **Sign In with LinkedIn using OpenID Connect**
   - **Marketing Developer Platform** (optional, requires application + approval)

### 2. Required scopes
| Scope | Purpose |
|---|---|
| `r_member_social` | Read authenticated member's posts & social actions (member mode) |
| `r_organization_social` | Read organization posts & social actions (org mode) |
| `rw_organization_admin` | Required for `organizationalEntityShareStatistics` |
| `openid`, `profile`, `email` | Identify the authenticated member |

### 3. OAuth 2.0 flow
1. Direct yourself to LinkedIn's authorization URL with the scopes above
2. Exchange the returned code for an access token at `/oauth/v2/accessToken`
3. The token is valid for 60 days

Quick-start: use the OAuth 2.0 tools tab in the Developer Portal to mint a token against your own account.

### 4. Organization vs member mode
- **Member mode (default):** no extra env var. Fetches your own posts.
- **Organization mode:** set `LINKEDIN_ORGANIZATION_URN`:
  ```bash
  export LINKEDIN_ORGANIZATION_URN="urn:li:organization:12345678"
  ```
  You must be an admin of the organization and your app must have `r_organization_social` approved.

### 5. What to expect without Marketing Developer Platform approval
- Post list and text — yes
- Aggregated likes/comments/shares per post (via `socialActions/{urn}`) — yes
- Impressions per post — no
- Organization-level share statistics — no

The fetcher will leave `impressions` as `null` for LinkedIn posts in that case, and the skill will mark engagement rates as N/A.

---

## TikTok

**Environment variable:** `TIKTOK_ACCESS_TOKEN`

### 1. Create a TikTok app
1. Go to [TikTok for Developers](https://developers.tiktok.com/)
2. **Manage Apps** → **Connect an app**
3. Fill in the app basics and request the **Login Kit** + **Display API** products

### 2. Required scopes
| Scope | Purpose |
|---|---|
| `user.info.basic` | Read profile (display name, follower count, etc.) |
| `video.list` | List the authenticated user's videos |

`video.list` returns per-video stats (views, likes, comments, shares) inline — there's no separate insights endpoint to call.

### 3. OAuth 2.0 flow
1. Direct yourself to TikTok's authorization URL with the scopes above
2. Exchange the returned code at `https://open.tiktokapis.com/v2/oauth/token/`
3. Access tokens are short-lived (24h). Refresh tokens are valid for 365 days.

### 4. What's not supported
- Comments — the public Display API does not expose video comments
- Hashtag research / competitor data — Research API is approval-gated and not wired up here

The TikTok provider leaves `replies: []` for every video and the skill will skip the Conversation Depth section for TikTok.

---

## Token storage

**Option A — environment variables:**
```bash
export THREADS_ACCESS_TOKEN="..."
export FACEBOOK_ACCESS_TOKEN="..."
export FACEBOOK_PAGE_ID="..."
export INSTAGRAM_ACCESS_TOKEN="..."
export LINKEDIN_ACCESS_TOKEN="..."
export TIKTOK_ACCESS_TOKEN="..."
```

**Option B — `.env` file** (in your project directory or `~/.env`):
```
THREADS_ACCESS_TOKEN=...
FACEBOOK_ACCESS_TOKEN=...
FACEBOOK_PAGE_ID=...
INSTAGRAM_ACCESS_TOKEN=...
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_ORGANIZATION_URN=urn:li:organization:12345
TIKTOK_ACCESS_TOKEN=...
```

The fetcher loads environment variables first and then `.env` (via `python-dotenv` if installed).

## Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `SKIP <platform>: <VAR> not set` | Token env var missing | Set it, or ignore if you don't want that platform |
| `SKIP <platform>: auth error` | Token expired / wrong scopes | Regenerate the token with the scopes listed above |
| `SKIP <platform>: rate limited` | Hit soft rate-limit ceiling | Wait a few hours, re-run with `--refresh` |
| Meta OAuth code `190` | Token expired or invalidated | Generate a new token |
| Meta OAuth code `10` | Missing permissions | Re-authorize with full scope set |
| `429` from any provider | Short-term rate-limit | The provider backs off and retries automatically |
| LinkedIn posts with `null` impressions | No Marketing Developer Platform approval | Apply for MDP, or accept that impression data is unavailable |
| Instagram returns empty data | Personal (non-Business) IG account | Convert to Business/Creator and link to a Page |
