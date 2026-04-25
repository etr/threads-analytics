"""Threads (Meta) provider.

This is the reference implementation — the original single-platform fetcher
lived here before the multi-platform refactor.

API: https://developers.facebook.com/docs/threads
Auth: long-lived user token (60-day expiry), ``threads_basic``,
``threads_manage_insights``, ``threads_read_replies``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import Metrics, NormalizedPost, Profile, Provider, Reply


class ThreadsProvider(Provider):
    name = "threads"
    display_name = "Threads"
    token_env_var = "THREADS_ACCESS_TOKEN"
    base_url = "https://graph.threads.net/v1.0"
    rate_limit_budget = 900
    rate_limit_hard = 950

    PROFILE_FIELDS = "id,username,name,threads_profile_picture_url,threads_biography"
    POST_FIELDS = "id,text,timestamp,media_type,permalink,shortcode,is_quote_post"
    POST_METRICS = "views,likes,replies,reposts,quotes,shares"
    ACCOUNT_METRICS = "views,likes,replies,reposts,quotes,followers_count"

    def fetch_profile(self) -> Profile:
        data = self.api_get("me", {"fields": self.PROFILE_FIELDS})
        if not data or "id" not in data:
            raise RuntimeError("Threads: could not fetch user profile.")
        return Profile(
            platform=self.name,
            id=str(data["id"]),
            username=data.get("username"),
            name=data.get("name"),
            bio=data.get("threads_biography"),
            profile_url=data.get("threads_profile_picture_url"),
            extra={"raw": data},
        )

    def fetch_posts(self, since: datetime) -> list[dict[str, Any]]:
        profile = self.api_get("me", {"fields": "id"})
        if not profile:
            return []
        user_id = profile["id"]

        params: dict[str, Any] = {
            "fields": self.POST_FIELDS,
            "limit": 50,
            "since": int(since.timestamp()),
        }
        url = f"{user_id}/threads"
        all_posts: list[dict[str, Any]] = []
        while url:
            data = self.api_get(url, params)
            if not data:
                break
            all_posts.extend(data.get("data", []))
            next_url = data.get("paging", {}).get("next")
            if next_url:
                url = next_url
                params = {}  # embedded in next URL
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
            elif "total_value" in item:
                insights[name] = item["total_value"].get("value", 0)
        return insights

    def fetch_conversation(self, post_id: str, top_n: int) -> list[Reply]:
        fields = "id,text,timestamp,username,has_replies"
        data = self.api_get(
            f"{post_id}/conversation", {"fields": fields, "limit": top_n}
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
                    has_replies=bool(item.get("has_replies", False)),
                )
            )
        return replies

    def fetch_account_insights(self) -> dict[str, Any]:
        profile = self.api_get("me", {"fields": "id"})
        if not profile:
            return {}
        data = self.api_get(
            f"{profile['id']}/threads_insights", {"metric": self.ACCOUNT_METRICS}
        )
        if not data:
            return {}
        insights: dict[str, Any] = {}
        for item in data.get("data", []):
            name = item.get("name")
            values = item.get("values", [])
            if values:
                insights[name] = values[0].get("value", 0)
            elif "total_value" in item:
                insights[name] = item["total_value"].get("value", 0)
        return insights

    def normalize(
        self, raw_post: dict[str, Any], insights: dict[str, Any]
    ) -> NormalizedPost:
        # Threads exposes reposts + quotes separately; we sum them into "shares"
        # in the normalized metrics but keep the raw breakdown available.
        reposts = insights.get("reposts", 0) or 0
        quotes = insights.get("quotes", 0) or 0
        raw_shares = insights.get("shares", 0) or 0
        shares_total = reposts + quotes + raw_shares

        metrics = Metrics(
            impressions=insights.get("views"),
            likes=insights.get("likes"),
            comments=insights.get("replies"),
            shares=shares_total if insights else None,
        )

        media_type = (raw_post.get("media_type") or "UNKNOWN").upper()
        if media_type == "TEXT_POST":
            media_type = "TEXT"

        return NormalizedPost(
            platform=self.name,
            id=str(raw_post.get("id", "")),
            url=raw_post.get("permalink"),
            text=raw_post.get("text", "") or "",
            posted_at=raw_post.get("timestamp"),
            media_type=media_type,
            metrics=metrics,
            raw={
                "shortcode": raw_post.get("shortcode"),
                "is_quote_post": raw_post.get("is_quote_post"),
                "insights": insights,
            },
        )
