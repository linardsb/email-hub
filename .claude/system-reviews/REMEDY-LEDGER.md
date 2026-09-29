# Remedy ledger

Recurring failures found by `system-evolution-review` and the AI-layer change that fixes each.

| Date | Symptom | Root cause | Remedy (file) | PR |
|---|---|---|---|---|
| 2026-09-28 | Green gate invalidated by the WIP fold; gate re-run at `c29122d8` (t1-social-section-column-content-review.md, E1) | Hand-off order validate→commit, and `piv-commit` folds only one WIP commit, while `piv-create-pr` requires record `head == HEAD` | `.claude/skills/converter-fix/SKILL.md` §8, `.claude/skills/piv-implement/SKILL.md` "Next", `.claude/skills/piv-commit/SKILL.md` step 1 | #412 (applied) |
| 2026-09-28 | Untracked report/review made gates `dirty`; lead parked files in scratch each gate (t1-…-review.md, E2) | `record-gate.sh:91-94` counts untracked files; the PIV artefact directories are not gitignored | `.claude/skills/piv-create-pr/scripts/record-gate.sh` (gate-evidence writer), `.claude/skills/piv-validate/SKILL.md` §2 | #412 (applied) |
| 2026-09-28 | Gate at `71b9db89` short: subagent created a file mid-run (t1-…-review.md, E3) | No write location for subagents during a gate | `.claude/skills/piv-validate/SKILL.md` §2 | open |
| 2026-09-28 | F3–F5 plan-born generality defects found only at review (t1-…-review.md, E7) | Plan limits handling to corpus shapes without ledgering the general case; tree check asserts presence only | `.claude/skills/piv-plan-implementation/SKILL.md` Quality Criteria, `.claude/skills/converter-fix/SKILL.md` §0.4 | open |
| 2026-09-28 | R1 three-part log event added by an amendment (t1-…-review.md, E6) | Amendments do not re-open Patterns to Follow references | `.claude/skills/piv-plan-implementation/SKILL.md` AMENDMENTS template | open |
| 2026-09-28 | Pre-push hook re-stamps `skill-versions.yaml` (3 or more times: #408 s1, s2, #409) (t1-…-review.md, E4) | `scripts/ci-local-fallback.sh` runs `make check` without restoring clean-before stamps | `scripts/ci-local-fallback.sh`, `CLAUDE.md` Known environment issues | open |
| 2026-09-28 | c8 `expected.html` stripped by trailing-whitespace again (t1-…-review.md, E5) | No exclusion for converter baselines | `.pre-commit-config.yaml` `trailing-whitespace` | open |
| 2026-09-28 | Guard hook blocked `rm -rf .tmpscratch/…` and a read-only grep (t1-…-review.md, E9) | Substring match on the whole command; broad rule blocks any dotted relative path | `.claude/hooks/block-dangerous.sh:59-70` | open |
| 2026-09-28 | zsh word-split and `=word` failures (t1-…-review.md, E8) | No zsh guidance in the AI layer | `CLAUDE.md` Known environment issues | open |
| 2026-09-28 | Preflight skipped on a converter ticket (t1-…-review.md, E13) | `converter-fix` §0.2 does not say whether a plan-time grep satisfies it | `.claude/skills/converter-fix/SKILL.md` §0.2 | open |
| 2026-09-28 | Drifted code_ref left on a closed entry (t1-…-review.md, E12) | Plan instruction conflicts with `deferred-items` close step | `.claude/skills/deferred-items/SKILL.md` close step | open |
| 2026-09-28 | Unquoted heredoc swallowed backticks in the PR body (t1-…-review.md, E10) | `piv-create-pr` documents create, not edit | `.claude/skills/piv-create-pr/SKILL.md` Phase 3 | open |
| 2026-09-28 | Background wrapper killed (exit 144) while `record-gate.sh` ran on as an orphan (t1-…-review.md, E11) | `piv-validate` does not say how to run or recover a background gate | `.claude/skills/piv-validate/SKILL.md` §2 | open |
