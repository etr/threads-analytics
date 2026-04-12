"""Facebook Page provider.

API: Facebook Graph API v19.0+ (``graph.facebook.com``).
Auth: Page access token with ``pages_read_engagement`` + ``read_insights``.

Caveats:
- This provider works against a **Facebook Page you manage**, not a personal
  profile. The Graph API does not expose personal-profile analytics.
- The page ID is read from ``FACEBOOK_PAGE_ID``. If it's not set we fall back
  to ``/me``, which on a page token resolves to the page itself.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .base import Metrics, NormalizedPost, Profile, Provider, Reply


class FacebookProvider(Provider):
    name = "facebook"
    display_name = "Facebook"
    token_env_var = "FACEBOOK_ACCESS_TOKEN"
    base_url = "https://graph.facebook.com/v19.0"
    rate_limit_budget = 180
    rate_limit_hard = 200  # BUC is generous, keep our ceiling modest

    POST_FIELDS = (
        "id,message,created_time,permalink_url,status_type,attachments{media_type,type}"
    )
    POST_METRICS = (
        "post_impressions,post_impressions_unique,post_clicks,"
        "post_reactions_by_type_total,post_video_views"
    )
    PAGE_METRICS = (
        "page_impressions,page_impressions_unique,page_post_engagements,"
        "page_fans"
    )

    def __init__(self) -> None:
        super().__init__()
        self.page_id: str = os.environ.get("FACEBOOK_PAGE_ID", "me")

    def fetch_profile(self) -> Profile:
        data = self.api_get(
            self.page_id,
            {"fields": "id,name,username,about,link,fan_count"},
        )
        if not data or "id" not in data:
            raise RuntimeError("Facebook: could not fetch page profile.")
        # Remember the real ID so subsequent calls don't have to resolve /me.
        self.page_id = str(data["id"])
        return Profile(
            platform=self.name,
            id=self.page_id,
            username=data.get("username"),
            name=data.get("name"),
            bio=data.get("about"),
            profile_url=data.get("link"),
            follower_count=data.get("fan_count"),
            extra={"raw": data},
        )

    def fetch_posts(self, since: datetime) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "fields": self.POST_FIELDS,
            "limit": 50,
            "since": int(since.timestamp()),
        }
        url = f"{self.page_id}/posts"
        all_posts: list[dict[str, Any]] = []
        while url:
            data = self.api_get(url, params)
            if not data:
                break
            all_posts.extend(data.get("data", []))
            next_url = data.get("paging", {}).get("next")
            if next_url:
                url = next_url
                params = {}
            else:
                url = None
        return all_posts

    def fetch_post_insights(self, post_id: str) -> dict[str, Any]:
        data = self.api_get(f"{post_id}/insights", {"metric": self.POST_METRICS})
        if not data:
            return {}
        insights: dict[str, Any] = {}
        for item in data.get("data", []):
            name = item.get("name")
            values = item.get("values", [])
            if values:
                insights[name] = values[0].get("value", 0)
        return insights

    def fetch_conversation(self, post_id: str, top_n: int) -> list[Reply]:
        data = self.api_get(
            f"{post_id}/comments",
            {
                "fields": "id,message,created_time,from",
                "limit": top_n,
                "order": "reverse_chronological",
            },
        )
        if not data:
            return []
        replies: list[Reply] = []
        for item in data.get("data", []):
            from_obj = item.get("from") or {}
            replies.append(
                Reply(
                    id=str(item.get("id", "")),
                    text=item.get("message", ""),
                    timestamp=item.get("created_time"),
                    username=from_obj.get("name"),
                )
            )
        return replies

    def fetch_account_insights(self) -> dict[str, Any]:
        data = self.api_get(
            f"{self.page_id}/insights",
            {"metric": self.PAGE_METRICS, "period": "days_28"},
        )
        if not data:
            return {}
        insights: dict[str, Any] = {}
        for item in data.get("data", []):
            name = item.get("name")
            values = item.get("values", [])
            if values:
                # Page insights return a list; take the most recent value.
                insights[name] = values[-1].get("value", 0)
        return insights

    def normalize(
        self, raw_post: dict[str, Any], insights: dict[str, Any]
    ) -> NormalizedPost:
        reactions_total = 0
        reactions = insights.get("post_reactions_by_type_total") or {}
        if isinstance(reactions, dict):
            reactions_total = sum(v for v in reactions.values() if isinstance(v, int))

        metrics = Metrics(
            impressions=insights.get("post_impressions"),
            reach=insights.get("post_impressions_unique"),
            likes=reactions_total or None,
            clicks=insights.get("post_clicks"),
            video_views=insights.get("post_video_views"),
        )

        # Derive media_type from attachments when available.
        media_type = "TEXT"
        attachments = (raw_post.get("attachments") or {}).get("data") or []
        if attachments:
            attach_media = (attachments[0].get("media_type") or "").upper()
            if attach_media in {"PHOTO", "IMAGE"}:
                media_type = "IMAGE"
            elif attach_media == "VIDEO":
                media_type = "VIDEO"
            elif attach_media == "ALBUM":
                media_type = "CAROUSEL"
            elif attach_media == "LINK":
                media_type = "LINK"
            elif attach_media:
                media_type = attach_media

        return NormalizedPost(
            platform=self.name,
            id=str(raw_post.get("id", "")),
            url=raw_post.get("permalink_url"),
            text=raw_post.get("message", "") or "",
            posted_at=raw_post.get("created_time"),
            media_type=media_type,
            metrics=metrics,
            raw={
                "status_type": raw_post.get("status_type"),
                "reactions_by_type": reactions,
                "insights": insights,
            },
        )
