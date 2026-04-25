"""TikTok provider.

API: TikTok Display API (``open.tiktokapis.com/v2``).
Auth: OAuth 2.0 bearer token with ``user.info.basic`` + ``video.list`` scopes.

This pulls the authenticated user's own videos and basic stats (view count,
like count, comment count, share count). Anything richer than that — hashtag
research, competitor stats — requires the Research API, which is approval-
gated and not supported here.

The Display API uses POST with JSON bodies for most list endpoints, so we
override the usual ``api_get`` path and use ``requests.post`` directly.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Any, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    print("ERROR: 'requests' package required.", file=sys.stderr)
    sys.exit(1)

from .base import (
    Metrics,
    NormalizedPost,
    Profile,
    Provider,
    ProviderAuthError,
    ProviderRateLimited,
    Reply,
)


class TikTokProvider(Provider):
    name = "tiktok"
    display_name = "TikTok"
    token_env_var = "TIKTOK_ACCESS_TOKEN"
    base_url = "https://open.tiktokapis.com/v2"
    rate_limit_budget = 500
    rate_limit_hard = 600

    USER_FIELDS = (
        "open_id,union_id,avatar_url,display_name,bio_description,"
        "profile_deep_link,follower_count,following_count,likes_count,video_count"
    )
    VIDEO_FIELDS = (
        "id,title,video_description,create_time,cover_image_url,share_url,"
        "duration,view_count,like_count,comment_count,share_count,"
        "embed_link,embed_html"
    )

    def _post_json(
        self,
        endpoint: str,
        body: dict[str, Any],
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """POST with JSON body + bearer auth + retries.

        TikTok's list endpoints (``/video/list/``, ``/user/info/``) are POSTs
        even though they read data, so the base class's GET helper is not a
        good fit.
        """

        if self.api_call_count >= self.rate_limit_hard:
            raise ProviderRateLimited(
                f"{self.name}: reached hard rate-limit ceiling ({self.api_call_count} calls)."
            )
        if self.api_call_count == self.rate_limit_budget:
            self._log(f"WARNING: {self.api_call_count} API calls made (soft budget).")

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        for attempt in range(3):
            try:
                resp = requests.post(
                    url, params=params or {}, headers=headers, json=body, timeout=30
                )
                self.api_call_count += 1
            except requests.RequestException as exc:
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                self._log(f"Request error: {exc}")
                return None

            if resp.status_code == 200:
                try:
                    payload = resp.json()
                except ValueError:
                    return None
                # TikTok wraps errors inside 200 responses under payload["error"].
                err = payload.get("error") or {}
                if err.get("code") and err.get("code") != "ok":
                    msg = err.get("message", "")
                    if err.get("code") in {"access_token_invalid", "scope_not_authorized"}:
                        raise ProviderAuthError(f"{self.name}: {msg}")
                    self._log(f"API error: {err.get('code')} — {msg}")
                    return None
                return payload.get("data") or {}

            if resp.status_code == 429:
                time.sleep(2 ** (attempt + 2))
                continue

            if resp.status_code in (401, 403):
                raise ProviderAuthError(
                    f"{self.name}: HTTP {resp.status_code} — token likely expired."
                )

            self._log(f"HTTP {resp.status_code} — {resp.text[:200]}")
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                return None
        return None

    def fetch_profile(self) -> Profile:
        data = self._post_json(
            "user/info/",
            body={},
            params={"fields": self.USER_FIELDS},
        )
        if not data or "user" not in data:
            raise RuntimeError("TikTok: could not fetch user info.")
        user = data["user"]
        return Profile(
            platform=self.name,
            id=str(user.get("open_id", "")),
            username=user.get("display_name"),
            name=user.get("display_name"),
            bio=user.get("bio_description"),
            profile_url=user.get("profile_deep_link"),
            follower_count=user.get("follower_count"),
            extra={
                "likes_count": user.get("likes_count"),
                "video_count": user.get("video_count"),
                "union_id": user.get("union_id"),
            },
        )

    def fetch_posts(self, since: datetime) -> list[dict[str, Any]]:
        since_ts = int(since.timestamp())
        cursor: Optional[int] = None
        all_videos: list[dict[str, Any]] = []
        while True:
            body: dict[str, Any] = {"max_count": 20}
            if cursor:
                body["cursor"] = cursor
            data = self._post_json(
                "video/list/", body=body, params={"fields": self.VIDEO_FIELDS}
            )
            if not data:
                break
            videos = data.get("videos", []) or []
            all_videos.extend(videos)
            if not data.get("has_more") or not videos:
                break
            oldest = min(v.get("create_time", 0) for v in videos)
            if oldest < since_ts:
                break
            cursor = data.get("cursor")
            if cursor is None:
                break
        # Filter to the requested window
        return [v for v in all_videos if v.get("create_time", 0) >= since_ts]

    def fetch_post_insights(self, post_id: str) -> dict[str, Any]:
        # TikTok returns per-video stats inline with /video/list/, so there's
        # nothing extra to fetch here. Return an empty dict and let normalize()
        # pull from the raw post.
        return {}

    def fetch_conversation(self, post_id: str, top_n: int) -> list[Reply]:
        # The Display API does not expose a public comments endpoint; the
        # Research API does, but it's approval-gated. Return empty to stay
        # consistent with the "try and skip" contract.
        return []

    def fetch_account_insights(self) -> dict[str, Any]:
        # Account-level aggregate stats (follower count, total likes) come
        # back from fetch_profile(). Nothing additional to fetch here.
        return {}

    def normalize(
        self, raw_post: dict[str, Any], insights: dict[str, Any]
    ) -> NormalizedPost:
        create_time = raw_post.get("create_time")
        posted_at: Optional[str] = None
        if create_time:
            posted_at = datetime.utcfromtimestamp(create_time).isoformat() + "Z"

        metrics = Metrics(
            impressions=raw_post.get("view_count"),
            likes=raw_post.get("like_count"),
            comments=raw_post.get("comment_count"),
            shares=raw_post.get("share_count"),
            video_views=raw_post.get("view_count"),
        )

        text = raw_post.get("video_description") or raw_post.get("title") or ""

        return NormalizedPost(
            platform=self.name,
            id=str(raw_post.get("id", "")),
            url=raw_post.get("share_url"),
            text=text,
            posted_at=posted_at,
            media_type="VIDEO",
            metrics=metrics,
            raw={
                "duration": raw_post.get("duration"),
                "cover_image_url": raw_post.get("cover_image_url"),
                "embed_link": raw_post.get("embed_link"),
            },
        )
