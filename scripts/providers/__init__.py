"""Platform providers for social-analytics.

Each provider implements the :class:`Provider` interface from ``base.py`` and
exposes a normalized view of a user's activity on a given social platform.

The registry below maps platform names (as used on the CLI and in cache file
names) to provider classes. Adding a new platform means adding a module here
and registering it in :data:`PROVIDERS`.
"""

from .base import Metrics, NormalizedPost, Profile, Provider, Reply
from .facebook import FacebookProvider
from .instagram import InstagramProvider
from .linkedin import LinkedInProvider
from .threads import ThreadsProvider
from .tiktok import TikTokProvider

PROVIDERS: dict[str, type[Provider]] = {
    "threads": ThreadsProvider,
    "facebook": FacebookProvider,
    "instagram": InstagramProvider,
    "linkedin": LinkedInProvider,
    "tiktok": TikTokProvider,
}

__all__ = [
    "PROVIDERS",
    "Provider",
    "Profile",
    "NormalizedPost",
    "Metrics",
    "Reply",
    "ThreadsProvider",
    "FacebookProvider",
    "InstagramProvider",
    "LinkedInProvider",
    "TikTokProvider",
]
