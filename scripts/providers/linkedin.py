"""LinkedIn provider.

API: LinkedIn REST API (``api.linkedin.com/rest``).
Auth: OAuth 2.0 bearer token with ``r_member_social`` (for personal posts)
or ``r_organization_social`` (for company pages). Most analytics endpoints
require Marketing Developer Platform approval.

We operate on the "optimistic" principle: if the token is set we try the
endpoints and let failures bubble up as warnings. The caller can inspect the
warnings in stderr.

Two modes:
- **Member mode** (default): acts on behalf of the authenticated user via
  ``/rest/me`` and ``/rest/posts?q=author&author={urn}``.
- **Organization mode**: if ``LINKEDIN_ORGANIZATION_URN`` is set (e.g.
  ``urn:li:organization:12345``), we fetch that organization's shares and
  ``organizationalEntityShareStatistics``.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from .base import Metrics, NormalizedPost, Profile, Provider, Reply


LINKEDIN_VERSION_HEADER = "202405"


class LinkedInProvider(Provider):
    name = "linkedin"
    display_name = "LinkedIn"
    token_env_var = "LINKEDIN_ACCESS_TOKEN"
    base_url = "https://api.linkedin.com/rest"
    rate_limit_budget = 400
    rate_limit_hard = 500

    def __init__(self) -> None:
        super().__init__()
        self.org_urn: Optional[str] = os.environ.get("LINKEDIN_ORGANIZATION_URN")
        self.author_urn: Optional[str] = None  # resolved lazily for member mode

    def _headers(self) -> dict[str, str]:
        return {
            "LinkedIn-Version": LINKEDIN_VERSION_HEADER,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def _get(
        self, endpoint: str, params: Optional[dict[str, Any]] = None
    ) -> Optional[dict[str, Any]]:
        return self.api_get(
            endpoint,
            params=params,
            headers=self._headers(),
            auth_style="bearer",
        )

    def fetch_profile(self) -> Profile:
        if self.org_urn:
            data = self._get(f"organizations/{self.org_urn.split(':')[-1]}")
            if not data or "id" not in data:
                raise RuntimeError("LinkedIn: could not fetch organization profile.")
            loc = data.get("localizedName") or data.get("vanityName")
            return Profile(
                platform=self.name,
                id=str(data["id"]),
                username=data.get("vanityName"),
                name=loc,
                bio=(data.get("description") or {}).get("localized", {}).get("en_US"),
                profile_url=f"https://www.linkedin.com/company/{data.get('vanityName', data['id'])}",
                extra={"raw": data},
            )

        # Member mode
        data = self._get("me")
        if not data or "id" not in data:
            raise RuntimeError("LinkedIn: could not fetch /me.")
        member_id = str(data["id"])
        self.author_urn = f"urn:li:person:{member_id}"
        name = " ".join(
            filter(
                None,
                [
                    (data.get("localizedFirstName") or ""),
                    (data.get("localizedLastName") or ""),
                ],
            )
        ).strip() or None
        return Profile(
            platform=self.name,
            id=member_id,
            name=name,
            extra={"raw": data},
        )

    def fetch_posts(self, since: datetime) -> list[dict[str, Any]]:
        author = self.org_urn or self.author_urn
        if not author:
            # fetch_profile populates author_urn in member mode
            self.fetch_profile()
            author = self.org_urn or self.author_urn
        if not author:
            return []

        params = {
            "q": "author",
            "author": author,
            "count": 50,
            "sortBy": "LAST_MODIFIED",
        }
        data = self._get("posts", params)
        if not data:
            return []
        since_ms = int(since.timestamp() * 1000)
        posts = [
            p
            for p in data.get("elements", [])
            if (p.get("publishedAt") or p.get("createdAt") or 0) >= since_ms
        ]
        return posts

    def fetch_post_insights(self, post_id: str) -> dict[str, Any]:
        # post_id is expected to be a URN like "urn:li:share:123" or "urn:li:ugcPost:123"
        encoded = post_id.replace(":", "%3A")
        data = self._get(f"socialActions/{encoded}")
        if not data:
            return {}
        return {
            "likesSummary": data.get("likesSummary", {}),
            "commentsSummary": data.get("commentsSummary", {}),
            "sharesSummary": data.get("sharesSummary", {}),
        }

    def fetch_conversation(self, post_id: str, top_n: int) -> list[Reply]:
        encoded = post_id.replace(":", "%3A")
        data = self._get(
            f"socialActions/{encoded}/comments",
            params={"count": top_n},
        )
        if not data:
            return []
        replies: list[Reply] = []
        for item in data.get("elements", []):
            message = (item.get("message") or {}).get("text", "")
            replies.append(
                Reply(
                    id=str(item.get("id", "")),
                    text=message,
                    timestamp=str(item.get("created", {}).get("time", "")) or None,
                    username=str(item.get("actor", "")),
                )
            )
        return replies

    def fetch_account_insights(self) -> dict[str, Any]:
        if not self.org_urn:
            # Member-level analytics aren't exposed.
            return {}
        encoded = self.org_urn.replace(":", "%3A")
        data = self._get(
            "organizationalEntityShareStatistics",
            params={"q": "organizationalEntity", "organizationalEntity": self.org_urn},
        )
        if not data:
            return {}
        return data

    def normalize(
        self, raw_post: dict[str, Any], insights: dict[str, Any]
    ) -> NormalizedPost:
        post_id = str(raw_post.get("id", ""))
        commentary = raw_post.get("commentary") or ""
        if not commentary:
            # Older posts use ``specificContent`` shape.
            sc = raw_post.get("specificContent") or {}
            commentary = (
                sc.get("com.linkedin.ugc.ShareContent", {})
                .get("shareCommentary", {})
                .get("text", "")
            )

        posted_at_ms = raw_post.get("publishedAt") or raw_post.get("createdAt")
        posted_at: Optional[str] = None
        if posted_at_ms:
            posted_at = datetime.utcfromtimestamp(posted_at_ms / 1000).isoformat() + "Z"

        # Media type detection is best-effort.
        media_type = "TEXT"
        content = raw_post.get("content") or {}
        if isinstance(content, dict):
            if "media" in content:
                media_type = "IMAGE"
            elif "article" in content:
                media_type = "LINK"
            elif "multiImage" in content:
                media_type = "CAROUSEL"
            elif "video" in content:
                media_type = "VIDEO"

        likes = (insights.get("likesSummary") or {}).get("totalLikes")
        comments = (insights.get("commentsSummary") or {}).get("aggregatedTotalComments")
        shares = (insights.get("sharesSummary") or {}).get("aggregatedTotalShares")

        metrics = Metrics(
            impressions=None,  # requires organizationalEntityShareStatistics per-share
            likes=likes,
            comments=comments,
            shares=shares,
        )

        return NormalizedPost(
            platform=self.name,
            id=post_id,
            url=f"https://www.linkedin.com/feed/update/{post_id}",
            text=commentary or "",
            posted_at=posted_at,
            media_type=media_type,
            metrics=metrics,
            raw={"insights": insights, "author": raw_post.get("author")},
        )
