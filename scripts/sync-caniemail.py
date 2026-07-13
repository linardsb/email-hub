#!/usr/bin/env python3
"""Sync caniemail.com CSS/HTML support data to data/caniemail-support.json.

Fetches the caniemail.com API data and transforms it into a local support
matrix keyed by feature slug and email client ID.

Usage:
    uv run python scripts/sync-caniemail.py
    uv run python scripts/sync-caniemail.py --check
    uv run python scripts/sync-caniemail.py --verbose
    make sync-caniemail
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

CANIEMAIL_API_URL = "https://www.caniemail.com/api/data.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "caniemail-support.json"

# Map caniemail client slugs to our internal client IDs.
# Only map clients we track in our email-client-matrix.yaml.
_CANIEMAIL_TO_HUB_CLIENT: dict[str, str] = {
    "gmail-desktop-webmail": "gmail_web",
    "gmail-android": "gmail_android",
    "gmail-ios": "gmail_ios",
    "apple-mail-macos": "apple_mail_macos",
    "apple-mail-ios": "apple_mail_ios",
    "outlook-2019": "outlook_2019",
    "outlook-2021": "outlook_2021",
    "outlook-windows-mail": "outlook_365_win",
    "outlook-macos": "outlook_macos",
    "outlook-ios": "outlook_ios",
    "outlook-android": "outlook_android",
    "outlook-com": "outlook_com",
    "yahoo-mail": "yahoo_mail",
    "thunderbird": "thunderbird",
    "samsung-email-android": "samsung_mail",
    "aol-desktop-webmail": "aol_web",
}

_SUPPORT_MAP: dict[str, str] = {
    "y": "yes",
    "n": "no",
    "a": "partial",
    "u": "unknown",
}


def fetch_caniemail_data(*, verbose: bool = False) -> dict[str, object]:
    """Fetch latest data from caniemail.com API."""
    if verbose:
        print(f"Fetching {CANIEMAIL_API_URL} ...")

    req = urllib.request.Request(  # noqa: S310
        CANIEMAIL_API_URL,
        headers={"User-Agent": "email-hub/sync-caniemail"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        data: dict[str, object] = json.loads(resp.read().decode())

    if verbose:
        print(f"  Received {len(data.get('data', []))} features")  # type: ignore[arg-type]

    return data


def transform_to_support_matrix(
    caniemail_data: dict[str, object],
) -> dict[str, dict[str, dict[str, str]]]:
    """Transform caniemail API format to our internal support matrix.

    Returns:
        ``{feature_slug: {client_id: {support: "yes"|"no"|"partial", notes: "..."}}}``
    """
    features: dict[str, dict[str, dict[str, str]]] = {}
    raw_features = caniemail_data.get("data", [])

    if not isinstance(raw_features, list):
        return features

    for feature in raw_features:
        if not isinstance(feature, dict):
            continue

        slug = feature.get("slug", "")
        if not slug:
            continue

        stats = feature.get("stats", {})
        if not isinstance(stats, dict):
            continue

        client_support: dict[str, dict[str, str]] = {}

        for family_id, family_data in stats.items():
            if not isinstance(family_data, dict):
                continue
            for version_id, support_code in family_data.items():
                # Build the caniemail client key
                caniemail_key = f"{family_id}-{version_id}" if version_id else family_id

                # Map to our client ID
                hub_client = _CANIEMAIL_TO_HUB_CLIENT.get(caniemail_key)
                if not hub_client:
                    # Try family-level match
                    hub_client = _CANIEMAIL_TO_HUB_CLIENT.get(family_id)
                    if not hub_client:
                        continue

                support_str = str(support_code).lower().strip()
                # Take first character for support level (e.g. "y #1" → "y")
                level_char = support_str[0] if support_str else "u"
                level = _SUPPORT_MAP.get(level_char, "unknown")

                # Extract notes (everything after the support character)
                notes = support_str[1:].strip().lstrip("#").strip() if len(support_str) > 1 else ""

                client_support[hub_client] = {"support": level, "notes": notes}

        if client_support:
            features[slug] = client_support

    return features


def write_support_file(
    features: dict[str, dict[str, dict[str, str]]],
    *,
    verbose: bool = False,
) -> None:
    """Write the support matrix to data/caniemail-support.json."""
    # Count unique clients
    all_clients: set[str] = set()
    for client_map in features.values():
        all_clients.update(client_map.keys())

    output = {
        "metadata": {
            "source": "caniemail.com",
            "api_url": CANIEMAIL_API_URL,
            "last_synced": datetime.now(UTC).isoformat(),
            "feature_count": len(features),
            "client_count": len(all_clients),
        },
        "features": features,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

    if verbose:
        print(f"Wrote {len(features)} features x {len(all_clients)} clients to {OUTPUT_PATH}")


def check_freshness(*, verbose: bool = False) -> bool:
    """Check if the existing data file is reasonably fresh."""
    if not OUTPUT_PATH.exists():
        print(f"MISSING: {OUTPUT_PATH}")
        return False

    data = json.loads(OUTPUT_PATH.read_text())
    metadata = data.get("metadata", {})
    last_synced = metadata.get("last_synced", "")
    feature_count = metadata.get("feature_count", 0)

    if verbose:
        print(f"Last synced: {last_synced}")
        print(f"Features: {feature_count}")

    if feature_count < 100:
        print(f"WARNING: Only {feature_count} features — expected 300+")
        return False

    print(f"OK: {feature_count} features, last synced {last_synced}")
    return True


def main() -> None:
    """Download, parse, and save caniemail.com support data."""
    parser = argparse.ArgumentParser(description="Sync caniemail.com support data")
    parser.add_argument("--check", action="store_true", help="Check existing file freshness")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.check:
        ok = check_freshness(verbose=args.verbose)
        sys.exit(0 if ok else 1)

    try:
        raw_data = fetch_caniemail_data(verbose=args.verbose)
    except urllib.error.URLError as exc:
        print(f"ERROR: Failed to fetch caniemail data: {exc}")
        sys.exit(1)

    features = transform_to_support_matrix(raw_data)
    if not features:
        print("ERROR: No features extracted from caniemail data")
        sys.exit(1)

    write_support_file(features, verbose=args.verbose)
    print(f"Synced {len(features)} features to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
