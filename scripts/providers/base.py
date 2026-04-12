"""Provider abstract base class and shared data structures.

Every social platform implements :class:`Provider` and maps its raw API
responses onto :class:`NormalizedPost` so the analysis skill can reason over
posts without caring which platform they came from.

Design notes:

* Metric fields are ``Optional`` on purpose. Different platforms expose
  different denominators (Threads has ``views``; Facebook/Instagram expose
  ``impressions`` and ``reach``; LinkedIn exposes ``impressionCount``;
  TikTok exposes ``view_count``). When a platform does not return a metric,
  we leave it as ``None`` rather than zeroing it so the skill can tell the
  difference between "zero engagement" and "this metric does not exist here".
* Providers are expected to fail soft. If a token is missing or scoped
  incorrectly, the provider should raise :class:`ProviderSkipped` so the
  dispatcher can warn and move on to the next platform.
"""

from __future__ import annotations

import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

try:
    import requests
except ImportError:  # pragma: no cover - import-time guard
    print(
        "ERROR: 'requests' package required. Install: pip install requests",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderSkipped(Exception):
    """Raised when a provider cannot run (missing token, config, etc.).

    The dispatcher catches this and logs a warning without failing the run.
    """


class ProviderRateLimited(Exception):
    """Raised when a provider hits its hard rate-limit ceiling for the run."""


class ProviderAuthError(Exception):
    """Raised when a provider's token is invalid or expired."""


# ---------------------------------------------------------------------------
# Shared dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Profile:
    """Platform-agnostic user profile snapshot."""

    platform: str
    id: str
    username: Optional[str] = None
    name: Optional[str] = None
    bio: Optional[str] = None
    profile_url: Optional[str] = None
    follower_count: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Metrics:
    """Normalized per-post engagement metrics.

    Any field left as ``None`` means the platform does not expose that metric
    (or it wasn't authorized). The skill should treat ``None`` as "N/A" rather
    than ``0`` when presenting data.
    """

    impressions: Optional[int] = None  # Threads views, FB/IG impressions, LI impressionCount, TT views
    reach: Optional[int] = None  # FB/IG only
    likes: Optional[int] = None
    comments: Optional[int] = None
    shares: Optional[int] = None  # Threads reposts+quotes, FB/IG shares, LI reshares, TT shares
    saves: Optional[int] = None  # IG saves, TT favorites
    clicks: Optional[int] = None  # FB/LI link clicks
    video_views: Optional[int] = None  # FB/IG/TT video-specific view counts

    def engagement_rate(self) -> Optional[float]:
        """Return (likes + comments + shares + saves) / impressions, or ``None``.

        Returns ``None`` when impressions is missing or zero, or when all
        engagement components are missing — there's no honest way to compute
        a rate in those cases.
        """

        if not self.impressions:
            return None
        parts = [x for x in (self.likes, self.comments, self.shares, self.saves) if x is not None]
        if not parts:
            return None
        return sum(parts) / self.impressions


@dataclass
class Reply:
    id: str
    text: str
    timestamp: Optional[str] = None
    username: Optional[str] = None
    has_replies: bool = False


@dataclass
class NormalizedPost:
    """The single shape the skill reasons over."""

    platform: str
    id: str
    url: Optional[str]
    text: str
    posted_at: Optional[str]  # ISO 8601
    media_type: str  # TEXT | IMAGE | VIDEO | CAROUSEL | LINK | UNKNOWN
    metrics: Metrics
    replies: list[Reply] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)  # platform-specific escape hatch

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Provider base class
# ---------------------------------------------------------------------------


class Provider(ABC):
    """Abstract base class every platform implements.

    Subclasses declare the class attributes (``name``, ``token_env_var``,
    ``base_url``, ``rate_limit_budget``) and implement the five ``fetch_*``
    methods plus :meth:`normalize`.

    The constructor enforces the "if we have a token, try it; otherwise skip"
    contract: it raises :class:`ProviderSkipped` when the environment variable
    is missing. Providers that need *multiple* pieces of config (e.g. LinkedIn
    organization URN, Facebook page ID) should override ``__init__`` to add
    additional checks.
    """

    name: str = ""
    display_name: str = ""
    token_env_var: str = ""
    base_url: str = ""
    rate_limit_budget: int = 1000  # soft warning threshold
    rate_limit_hard: int = 1200  # abort threshold

    def __init__(self) -> None:
        if not self.name or not self.token_env_var or not self.base_url:
            raise RuntimeError(
                f"{type(self).__name__} is missing required class attributes "
                "(name, token_env_var, base_url)."
            )
        token = os.environ.get(self.token_env_var)
        if not token:
            raise ProviderSkipped(
                f"{self.display_name or self.name}: {self.token_env_var} not set — "
                "skipping this platform. See setup-guide.md."
            )
        self.token: str = token
        self.api_call_count: int = 0

    # ------------------------------------------------------------------
    # HTTP helper shared by all providers
    # ------------------------------------------------------------------

    def _log(self, msg: str) -> None:
        print(f"[{self.name}] {msg}", file=sys.stderr)

    def api_get(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        auth_style: str = "query",
    ) -> Optional[dict[str, Any]]:
        """GET request with rate-limit tracking and exponential backoff.

        ``auth_style`` controls how the token is attached:
        - ``"query"``: appended as ``access_token`` query parameter (Meta APIs)
        - ``"bearer"``: sent as ``Authorization: Bearer`` header (LinkedIn, TikTok)
        """

        if self.api_call_count >= self.rate_limit_hard:
            raise ProviderRateLimited(
                f"{self.name}: reached hard rate-limit ceiling ({self.api_call_count} calls). "
                "Stopping to avoid a 24-hour block."
            )
        if self.api_call_count == self.rate_limit_budget:
            self._log(
                f"WARNING: {self.api_call_count} API calls made (soft budget)."
            )

        params = dict(params or {})
        headers = dict(headers or {})

        if auth_style == "query":
            params.setdefault("access_token", self.token)
        elif auth_style == "bearer":
            headers.setdefault("Authorization", f"Bearer {self.token}")
        else:
            raise ValueError(f"Unknown auth_style: {auth_style}")

        url = endpoint if endpoint.startswith("http") else f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=30)
                self.api_call_count += 1
            except requests.RequestException as exc:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    self._log(f"Request error: {exc}. Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                self._log(f"ERROR: Request failed after {max_retries} attempts: {exc}")
                return None

            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    self._log(f"ERROR: Non-JSON 200 response from {url}")
                    return None

            if resp.status_code == 429:
                wait = 2 ** (attempt + 2)
                self._log(f"Rate limited (429). Waiting {wait}s before retry...")
                time.sleep(wait)
                continue

            if resp.status_code in (401, 403):
                raise ProviderAuthError(
                    f"{self.name}: auth error {resp.status_code} — token likely expired or "
                    f"missing scopes. Response: {resp.text[:200]}"
                )

            # Surface useful error info to stderr, then back off once before giving up.
            try:
                err_body = resp.json()
                err = err_body.get("error", err_body) if isinstance(err_body, dict) else {}
                msg = err.get("message") if isinstance(err, dict) else None
                self._log(f"API error: {resp.status_code} — {msg or resp.text[:200]}")
                # Meta OAuth code 190 = expired token; worth treating as auth error.
                if isinstance(err, dict) and err.get("code") == 190:
                    raise ProviderAuthError(
                        f"{self.name}: token expired or invalid (code 190)."
                    )
            except ValueError:
                self._log(f"API error: {resp.status_code} — {resp.text[:200]}")

            if attempt < max_retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                return None

        return None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def fetch_profile(self) -> Profile:
        """Return the authenticated user's profile."""

    @abstractmethod
    def fetch_posts(self, since: datetime) -> list[dict[str, Any]]:
        """Return raw post objects newer than ``since``. Shape is provider-specific."""

    @abstractmethod
    def fetch_post_insights(self, post_id: str) -> dict[str, Any]:
        """Return per-post insight data. Shape is provider-specific."""

    @abstractmethod
    def fetch_conversation(self, post_id: str, top_n: int) -> list[Reply]:
        """Return the top ``top_n`` replies/comments for a post."""

    @abstractmethod
    def fetch_account_insights(self) -> dict[str, Any]:
        """Return account-level metrics (followers, total views, etc.)."""

    @abstractmethod
    def normalize(
        self, raw_post: dict[str, Any], insights: dict[str, Any]
    ) -> NormalizedPost:
        """Combine raw post + insights into a :class:`NormalizedPost`."""

    # ------------------------------------------------------------------
    # Orchestration — shared across providers
    # ------------------------------------------------------------------

    def run(
        self,
        since: datetime,
        include_replies: bool = True,
        top_replies: int = 3,
    ) -> dict[str, Any]:
        """Fetch profile + posts + insights + (optionally) conversations.

        Returns a dict with the same top-level shape for every platform, so
        the dispatcher can dump it to a per-platform cache file.
        """

        self._log("Fetching profile...")
        profile = self.fetch_profile()

        self._log("Fetching account insights...")
        try:
            account_insights = self.fetch_account_insights()
        except NotImplementedError:
            account_insights = {}

        self._log(f"Fetching posts since {since.strftime('%Y-%m-%d')}...")
        raw_posts = self.fetch_posts(since)
        self._log(f"  Retrieved {len(raw_posts)} posts.")

        normalized: list[NormalizedPost] = []
        for i, raw in enumerate(raw_posts):
            post_id = self._post_id(raw)
            insights: dict[str, Any] = {}
            if post_id:
                try:
                    insights = self.fetch_post_insights(post_id)
                except ProviderAuthError:
                    raise
                except Exception as exc:  # noqa: BLE001 - best-effort per post
                    self._log(f"  Insight fetch failed for {post_id}: {exc}")
            post = self.normalize(raw, insights)

            if include_replies and post_id:
                try:
                    post.replies = self.fetch_conversation(post_id, top_replies)
                except NotImplementedError:
                    post.replies = []
                except Exception as exc:  # noqa: BLE001
                    self._log(f"  Reply fetch failed for {post_id}: {exc}")
                    post.replies = []

            normalized.append(post)
            if (i + 1) % 10 == 0:
                self._log(f"  Processed {i + 1}/{len(raw_posts)} posts.")

        return {
            "platform": self.name,
            "profile": asdict(profile),
            "account_insights": account_insights,
            "posts": [p.to_dict() for p in normalized],
            "api_calls_made": self.api_call_count,
        }

    @staticmethod
    def _post_id(raw: dict[str, Any]) -> Optional[str]:
        """Best-effort extraction of a platform post ID from a raw response."""

        for key in ("id", "post_id", "media_id", "video_id", "urn"):
            if key in raw and raw[key]:
                return str(raw[key])
        return None
