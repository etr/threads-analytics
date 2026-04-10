# Threads API Setup Guide

## 1. Create a Meta App

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Click **My Apps** → **Create App**
3. Select **Other** as the use case → **Business** as the app type
4. Fill in app name (e.g. "Threads Analytics") and contact email
5. Click **Create App**

## 2. Add the Threads API Product

1. In your app dashboard, scroll to **Add Products**
2. Find **Threads API** and click **Set Up**
3. The Threads API product will appear in the left sidebar

## 3. Configure Permissions

Under **Threads API** → **Permissions**, ensure these are enabled:

| Permission | Purpose |
|---|---|
| `threads_basic` | Read user profile and posts |
| `threads_manage_insights` | Access post and user-level insights/metrics |
| `threads_read_replies` | Read conversation threads and replies |

## 4. Add Yourself as a Test User

1. Go to **App Roles** → **Roles**
2. Click **Add People** → enter your Threads/Instagram username
3. Accept the invitation from your Threads account settings:
   - Threads app → Settings → Account → Website Permissions → Tester Invites

> **Note**: While your app is in Development mode, only added test users can authenticate.

## 5. Generate an Access Token

### Short-Lived Token (1 hour)

1. Go to **Threads API** → **API Setup with Access Tokens**
2. Click **Generate Token** for your test user
3. Approve the permissions in the popup
4. Copy the token

### Exchange for Long-Lived Token (60 days)

```bash
curl -s "https://graph.threads.net/access_token?\
grant_type=th_exchange_token&\
client_secret=YOUR_APP_SECRET&\
access_token=YOUR_SHORT_LIVED_TOKEN" | python3 -m json.tool
```

The response contains your long-lived `access_token` and `expires_in` (seconds).

## 6. Store the Token

Option A — environment variable:
```bash
export THREADS_ACCESS_TOKEN="your-long-lived-token"
```

Option B — `.env` file (in your project directory or home directory):
```
THREADS_ACCESS_TOKEN=your-long-lived-token
```

The fetcher checks the env var first, then falls back to `.env`.

## 7. Token Refresh

Long-lived tokens expire after **60 days**. Refresh before expiry:

```bash
curl -s "https://graph.threads.net/refresh_access_token?\
grant_type=th_refresh_token&\
access_token=YOUR_LONG_LIVED_TOKEN" | python3 -m json.tool
```

This returns a new 60-day token. The old one is invalidated.

**Tip**: Set a calendar reminder for ~50 days to refresh your token.

## Rate Limits

The Threads API enforces **250 calls per user per hour** and approximately **1000 calls per 24-hour period**. The fetcher tracks call counts and warns/aborts as limits approach.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `OAuthException` code 190 | Token expired or invalid | Generate a new token (steps 5-6) |
| `OAuthException` code 10 | Missing permissions | Check step 3, re-authorize |
| 429 response | Rate limit hit | Wait and retry (fetcher handles this automatically) |
| Empty data | User not a tester | Complete step 4 |
