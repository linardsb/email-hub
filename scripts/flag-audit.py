#!/usr/bin/env python3
"""Feature flag lifecycle audit (Phase 44.3).

Compares feature-flags.yaml manifest against .env.example and the
``app/core/config`` package. Lifecycle debt (a past removal_date, or an old
flag with no removal plan) is advisory — it WARNS so it stays visible without
hard-blocking unrelated pushes on calendar rot. The only hard error is a flag
present in source but unregistered in the manifest (the pusher's own change).
Enforce graduation via an owned/scheduled job, not the pre-push gate.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

WARN_THRESHOLD_DAYS = 90
ERROR_THRESHOLD_DAYS = 180


@dataclass
class Finding:
    """A single audit finding (error or warning)."""

    flag: str
    code: str
    severity: str  # error | warn
    detail: str


def parse_env_flags(env_path: Path) -> set[str]:
    """Extract _ENABLED flag names from .env.example.

    Matches both commented (``# FOO=``) and uncommented (``FOO=``) lines.
    """
    pattern = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*_ENABLED)\s*=")
    flags: set[str] = set()
    for line in env_path.read_text().splitlines():
        m = pattern.match(line)
        if m:
            flags.add(m.group(1))
    return flags


def parse_config_flags(config_path: Path) -> set[str]:
    """Extract feature flag env var names from the config source.

    Accepts either a single ``.py`` file (legacy single-module layout) or
    a directory (current ``app/core/config`` package). For packages, every
    ``*.py`` file is scanned; class-tracking state is reset per file so a
    bare ``enabled: bool`` field in one module never picks up the wrong
    class header from another.

    Two strategies:
    1. Explicit inline comments: ``field: bool = ...  # ENV_VAR_NAME``
    2. Derived from Settings field → config class → _enabled fields.
       Example: ``qa_chaos: QAChaosConfig`` + ``enabled: bool`` → ``QA_CHAOS__ENABLED``
    """
    py_files = sorted(config_path.rglob("*.py")) if config_path.is_dir() else [config_path]

    flags: set[str] = set()

    # Aggregated across all files — class definitions in domain modules,
    # ``Settings`` field declarations in ``__init__.py``.
    class_fields: dict[str, list[str]] = {}
    prefix_map: dict[str, str] = {}  # class_name → ENV_PREFIX (e.g. "QA_CHAOS")

    comment_re = re.compile(r"#\s*([A-Z][A-Z0-9_]*_ENABLED)")
    class_re = re.compile(r"^class\s+(\w+)\(")
    field_re = re.compile(r"^\s+(\w+_enabled)\s*:\s*bool\s*=")
    # Also match bare "enabled: bool" (master toggles like QA_CHAOS__ENABLED)
    bare_field_re = re.compile(r"^\s+enabled\s*:\s*bool\s*=")
    settings_re = re.compile(r"^\s+(\w+)\s*:\s*(\w+Config)\s*=")

    for py_file in py_files:
        lines = py_file.read_text().splitlines()

        # Strategy 1: explicit comments
        for line in lines:
            m = comment_re.search(line)
            if m:
                flags.add(m.group(1))

        # Strategy 2a: per-file class field map (current_class resets between files)
        current_class = ""
        for line in lines:
            cm = class_re.match(line)
            if cm:
                current_class = cm.group(1)
                class_fields.setdefault(current_class, [])
                continue
            if current_class != "":
                fm = field_re.match(line)
                if fm:
                    class_fields[current_class].append(fm.group(1))
                elif bare_field_re.match(line) and "enabled" not in class_fields[current_class]:
                    class_fields[current_class].append("enabled")

        # Strategy 2b: Settings field map (only present in the package's __init__.py)
        in_settings = False
        for line in lines:
            if "class Settings(" in line:
                in_settings = True
                continue
            if in_settings:
                if line.startswith("class ") or (
                    line.strip() and not line.startswith(" ") and not line.startswith("#")
                ):
                    break
                sm = settings_re.match(line)
                if sm:
                    field_name, class_name = sm.group(1), sm.group(2)
                    prefix_map[class_name] = field_name.upper()

    # Step 2c: combine to produce env var names
    for class_name, field_list in class_fields.items():
        prefix = prefix_map.get(class_name)
        if not prefix:
            continue
        for field_name in field_list:
            if field_name == "enabled":
                env_name = f"{prefix}__ENABLED"
            else:
                env_name = f"{prefix}__{field_name.upper()}"
            flags.add(env_name)

    return flags


def load_manifest(manifest_path: Path) -> list[dict[str, object]]:
    """Load feature-flags.yaml and return flag entries."""
    data: object = yaml.safe_load(manifest_path.read_text())  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(data, dict):
        return []
    raw: object = data.get("flags")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    if not isinstance(raw, list):
        return []
    result: list[dict[str, object]] = []
    for item in raw:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(item, dict):
            result.append({str(k): v for k, v in item.items()})  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
    return result


def audit(
    manifest_path: Path,
    env_path: Path,
    config_path: Path,
    today: date,
) -> list[Finding]:
    """Run all audit checks. Returns findings sorted by severity."""
    findings: list[Finding] = []
    manifest_entries = load_manifest(manifest_path)
    manifest_names = {str(e["name"]) for e in manifest_entries}

    # Source flags from both .env.example and config.py
    source_flags = parse_env_flags(env_path) | parse_config_flags(config_path)

    # 1. Unregistered: in source but not manifest
    for flag in sorted(source_flags - manifest_names):
        findings.append(
            Finding(
                flag,
                "UNREGISTERED",
                "error",
                f"Flag in source but not in {manifest_path.name}",
            )
        )

    # 2. Orphaned: in manifest but not in source
    for flag in sorted(manifest_names - source_flags):
        findings.append(
            Finding(
                flag,
                "ORPHANED_MANIFEST",
                "warn",
                f"Flag in {manifest_path.name} but not found in source",
            )
        )

    # 3. Lifecycle checks on manifest entries
    for entry in manifest_entries:
        name = str(entry["name"])
        created = date.fromisoformat(str(entry["created"]))
        removal = entry.get("removal_date")
        age_days = (today - created).days
        status = str(entry.get("status", "unknown"))

        if removal:
            removal_date = date.fromisoformat(str(removal))
            if removal_date < today and status != "deprecated":
                days_past = (today - removal_date).days
                # Lifecycle rot is advisory: a flag whose removal_date has
                # passed shouldn't hard-block whoever pushes next (the debt is
                # rarely theirs). Warn so it stays visible; enforce graduation
                # via an owned/scheduled job, not every contributor's push.
                findings.append(
                    Finding(
                        name,
                        "PAST_REMOVAL_DATE",
                        "warn",
                        f"Removal date {removal} has passed ({days_past}d ago)",
                    )
                )
        else:
            # No removal date — permanent_reason required for old flags
            reason = entry.get("permanent_reason")
            if not reason and age_days > ERROR_THRESHOLD_DAYS:
                # Same rot policy as PAST_REMOVAL_DATE: advisory, not blocking.
                findings.append(
                    Finding(
                        name,
                        "NO_REMOVAL_PLAN_180D",
                        "warn",
                        f"Flag is {age_days}d old with no removal_date or permanent_reason",
                    )
                )
            elif not reason and age_days > WARN_THRESHOLD_DAYS:
                findings.append(
                    Finding(
                        name,
                        "NO_REMOVAL_PLAN_90D",
                        "warn",
                        f"Flag is {age_days}d old with no removal_date or permanent_reason",
                    )
                )

    return sorted(findings, key=lambda f: (0 if f.severity == "error" else 1, f.flag))


def main() -> int:
    """Run the feature flag audit."""
    parser = argparse.ArgumentParser(description="Audit feature flag lifecycle")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=_PROJECT_ROOT / "feature-flags.yaml",
        help="Path to feature-flags.yaml manifest",
    )
    parser.add_argument(
        "--env-example",
        type=Path,
        default=_PROJECT_ROOT / ".env.example",
        help="Path to .env.example",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_PROJECT_ROOT / "app" / "core" / "config",
        help="Path to the app/core/config package (or legacy single-file module)",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Exit 0 even on errors (for initial rollout)",
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    today = datetime.now(tz=UTC).date()
    findings = audit(args.manifest, args.env_example, args.config, today)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warn"]

    if warnings:
        print(f"\n{len(warnings)} warning(s):", file=sys.stderr)
        for f in warnings:
            print(
                f"  WARN  {f.code:30s} {f.flag}: {f.detail}",
                file=sys.stderr,
            )

    if errors:
        print(f"\n{len(errors)} error(s):", file=sys.stderr)
        for f in errors:
            print(
                f"  ERROR {f.code:30s} {f.flag}: {f.detail}",
                file=sys.stderr,
            )

    total = len(findings)
    if total == 0:
        manifest_count = len(load_manifest(args.manifest))
        print(f"Flag audit passed ({manifest_count} flags registered)")
        return 0

    if total > 0:
        print(
            f"\nFlag audit: {len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )

    if errors and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
