#!/usr/bin/env python3
"""Multi-platform social analytics fetcher.

Runs one or more :class:`~providers.Provider` implementations and writes
normalized JSON to disk. Each provider's output gets its own file; when
``--platform all`` is used an additional ``combined-...json`` file is
written so the analysis skill has one place to load everything from.

The behavior contract for providers is "optimistic auth": if the relevant
environment variable is set we try to fetch; if it fails we warn and move on
to the next platform. Missing tokens are not errors — they just mean that
platform is skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
    home_env = Path.home() / ".env"
    if home_env.exists():
        load_dotenv(home_env)
except ImportError:  # python-dotenv is optional
    pass

# Make the "providers" package importable whether fetch.py is run as a script
# from the repo root, from inside scripts/, or via an absolute path.
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from providers import PROVIDERS  # noqa: E402
from providers.base import (  # noqa: E402
    ProviderAuthError,
    ProviderRateLimited,
    ProviderSkipped,
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def run_provider(
    platform: str,
    since: datetime,
    include_replies: bool,
    top_replies: int,
) -> Optional[dict[str, Any]]:
    """Instantiate and run a single provider. Returns ``None`` on skip/failure."""

    cls = PROVIDERS.get(platform)
    if cls is None:
        log(f"Unknown platform: {platform}")
        return None

    try:
        provider = cls()
    except ProviderSkipped as exc:
        log(f"SKIP {platform}: {exc}")
        return None

    log(f"=== Running provider: {platform} ===")
    try:
        return provider.run(
            since=since, include_replies=include_replies, top_replies=top_replies
        )
    except ProviderAuthError as exc:
        log(f"SKIP {platform}: auth error — {exc}")
        return None
    except ProviderRateLimited as exc:
        log(f"SKIP {platform}: rate limited — {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - best-effort per platform
        log(f"SKIP {platform}: unexpected error — {exc}")
        return None


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch social media posting activity across one or more platforms."
    )
    parser.add_argument(
        "--platform",
        choices=[*PROVIDERS.keys(), "all"],
        default="all",
        help="Which platform(s) to fetch. 'all' runs every configured provider (default).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of history to fetch (default: 30).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to write per-platform JSON files. "
        "Default: ~/.claude/social-analytics/cache/",
    )
    parser.add_argument(
        "--no-replies",
        action="store_true",
        help="Skip fetching conversation/reply data (faster, fewer API calls).",
    )
    parser.add_argument(
        "--top-replies",
        type=int,
        default=3,
        help="Number of top replies to fetch per post (default: 3).",
    )
    args = parser.parse_args()

    since_date = datetime.now(timezone.utc) - timedelta(days=args.days)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = Path(
        args.output_dir
        or (Path.home() / ".claude" / "social-analytics" / "cache")
    )

    platforms = list(PROVIDERS.keys()) if args.platform == "all" else [args.platform]

    results: dict[str, Any] = {}
    skipped: list[str] = []
    for platform in platforms:
        data = run_provider(
            platform=platform,
            since=since_date,
            include_replies=not args.no_replies,
            top_replies=args.top_replies,
        )
        if data is None:
            skipped.append(platform)
            continue
        results[platform] = data
        out_path = output_dir / f"{platform}-{args.days}d-{today}.json"
        write_json(
            out_path,
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "days": args.days,
                "since": since_date.isoformat(),
                **data,
            },
        )
        log(f"  Wrote {out_path}")

    # Always write a combined manifest so the skill can discover what actually
    # succeeded in a single read. For single-platform runs this is still a
    # useful index of what's on disk.
    combined_path = output_dir / f"combined-{args.days}d-{today}.json"
    combined_payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "since": since_date.isoformat(),
        "requested_platforms": platforms,
        "succeeded_platforms": sorted(results.keys()),
        "skipped_platforms": skipped,
        "platforms": results,
    }
    write_json(combined_path, combined_payload)
    log(f"  Wrote {combined_path}")

    if not results:
        log("No platforms produced data. Check tokens and setup-guide.md.")
        return 1
    if skipped:
        log(f"Done. Succeeded: {sorted(results.keys())}. Skipped: {skipped}.")
    else:
        log(f"Done. Succeeded: {sorted(results.keys())}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
