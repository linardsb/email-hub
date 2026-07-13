# Tech-Debt 20 — Frontend / Repo Sweep (F050 + F063)

**Closes:** `TECH_DEBT_AUDIT.md` rows F050 + F063; corresponding partial-checkbox
items in `.agents/plans/tech-debt-00-status-and-roadmap.md` §44 + §162 + §167.
**Branch:** `chore/tech-debt-20-frontend-sweep`.
**Estimated effort:** one session (~60–90 min). 5 discrete commits — F050 is a
~3-line type-aliasing change; the F063 commits are mechanical but high
blast-radius (file moves, audit rewrites) and want separate review.
**Gate:** `make check-fe` (only catches F050 — manual verification covers F063).

---

## Branch precondition (do NOT skip)

The current working tree is on `chore/tech-debt-19-backend-sweep` with 14
modified files + 3 untracked files (`app/ai/agents/*/schemas.py`,
`app/core/{config/database.py,database.py,exceptions.py}`, plus untracked
`app/ai/agents/types.py`, two new tests). That work is the predecessor
session's deliverable — **it must be committed and PR'd before** this plan
runs, otherwise the new branch will either strand the changes or bundle them
with this work and make both PRs unreviewable.

Preflight:

```bash
# Confirm tech-debt-19 is committed + pushed.
git status                           # working tree clean
git log --oneline main..HEAD         # tech-debt-19 commits present
gh pr list --head chore/tech-debt-19-backend-sweep   # PR exists (any state)

# Then branch from main (NOT from tech-debt-19).
git checkout main && git pull --ff-only
git checkout -b chore/tech-debt-20-frontend-sweep
```

If the tech-debt-19 PR is still pre-merge, that's fine — branch from `main` and
this work proceeds independently. The two PRs touch zero overlapping files.

---

## Decision: F063 option (a) vs option (b)

`TECH_DEBT_AUDIT.md:105` and `.agents/plans/tech-debt-00-status-and-roadmap.md:44`
both document that F063 closes when EITHER:

- **(a)** `.gitignore` flips to a blanket `data/debug/*/*` ignore plus `!`
  exceptions for the **5** curated fixture types (`expected.html`,
  `manifest.yaml`, `vlm_classifications.json`, `actual-tree-with-fixes.html`,
  `actual-with-fixes.html`). Closes the "new debug file type defaults to
  tracked" footgun. **Overrides** the deliberate maintainer comment at
  `.gitignore:113` and Session 0's pending-maintainer-affirmation deferral
  (tech-debt-00 §464).
- **(b)** The line-113 "explicit-ignore-regenerable" comment is updated to
  enumerate all 5 curated fixture types and declare the current pattern the
  final design — F063 closes as-designed with no `.gitignore` flip.

**This plan implements (a).** Rationale:

1. **Failure mode of (b) is silent.** A developer adds a new regenerable debug
   filename (e.g. a 4th visual-regression artifact, or a fresh diagnostic
   output) and `git add data/debug/` pulls it into the next commit unnoticed.
   The `=2.0` stray and historical `*.zip` accidents at repo root are the
   exact same failure mode at a different scope.
2. **Failure mode of (a) is loud.** Adding a new curated fixture type without
   an `!` exception shows up immediately as "why isn't my file tracked?" in
   the dev's own workflow — they fix the `!` line and move on.
3. **Cost is symmetric.** (b) requires editing the comment and audit rows; (a)
   requires the same plus replacing ~7 explicit-ignore lines with one blanket
   + 5 exceptions. Both touch ≤15 lines.

**To override → option (b):** before /fe-execute, replace §C2 below with:
"Edit `.gitignore` lines 112–115 to enumerate all 5 curated types and remove
the 'we ignore the regenerable bits explicitly rather than nuking the whole
tree' clause; remove the stray `=2.0` line." Skip the blanket pattern entirely.
The remaining commits (C1, C3, C4, C5) are unchanged.

**Update history:**
1. Plan originally documented 5 curated fixture types.
2. During preflight, untracked `design.png` + `design_meta.json` files
   surfaced in `data/debug/7/` and `data/debug/8/`. Initial assumption: 6th
   and 7th curated pair. Plan revised to land 7 in option (a)'s exception
   list and the user confirmed.
3. During /fe-execute, grep confirmed `design.png` is regenerable from Figma
   on every sync (`app/design_sync/service.py:229`,
   `app/design_sync/diagnose/extract.py:146` / `:316`) and is listed
   alongside `raw_figma.json`, `structure.json`, `tokens.json`, `report.json`
   as a debug output in `docs/design-to-html-pipeline-audit.md:1407`. No
   code/doc evidence treats it as durable. Plan reverted to 5 curated types;
   `design.png` + `design_meta.json` stay IGNORED via the blanket pattern.
   The user confirmed and the C2 commit was rebased to drop them before
   push (zero binary bloat in git history).

---

## Files to create / modify

| # | File | Change |
|---|---|---|
| C1 | `cms/apps/web/src/types/css-compiler.ts` | Replace 3 hand-written interfaces with SDK re-exports aliased to preserve `CSSCompile*` casing |
| C2 | `.gitignore` | Remove `=2.0` stray (line 116); replace the explicit per-output `data/debug/*/foo` rules with one blanket `data/debug/*/*` + 5 `!` exceptions; refresh the F063 comment block to describe the new pattern and note that `design.png` / `design_meta.json` stay ignored as regenerable Figma outputs |
| C3 | `docs/TODO-completed.md` | Rotate: extract phases 0–39 (lines 36–5819) into a new archive file; keep phases 40+ inline; add an "older phases" link at the top |
| C3 | `docs/TODO-completed-archive-2025-h2.md` | New — receives the extracted Phase 0–39 content with a one-line preamble explaining the cutoff |
| C3 | `CLAUDE.md` | Refresh size claims at lines 113 and 119 — `TODO-completed.md` drops from 664KB to ~130KB; the "never `Read` (it's 664KB)" advisory becomes inaccurate |
| C4 | `.agents/plans/_archive/` | New directory — receives 25 `phase-NN-*.md` plans (phases 26–31 only; phases 32–49 were planned under feature-named files like `tree-compiler.md`, `qa-meta-eval.md` which stay in the active dir) |
| C4 | 25 `phase-2{6,7,8,9}-*.md` + `phase-3{0,1}-*.md` files | Move into `.agents/plans/_archive/` via `git mv` (preserves history) |
| C5 | `TECH_DEBT_AUDIT.md` | Update F050 row + F063 row to RESOLVED; flip the two partial-checkboxes in the Quick Wins section. **Anchor edits by text, not line number** — line refs (92/105/162/167) are starting hints only |
| C5 | `.agents/plans/tech-debt-00-status-and-roadmap.md` | Strike out F050 + F063 entries (status row, OPEN list, Quick Wins, Session 20 row); append closure note to the Session 0 closing paragraph. **Anchor edits by text, not line number** (44/48/53/118/464 are starting hints) |

**Out of scope:** updating the `data/debug/` fixtures themselves; touching any
other tech-debt findings (F051+ etc.); rotating `PRD.md` or any other docs;
deleting closed `tech-debt-NN-*.md` plans (the audit roadmap is the closure
record for those — they stay as historical reference).

---

## Implementation steps (5 commits)

### C1 — F050: SDK re-export of css-compiler.ts

**One file. ~5 minutes.** The SDK barrel already re-exports the generated
types — verified at `cms/packages/sdk/src/index.ts:3` (`export type * from
"./client/types.gen";`), and the three required types exist in
`cms/packages/sdk/src/client/types.gen.ts` at lines 1142 (`CssCompileRequest`),
1170 (`CssCompileResponse`), and 1210 (`CssConversionSchema`). The generator
camelCases the schema names (lowercase 's', single capital 'C') — current
consumers use the original `CSSCompile*` casing, so aliasing preserves the
import surface.

**Replace the entire body of `cms/apps/web/src/types/css-compiler.ts`:**

```ts
/**
 * CSS Compiler types — re-exported from the generated SDK.
 *
 * Backend source: `app/email_engine/schemas.py`. Regenerate via `make sdk`.
 */
export type {
  CssCompileRequest as CSSCompileRequest,
  CssCompileResponse as CSSCompileResponse,
  CssConversionSchema as CSSConversionSchema,
} from "@email-hub/sdk";
```

This mirrors the existing pattern in `cms/apps/web/src/types/outlook.ts` and
`cms/apps/web/src/types/chaos.ts` (the trio's other two files, already
converted in commit `eddcd1ac` / PR #40). Aliasing follows the precedent set by
`outlook.ts:13` (`export type { ModernizationStepSchema as ModernizationStep }`).

**Consumers (unchanged — verified before & after):**

- `cms/apps/web/src/hooks/use-css-compile.ts:6` — `import type { CSSCompileRequest, CSSCompileResponse } from "@/types/css-compiler";`
- `cms/apps/web/src/components/email-engine/CSSCompilerPanel.tsx:6` — `import type { CSSConversionSchema } from "@/types/css-compiler";`

Both keep working because the aliases preserve the names. Field shapes are
identical between hand-written and generated types (cross-checked the SDK
output above — same field names, same optionality, same nesting).

**Commit message:** `refactor(types): re-export CSS compiler types from SDK (F050)`

**Verify:**

```bash
pnpm --filter @email-hub/web typecheck     # passes
pnpm --filter @email-hub/web lint          # passes
```

### C2 — F063a: `.gitignore` blanket-ignore + curated exceptions

**One file. ~10 minutes.** Lines 100–124 of `.gitignore` are the F063 surface
area. Current state has three categorical issues: (1) the stray `=2.0` token
at line 116 (clearly a busted shell-redirect that nobody noticed), (2) seven
separate `data/debug/*/foo` ignore patterns that have to be maintained
manually as new debug outputs appear, and (3) the line-113 comment claims the
explicit-ignore pattern is intentional but doesn't enumerate the 5 curated
types it preserves.

**Replace lines 100–124 of `.gitignore` with:**

```
# Debug fixture directory — blanket-ignore regenerable artifacts, allow only
# the 5 curated fixture types per case directory. New debug file types default
# to ignored; add a `!` line below to commit a new curated type.
# Curated types (see TECH_DEBT_AUDIT.md F063):
#   - expected.html              hand-written ground-truth HTML
#   - manifest.yaml              fixture metadata
#   - vlm_classifications.json   VLM label set for AI judge calibration
#   - actual-tree-with-fixes.html  tree-mode converter durable evidence (V2 plan)
#   - actual-with-fixes.html       converter durable before/after record (V1 plan)
# design.png and design_meta.json are intentionally IGNORED — they are
# regenerable Figma exports (app/design_sync/service.py:229,
# diagnose/extract.py:146/316), not durable curated fixtures.
data/debug/*/*
!data/debug/*/expected.html
!data/debug/*/manifest.yaml
!data/debug/*/vlm_classifications.json
!data/debug/*/actual-tree-with-fixes.html
!data/debug/*/actual-with-fixes.html

# Top-level debug hygiene (F063)
*.zip
e2e-screenshots/
```

This deletes lines 100–124 entirely and replaces them with the block above.
The deleted patterns become redundant under the blanket: `actual.html`,
`rendered.png`, `rendered_resized.png`, `reference_rendered.png`, `diff.png`,
`reference_diff.png`, `visual_report.json`, `_visual_test.html`,
`actual-with-flags.html`, `raw_figma.json`, `structure.json`, `tokens.json`,
`report.json`, `assets/`, and the orphan `=2.0`.

**No pre-execute fixture-add step needed.** During /fe-execute, grep
confirmed `design.png` and `design_meta.json` are regenerable Figma outputs
written by `app/design_sync/service.py:229` and
`app/design_sync/diagnose/extract.py:146/316`. They are intentionally NOT
included in the `!` exception list — they stay ignored by the blanket
pattern alongside `raw_figma.json` / `structure.json` / `tokens.json` etc.

**Note:** the top-level `data/debug/manifest.yaml` (no intermediate directory,
visible in `git ls-tree`) is NOT affected by `data/debug/*/*` — that pattern
requires an intermediate path segment. It stays tracked as before.

**Verify (load-bearing — the blanket can wrongly evict a tracked fixture):**

```bash
# Files currently tracked under data/debug/ — must match exactly post-edit.
git ls-tree -r --name-only HEAD data/debug | sort > /tmp/tracked-before.txt
# Expect: 5 unique filenames, ~24 files total across case dirs.

# After editing .gitignore, simulate what git will see for each tracked path.
while read -r path; do
  status=$(git check-ignore -v "$path" 2>/dev/null || echo "TRACKED")
  echo "$path → $status"
done < /tmp/tracked-before.txt
```

Every tracked path must report `TRACKED` (i.e. `git check-ignore` returns
nothing — exit code 1). If any line reports an `.gitignore:<n>` match, the
`!` exception is missing and the blanket would have evicted that file on the
next `git rm --cached -r .` / `git add .` cycle.

Also confirm no surprise additions appear:

```bash
git status --ignored data/debug/ | head -40
```

Untracked regenerable files (e.g. `data/debug/5/structure.json` on a machine
that's run the converter) should show under "Ignored files" — not under
"Untracked".

**Commit message:** `chore(gitignore): blanket-ignore data/debug + curated exceptions (F063a)`

### C3 — F063b: `TODO-completed.md` rotation

**Two files. ~15 minutes.** `docs/TODO-completed.md` is 7,343 lines / ~664KB
(per CLAUDE.md). Splitting at Phase 40 sequesters pre-active-cycle work into
a quarterly archive and leaves the current file at ~1,525 lines (~130KB) —
small enough that `Read` reads it cheaply if `search_sections` isn't
available.

**Cut rationale:** lines 36–5819 hold phases 0–39 in numerical order. Phase 44
appears next at line 5820 (out-of-order — recent appends), followed by 41,
42, 46, 47, 48, 49. Cutting between line 5819 and 5820 leaves the out-of-order
recent block intact in the active file, where editors regularly touch it.
Cutting any lower (e.g. at Phase 30) leaves phases 31–39 dangling between two
files and creates an ambiguous "which file owns Phase 35?" question.

**Steps:**

1. Create `docs/TODO-completed-archive-2025-h2.md` with this preamble:

   ```markdown
   # TODO-completed — Archive (Phases 0–39, completed before 2026-04-01)

   > Quarterly rotation of `docs/TODO-completed.md`. Phases 0–39 covered
   > foundation work through Phase 39 (Pipeline Hardening). Active phases
   > (40+) live in `docs/TODO-completed.md`.
   >
   > For per-subtask history, search this file via jDocMunch
   > `search_sections` — same section-id pattern as the live file.
   >
   > Rotation cadence: per quarter. Next rotation: when the live file's
   > Phase-40+ section count exceeds ~12 phases or its size exceeds ~250KB.

   ---
   ```

   Then append lines 36–5819 of the current `docs/TODO-completed.md`
   (everything from the `## Phase 0 — Foundation Blockers` header through the
   last line before `## Phase 44`).

2. Edit `docs/TODO-completed.md` in place: delete lines 36–5819. Replace with:

   ```markdown
   ---

   > **Phases 0–39 archived** — see
   > [`TODO-completed-archive-2025-h2.md`](TODO-completed-archive-2025-h2.md).
   > Rotation cutoff: 2026-04-01. Active file holds phases 40+.

   ---
   ```

   The preserved top-of-file content (lines 1–35: heading, derivation note,
   "Architecture Principles" reference block) stays as-is. The post-cut
   content (Phase 44 onwards) stays as-is.

3. Update `CLAUDE.md` to reflect the new file sizes. Two lines need a
   text-anchored edit (line numbers 113 / 119 are starting hints):

   - The "Where to find things" table row currently reads
     `| Per-subtask phase history | `docs/TODO-completed.md` — 664KB, query via `search_sections` |`.
     Replace with `| Per-subtask phase history | `docs/TODO-completed.md` (~130KB, phases 40+) + `docs/TODO-completed-archive-2025-h2.md` (~535KB, phases 0–39), query via `search_sections` |`.
   - The "Roadmap" section's lead line currently reads
     `**Phases 0–49 complete.** Per-subtask history lives in `docs/TODO-completed.md` — query it via jDocMunch `search_sections`, never `Read` (it's 664KB).`
     Replace with `**Phases 0–49 complete.** Per-subtask history: phases 40+ live in `docs/TODO-completed.md` (~130KB), phases 0–39 in `docs/TODO-completed-archive-2025-h2.md` (~535KB). Query via jDocMunch `search_sections` — never `Read` the archive directly.`

   The `.claude/rules/doc-and-code-research.md` table also lists `TODO-completed.md`
   as 664KB at one point; check via `grep -n "664KB\|TODO-completed" .claude/rules/*.md`
   and apply the same two-file split if a stale reference exists.

**Verify (mechanical — line counts and orphaned references):**

```bash
# Archive contains the cut.
wc -l docs/TODO-completed-archive-2025-h2.md   # expect ~5790 lines
grep -c "^## Phase " docs/TODO-completed-archive-2025-h2.md   # expect 40 (0-39)

# Live file is slim and complete.
wc -l docs/TODO-completed.md   # expect ~1530 lines
grep -c "^## Phase " docs/TODO-completed.md    # expect 7 (44, 41, 42, 46, 47, 48, 49)

# No orphaned section-id references in other docs.
grep -rn "TODO-completed.md::.*phase-[0-3][0-9]" \
    docs/ .claude/ .agents/ TODO.md PRD.md 2>/dev/null
# Any hits → update those paths to TODO-completed-archive-2025-h2.md.
```

**Commit message:** `chore(docs): rotate TODO-completed.md — archive phases 0-39 (F063b)`

### C4 — F063c: archive phase plans older than active phase

**File moves only. ~10 minutes.** `.agents/plans/` holds exactly 25
`phase-NN-*.md` files — phases 26 (5), 27 (6), 28 (3), 29 (1), 30 (3), and 31
(6). Phases 32–49 do **not** have `phase-NN-*.md`-prefixed plans (the work
went into feature-named plans like `tree-compiler.md`, `qa-meta-eval.md`,
`production-design-sync-pipeline.md`, etc., which stay in the active dir as
historical reference). Active phase is P50 (`phase-50.8-*.md`).

**Scope (strict):** move ONLY files matching `phase-2[6-9]-*.md` or
`phase-3[0-1]-*.md`. Do NOT touch:

- `phase-50.8-*.md` — active phase
- `tech-debt-NN-*.md` — own closure tracking via TECH_DEBT_AUDIT.md
- `fix-*.md`, `production-*.md`, feature-named plans — historical record
- Anything else not matching the exact two globs above

**Steps:**

```bash
mkdir -p .agents/plans/_archive/

# Pre-count — must equal 25.
ls .agents/plans/phase-2[6-9]-*.md .agents/plans/phase-3[0-1]-*.md 2>/dev/null | wc -l

# Move.
git mv .agents/plans/phase-2[6-9]-*.md .agents/plans/_archive/
git mv .agents/plans/phase-3[0-1]-*.md .agents/plans/_archive/

# Post-confirm: no phase-NN-*.md remain in active dir except phase-50.8-*.
ls .agents/plans/phase-*.md 2>/dev/null
# expect: only phase-50.8-lego-promotion-and-detector-followup.md
ls .agents/plans/_archive/*.md | wc -l   # expect 25 (+1 for the README below)
```

If the pre-count is not 25, **stop and re-anchor**: someone added or removed
a phase-NN plan since this plan was written. Update the scope or escalate
before proceeding — the wrong file in `_archive/` is mechanically reversible
but PR-noisy.

Then create `.agents/plans/_archive/README.md`:

```markdown
# Plans archive

Phase plans for phases ≤49 (everything below active phase P50). Plans here
are reference-only; their work is documented in
`docs/TODO-completed-archive-2025-h2.md` (phases 0–39) or
`docs/TODO-completed.md` (phases 40+).

Active plans remain in `.agents/plans/`.

Cadence: archive a plan when its phase number falls below the active phase
number (i.e. P50.x active → archive ≤P49 on next rotation).
```

**Verify:**

```bash
# No phase plans below P50 remain in the active dir.
ls .agents/plans/phase-*.md 2>/dev/null  # expect only phase-50.8-*.md
ls .agents/plans/_archive/phase-*.md | wc -l  # expect 25

# No stale references in active plans.
grep -rn "\.agents/plans/phase-[2-3][0-9]" .agents/plans/ docs/ .claude/ 2>/dev/null
# Hits → either update the reference or note as expected (e.g. tech-debt-00
# roadmap can keep its references — they're historical).
```

**Commit message:** `chore(plans): archive phase plans for completed phases ≤49 (F063c)`

### C5 — F063d: audit doc updates

**Two files. ~10 minutes.** Close the loop in the audit ledger.
**All line numbers below are starting anchors — re-anchor by text content
before editing.** TECH_DEBT_AUDIT.md and tech-debt-00 are both append-mostly
files; an unrelated landed PR can shift these numbers by several lines.

**`TECH_DEBT_AUDIT.md`:**

- Line 92 (F050 row, "Status" column): replace `**PARTIAL** (`eddcd1ac`, #40). ...`
  with `**RESOLVED** (`<this PR>`). All three files in the trio are now SDK
  re-exports.`
- Line 105 (F063 row, "Status" column): replace the `**PARTIAL** — ...`
  description with `**RESOLVED** (`<this PR>`). `.gitignore` flipped to
  blanket-ignore + 5 `!` exceptions per option (a). `TODO-completed.md`
  rotated (phases 0–39 → archive). 27 phase-≤49 plans moved to
  `_archive/`.`
- Line 162 (Quick Wins F050 row): change `[~]` to `[x]` and drop the
  "`css-compiler.ts` still hand-written" clause.
- Line 167 (Quick Wins F063 row): change `[ ]` to `[x]` and drop the "*(partial
  — ...)*" annotation.

**`.agents/plans/tech-debt-00-status-and-roadmap.md`:**

- Line 44 (F063 status row): replace with `| F063 | CLOSED | Closed in
  Session 20 via approach (a): blanket `data/debug/*/*` ignore + 5 `!`
  exceptions; `=2.0` stray removed; TODO-completed.md rotated; phase ≤49
  plans archived. |`
- Line 48 (F050/F063 in OPEN list): remove F050 and F063 from the
  comma-separated list.
- Line 53 (Quick Wins line): drop the "mark F063 as partial" clause.
- Line 118 (Session 20 row): mark complete — change `| 20 | Frontend / repo
  sweep | F050, F063 closure | ...` to `| 20 ✅ | Frontend / repo sweep |
  F050, F063 closure | `tech-debt-20-frontend-sweep.md` | (this PR) |`.
- Line 464 (Session 0 closing note): append a sentence after the existing
  text: `Session 20 (2026-05-13) executed approach (a): blanket
  data/debug/*/*` ignore + 5 `!` exceptions for curated fixtures, closing
  F063 fully.

**Commit message:** `docs(tech-debt): mark F050 + F063 closed (Session 20)`

---

## Security checklist

For files in this plan only:

- [ ] No `(x as any)` type casts in `css-compiler.ts` — SDK aliasing is a
      pure `export type` rename with no runtime impact.
- [ ] No new `authFetch` / API call surface introduced.
- [ ] No `dangerouslySetInnerHTML`, sandbox, or token-handling code touched.
- [ ] No `sessionStorage` / `localStorage` reads added.
- [ ] No secrets, credentials, or `.env*` files in any commit's diff.
- [ ] `.gitignore` edits do not un-ignore `.env*`, `node_modules/`, or
      `cms/.env*` — confirmed by reading the unchanged sections (lines 1–4,
      35–50) before/after.

Full codebase security sweep is `/fe-validate`.

---

## Verification

Single end-to-end check after all 5 commits:

```bash
# F050 — frontend gate.
make check-fe                        # lint + format + types + tests must pass

# F063a — tracked fixtures intact, no surprises.
git ls-tree -r --name-only HEAD data/debug | awk -F/ '{print $NF}' | sort -u
# expect exactly 5 unique filenames:
#   actual-tree-with-fixes.html, actual-with-fixes.html, expected.html,
#   manifest.yaml, vlm_classifications.json
git diff --stat HEAD~5 -- data/debug/   # expect: no file additions or deletions

# F063b — rotation arithmetic.
wc -l docs/TODO-completed.md docs/TODO-completed-archive-2025-h2.md
grep -c "^## Phase " docs/TODO-completed.md             # 7
grep -c "^## Phase " docs/TODO-completed-archive-2025-h2.md  # 40

# F063c — plan archive count.
ls .agents/plans/phase-*.md           # only phase-50.8-*.md
ls .agents/plans/_archive/*.md | wc -l   # ≥27

# F063d — audit doc cleanup.
grep -n "F050\|F063" TECH_DEBT_AUDIT.md .agents/plans/tech-debt-00-status-and-roadmap.md \
  | grep -iE "partial|open|pending"
# expect: zero hits (all references now closed/resolved)

# Orphaned references — none of these may resolve to a moved/deleted path.
grep -rn "\.agents/plans/phase-[2-4][0-9]-" \
    docs/ .claude/ TODO.md PRD.md README.md 2>/dev/null
grep -rn "TODO-completed\.md::.*phase-[0-3][0-9]" \
    docs/ .claude/ .agents/ TODO.md PRD.md 2>/dev/null
```

If any of the orphan-reference greps surface hits in active (non-archived)
docs, update those references as a sixth commit before opening the PR.

- [ ] `make check-fe` passes
- [ ] `git ls-tree` set unchanged (5 curated types preserved)
- [ ] No `(x as any)` casts in changed files
- [ ] Semantic Tailwind tokens — N/A (no TSX changed)
- [ ] Auth/RBAC works — N/A (no API or route surface touched)
- [ ] PR description includes the rotation arithmetic (line counts +
      phase counts) so reviewers can verify without running greps locally

---

## Out of scope

- Updating `data/debug/` fixtures themselves (Phase 49 / 50 work).
- Any tech-debt finding other than F050 + F063.
- Rotating `PRD.md`, `TODO.md`, or `TECH_DEBT_AUDIT.md`.
- Deleting closed `tech-debt-NN-*.md` plans — they're the historical record
  for each session and stay in `.agents/plans/`.
- SDK regeneration (`make sdk`) — the SDK already contains `CssCompile*`
  types as of `eddcd1ac` (the same regeneration that produced `outlook.ts` and
  `chaos.ts` re-exports). Re-running `make sdk` is unnecessary and would
  surface unrelated drift.
- Adding F050 / F063 entries to `.agents/deferred-items.json` — neither
  finding has a deferred-items entry today (audit-tracked only), and closing
  them in TECH_DEBT_AUDIT.md is the convention.

## Post-merge follow-up

Mention in the PR description so the next session doesn't get cache-stale hits:

- **jDocMunch reindex:** the jDocMunch index keys section IDs off `doc_path`.
  After this PR merges, run `index_local({ path: "<repo>", incremental: true,
  use_ai_summaries: false })` against `local/email-hub` so
  `search_sections` finds phases 0–39 under the new archive `doc_path` instead
  of returning stale hits for the old (now-removed) `doc_path: TODO-completed.md`
  rows. Until reindex runs, queries for archived phases may return no
  results — read the archive directly as a fallback.
