# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
# ruff: noqa: T201, S603, S607  (CLI output; fixed git argv, no shell)
"""Stamp a squash-merge SHA into the deferred-items ledger placeholders a merged PR added.

Scope = entries whose `introduced_commit` / `closed_commit` is a placeholder ("pending" or
"pending commit") at SHA and was not that same value at SHA^ (i.e. the PR wrote it). Older
unstamped placeholders are left alone. Stamps are applied by entry id to the CURRENT ledger file,
line by line, so every other byte is preserved; the parsed result is checked before writing.

Usage: python3 stamp_ledger.py --sha <squash-sha> [--file PATH] [--length 8] [--dry-run]
Exit: 0 stamped (or would stamp), 1 nothing to stamp, 2 error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

LEDGER = ".agents/deferred-items.json"
FIELDS = ("introduced_commit", "closed_commit")
PLACEHOLDERS = {"pending", "pending commit"}
ID_RE = re.compile(r'^( *)"id": "([^"]+)",?\s*$')
FIELD_RE = re.compile(
    r'^( *)"(introduced_commit|closed_commit)": "(pending(?: commit)?)"(,?\r?\n?)$'
)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def items_at(rev: str) -> dict[str, dict[str, Any]]:
    if subprocess.run(["git", "cat-file", "-e", f"{rev}:{LEDGER}"], capture_output=True).returncode:
        return {}  # ledger absent at that (already verified) revision
    return {i["id"]: i for i in json.loads(git("show", f"{rev}:{LEDGER}"))["items"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sha", required=True, help="squash-merge commit of the PR")
    ap.add_argument("--file", help=f"ledger to edit (default: <repo root>/{LEDGER})")
    ap.add_argument(
        "--length", type=int, default=8, help="stamped SHA length (ledger convention: 8)"
    )
    ap.add_argument("--dry-run", action="store_true", help="print planned stamps, write nothing")
    a = ap.parse_args()

    full = git("rev-parse", "--verify", f"{a.sha}^{{commit}}").strip()
    parent = git("rev-parse", "--verify", f"{full}^^{{commit}}").strip()
    stamp = full[: a.length]
    path = Path(a.file) if a.file else Path(git("rev-parse", "--show-toplevel").strip()) / LEDGER
    original = path.read_text(encoding="utf-8")
    old = json.loads(original)
    current = {i["id"]: i for i in old["items"]}

    after, before = items_at(full), items_at(parent)
    scope = {
        (iid, f)
        for iid, entry in after.items()
        for f in FIELDS
        if entry.get(f) in PLACEHOLDERS and before.get(iid, {}).get(f) != entry.get(f)
    }
    for iid, f in sorted(scope):
        if current.get(iid, {}).get(f) not in PLACEHOLDERS:
            print(f"skip {iid}.{f}: no longer a placeholder in {path}", file=sys.stderr)
    scope = {(iid, f) for iid, f in scope if current.get(iid, {}).get(f) in PLACEHOLDERS}
    if not scope:
        print(f"nothing to stamp for {stamp}", file=sys.stderr)
        return 1

    # Line-level edit: json.dump would re-escape (or un-escape) text and churn unrelated lines.
    lines = original.splitlines(keepends=True)
    item_indent: int | None = None
    cur_id: str | None = None
    done: set[tuple[str, str]] = set()
    for n, line in enumerate(lines):
        m = ID_RE.match(line)
        if m and (item_indent is None or len(m.group(1)) == item_indent) and m.group(2) in current:
            item_indent, cur_id = len(m.group(1)), m.group(2)
            continue
        m = FIELD_RE.match(line)
        if m and cur_id and (cur_id, m.group(2)) in scope and len(m.group(1)) == item_indent:
            lines[n] = f'{m.group(1)}"{m.group(2)}": "{stamp}"{m.group(4)}'
            done.add((cur_id, m.group(2)))
            print(f"{cur_id}.{m.group(2)}: {m.group(3)!r} -> {stamp!r}")
    if done != scope:
        print(
            f"error: could not locate {sorted(scope - done)} as single-line fields", file=sys.stderr
        )
        return 2

    result = "".join(lines)
    expected = json.loads(original)
    for entry in expected["items"]:
        for f in FIELDS:
            if (entry["id"], f) in scope:
                entry[f] = stamp
    if json.loads(result) != expected:
        print("error: edit changed more than the scoped fields; nothing written", file=sys.stderr)
        return 2
    if not a.dry_run:
        path.write_text(result, encoding="utf-8")
    print(f"{'would stamp' if a.dry_run else 'stamped'} {len(done)} field(s) with {stamp}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else exc
        print(f"error: {detail}", file=sys.stderr)
        sys.exit(2)
