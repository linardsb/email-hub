#!/usr/bin/env bash
# inherited-figures.sh — find MEASUREMENTS a surface inherited rather than re-derived.
#
# The defect this exists for: a number is copied plan -> report -> PR body ->
# handoff prompt and re-derived at none of them. Provenance labels do not catch
# it; the label is usually present and simply names a run that is no longer the
# current one. What discriminates it is head-relative staleness — the same digits
# survive unchanged while the commit they describe moves.
#
#   inherited-figures.sh <new-surface> <prior-surface> [<prior-surface>...]
#   inherited-figures.sh <draft-body> --pr 150        # adds the PR's published body
#
# Scope is deliberately narrow. It matches a number ONLY when bound to a
# measurement word (passed/failed/skipped/suites/files/lines/s/ms/queries/rows/…),
# so issue references, dates, phase numbers and session ids do not drown the
# signal. An earlier draft matched every 2+ digit number and produced 29 hits on
# a real PR body, nearly all noise — a check people switch off is worth nothing.
#
# Exits 1 if any inherited measurement is found. They are not necessarily wrong;
# they are UNAUDITED. Re-derive each at the current head, or say why it is
# head-independent.
#
# What this does NOT catch, stated so it is not oversold: a correct number under
# a wrong label, a correctly-derived counterfactual printed as Observed, or a
# prose claim with no numeral in it at all ("GitHub retargets automatically").
# It catches the copying, which is the mechanism the numeric instances shared. For the gate line specifically, prefer record-gate.sh,
# which removes the opportunity instead of auditing it.
#
# It also does not reach a figure bound to no unit word, and its duration matcher
# drops a minute prefix — 1m22.325s and a bare 22.325s reduce to the same key, so
# a genuinely distinct pair of durations can read as one inherited figure and a
# genuinely shared one can be missed. Do not describe its output as EVERY shared
# measurement; it is every measurement it can bind to a unit word or a duration.
#
# Two design choices: --pr fetches the published body (the surface that is NOT
# in the working tree, and the one a retired claim most often survives on), and
# a missing prior surface is a printed note and exit 0 rather than a usage
# error — a docs-only PR has no implementation report, and a check that errors
# on the ordinary case gets removed from the skill that calls it.

set -uo pipefail

usage() { echo "usage: $(basename "$0") <new-surface> [<prior-surface>...] [--pr <N>]" >&2; }

new=""
pr=""
priors=()
while [ $# -gt 0 ]; do
  case "$1" in
    --pr) pr=${2:-}; shift 2 || { usage; exit 2; } ;;
    -h|--help) usage; exit 0 ;;
    *) if [ -z "$new" ]; then new=$1; else priors+=("$1"); fi; shift ;;
  esac
done

[ -n "$new" ] || { usage; exit 2; }
# -f, not -r: a directory is readable, extracts nothing, and used to land on the
# clean-comparison path as a confident PASS.
[ -f "$new" ] && [ -r "$new" ] || { echo "cannot read file $new" >&2; exit 2; }

tmpdir=$(mktemp -d) || { echo "mktemp -d failed" >&2; exit 2; }
trap 'rm -f "$tmpdir"/* 2>/dev/null; rmdir "$tmpdir" 2>/dev/null' EXIT

if [ -n "$pr" ]; then
  body="$tmpdir/pr-$pr-body.md"
  if gh pr view "$pr" --json body -q '.body' > "$body" 2>/dev/null && [ -s "$body" ]; then
    priors+=("$body")
    echo "note: added PR #$pr's published body as a prior surface ($(wc -l < "$body" | tr -d ' ') lines)."
  else
    echo "note: could not fetch PR #$pr's body (gh not authenticated, or no such PR)." >&2
    echo "      Continuing without it — the published body is UNCHECKED." >&2
  fi
fi

UNITS='passed|failed|skipped|total|suites?|files?|tests?|cases|lines|queries|rows|frames|successful|cached'

# number + measurement word, or a bare duration (58.724s, 1m0.33s, 250 ms).
extract() {
  {
    grep -oiE "[0-9][0-9.,]*[[:space:]]*(${UNITS})" "$1" 2>/dev/null
    grep -oiE '[0-9][0-9.]*[[:space:]]*(ms|s)\b' "$1" 2>/dev/null
  } | tr '\t' ' ' | tr -s ' ' ' ' | tr 'A-Z' 'a-z' | sed 's/[[:space:]]*$//' | sort -u
}

prior_all="$tmpdir/prior_all"
: > "$prior_all"
readable=0
for p in "${priors[@]+"${priors[@]}"}"; do
  # -f here too: a directory prior would otherwise count as readable, extract
  # nothing, and be reported below as "a surface with no measurements in it".
  if [ -f "$p" ] && [ -r "$p" ]; then extract "$p" >> "$prior_all"; readable=$((readable + 1))
  else echo "note: skipping unreadable prior surface $p" >&2; fi
done

if [ "$readable" -eq 0 ]; then
  echo "NOTE — no readable prior surface, so nothing can be compared."
  echo "This is the ordinary case for a docs-only PR with no implementation report."
  echo "It is NOT a pass: every figure in $(basename "$new") is still unaudited, and"
  echo "the by-eye checks (a right number under a wrong label, a claim with no"
  echo "numeral) are the only ones that apply here."
  exit 0
fi

sort -u -o "$prior_all" "$prior_all"

# A readable prior with no measurement in it compares nothing, and used to print
# the same confident PASS as a real clean check. The no-prior-surface path above
# is careful to say "this is NOT a pass"; this adjacent one has to be too.
if [ ! -s "$prior_all" ]; then
  echo "NOTE — $readable prior surface(s) read, but none contains a figure this check can"
  echo "bind to a unit word or a duration, so there was nothing to compare against."
  echo "It is NOT a pass: every figure in $(basename "$new") is still unaudited, and the"
  echo "by-eye checks (a right number under a wrong label, a claim with no numeral) are"
  echo "the only ones that apply here."
  exit 0
fi

carried=$(extract "$new" | grep -Fxf "$prior_all" 2>/dev/null || true)

if [ -z "$carried" ]; then
  echo "PASS — no measurement in $(basename "$new") also appears in the prior surface(s)."
  exit 0
fi

count=$(printf '%s\n' "$carried" | grep -c .)
echo "INHERITED MEASUREMENTS: $count in $(basename "$new"), each also present in a prior surface."
echo "Re-derive each at the current head, or state why it is head-independent."
echo
while IFS= read -r fig; do
  [ -n "$fig" ] || continue
  echo "  \"$fig\""
  # $fig is whitespace-normalised, so a fixed-string grep misses the source line
  # whenever its spacing is irregular ("22  passed", "22passed") and the figure
  # then prints with no file:line to chase. Match it space-flexibly instead.
  pat=$(printf '%s' "$fig" | sed 's/[.]/\\./g; s/ /[[:space:]]*/g')
  grep -niE "$pat" "$new" | head -2 | cut -c1-160 | sed 's/^/      /'
done <<< "$carried"

echo
if head_sha=$(git rev-parse --short HEAD 2>/dev/null); then
  if grep -qF "$head_sha" "$new"; then
    echo "Surface names the current head ($head_sha) — confirm the figures above came from a run AT it."
  else
    echo "WARNING: surface does not name the current head ($head_sha). Any figure quoted from a"
    echo "named run describes a different tree than the one being shipped."
  fi
fi

exit 1
