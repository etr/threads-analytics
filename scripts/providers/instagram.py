"""Instagram Graph API provider.

API: Instagram Graph API (``graph.facebook.com``). An Instagram Business or
Creator account must be linked to a Facebook Page.

Auth: token with ``instagram_basic`` + ``instagram_manage_insights`` +
``pages_show_list``. Personal Instagram accounts are **not** supported by the
Graph API and will return no data.

The IG user ID is read from ``INSTAGRAM_USER_ID``. If it's not set we try to
resolve it from the linked page via ``FACEBOOK_PAGE_ID`` (``?fields=instagram_business_account``).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from .base import Metrics, NormalizedPost, Profile, Provider, Reply


class InstagramProvider(Provider):
    name = "instagram"
    display_name = "Instagram"
    token_env_var = "INSTAGRAM_ACCESS_TOKEN"
    base_url = "https://graph.facebook.com/v19.0"
    rate_limit_budget = 180
    rate_limit_hard = 200

    MEDIA_FIELDS = (
        "id,caption,media_type,media_url,permalink,timestamp,thumbnail_url,"
        "like_count,comments_count"
    )
    POST_METRICS = "impressions,reach,saved,video_views"
    ACCOUNT_METRICS = "impressions,reach,profile_views,follower_count"

    def __init__(self) -> None:
        super().__init__()
        self.ig_user_id: str | None = os.environ.get("INSTAGRAM_USER_ID")
        self._fb_page_id: str | None = os.environ.get("FACEBOOK_PAGE_ID")

    def _resolve_ig_user_id(self) -> str:
        if self.ig_user_id:
            return self.ig_user_id
        if self._fb_page_id:
            data = self.api_get(
                self._fb_page_id, {"fields": "instagram_business_account"}
            )
            if data and "instagram_business_account" in data:
                self.ig_user_id = str(data["instagram_business_account"]["id"])
                return self.ig_user_id
        raise RuntimeError(
            "Instagram: set INSTAGRAM_USER_ID, or set FACEBOOK_PAGE_ID so we "
            "can resolve the linked Instagram Business account."
        )

    def fetch_profile(self) -> Profile:
        user_id = self._resolve_ig_user_id()
        data = self.api_get(
            user_id,
            {
                "fields": (
                    "id,username,name,biography,profile_picture_url,"
                    "followers_count,media_count,website"
                )
            },
        )
        if not data or "id" not in data:
            raise RuntimeError("Instagram: could not fetch user profile.")
        return Profile(
            platform=self.name,
            id=str(data["id"]),
            username=data.get("username"),
            name=data.get("name"),
            bio=data.get("biography"),
            profile_url=data.get("profile_picture_url"),
            follower_count=data.get("followers_count"),
            extra={"website": data.get("website"), "media_count": data.get("media_count")},
        )

    def fetch_posts(self, since: datetime) -> list[dict[str, Any]]:
        user_id = self._resolve_ig_user_id()
        params: dict[str, Any] = {
            "fields": self.MEDIA_FIELDS,
            "limit": 50,
            "since": int(since.timestamp()),
        }
        url = f"{user_id}/media"
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
            {"fields": "id,text,timestamp,username", "limit": top_n},
        )
        if not data:
            return []
        replies: list[Reply] = []
        for item in data.get("data", []):
            replies.append(
                Reply(
                    id=str(item.get("id", "")),
                    text=item.get("text", ""),
                    timestamp=item.get("timestamp"),
                    username=item.get("username"),
                )
            )
        return replies

    def fetch_account_insights(self) -> dict[str, Any]:
        user_id = self._resolve_ig_user_id()
        data = self.api_get(
            f"{user_id}/insights",
            {"metric": self.ACCOUNT_METRICS, "period": "day"},
        )
        if not data:
            return {}
        insights: dict[str, Any] = {}
        for item in data.get("data", []):
            name = item.get("name")
            values = item.get("values", [])
            if values:
                insights[name] = values[-1].get("value", 0)
        return insights

    def normalize(
        self, raw_post: dict[str, Any], insights: dict[str, Any]
    ) -> NormalizedPost:
        media_type = (raw_post.get("media_type") or "UNKNOWN").upper()
        if media_type == "CAROUSEL_ALBUM":
            media_type = "CAROUSEL"
        elif media_type == "IMAGE":
            media_type = "IMAGE"
        elif media_type in {"VIDEO", "REELS"}:
            media_type = "VIDEO"

        metrics = Metrics(
            impressions=insights.get("impressions"),
            reach=insights.get("reach"),
            likes=raw_post.get("like_count"),
            comments=raw_post.get("comments_count"),
            saves=insights.get("saved"),
            video_views=insights.get("video_views"),
        )

        return NormalizedPost(
            platform=self.name,
            id=str(raw_post.get("id", "")),
            url=raw_post.get("permalink"),
            text=raw_post.get("caption", "") or "",
            posted_at=raw_post.get("timestamp"),
            media_type=media_type,
            metrics=metrics,
            raw={
                "media_url": raw_post.get("media_url"),
                "thumbnail_url": raw_post.get("thumbnail_url"),
                "insights": insights,
            },
        )
