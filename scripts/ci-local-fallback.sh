#!/usr/bin/env bash
# Pre-push local-CI fallback.
#
# Runs the full local gate (`make check`) ONLY when GitHub-hosted Actions appear
# unavailable (billing/quota exhausted), so everyday pushes stay fast while CI is
# healthy and automatically fall back to local validation when it is not.
# Bypass entirely with `git push --no-verify`.
#
# Detection: when Actions is unfunded, GitHub still *creates* a workflow run, but
# it fails to start and no steps execute (vs a genuine failure, which runs steps
# and just fails them). We sample the most recent *completed* run; zero executed
# steps across its jobs ⇒ CI is not running ⇒ validate locally.
#
# Fail-safe bias: any uncertainty (gh missing, not authenticated, API error, no
# runs yet) runs the local gate — better to over-validate than skip silently.
#
# Override with env vars:
#   LOCAL_CI=1   force the local gate to run regardless of GitHub state
#   LOCAL_CI=0   skip the local gate regardless of GitHub state

set -uo pipefail

run_local() {
	echo "→ GitHub Actions unavailable — running local gate (make check)…" >&2
	exec make check
}
skip_local() {
	echo "✓ GitHub Actions healthy (last run executed) — skipping local gate; CI will validate." >&2
	exit 0
}

# Explicit overrides win.
case "${LOCAL_CI:-}" in
	1) run_local ;;
	0) echo "LOCAL_CI=0 — skipping local gate." >&2; exit 0 ;;
esac

command -v gh >/dev/null 2>&1 || run_local
gh auth status >/dev/null 2>&1 || run_local

repo=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || run_local
[ -n "${repo:-}" ] || run_local

# Most recent run (any branch — billing/quota is account/repo-wide).
read -r run_id status < <(
	gh run list --repo "$repo" --limit 1 \
		--json databaseId,status -q '.[0] | "\(.databaseId) \(.status)"' 2>/dev/null
) || run_local
[ -n "${run_id:-}" ] || run_local        # no runs yet → be safe

# An in-progress run means Actions is actively executing → CI is up.
[ "${status:-}" != "completed" ] && skip_local

# Completed run: count executed steps. Zero ⇒ nothing ran ⇒ billing/startup block.
steps=$(gh api "repos/$repo/actions/runs/$run_id/jobs" \
	-q '[.jobs[].steps[]] | length' 2>/dev/null)
[ "${steps:-0}" -eq 0 ] && run_local

skip_local
