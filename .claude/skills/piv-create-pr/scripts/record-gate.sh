#!/usr/bin/env bash
# record-gate.sh — run the validation gate and record its result against a commit.
#
# The gate line is the single most-copied figure in this loop, and the one that
# goes wrong most often: a count from an earlier run pasted next to a delta
# from a later one, a duration that drifted between the report and the handoff
# note, a suite total that a rebase invalidated. Auditing prose after the fact
# does not fix that. This removes the opportunity: the numbers are captured by
# the run itself, stamped with the commit they describe, and the PR body renders
# them instead of restating them.
#
#   record-gate.sh                          # runs `make check-full` (Makefile:182)
#   record-gate.sh -- make ci-fe            # other gate (frontend CI mirror, Makefile:195)
#   record-gate.sh --parse-only <log>       # parse a saved log, print JSON, write nothing
#
# Writes .claude/last-gate.json (gitignored) at the repo root, keeps the full
# tee'd log under .claude/state/gate/ (gitignored), and prints a ready-to-paste
# Validation block. Exits with the gate's own exit code, so a red gate cannot
# quietly produce a green-looking record — and exits 3 ("GATE SHORT") when make
# exits 0 but the run checked less than it looks like it checked.
#
# Needs bash, git and python3 (stdlib only, 3.9-compatible). No node.
#
# WHAT THE PARSER READS, and why each rule is what it is:
#
#  1. pytest. `make check-full` prints MORE THAN ONE pytest summary: the `test`
#     target's full unit run (Makefile:86, `uv run pytest -v -m "not integration
#     and not benchmark ..."`, observed 8492 passed at S0) and later the small
#     `golden-conformance` run (Makefile:155). The last summary is therefore the
#     wrong one. Rule: every summary is attributed to the most recent
#     `uv run pytest` command line make echoed above it; `pytest_*` come from the
#     summary whose command carries `-m "not integration` (the `test` recipe,
#     and `ci-be`'s at Makefile:192). If no such command is found (a custom
#     gate), the summary with the largest `passed` count is used instead.
#     `pytest_failed` counts `failed` plus `error(s)`.
#  2. vitest. `check-fe` / `ci-fe` run `vitest run`; its `Tests  N passed (N)`
#     line (or `Tests  F failed | P passed (N)`) gives `vitest_*`. Last one wins.
#  3. make errors. Every `make: *** [target] Error N` line (BSD/Apple make 3.81
#     and GNU make `[Makefile:L: target]` forms) becomes "target: N".
#  4. short_gate. True, with a reason each, when any of these holds:
#     - pytest ran fewer than PYTEST_FLOOR (8000) tests, or printed no summary,
#       on a gate that runs the unit suite (`make check-full|check|test|ci|ci-be`);
#     - no vitest summary on a gate that runs it (`check-full|check|check-fe|ci|ci-fe|test-fe`);
#     - a make target errored (make_errors is non-empty);
#     - a step masked by `|| true` failed anyway. `check-fe` (Makefile:138-139)
#       ends lint and format:check in `|| true`, so a missing node_modules still
#       exits 0 there; the log's `ERR_PNPM_` / `command not found` /
#       `node_modules missing` lines are what reveal it;
#     - for `make check-full|check`, an echoed recipe line of a target in the
#       chain is absent from the log (the target did not run);
#     - the tree changed during the run (see 5).
#     A red run can be short as well; the Validation block still says RED first.
#  5. dirty / dirty_after. The tree is sampled before and after the run.
#     `make lint` (Makefile:130-131, first in check-full) rewrites files, and
#     `make test` rewrites the `date:` of app/ai/agents/*/skill-versions.yaml.
#     Each skill-versions.yaml that was clean before the run is restored with
#     `git checkout --` after it, and only then is the tree compared. Any
#     remaining change is a short reason: what was validated is not what HEAD
#     (plus the uncommitted work) contains. Untracked files under
#     .claude/{reports,code-reviews,execution-reports,system-reviews}/ are left
#     out of both samples: the loop writes them and ships them later.
#
# Never runs DB-destructive commands; it runs exactly the gate command given.

set -uo pipefail

GATE_DEFAULT=(make check-full)
PYTEST_FLOOR=8000

parse_only=""
while [ $# -gt 0 ]; do
  case "$1" in
    --parse-only) parse_only=${2:-}; [ -n "$parse_only" ] || { echo "--parse-only needs a log path" >&2; exit 2; }; shift 2 ;;
    --) shift; break ;;
    # Print the whole leading comment block, however long it grows.
    -h|--help) awk 'NR>1 && /^#/ {print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) break ;;
  esac
done

if [ $# -ge 1 ]; then gate=("$@"); else gate=("${GATE_DEFAULT[@]}"); fi

command -v python3 >/dev/null 2>&1 || { echo "record-gate.sh needs python3 on PATH" >&2; exit 2; }

root=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "not a git repo" >&2; exit 2; }
cd "$root" || exit 2
head_sha=$(git rev-parse HEAD)
head_short=$(git rev-parse --short HEAD)
branch=$(git branch --show-current)

# Porcelain status minus untracked PIV artefacts. Reports and reviews under these
# four directories are written by the loop itself and are often left untracked
# until a follow-up PR, so they must not make a gate dirty. Tracked edits there
# still count.
porcelain() {
  git status --porcelain | grep -Ev '^\?\? \.claude/(reports|code-reviews|execution-reports|system-reviews)/'
}

# Tree signature: porcelain status plus a hash of the tracked diff, so a change
# to an already-modified file is seen too.
tree_sig() { { porcelain; git diff HEAD | git hash-object --stdin; } 2>/dev/null; }

dirty=false
[ -n "$(porcelain)" ] && dirty=true

if [ -n "$parse_only" ]; then
  [ -f "$parse_only" ] || { echo "cannot read $parse_only" >&2; exit 2; }
  log=$parse_only
  rc=""               # derived from the log by the parser
  started=""; finished=""
  dirty_after=$dirty
  tree_changed=false
  changed_paths=""
else
  if [ "$dirty" = true ]; then
    echo "WARNING: working tree is dirty. The record will name $head_short, but the run" >&2
    echo "         covers uncommitted changes that commit does not contain." >&2
  fi
  clean_sv=()
  for f in app/ai/agents/*/skill-versions.yaml; do
    [ -f "$f" ] || continue
    git diff --quiet HEAD -- "$f" 2>/dev/null && clean_sv+=("$f")
  done
  sig_before=$(tree_sig)
  status_before=$(porcelain)

  mkdir -p "$root/.claude/state/gate"
  log="$root/.claude/state/gate/$(date -u +%Y%m%dT%H%M%SZ)-$head_short.log"
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "recording gate at $head_short ($branch): ${gate[*]}"
  echo "full log: $log"
  "${gate[@]}" 2>&1 | tee "$log"
  rc=${PIPESTATUS[0]}
  finished=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  for f in "${clean_sv[@]+"${clean_sv[@]}"}"; do
    if ! git diff --quiet HEAD -- "$f" 2>/dev/null; then
      git checkout -- "$f" && echo "restored $f (gate rewrote its date; it was clean before the run)"
    fi
  done

  dirty_after=false
  [ -n "$(porcelain)" ] && dirty_after=true
  tree_changed=false
  changed_paths=""
  if [ "$(tree_sig)" != "$sig_before" ]; then
    tree_changed=true
    changed_paths=$(diff <(printf '%s\n' "$status_before") <(porcelain) | sed -n 's/^> //p')
    [ -n "$changed_paths" ] || changed_paths="(content of an already-modified file changed; see git diff)"
  fi
fi

json=$(
  GATE_LOG="$log" GATE_RC="$rc" GATE_CMD="${gate[*]}" GATE_PARSE_ONLY="$parse_only" \
  GATE_HEAD="$head_sha" GATE_HEAD_SHORT="$head_short" GATE_BRANCH="$branch" \
  GATE_DIRTY="$dirty" GATE_DIRTY_AFTER="$dirty_after" GATE_STARTED="$started" GATE_FINISHED="$finished" \
  GATE_TREE_CHANGED="$tree_changed" GATE_CHANGED_PATHS="$changed_paths" GATE_PYTEST_FLOOR="$PYTEST_FLOOR" \
  python3 - <<'PY'
import json
import os
import re

env = os.environ
ansi = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
with open(env["GATE_LOG"], encoding="utf-8", errors="replace") as fh:
    lines = [ansi.sub("", ln).rstrip("\r\n") for ln in fh]

# 1. pytest summaries, each attributed to the last echoed `uv run pytest` line.
#    `docker run` lines (the `fidelity-gate` target runs pytest inside the pinned
#    image) also start a new command, so that run's summary is not taken as `test`'s.
summary_re = re.compile(
    r"^(?:=+ )?((?:\d+ (?:passed|failed|skipped|deselected|xfailed|xpassed|errors?|warnings?)(?:, )?)+)"
    r" in [0-9.]+s.*?(?: =+)?$"
)
count_re = re.compile(r"(\d+) (passed|failed|skipped|deselected|xfailed|xpassed|errors?|warnings?)")
last_cmd = ""
summaries = []
for ln in lines:
    if ln.startswith(("uv run pytest", "docker run ")):
        last_cmd = ln
        continue
    m = summary_re.match(ln.strip())
    if m:
        counts = {}
        for n, word in count_re.findall(m.group(1)):
            key = "error" if word.startswith("error") else word
            counts[key] = counts.get(key, 0) + int(n)
        summaries.append((last_cmd, counts))

chosen = None
for cmd, counts in summaries:
    if '-m "not integration' in cmd:
        chosen = counts
if chosen is None and summaries:
    chosen = max((c for _, c in summaries), key=lambda c: c.get("passed", 0))

pytest_passed = chosen.get("passed", 0) if chosen is not None else None
pytest_failed = (chosen.get("failed", 0) + chosen.get("error", 0)) if chosen is not None else None
pytest_skipped = chosen.get("skipped", 0) if chosen is not None else None

# 2. vitest `Tests  ... (N)` line; last one wins.
vitest_passed = vitest_failed = None
vt_re = re.compile(r"^\s*Tests\s+(.*)\(\d+\)\s*$")
for ln in lines:
    m = vt_re.match(ln)
    if m:
        p = re.search(r"(\d+) passed", m.group(1))
        f = re.search(r"(\d+) failed", m.group(1))
        vitest_passed = int(p.group(1)) if p else 0
        vitest_failed = int(f.group(1)) if f else 0

# 3. make errors (Apple make 3.81 `[target]`, GNU make `[Makefile:L: target]`).
make_errors = []
me_re = re.compile(r"make(?:\[\d+\])?: \*\*\* \[([^\]]+)\] Error (\d+)")
for ln in lines:
    m = me_re.search(ln)
    if m:
        target = m.group(1).split(": ")[-1]
        entry = "%s: %s" % (target, m.group(2))
        if entry not in make_errors:
            make_errors.append(entry)

cmd = env["GATE_CMD"]
if env["GATE_RC"] == "":
    # --parse-only: make exits 2 when a target errors.
    exit_code = 2 if make_errors else 0
else:
    exit_code = int(env["GATE_RC"])

# 4. short reasons.
words = cmd.split()
target = words[1] if len(words) >= 2 and words[0] == "make" else ""
floor = int(env["GATE_PYTEST_FLOOR"])
reasons = []
if target in ("check-full", "check", "test", "ci", "ci-be"):
    if pytest_passed is None:
        reasons.append("no pytest summary in the log")
    elif pytest_passed < floor:
        reasons.append("pytest passed %d < floor %d" % (pytest_passed, floor))
if target in ("check-full", "check", "check-fe", "ci", "ci-fe", "test-fe") and vitest_passed is None:
    reasons.append("no vitest summary in the log")
for e in make_errors:
    reasons.append("make target errored: " + e)
masked = [ln.strip() for ln in lines
          if "ERR_PNPM_" in ln or "command not found" in ln or "node_modules missing" in ln]
if masked:
    reasons.append("a step failed (some masked by `|| true`): " + masked[0])
if target in ("check-full", "check"):
    markers = {
        "lint": "uv run ruff format .",
        "types": "uv run mypy app/",
        "test": "uv run pytest -v -m",
        "check-fe": "cd cms && pnpm --filter web test",
        "security-check": "uv run ruff check app/ --select=S",
        "validate-overlays": "uv run python scripts/validate-overlays.py",
        "lint-numeric": "Checking for falsy-numeric traps",
        "golden-conformance": "uv run pytest app/design_sync/tests/test_golden_conformance.py",
        "flag-audit": "uv run python scripts/flag-audit.py",
    }
    for name, marker in markers.items():
        if not any(ln.startswith(marker) for ln in lines):
            reasons.append("target did not run: " + name)
if env["GATE_TREE_CHANGED"] == "true":
    reasons.append("tree changed during the run: " + " | ".join(env["GATE_CHANGED_PATHS"].splitlines()))

record = {
    "head": env["GATE_HEAD"],
    "head_short": env["GATE_HEAD_SHORT"],
    "branch": env["GATE_BRANCH"],
    "dirty": env["GATE_DIRTY"] == "true",
    "dirty_after": env["GATE_DIRTY_AFTER"] == "true",
    "command": cmd if not env["GATE_PARSE_ONLY"] else "%s (parse-only: %s)" % (cmd, env["GATE_PARSE_ONLY"]),
    "exit_code": exit_code,
    "started": env["GATE_STARTED"] or None,
    "finished": env["GATE_FINISHED"] or None,
    "pytest_passed": pytest_passed,
    "pytest_failed": pytest_failed,
    "pytest_skipped": pytest_skipped,
    "vitest_passed": vitest_passed,
    "vitest_failed": vitest_failed,
    "make_errors": make_errors,
    "short_gate": bool(reasons),
    "short_reasons": reasons,
}
print(json.dumps(record, indent=2))
PY
) || { echo "record-gate.sh: parser failed" >&2; exit 2; }

if [ -n "$parse_only" ]; then
  printf '%s\n' "$json"
  exit 0
fi

out="$root/.claude/last-gate.json"
printf '%s\n' "$json" > "$out"

# Read back the fields the block needs (python, not jq: jq is not guaranteed).
field() { printf '%s' "$json" | python3 -c 'import json,sys; v=json.load(sys.stdin)[sys.argv[1]]; print("" if v is None else (json.dumps(v) if isinstance(v,(list,bool)) else v))' "$1"; }
short=$(field short_gate)

echo
echo "wrote $out"
echo
echo "--- Validation block (paste verbatim; do not retype the numbers) ---"
echo
if [ "$rc" -ne 0 ]; then
  echo "**GATE RED** (exit $rc) — \`${gate[*]}\`, at \`$head_short\`:"
elif [ "$short" = true ]; then
  echo "**GATE SHORT** — \`${gate[*]}\` exited 0 at \`$head_short\`, but checked less than it looks like."
  echo "This record is NOT a pass."
else
  echo "\`observed\` — \`${gate[*]}\`, at \`$head_short\`, exit 0:"
fi
# The dirty warning above went to stderr, which is NOT part of what gets pasted.
if [ "$dirty" = true ]; then
  echo "(dirty tree — this run covers uncommitted changes \`$head_short\` does not contain.)"
fi
echo
echo '```'
[ -n "$(field pytest_passed)" ] && echo "pytest:  $(field pytest_passed) passed, $(field pytest_failed) failed, $(field pytest_skipped) skipped"
[ -n "$(field vitest_passed)" ] && echo "vitest:  $(field vitest_passed) passed, $(field vitest_failed) failed"
echo "window:  $started -> $finished"
echo '```'
if [ "$short" = true ]; then
  echo
  echo "Short reasons:"
  printf '%s' "$json" | python3 -c 'import json,sys; [print("    " + r) for r in json.load(sys.stdin)["short_reasons"]]'
fi
echo
echo "full log: ${log#"$root"/}"

if [ "$short" = true ] && [ "$rc" -eq 0 ]; then exit 3; fi
exit "$rc"
