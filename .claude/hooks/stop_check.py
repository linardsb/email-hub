#!/usr/bin/env python3
# ruff: noqa: S603, S607  (fixed argv lists, no shell, no user input; tools resolved from PATH on purpose)
"""Stop hook: a fast check on the files this session changed (job D1/D2).

Modes:
  --snapshot  (SessionStart startup|resume|clear) record HEAD + the hash of every
              file already dirty, in .claude/state/stop-baseline-<session>.json.
              Kept if it already exists, so a resume keeps the original baseline.
  (default)   (Stop) diff the tree against that baseline; ruff check/format on every
              changed .py (CI lints repo-wide), mypy + pyright + the nearest pytest
              file for app/ changes, and
              `pnpm --dir cms type-check` for cms/ changes. Red -> exit 2 with the
              tail fed back. The full gate stays in piv-validate (make check-full).

Never a silent pass:
  - stop_hook_active (already blocked once this turn) -> not re-run, note, exit 1.
  - no baseline (hook added mid-session) -> check every dirty in-scope file, note.
  - uv/pnpm off PATH, own time budget exceeded, or an internal error -> stderr
    note, exit 1 (non-blocking; the note is shown to the user).
Stdlib only, Python 3.9-compatible (runs as plain python3, V1).
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

TYPED_PREFIX = "app/"  # `make types` checks app/ only (Makefile:133-135)
CMS_PREFIX = "cms/"
CMS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json")
LOCK_FILES = ("pyproject.toml", "uv.lock")
PYTEST_MARKERS = "not integration and not benchmark and not visual_regression and not collab"
# make test rewrites these dates (job §7, S0); restore if the hook's pytest touched them
SIDE_EFFECT_GLOB = "app/ai/agents/*/skill-versions.yaml"
BUDGET_S = 240  # below the settings.json timeout (300) so a slow run ends with a note
TAIL_CHARS = 3000


class BudgetExceeded(Exception):
    pass


def root(cwd: str) -> Path:
    # stdin cwd follows the session into a worktree; CLAUDE_PROJECT_DIR stays at the
    # original root (hooks docs, research 2026-09-27), so it is only the fallback
    start = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
    out = subprocess.run(
        ["git", "-C", start, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return Path(out.stdout.strip() or start)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30
    ).stdout


def file_hash(repo: Path, rel: str) -> str:
    p = repo / rel
    if not p.is_file():
        return "<absent>"
    return hashlib.sha1(p.read_bytes(), usedforsecurity=False).hexdigest()


def dirty_paths(repo: Path) -> list:
    out = git(repo, "status", "--porcelain", "--untracked-files=all", "-z")
    paths, entries, i = [], out.split("\0"), 0
    while i < len(entries):
        e = entries[i]
        if len(e) > 3:
            paths.append(e[3:])
            if e[0] in "RC":  # rename/copy: next entry is the old path
                i += 1
        i += 1
    return paths


def baseline_file(repo: Path, session: str) -> Path:
    safe = "".join(c for c in session if c.isalnum() or c in "-_") or "unknown"
    return repo / ".claude" / "state" / f"stop-baseline-{safe}.json"


def snapshot(repo: Path, session: str) -> None:
    bf = baseline_file(repo, session)
    if bf.exists():
        return
    bf.parent.mkdir(parents=True, exist_ok=True)
    head = git(repo, "rev-parse", "HEAD").strip()
    dirty = {p: file_hash(repo, p) for p in dirty_paths(repo)}
    bf.write_text(json.dumps({"head": head, "dirty": dirty, "taken": time.time()}))


def changed_since_baseline(repo: Path, session: str) -> tuple:
    """Return (files, note). Files changed since the session baseline (D2)."""
    bf = baseline_file(repo, session)
    if not bf.exists():
        return dirty_paths(repo), "no session baseline; checking every dirty file"
    base = json.loads(bf.read_text())
    cands = set(dirty_paths(repo))
    if base.get("head"):
        # also catches files committed mid-session (chore(wip): commits)
        cands.update(p for p in git(repo, "diff", "--name-only", base["head"]).splitlines() if p)
    start = base.get("dirty", {})
    files = sorted(p for p in cands if not (p in start and start[p] == file_hash(repo, p)))
    return files, ""


def in_scope(files: list) -> tuple:
    py = [f for f in files if f.endswith(".py") and Path(f).exists()]
    cms = [f for f in files if f.startswith(CMS_PREFIX) and f.endswith(CMS_SUFFIXES)]
    locks = [f for f in files if f in LOCK_FILES]
    return py, cms, locks


def nearest_tests(py: list) -> list:
    tests = set()
    for f in py:
        p = Path(f)
        if not f.startswith(TYPED_PREFIX):
            continue
        if p.name.startswith("test_"):
            tests.add(f)
            continue
        # walk up from the module's dir to app/<feature>: nearest tests/test_<module>.py
        d = p.parent
        while len(d.parts) >= 2:
            cand = d / "tests" / f"test_{p.stem}.py"
            if cand.is_file():
                tests.add(str(cand))
                break
            d = d.parent
    return sorted(tests)


def run(cmd: list, repo: Path, deadline: float) -> tuple:
    left = deadline - time.monotonic()
    if left <= 5:
        raise BudgetExceeded(" ".join(cmd[:4]))
    try:
        r = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=left)
    except subprocess.TimeoutExpired as err:
        raise BudgetExceeded(" ".join(cmd[:4])) from err
    return r.returncode, (r.stdout + "\n" + r.stderr).strip()


def note(msg: str) -> None:
    sys.stderr.write(f"stop_check: {msg}\n")
    sys.exit(1)


def main() -> None:
    data = json.load(sys.stdin)
    repo = root(str(data.get("cwd") or ""))
    os.chdir(repo)
    session = str(data.get("session_id") or "unknown")

    if "--snapshot" in sys.argv:
        snapshot(repo, session)
        sys.exit(0)

    if data.get("stop_hook_active"):
        note("already blocked once this turn; not re-run. Run piv-validate before claiming done.")

    files, why = changed_since_baseline(repo, session)
    py, cms, locks = in_scope(files)
    if not (py or cms or locks):
        sys.exit(0)

    needed = (["uv"] if (py or locks) else []) + (["pnpm"] if cms else [])
    missing = [t for t in needed if shutil.which(t) is None]
    if missing:
        note(
            f"{', '.join(missing)} not on PATH; changed files NOT checked: {', '.join(py + cms + locks)}"
        )

    side_clean = not git(repo, "status", "--porcelain", "--", SIDE_EFFECT_GLOB).strip()
    deadline = time.monotonic() + BUDGET_S
    steps = []
    if py:
        uvr = ["uv", "run", "--no-sync"]
        steps.append(("ruff check", [*uvr, "ruff", "check", "--no-fix", "--force-exclude", *py]))
        steps.append(("ruff format", [*uvr, "ruff", "format", "--check", "--force-exclude", *py]))
        typed = [f for f in py if f.startswith(TYPED_PREFIX)]
        if typed:
            steps.append(("mypy", [*uvr, "mypy", *typed]))
            steps.append(("pyright", [*uvr, "pyright", *typed]))
        tests = nearest_tests(py)
        if tests:
            steps.append(("pytest", [*uvr, "pytest", *tests, "-q", "-x", "-m", PYTEST_MARKERS]))
    if locks:
        steps.append(("uv lock --check", ["uv", "lock", "--check"]))
    if cms:
        steps.append(("cms type-check", ["pnpm", "--dir", "cms", "type-check"]))

    failures = []
    try:
        for name, cmd in steps:
            code, out = run(cmd, repo, deadline)
            if code != 0 and not (name == "pytest" and code == 5):  # 5 = no tests collected
                failures.append(f"--- {name} (exit {code})\n{out[-TAIL_CHARS:]}")
    except BudgetExceeded as e:
        note(
            f"own {BUDGET_S}s budget exceeded at `{e}`; remaining checks NOT run. Run piv-validate."
        )
    finally:
        if side_clean:
            git(repo, "checkout", "--", SIDE_EFFECT_GLOB)

    if failures:
        head = f"({why}) " if why else ""
        sys.stderr.write(
            f"BLOCKED: {head}fast check red on changed files. Fix before finishing "
            f"(full gate = piv-validate):\n" + "\n".join(failures)[-TAIL_CHARS * 2 :] + "\n"
        )
        sys.exit(2)
    if why:
        note(f"{why}; fast check green.")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail open, but never silently
        sys.stderr.write(f"stop_check: internal error, changed files NOT checked: {e!r}\n")
        sys.exit(1)
