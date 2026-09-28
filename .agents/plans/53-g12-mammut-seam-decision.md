# Decision Doc — G12 Mammut Semantic-Split Spike (ship or park)

> Scope: the **ship-or-park GATE** for the mammut (case 10) 12-vs-18 below-candidate
> under-count, prescribed by `.agents/plans/53-g12-generalization-insurance.md` §Phase S.
> Inputs: the A2 structural ladder (`python -m app.design_sync.tests.ladder_harness`, flag
> off + on, re-run this session), the A3 advisory pixel metric (`scripts/score-fidelity-cases.py`,
> flag off + on), and the structural read of `data/debug/10/structure.json`. Branch
> `feature/g12-generalization-insurance` off `origin/main 60c98bc6`. Every number below was
> **measured this session**, not quoted.
>
> **Status: DECIDED + RATIFIED — PARK + DELETE (user, 2026-07-22).** The mechanism the prompt
> names (Arm 1, deterministic role-seam) was implemented, gated (`DESIGN_SYNC__SEMANTIC_SPLIT_ENABLED`,
> default OFF), and measured — it fails the non-regression floor. On the PARK the user chose
> **DELETE** (Simplicity-First): the flag + `_split_sections_by_role_seams` and their unit tests
> were removed from the tree; **this doc + the branch's git history are the durable record.**
> Arm 2 (offline VLM) was **not pursued** — reasoning below.

## The question

Can a deterministic, flag-gated post-pass close mammut's 12→18 under-count by splitting fat
candidates at role-transition seams — **without** regressing the 7/8/9 = 8/10/8 exact floor
or the 5/6 = 13/9 counts — on live numbers from the committed fixtures?

## Measured evidence

### A2 structural ladder (deterministic, authoritative)

| case | name | target | rendered OFF | rendered **ON (Arm 1)** | verdict |
|---|---|---:|---:|---:|---|
| 7 | lego-insiders-halloween | 8 | 8 | **8** | ✅ held |
| 8 | performance-reimagined | 10 | 10 | **14** | ❌ over +4 (the §C2b regression) |
| 9 | slate-newsletter | 8 | 8 | **10** | ❌ over +2 |
| 5 | maap-kask | 13 | 13 | **18** | ❌ over +5 |
| 6 | starbucks-pumpkin-spice | 9 | 9 | **10** | ❌ over +1 |
| 10 | mammut-duvet-day | 18 | 12 | **16** | moved +4, but by over-segmenting |

**Ship gate = mammut 12→toward 18 AND 7/8/9 hold 8/10/8 AND 5/6 hold 13/9.** Result: the
floor breaks on **4 of 5** cases. Flag-OFF is byte-identical to `main` (corpus suite: 107
passed / 2 xfailed; the splitter returns its input unchanged when off).

### A3 advisory pixel fidelity (CIEDE2000 similarity 0–1, local Playwright + reference PNGs)

| case | full-image OFF | full-image **ON** | Δ | section-median OFF→ON |
|---|---:|---:|---:|---|
| 8 | 0.822 | 0.845 | +0.023 | 0.840 → 0.881 |
| 10 | 0.720 | 0.716 | **−0.004** | 0.827 → **0.793** |

**Load-bearing reading:** flag-ON raises mammut's *count* 12→16 but its *pixel fidelity does
not improve* (full-image flat, median −0.034). The count rose without the render getting
closer to the design — the extra "sections" are over-segmentation artifacts, not recovered
content. Case 8's +0.023 full-image rise is the known A3 section-instability (per-section
scores jitter on any vertical redistribution — `reference_a3_scorer_section_instability`),
**not** a real gain: its count regressed 10→14 against target 10. A3 does not discriminate
here; the A2 count is the authoritative signal, and it says over-segmentation.

## The three findings that decide it

1. **The plan's premise is wrong — the missing sections are not un-surfaced content inside
   fat candidates.** `analyze_layout` already emits **17** sections for mammut; band-grouping
   (`band_grouping_enabled`, default-ON since the 53.1 fork ratification) re-collapses them to
   12 — `wrappers[1175=2, 1240=5] solo=10`. The 12→17 delta is already surfaced then
   deliberately regrouped; regrouping is **explicitly out of scope** (plan §Non-Goals). The
   deferred item `phase-53-d3-mammut-below-candidate-undercount` frames the gap as
   below-candidate content; the structure refutes that framing.

2. **The residual 12→18 gap lives where a solo-candidate role-seam split at `:382` cannot
   reach it in scope.** It is (a) the band-grouped product grid (`2833:1175`, two
   3-column rows) and nav list (`2833:1240`, five rows → one band) — both banded, both left
   untouched by design; and (b) the product grid is the **exact §C2b horizontal
   cards-vs-stats trap** (no deterministic structural split, proven in
   `docs/phase-53-track-c-spike.md` §C2b). The plan's own §NOTES bet on mammut's *vertical*
   editorial stacks being separable; they are not — see finding 3.

3. **Spec/code mismatch: there is no "heading" role to seam on.** `_MJ_CONTENT_ROLES` maps
   every text to `"text"` — the plan's "slices bounded by heading-role children per
   `_get_mj_role`" is not implementable as written. Arm 1 synthesizes a heading (uppercase
   leading text or a font-size step). But each mammut solo editorial (`2833:1159`,
   `2833:1227`) is *heading + body + a trailing uppercase CTA-link* ("BUILD YOUR LAYERS →",
   "DISCOVER OUR GIFT GUIDE →"), and the hero (`2833:1141`) is heading + body + two uppercase
   buttons. A conservative "≥2 heading seams" rule therefore either **no-ops** (single true
   heading) or **over-segments at the CTA-link/eyebrow** — the vertical form of the §C2b
   semantic ambiguity. No threshold closes 12→18 without breaking the floor; the measured
   flag-ON floor break is that ambiguity firing across the corpus.

## Decision

**PARK (ratified).** The mammut 12-vs-18 residual is an **honest cap**, not a bug the
deterministic role-seam mechanism can close. Recorded in `docs/converter-fidelity-ceiling.md` §4.

**Arm 2 (offline VLM seam-proposal into a committed fixture): not pursued.** Rationale (a
measured negative, sanctioned by plan §S5): the gap is out-of-scope band-grouping + the §C2b
horizontal trap, neither of which a per-fat-candidate seam annotation reaches; a VLM
hand-annotating mammut's seams would move one case by manual labelling, not a generalizable
capability, and the flag would remain default-off regardless. Arm 1 already showed the count
can be raised without improving fidelity — Arm 2 would not change the ship-or-park verdict.

**Flag fate — DELETE (user-ratified 2026-07-22).** Since the mechanism is measured-*harmful*
when enabled (breaks 4/5 cases), it is not switch-on insurance; per Simplicity-First the config
flag, the `feature-flags.yaml` entry, the `.env.example` line, `_split_sections_by_role_seams`
+ helpers, and their unit tests were removed. The measured evidence (this doc), the ceiling §4
cap, the ledger note, and the branch git history preserve the attempt in full. (KEEP was the
alternative — flag default-off, satisfying AC #6/#7 literally; not chosen.)

### Effort ledger

| Arm | Effort | Closes 12→18 | Holds 7/8/9=8/10/8 floor |
|---|---|---|---|
| 1 · deterministic role-seam | implemented + measured (this session) | No — 12→16 via over-seg | **No — measured** (8→14, 9→10, 5→18, 6→10) |
| 2 · offline VLM fixture | not pursued (measured-negative rationale above) | n/a (per-case labelling, not a rule) | n/a |

## Deferred items touched (per `.claude/rules/deferred-items.md`)

- `phase-53-d3-mammut-below-candidate-undercount` (deferred, soft) — **stays deferred**; its
  `closes_when` allows "documented as a known cap (with the per-client table pointing here)."
  This doc + ceiling §4 record the cap and add the new evidence: the gap is band-grouping +
  §C2b horizontal, and the deterministic role-seam actuator was tried and breaks the floor.
  Note appended to the ledger entry.
- `phase-53-a2-target-strict-*` — unchanged; mammut's target gate stays xfail
  (`SEMANTIC_UNDERCOUNT_CASES = {"10"}`) — no convergence, so it is not flipped strict.

## Sign-off

- [x] Mechanism (Arm 1) implemented, flag-gated default-off, unit-tested
- [x] Measured A2 both-ways + A3 advisory; flag-OFF byte-identical proven
- [x] Recommendation recorded with measured evidence + effort per arm (this doc)
- [x] **Stakeholder (user) ratification** — PARK + DELETE (2026-07-22)
