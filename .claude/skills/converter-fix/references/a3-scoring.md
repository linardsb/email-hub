# A3 fidelity scoring

Detail for `converter-fix` step 5. A3 is advisory: it is reported on every converter change (CLAUDE.md
"Converter changes carry full-corpus A3") and a non-target regression stops for ratification, but it never
blocks a ship on its own number. How to state the numbers: `docs/converter-fidelity-ceiling.md` § 5.

## What the scorer does

`scripts/score-fidelity-cases.py` renders each case's live converter output with Playwright
(`render_case_png`, `app/design_sync/fidelity_case_scorer.py:193`), scores it against the design
reference PNG (`score_case_fidelity`, :91), prints `full_image / section_min / section_median` per case,
and writes `case<n>_rendered.png`, `case<n>_side_by_side.png` and `scores.json` to `.tmpscratch/fidelity/`
(gitignored, `.gitignore:205`). It converts through `run_case_conversion`
(`app/design_sync/tests/regression_runner.py:48-61`), so it scores the code in the checkout it lives in:
`REPO` is derived from the script's own path.

Composites: **LEFT = reference, RIGHT = render** (`scripts/score-fidelity-cases.py:78` pastes `ref_img` at `(0, 0)`).

## Setup in a worktree (required for a full-corpus run)

A clean checkout carries only case 5's reference (`maap/visual_design.png`, allowlisted at
`.gitignore:192-195`) and assets. For cases 6 to 10 the script prints `case <n>: NO reference PNG` and
skips; without `data/debug/<n>/assets/` the render has broken images. Copy the gitignored files from the
main checkout into the worktree (both paths are ignored there, so nothing is staged):

```bash
MAIN=<main checkout>; WT=$(git rev-parse --show-toplevel)
for d in "$MAIN"/email-templates/training_HTML/for_converter_engine/*/; do
  n=$(basename "$d"); cp -n "$d"*ual_design.png "$WT/email-templates/training_HTML/for_converter_engine/$n/" 2>/dev/null
done
for c in 5 6 7 8 9 10; do mkdir -p "$WT/data/debug/$c/assets"; cp -n "$MAIN/data/debug/$c/assets/"* "$WT/data/debug/$c/assets/"; done
git status --porcelain email-templates data/debug   # must print nothing new
```

If the main checkout lacks them, re-export with `scripts/export-case-assets.py` and a `FIGMA_TOKEN`
(ceiling doc § 4, ledger `phase-53.7-asset-reexport-prerequisite`). Playwright's Chromium must be
installed. A run whose table has fewer than six rows is short: report it as short, not as full-corpus A3.

## Running it

```bash
DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py            # all six
DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py --cases 7 8
```

- **Cases go through `--cases`, not positionally.** A positional id makes argparse exit, and the
  `scores.json` left from an earlier run is then read as current (this confounded G7's first
  measurements). Read the table this run printed, or check `scores.json`'s mtime.
- **The cache flag.** `DESIGN_SYNC__SECTION_CACHE_ENABLED` is a real setting
  (`app/core/config/design_sync.py:29`, default true). G7 (#359) recorded that the section cache poisoned
  the harness and scored with it off. In the current code the cache is consulted only when a
  `connection_id` is passed (`app/design_sync/converter_service.py:373`, :522, :833), and
  `run_case_conversion` passes none, so the harness should not reach it; that gating dates from 35.10,
  before #359. Keep the flag in the command anyway: it costs nothing and matches how every Track-G number
  was produced. It does matter for any score taken through the app or API path.

## Before and after

Scores are deterministic for fixed code (`observed` in #353's PR body: re-ran twice, identical). Take both in the same checkout:

1. `git stash push -- <the render-affecting .py files only>` (baselines and tests do not affect the
   scorer; it renders live). Add `-u` if the fix created new modules, or they stay behind and the
   "before" run imports them.
2. Score all six; copy `.tmpscratch/fidelity/scores.json` and the composites aside as "before".
3. `git stash pop`; score all six again as "after".

Report a six-row table: `full_image`, `section_min`, `section_median` before → after, per case.

## The jitter rule

The scorer scales the render to the reference height and scores fixed bands placed at
design-fraction positions taken from the design. Any change that moves content vertically in the render
(a shorter pill, a shrunk icon, an added row) shifts every band below it onto different content, so
per-section scores swing both ways even in sections whose HTML never changed (`observed` in #365's PR body: case 10
sections moved −0.54 to +0.14; a case 7 section above every change still moved). `full_image` moves only a little
as the swings net out.

Therefore, on a **target** case, a per-section or `section_min` drop is a scorer artifact until the
evidence says otherwise. Evidence, in order of trust:

1. **Non-target flatness.** Cases the fix does not touch should be flat. A real regression there means
   something; it stops for the user.
2. **The composites.** Look at the actual element on the right-hand render against the left-hand
   reference.
3. **Geometry.** `data/debug/<n>/structure.json` says what size and position the element really has.

Per-band trades on a target (for example, `observed` in #359's PR body: `section_min` 0.778 → 0.708 while `full_image` and median
rose) are ratified by the user, named in the PR body, and never "tuned away" by reverting a design-correct
change (#352: do not resurrect ghosts to win back a band).
