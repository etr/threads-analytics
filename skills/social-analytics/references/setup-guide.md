# Social Analytics Setup Guide

This plugin supports five platforms. You only need to configure the ones you
actually want analyzed — the fetcher runs on **optimistic auth**: if the token
for a platform is set, it's used; otherwise that platform is skipped and we
move on.

All tokens can be set as environment variables or in a `.env` file (project
directory or `~/.env`).

## Quick reference

| Platform | Required env var | Optional env var | Where to create the app | Token lifetime |
|---|---|---|---|---|
| Threads | `THREADS_ACCESS_TOKEN` | — | [Meta for Developers](https://developers.facebook.com/) | 60 days (refreshable) |
| Facebook Pages | `FACEBOOK_ACCESS_TOKEN` | `FACEBOOK_PAGE_ID` | [Meta for Developers](https://developers.facebook.com/) | Long-lived (Page token) |
| Instagram | `INSTAGRAM_ACCESS_TOKEN` | `INSTAGRAM_USER_ID` | [Meta for Developers](https://developers.facebook.com/) | Long-lived (Page token) |
| LinkedIn | `LINKEDIN_ACCESS_TOKEN` | `LINKEDIN_ORGANIZATION_URN` | [LinkedIn Developer Portal](https://www.linkedin.com/developers/) | 60 days |
| TikTok | `TIKTOK_ACCESS_TOKEN` | — | [TikTok for Developers](https://developers.tiktok.com/) | 24h (refreshable via refresh token, 1 year) |

## Table of contents

- [Threads](#threads)
- [Facebook Pages](#facebook-pages)
- [Instagram](#instagram)
- [LinkedIn](#linkedin)
- [TikTok](#tiktok)
- [Token storage](#token-storage)
- [Verify your tokens](#verify-your-tokens)
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

### 3. Configure a redirect URI
Threads API → **Settings** → **Redirect Callback URLs**. Add at least one URL
(e.g. `https://localhost/`) — Meta requires a registered redirect URI even
for the in-portal token generator.

### 4. Configure permissions
Under **Threads API** → **Permissions**, enable:

| Permission | Purpose |
|---|---|
| `threads_basic` | Read user profile and posts |
| `threads_manage_insights` | Access post and user-level insights |
| `threads_read_replies` | Read conversation threads and replies |

### 5. Add yourself as a test user
While the app is in **Development mode** (the default for new apps), only
added test users can authenticate.

- **App Roles** → **Roles** → **Add People** → enter your Threads/Instagram username
- On your phone, open the Threads app → **Settings** → **Account** → **Website Permissions** → **Tester Invites** → accept the invite

### 6. Generate a short-lived token
1. **Threads API** → **API Setup with Access Tokens**
2. Click **Generate Token** next to your test user
3. Approve the scopes in the popup
4. Copy the token (valid for 1 hour)

### 7. Exchange for a long-lived token (60 days)
Find your **App Secret** in **App Settings** → **Basic** → **App Secret** → **Show**.

```bash
SHORT_TOKEN="paste-short-lived-token"
APP_SECRET="paste-app-secret"

curl -s "https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=${APP_SECRET}&access_token=${SHORT_TOKEN}" \
  | python3 -m json.tool
```

The response includes `access_token` (your long-lived token) and `expires_in`
(seconds, typically `5184000` = 60 days).

### 8. Refresh before expiry
Set a calendar reminder for ~50 days from issuance:

```bash
curl -s "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=${LONG_TOKEN}" \
  | python3 -m json.tool
```

### 9. Rate limits
Threads API enforces ~250 calls/user/hour and ~1000/24h. The provider tracks
the call count and warns/aborts as the soft ceiling (900) is approached.

---

## Facebook Pages

**Environment variables:**
- `FACEBOOK_ACCESS_TOKEN` (required)
- `FACEBOOK_PAGE_ID` (optional — falls back to `/me` on a Page access token)

> **This only works for Facebook Pages you manage**, not personal profiles. The Graph API does not expose analytics for personal Facebook profiles.

### 1. Create a Meta App (or reuse the Threads one)
Same as Threads step 1 (you can reuse the same Meta app for all three Meta
platforms — Threads, Facebook, Instagram).

### 2. Add the Facebook Login product
**Add Products** → **Facebook Login for Business** → **Set Up**. Under
**Facebook Login** → **Settings**, add a redirect URI (e.g.
`https://localhost/`).

### 3. Required permissions
| Permission | Purpose |
|---|---|
| `pages_read_engagement` | Read posts, comments, and reactions |
| `pages_show_list` | List Pages you manage |
| `read_insights` | Per-post and Page-level insights |

### 4. Generate a User Access Token
1. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. In the top-right, select **your app** from the **Meta App** dropdown
3. Click **Generate Access Token**
4. A consent dialog pops up — enable the three permissions above and authorize
5. Copy the **User Access Token** (valid 1–2 hours)

### 5. Exchange for a long-lived User token (60 days)
Find your **App ID** and **App Secret** in **App Settings** → **Basic**.

```bash
APP_ID="your-app-id"
APP_SECRET="your-app-secret"
SHORT_TOKEN="paste-user-access-token"

curl -s "https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${APP_ID}&client_secret=${APP_SECRET}&fb_exchange_token=${SHORT_TOKEN}" \
  | python3 -m json.tool
```

### 6. Swap to a Page Access Token
A Page Access Token derived from a long-lived User token **does not expire**
as long as your password doesn't change and you don't revoke the app.

```bash
LONG_USER_TOKEN="paste-long-lived-user-token"

curl -s "https://graph.facebook.com/v19.0/me/accounts?access_token=${LONG_USER_TOKEN}" \
  | python3 -m json.tool
```

The response contains one object per Page you manage with:
- `id` → this is your `FACEBOOK_PAGE_ID`
- `access_token` → this is your `FACEBOOK_ACCESS_TOKEN`
- `name` → the Page name

Copy the right Page's `id` and `access_token`.

### 7. Store the values
```bash
export FACEBOOK_ACCESS_TOKEN="EAAG..."
export FACEBOOK_PAGE_ID="123456789012345"
```

If `FACEBOOK_PAGE_ID` is unset, the fetcher calls `/me` which on a Page access
token resolves to the Page itself — so the env var is technically optional
when the token is Page-scoped.

---

## Instagram

**Environment variables:**
- `INSTAGRAM_ACCESS_TOKEN` (required)
- `INSTAGRAM_USER_ID` (optional if `FACEBOOK_PAGE_ID` is set — we resolve the linked Instagram Business account automatically)

> **Instagram analytics require a Business or Creator account linked to a Facebook Page.** Personal Instagram accounts are not supported by the Graph API.

### 1. Convert your Instagram to Business or Creator
In the Instagram app: **Settings** → **Account** → **Account Type and tools**
→ **Switch to Professional Account** → choose **Business** or **Creator**.

### 2. Link the Instagram account to a Facebook Page
- Desktop Facebook → open the Page you own → **Settings** → **Linked Accounts** → **Instagram** → **Connect**
- Or in the Meta Business Suite: **Settings** → **Business Assets** → **Instagram accounts** → **Add**

### 3. Use the same Meta app as Facebook
You can share the same app you set up for Facebook Pages. Go to
**Add Products** → **Instagram Graph API** → **Set Up** if it's not already
enabled.

### 4. Required permissions
| Permission | Purpose |
|---|---|
| `instagram_basic` | Read profile and media |
| `instagram_manage_insights` | Per-post and account-level insights |
| `pages_show_list` | Needed to discover the linked IG account |
| `pages_read_engagement` | Required alongside the above for media access |

### 5. Generate a token
Use the Graph API Explorer exactly as in the Facebook section above, adding
the four permissions listed here. The resulting Page access token also
authorizes Instagram calls for the linked IG Business account — you typically
reuse the same token:

```bash
export INSTAGRAM_ACCESS_TOKEN="$FACEBOOK_ACCESS_TOKEN"
```

### 6. Find your Instagram Business Account ID (optional)
If `FACEBOOK_PAGE_ID` is set, the fetcher auto-resolves this. To set it
explicitly (useful for scripts):

```bash
curl -s "https://graph.facebook.com/v19.0/${FACEBOOK_PAGE_ID}?fields=instagram_business_account&access_token=${INSTAGRAM_ACCESS_TOKEN}" \
  | python3 -m json.tool
```

The returned `instagram_business_account.id` is your `INSTAGRAM_USER_ID`:

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
2. **Create app** — fill in name, an associated company Page, and a logo (all required)
3. In the **Auth** tab, note your **Client ID** and **Client Secret** — you'll
   need them for the token exchange

### 2. Configure the redirect URL
Still in the **Auth** tab → **OAuth 2.0 settings** → **Authorized redirect
URLs for your app** → **Add redirect URL**. For local development,
`https://localhost/` works.

### 3. Add products
In the **Products** tab, request:
- **Share on LinkedIn** (usually auto-approved)
- **Sign In with LinkedIn using OpenID Connect** (usually auto-approved)
- **Marketing Developer Platform** (optional, requires an application + review
  process that can take weeks; needed for impression counts and organizational
  share statistics)

### 4. Required scopes
| Scope | Purpose |
|---|---|
| `r_member_social` | Read authenticated member's posts & social actions (member mode) |
| `r_organization_social` | Read organization posts & social actions (org mode) |
| `rw_organization_admin` | Required for `organizationalEntityShareStatistics` |
| `openid`, `profile`, `email` | Identify the authenticated member |

### 5. OAuth 2.0 flow

**Step 1 — Build the authorization URL** (replace `YOUR_CLIENT_ID` and
`YOUR_REDIRECT_URI`, URL-encoded):

```
https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI&state=random-state-string&scope=r_member_social%20openid%20profile%20email
```

Open that URL in your browser, approve the consent screen, and copy the
`code` parameter from the redirect URL.

**Step 2 — Exchange the code for an access token:**

```bash
CODE="paste-code-from-redirect"
CLIENT_ID="your-client-id"
CLIENT_SECRET="your-client-secret"
REDIRECT_URI="https://localhost/"

curl -X POST https://www.linkedin.com/oauth/v2/accessToken \
  -d "grant_type=authorization_code" \
  -d "code=${CODE}" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "redirect_uri=${REDIRECT_URI}"
```

The response contains `access_token` (valid 60 days) and `expires_in`.

**Quick-start alternative**: the LinkedIn Developer Portal has an **OAuth 2.0
Tools** tab that generates a token against your own account without the
manual URL dance. Use that for testing.

### 6. Organization mode (optional)
To analyze a company Page instead of your personal posts:

1. You must be an admin of the LinkedIn organization
2. Your app needs `r_organization_social` approved
3. Find the organization URN via the REST API:
   ```bash
   curl -s https://api.linkedin.com/rest/me \
     -H "Authorization: Bearer ${LINKEDIN_ACCESS_TOKEN}" \
     -H "LinkedIn-Version: 202405" \
     -H "X-Restli-Protocol-Version: 2.0.0"
   ```
4. Set the URN:
   ```bash
   export LINKEDIN_ORGANIZATION_URN="urn:li:organization:12345678"
   ```

### 7. What to expect without Marketing Developer Platform approval
- Post list and text — yes
- Aggregated likes/comments/shares per post (via `socialActions/{urn}`) — yes
- Impressions per post — no
- Organization-level share statistics — no

The fetcher will leave `impressions` as `null` for LinkedIn posts in that
case, and the skill will mark engagement rates as N/A. The provider
automatically sends the required `LinkedIn-Version: 202405` and
`X-Restli-Protocol-Version: 2.0.0` headers — you don't need to set them.

---

## TikTok

**Environment variable:** `TIKTOK_ACCESS_TOKEN`

### 1. Create a TikTok app
1. Go to [TikTok for Developers](https://developers.tiktok.com/)
2. **Manage Apps** → **Connect an app** → fill in app name, description, category, platform
3. Under **Add products**, enable **Login Kit** and **Display API**
4. In the **App info** panel, note your **Client Key** and **Client Secret**

### 2. Configure the redirect URI
In the **Login Kit** product settings, add a **Redirect URI**
(e.g. `https://localhost/`). TikTok will reject the token exchange if the
`redirect_uri` you pass doesn't match one registered here exactly.

### 3. Required scopes
| Scope | Purpose |
|---|---|
| `user.info.basic` | Read profile (display name, follower count, etc.) |
| `video.list` | List the authenticated user's videos |

Enable these in **Login Kit** → **Scopes**. `video.list` returns per-video
stats (views, likes, comments, shares) inline — there's no separate insights
endpoint to call.

### 4. Add yourself as a sandbox user
New apps start in **sandbox mode**. Only videos posted by users explicitly
added to your sandbox will appear in `video.list`. In the app dashboard:

- **Sandbox** tab → **Target Users** → **Add Users** → enter your TikTok username
- Accept the invite from your TikTok account

To access a broader set of users you must submit the app for review and
request production mode — expect a manual review.

> **Gotcha:** videos marked as private by the user will **not** appear in
> `video.list`, even for the authenticated user. If the fetcher reports zero
> videos and you know there should be some, check that at least one is public.

### 5. OAuth 2.0 flow

**Step 1 — Build the authorization URL** (replace `YOUR_CLIENT_KEY` and
`YOUR_REDIRECT_URI`, URL-encoded):

```
https://www.tiktok.com/v2/auth/authorize/?client_key=YOUR_CLIENT_KEY&response_type=code&scope=user.info.basic,video.list&redirect_uri=YOUR_REDIRECT_URI&state=random-state-string
```

Open it, approve the scopes, and copy the `code` parameter from the redirect.

**Step 2 — Exchange the code for an access token:**

```bash
CODE="paste-code-from-redirect"
CLIENT_KEY="your-client-key"
CLIENT_SECRET="your-client-secret"
REDIRECT_URI="https://localhost/"

curl -X POST https://open.tiktokapis.com/v2/oauth/token/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_key=${CLIENT_KEY}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "code=${CODE}" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=${REDIRECT_URI}"
```

The response contains:
- `access_token` — valid 24 hours (this is `TIKTOK_ACCESS_TOKEN`)
- `refresh_token` — valid 365 days
- `expires_in` — seconds until access token expiry

### 6. Refresh the access token
TikTok access tokens are short-lived. Refresh before expiry:

```bash
curl -X POST https://open.tiktokapis.com/v2/oauth/token/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_key=${CLIENT_KEY}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=${REFRESH_TOKEN}"
```

### 7. What's not supported
- Comments — the public Display API does not expose video comments
- Hashtag research / competitor data — Research API is approval-gated and not wired up here

The TikTok provider leaves `replies: []` for every video and the skill will
skip the Conversation Depth section for TikTok.

---

## Token storage

**Option A — environment variables:**
```bash
export THREADS_ACCESS_TOKEN="..."
export FACEBOOK_ACCESS_TOKEN="..."
export FACEBOOK_PAGE_ID="..."
export INSTAGRAM_ACCESS_TOKEN="..."
export INSTAGRAM_USER_ID="..."
export LINKEDIN_ACCESS_TOKEN="..."
export LINKEDIN_ORGANIZATION_URN="urn:li:organization:12345"
export TIKTOK_ACCESS_TOKEN="..."
```

**Option B — `.env` file** (in your project directory or `~/.env`):
```
THREADS_ACCESS_TOKEN=...
FACEBOOK_ACCESS_TOKEN=...
FACEBOOK_PAGE_ID=...
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_USER_ID=...
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_ORGANIZATION_URN=urn:li:organization:12345
TIKTOK_ACCESS_TOKEN=...
```

The fetcher loads environment variables first and then `.env` (via
`python-dotenv` if installed).

## Verify your tokens

Before invoking `/social-analytics`, run the smoke test matching each platform
you've configured. A successful JSON response with your identity means the
token is good.

### Threads
```bash
curl -s "https://graph.threads.net/v1.0/me?fields=id,username&access_token=${THREADS_ACCESS_TOKEN}" \
  | python3 -m json.tool
```
Expected: `{"id": "...", "username": "your_handle"}`.

### Facebook
```bash
curl -s "https://graph.facebook.com/v19.0/me?fields=id,name&access_token=${FACEBOOK_ACCESS_TOKEN}" \
  | python3 -m json.tool
```
Expected: `{"id": "...", "name": "Your Page Name"}` (a Page name, not your
personal name — if you see a personal name, you're still using a User token).

### Instagram
```bash
curl -s "https://graph.facebook.com/v19.0/${INSTAGRAM_USER_ID:-$FACEBOOK_PAGE_ID?fields=instagram_business_account}?access_token=${INSTAGRAM_ACCESS_TOKEN}" \
  | python3 -m json.tool
```
Expected: your IG handle and follower count (or the linked `instagram_business_account.id` if you passed the Page ID).

### LinkedIn
```bash
curl -s https://api.linkedin.com/v2/userinfo \
  -H "Authorization: Bearer ${LINKEDIN_ACCESS_TOKEN}" \
  | python3 -m json.tool
```
Expected: `{"sub": "...", "name": "Your Name", ...}`.

### TikTok
```bash
curl -s -X POST "https://open.tiktokapis.com/v2/user/info/?fields=open_id,display_name,follower_count" \
  -H "Authorization: Bearer ${TIKTOK_ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}' \
  | python3 -m json.tool
```
Expected: `{"data": {"user": {"open_id": "...", "display_name": "..."}}}`.

## Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `SKIP <platform>: <VAR> not set` | Token env var missing | Set it, or ignore if you don't want that platform |
| `SKIP <platform>: auth error` | Token expired / wrong scopes | Regenerate the token with the scopes listed above |
| `SKIP <platform>: rate limited` | Hit soft rate-limit ceiling | Wait a few hours, re-run with `--refresh` |
| Meta OAuth code `190` | Token expired or invalidated | Generate a new token |
| Meta OAuth code `10` | Missing permissions | Re-authorize with full scope set |
| Meta OAuth code `100` + "Unsupported get request" | Facebook Page ID wrong, or you're querying `/me` with a User token | Use `/me/accounts` to get the right Page token + ID |
| `429` from any provider | Short-term rate-limit | The provider backs off and retries automatically |
| LinkedIn `401 Unauthorized` | Missing `LinkedIn-Version` header or expired token | The provider sets the header automatically — regenerate the token |
| LinkedIn posts with `null` impressions | No Marketing Developer Platform approval | Apply for MDP, or accept that impression data is unavailable |
| Instagram returns empty data | Personal (non-Business) IG account, or Page not linked | Convert to Business/Creator and link to a Page (steps 1–2) |
| TikTok `video/list` returns empty | User not added as sandbox tester, or all videos are private | Add user to sandbox, or make at least one video public |
| TikTok `access_token_invalid` | 24-hour token expired | Use the refresh token to get a new access token |
