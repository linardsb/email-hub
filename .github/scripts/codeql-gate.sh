#!/usr/bin/env bash
# codeql-gate.sh — fail when the PR's CodeQL analysis has an open alert at the
# gate's severity that the base branch's analysis does not.
#
# Ported from the taxi repo (f2cc6c4, .github/scripts/codeql-gate.sh). One
# email-hub change: every API call filters on tool_name=CodeQL. Semgrep OSS
# (.github/workflows/semgrep.yml) uploads SARIF to the same code-scanning API
# on the same PR ref, so without the filter a Semgrep upload would answer "was
# this ref analysed?" when CodeQL's upload never processed (green on a PR
# nothing CodeQL scanned), and an error-level Semgrep rule would gate here.
# Semgrep stays in its own workflow (advisory today: `continue-on-error`).
#
# Two more email-hub differences, in behaviour, not code: ci.yml runs only on
# PRs based on `main` (`pull_request: branches: [main]`), so the stacked-PR
# fallback below does not fire here until that filter is widened; and ci.yml's
# concurrency cancels superseded pushes to main, so main's baseline is its
# latest completed analysis, and a PR can briefly see a just-merged change's
# alerts as new until that push is analysed (re-run the PR's job then). The
# first run after this job lands compares against a main that CodeQL default
# setup analysed for `actions` only, so every existing python/JS alert at the
# gate's severity counts as new until the first push to main is analysed.
#
# Why a script: `github/codeql-action/analyze` never fails on findings. It
# uploads a SARIF and GitHub adds a separate "Code scanning results" check
# run to the PR; that check is not a job in ci.yml, so `ready.needs` cannot
# see it. This job reads the alerts GitHub produced from that upload (the
# analyze step waits for processing before it returns) and turns them into
# an exit code the `ready` job depends on.
#
# The rule is the audit-diff rule applied to CodeQL: the PR may not ADD an
# alert at the gate's severity that the base does not carry. The backlog
# rides. A dismissed alert is not open and never counts, so a human's
# dismissal in the GitHub UI (with a reason) is honoured; the AI-layer hook refuses
# that dismissal from a Claude session.
#
#   codeql-gate.sh --pr N --base BRANCH               # CI: GH_TOKEN + GITHUB_REPOSITORY set
#   codeql-gate.sh --pr N --base BRANCH --repo o/r    # locally, with `gh auth`
#   codeql-gate.sh --pr N --base BRANCH --fallback-base main   # default is main
#   codeql-gate.sh --pr-alerts f.json --base-alerts f.json   # offline, fixture JSON arrays
#   codeql-gate.sh -h|--help
#
# Gate severity: rule.security_severity_level in {high, critical} (GitHub's
# mapping of security-severity 7.0 and above) OR rule.severity == "error".
# Alerts are matched by their number, which is one entity across refs.
#
# Exit codes:
#   0  no new alert at the gate's severity (zero alerts is a valid answer and says so)
#   1  at least one new alert; or the PR ref has no analysis (red, not green)
#   2  usage, gh or jq missing, an API error other than "no analysis found"
#
# "Was this ref analysed?" is asked of the ANALYSES endpoint, not inferred from
# an empty alert list. GitHub answers [] for a ref it never analysed exactly as
# it does for a clean one, so the two are indistinguishable from the alerts
# endpoint alone once the repo has any upload at all.
# The PR ref with zero analyses is exit 1, red not green.
#
# A base with zero analyses falls back to the default branch's analysis
# (--fallback-base, default `main`). The codeql job runs on push to main only,
# so a STACKED PR — one whose base is another feature branch — has a base that
# was never analysed, and without the fallback every alert it inherits from
# main would count as new. If the fallback has no analysis either, the
# base counts as empty: every open alert on the PR at the gate's severity is
# new, with a warning. That is the state until a push to main has been
# analysed; a human marking that one PR ready in the GitHub UI is the bypass.
#
# What it does NOT catch: anything CodeQL does not query for (ci.yml asks for
# `queries: security-extended`; `security-and-quality` would widen it further
# and is deliberately not used,
# because its maintainability rules are not security findings yet would still
# reach the `rule.severity == "error"` branch below); an alert below the
# gate's severity; an alert on the base
# that GitHub tracks as the same alert after the PR moved it; and, through the
# fallback, an alert the PARENT PR of a stack introduced — the fallback
# compares against main, which does not carry it until the parent merges, so
# it counts as new on the child. Fixing that needs the parent's own
# refs/pull/<n>/merge analysis and therefore its number, which this script is
# not given; a human marking the PR ready is the bypass until the parent lands.

set -uo pipefail

pr=""; base=""; repo="${GITHUB_REPOSITORY:-}"; pr_file=""; base_file=""; fallback_base="main"
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) awk 'NR>1 && /^#/ {print; next} NR>1 {exit}' "$0"; exit 0 ;;
    --pr) pr=${2:-}; shift 2 ;;
    --base) base=${2:-}; shift 2 ;;
    --fallback-base) fallback_base=${2:-}; shift 2 ;;
    --repo) repo=${2:-}; shift 2 ;;
    --pr-alerts) pr_file=${2:-}; shift 2 ;;
    --base-alerts) base_file=${2:-}; shift 2 ;;
    *) echo "unknown argument: $1 (-h for the header)" >&2; exit 2 ;;
  esac
done
command -v jq >/dev/null 2>&1 || { echo "::error::jq is not installed; codeql-gate needs it"; exit 2; }

offline=0
if [ -n "$pr_file" ] || [ -n "$base_file" ]; then
  offline=1
  [ -n "$pr_file" ] && [ -n "$base_file" ] || { echo "usage: --pr-alerts and --base-alerts go together" >&2; exit 2; }
else
  [ -n "$pr" ] && [ -n "$base" ] || { echo "usage: codeql-gate.sh --pr N --base BRANCH [--repo o/r]   (-h for the header)" >&2; exit 2; }
  [ -n "$repo" ] || { echo "usage: --repo o/r (GITHUB_REPOSITORY is unset)" >&2; exit 2; }
  command -v gh >/dev/null 2>&1 || { echo "::error::gh is not installed; codeql-gate needs it"; exit 2; }
fi

# fetch <ref> → JSON array of open alerts on stdout.
# Returns 44 when GitHub answers "no analysis found" for that ref.
#
# stderr goes to its own file, never into `out`: a gh warning on an otherwise
# successful call would land in the JSON stream and break the `jq -s` below,
# exiting 2 on a healthy repo.
fetch() {
  local ref=$1 out rc err
  err=$(mktemp)
  out=$(gh api --paginate "repos/$repo/code-scanning/alerts?ref=$ref&state=open&tool_name=CodeQL&per_page=100" 2>"$err"); rc=$?
  if [ "$rc" -ne 0 ]; then
    if grep -q 'no analysis found' "$err"; then rm -f "$err"; return 44; fi
    cat "$err" >&2; rm -f "$err"; return 1
  fi
  rm -f "$err"
  printf '%s' "$out" | jq -s 'add // []'
}

# analyses <ref> → how many CodeQL analyses GitHub holds for that ref.
#
# The alerts endpoint cannot answer "was this ref ever analysed?". Before taxi's
# first upload it answered 404 "no analysis found" for an unanalysed
# ref, which is what `fetch`'s 44 keys on; after the first upload it answers a
# plain empty array instead, exactly like a clean ref (`observed` on taxi 2026-09-10:
# refs/pull/999/merge, refs/heads/main and refs/heads/does-not-exist all
# return [] with rc=0). So 44 no longer fires here and "no analysis" would
# read as "no alerts" — green on a PR nothing scanned. Count the analyses to
# tell the two apart.
analyses() {
  local ref=$1 out
  out=$(gh api --paginate "repos/$repo/code-scanning/analyses?ref=$ref&tool_name=CodeQL&per_page=100" 2>/dev/null) || return 1
  printf '%s' "$out" | jq -s 'add // [] | length'
}

if [ "$offline" -eq 1 ]; then
  pr_json=$(jq '.' "$pr_file") || { echo "::error::$pr_file is not JSON"; exit 2; }
  base_json=$(jq '.' "$base_file") || { echo "::error::$base_file is not JSON"; exit 2; }
  for f in "$pr_file" "$base_file"; do
    jq -e 'type == "array"' "$f" >/dev/null 2>&1 || { echo "::error::$f is not a JSON array of alerts"; exit 2; }
  done
  pr_ref="(fixture $pr_file)"; base_ref="(fixture $base_file)"
else
  pr_ref="refs/pull/$pr/merge"; base_ref="refs/heads/$base"

  # Ask "was it analysed?" before "what did it find?", so an unanalysed ref is
  # red rather than an empty alert list read as clean (F6).
  pr_analyses=$(analyses "$pr_ref") \
    || { echo "::error::listing CodeQL analyses for $pr_ref failed"; exit 2; }
  if [ "$pr_analyses" -eq 0 ]; then
    echo "::error::no CodeQL analysis for $pr_ref; the analyze step's upload was not processed, so this is red, not green"
    exit 1
  fi
  pr_json=$(fetch "$pr_ref"); rc=$?
  if [ "$rc" -eq 44 ]; then
    echo "::error::no CodeQL analysis for $pr_ref; the analyze step's upload was not processed, so this is red, not green"
    exit 1
  elif [ "$rc" -ne 0 ]; then
    echo "::error::listing alerts for $pr_ref failed"; exit 2
  fi

  base_analyses=$(analyses "$base_ref") \
    || { echo "::error::listing CodeQL analyses for $base_ref failed"; exit 2; }

  # A stacked PR bases on another feature branch, and the codeql job runs on
  # push to `main` only — so that base has no analysis of its own and every
  # alert the PR INHERITS from main would count as new. Fall back to the
  # default branch, which is the nearest ref that answers "what does this PR
  # add". base_ref is reassigned, so every message below names the ref the
  # comparison actually used.
  if [ "$base_analyses" -eq 0 ] && [ -n "$fallback_base" ] && [ "$base" != "$fallback_base" ]; then
    fallback_ref="refs/heads/$fallback_base"
    fallback_analyses=$(analyses "$fallback_ref") \
      || { echo "::error::listing CodeQL analyses for $fallback_ref failed"; exit 2; }
    # Same reason as the counts guard below: an empty value makes `-gt` exit 2
    # and the `if` take the else branch silently. Here that degrades to the old
    # behaviour (no fallback), not to green — but say so rather than rely on it.
    case "$fallback_analyses" in
      ''|*[!0-9]*) echo "::error::could not read the analysis count for $fallback_ref: '$fallback_analyses'"; exit 2 ;;
    esac
    if [ "$fallback_analyses" -gt 0 ]; then
      echo "::warning::no CodeQL analysis on refs/heads/$base (the codeql job runs on push to $fallback_base only); comparing against $fallback_ref instead, which has $fallback_analyses"
      base_ref="$fallback_ref"
      base_analyses="$fallback_analyses"
    fi
  fi

  if [ "$base_analyses" -eq 0 ]; then
    echo "::warning::no CodeQL analysis on $base_ref, and none on the $fallback_base fallback; every open alert on the PR at the gate's severity counts as new until a push to $fallback_base is analysed"
    base_json='[]'
  else
    base_json=$(fetch "$base_ref"); rc=$?
    if [ "$rc" -eq 44 ]; then
      echo "::warning::no CodeQL analysis on $base_ref; every open alert on the PR at the gate's severity counts as new until that ref is analysed"
      base_json='[]'
    elif [ "$rc" -ne 0 ]; then
      echo "::error::listing alerts for $base_ref failed"; exit 2
    fi
  fi
fi

report=$(jq -rn --argjson p "$pr_json" --argjson b "$base_json" '
  def gated: select(.state == "open"
    and ((((.rule.security_severity_level // "") | IN("high", "critical"))
      or ((.rule.severity // "") == "error"))));
  ($b | map(.number)) as $bn
  | ($p | map(gated)) as $pg
  | ($pg | map(select(.number as $n | ($bn | index($n)) == null))) as $new
  | ($new[] | "::error file=\(.most_recent_instance.location.path // "?"),line=\(.most_recent_instance.location.start_line // 0)::#\(.number) \(.rule.id) (\(.rule.security_severity_level // .rule.severity // "?")) — \((.most_recent_instance.message.text // .rule.description // "") | gsub("\n"; " ") | .[0:160]) \(.html_url // "")"),
    "COUNTS \($p | length) \($pg | length) \($b | length) \($new | length)"
') || { echo "::error::jq failed over the alert lists"; exit 2; }

printf '%s\n' "$report" | grep -v '^COUNTS '
counts=$(printf '%s\n' "$report" | grep '^COUNTS ')
pr_open=$(printf '%s' "$counts" | awk '{print $2}')
pr_gated=$(printf '%s' "$counts" | awk '{print $3}')
base_open=$(printf '%s' "$counts" | awk '{print $4}')
new=$(printf '%s' "$counts" | awk '{print $5}')

# Without this, an absent or malformed COUNTS line makes `$new` empty, `[ "" -gt
# 0 ]` errors with status 2, the `if` takes the else branch and the script
# prints "no new alert" and exits 0 — green because it could not read its own
# output. `set -u` does not catch a set-but-empty variable and there is no -e.
# The report records this exact shape biting once during development (a `jq -n`
# without -r); the cause was fixed, the fail-open was not.
for v in pr_open pr_gated base_open new; do
  case "${!v}" in
    ''|*[!0-9]*)
      echo "::error::codeql-gate could not parse its counts line: '$counts'"; exit 2 ;;
  esac
done

if [ "$new" -gt 0 ]; then
  echo "::error::codeql-gate: $new new alert(s) at high/critical or error on $pr_ref that $base_ref does not carry ($pr_open open on the PR, $pr_gated of them at the gate's severity, $base_open open on the base)"
  exit 1
fi
echo "codeql-gate: no new alert at high/critical or error on $pr_ref vs $base_ref ($pr_open open on the PR, $pr_gated at the gate's severity, $base_open open on the base)"
exit 0
