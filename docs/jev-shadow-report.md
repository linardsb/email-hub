# Jev shadow classifier report (O1, O2, O3)

**Status:** T12 of `.agents/plans/jev-shadow-classifier.md` (AC7). **Date:** 2026-09-29.
**Branch head:** `ddfe6762` (feat/jev-shadow-classifier; tables from a run at `4b3c27e7`, no code change since; §5 O2 rule line re-run after PR #413 F6). **Model:** `jev-1.13.0` on all 293 records (observed).
**Scope:** the 7 audit designs (cases 5, 6, 7, 8, 9, 10, reframe). The verdicts hold for these 7 designs only;
a follow-up override ticket must re-measure on new designs.

## 1. Verdict

Read off the `Rule result` line of `--summary`. The rule was fixed in the plan (T12) before any label was read.

| Point | Cause | n | Verdict | Condition that failed |
|---|---|---|---|---|
| o1_type | R1 | 92 | don't wire it in | breaks = 0 is never met with fixes ≥ 1: 2 breaks at t = 0.8 and 0.9 (Wilson 0.836 and 0.801 would pass); leave-one-design-out finds no threshold |
| o1_template | R3 | 92 | don't wire it in | Wilson lower bound below 0.80 at every t (best 0.709 at t = 0.8); leave-one-design-out breaks on reframe |
| o2_button_icon | R2 | 5 | insufficient evidence | n = 5 < 16, so it cannot pass by construction (plan T12); Jev 5/5, heuristic 0/5 |
| o3_slot | R3 | 20 | don't wire it in | Jev 9/20 against heuristic 18/20; breaks at every t |

All figures observed from `uv run python scripts/jev_shadow_report.py --summary` on 2026-09-29 (full output in §5).

## 2. Reading per cause

- **R1 (social vs footer, O1 type).** Jev is right on all 5 sections the heuristic calls `social` but which
  carry legal text (10:1270, 6:1475, 8:2348, 9:2149, reframe:1607), at confidence 0.99–1.00 (observed). The two
  breaks that block the rule are both Jev calling a content section `hero` at high confidence (10:1168 at 0.97,
  9:2132 at 1.00) (observed). Jev over-assigns `hero` to image-led content bands (11 of its 37 disagreements
  answer `hero` against a `content` label; counted from the table in §5, derived).
- **R2 (icon inside a button, O2).** Jev 5/5, heuristic 0/5 (observed). The signal is as the audit predicted,
  but 5 items give a Wilson lower bound of 0.566 (observed); the rule needs n ≥ 16.
- **R3 (template and slot choice, O1 template and O3).** Jev beats the heuristic on template (54/92 against
  35/92, observed) but is not accurate enough to gate on: at t = 0.7 there are 8 fixes and 0 breaks, yet only
  37 of 44 answers at that confidence are right (Wilson 0.706) (observed). On slots Jev answers
  `none_of_the_above` on 11 of 20 labelled slots and is wrong on 10 of them (observed; counted from §5).

## 3. Labels

- File: `data/debug/jev_shadow_labels.yaml`, sha256 `a0f40fcb7126ba6758a581de6d465136431f25436752461b7596c8778c62216c`,
  hashed before `--summary` was first run (observed). Rules: `data/debug/jev_shadow_labeling_rules.md`
  (content-based and design-agnostic; the hand build is evidence, not the template-name authority).
- Labelled blind: the labeller never saw the `heuristic`, `jev` or `jev_confidence` fields.
- Coverage (observed): every O1 and O2 row (92 + 92 + 5). O3: 20 of 59 rows, which are all 11 disagreements
  plus every slot of cases 6 (5) and 9 (7). The 39 unlabelled O3 rows are all agreements, checked after the
  labels were frozen.
- Sources (observed): `hand_build` 81 / 81 / 5 / 20 (o1_type / o1_template / o2 / o3); `visual` 9 and 11 (o1
  type and template); `audit` 2 (o1_type).
- Inter-labeller agreement with the final labels, over 4 independent blind labellers (observed):
  o1_type 89–92/92, o1_template 68–86/92, o3_slot 18–20/20, o2 5/5. With the final labels counted as a 5th
  vote, no row has another label with more votes. The template labels are the least settled: 23 template rows
  had 2 or more labellers differ (hero-block against text-block, email-footer against footer-social,
  navigation-bar against column-layout-N, article-card against article-2). Template accuracy figures carry that
  uncertainty; the rule was applied unchanged.

## 4. Cost and latency

- Requests: 92 (one fan-out per section), 0 errors, 45 skipped decisions (observed, `traces/jev_shadow.jsonl`).
- Input tokens: 251,644 in total, 2,735 mean per request (observed, summed from `input_tokens`).
- Cost: 251,644 × $0.042 / 1M ≈ $0.011 (derived; assumes the plan's $0.042/M input price).
- Latency: **not recorded.** The trace records carry no timing field, so no latency figure is claimed.

## 5. `--summary` output (observed, 2026-09-29)

## o1_type (n=92)

| n | agree | disagree | heuristic acc | Jev acc | mean conf right | mean conf wrong |
|---|---|---|---|---|---|---|
| 92 | 55 | 37 | 59/92 | 66/92 | 0.88 | 0.64 |

| case | section | subject | heuristic | Jev | conf | label |
|---|---|---|---|---|---|---|
| 10 | 2833:1154 | 2833:1154 | content | hero | 0.60 | content |
| 10 | 2833:1168 | 2833:1168 | content | hero | 0.97 | content |
| 10 | 2833:1222 | 2833:1222 | content | hero | 0.63 | content |
| 10 | 2833:1270 | 2833:1270 | social | footer | 1.00 | footer |
| 5 | 2833:1629 | 2833:1629 | content | hero | 0.47 | hero |
| 5 | 2833:1643 | 2833:1643 | hero | content | 0.94 | content |
| 5 | 2833:1650 | 2833:1650 | hero | content | 0.92 | content |
| 5 | 2833:1660 | 2833:1660 | content | nav | 0.84 | nav |
| 5 | 2833:1697 | 2833:1697 | content | nav | 0.59 | nav |
| 5 | 2833:1729 | 2833:1729 | hero | content | 0.85 | content |
| 5 | 2833:1732 | 2833:1732 | hero | content | 0.85 | content |
| 5 | 2833:1735 | 2833:1735 | hero | content | 0.85 | content |
| 6 | 2833:1430 | 2833:1430 | content | hero | 0.54 | hero |
| 6 | 2833:1442 | 2833:1442 | hero | content | 0.81 | content |
| 6 | 2833:1455 | 2833:1455 | cta | content | 0.45 | nav |
| 6 | 2833:1460 | 2833:1460 | cta | content | 0.65 | nav |
| 6 | 2833:1465 | 2833:1465 | cta | content | 0.58 | nav |
| 6 | 2833:1470 | 2833:1470 | social | content | 0.56 | nav |
| 6 | 2833:1475 | 2833:1475 | social | footer | 0.99 | footer |
| 7 | 2833:1870 | 2833:1870 | content | preheader | 0.76 | preheader |
| 7 | 2833:1892 | 2833:1892 | content | hero | 0.67 | content |
| 7 | 2833:2041 | 2833:2041 | content | social | 0.71 | content |
| 8 | 2833:2258 | 2833:2258 | hero | header | 0.41 | hero |
| 8 | 2833:2272 | 2833:2272 | content | hero | 0.62 | content |
| 8 | 2833:2300 | 2833:2300 | content | hero | 0.51 | content |
| 8 | 2833:2317 | 2833:2317 | content | hero | 0.59 | content |
| 8 | 2833:2334 | 2833:2334 | content | nav | 0.98 | nav |
| 8 | 2833:2348 | 2833:2348 | social | footer | 1.00 | footer |
| 9 | 2833:2132 | 2833:2132 | content | hero | 1.00 | content |
| 9 | 2833:2149 | 2833:2149 | social | footer | 1.00 | footer |
| reframe | 2833:1497 | 2833:1497 | content | hero | 0.88 | hero |
| reframe | 2833:1553 | 2833:1553 | content | cta | 0.98 | cta |
| reframe | 2833:1561 | 2833:1561 | content | hero | 0.49 | content |
| reframe | 2833:1577 | 2833:1577 | content | hero | 0.45 | content |
| reframe | 2833:1589 | 2833:1589 | content | cta | 0.99 | cta |
| reframe | 2833:1597 | 2833:1597 | content | hero | 0.49 | content |
| reframe | 2833:1607 | 2833:1607 | social | footer | 1.00 | footer |

| t | fixes | breaks | n at >= t | Jev correct at >= t | Wilson 95% lower |
|---|---|---|---|---|---|
| 0.5 | 19 | 9 | 84 | 64 | 0.661 |
| 0.6 | 17 | 7 | 75 | 60 | 0.696 |
| 0.7 | 17 | 3 | 67 | 59 | 0.782 |
| 0.8 | 16 | 2 | 58 | 54 | 0.836 |
| 0.9 | 10 | 2 | 40 | 37 | 0.801 |

Leave-one-design-out (threshold picked on the other designs):

| held out | t | fixes | breaks |
|---|---|---|---|
| 10 | none | - | - |
| 5 | none | - | - |
| 6 | none | - | - |
| 7 | none | - | - |
| 8 | none | - | - |
| 9 | none | - | - |
| reframe | none | - | - |

Rule result: don't wire it in (no threshold meets breaks=0, fixes>=1, n>=16, Wilson>=0.80).

## o1_template (n=92)

| n | agree | disagree | heuristic acc | Jev acc | mean conf right | mean conf wrong |
|---|---|---|---|---|---|---|
| 92 | 49 | 43 | 35/92 | 54/92 | 0.78 | 0.53 |

| case | section | subject | heuristic | Jev | conf | label |
|---|---|---|---|---|---|---|
| 10 | 2833:1141 | 2833:1141 | text-block | hero-2cta | 0.53 | hero-2cta |
| 10 | 2833:1168 | 2833:1168 | article-card | image-block | 0.55 | image-block |
| 10 | 2833:1176 | 2833:1176 | column-layout-2 | product-grid | 0.77 | product-grid |
| 10 | 2833:1197 | 2833:1197 | column-layout-2 | product-grid | 0.80 | product-grid |
| 10 | 2833:1270 | 2833:1270 | social-icons | footer | 0.45 | email-footer |
| 5 | 2833:1643 | 2833:1643 | hero-block | image-block | 0.75 | image-block |
| 5 | 2833:1650 | 2833:1650 | hero-block | image-block | 0.87 | image-block |
| 5 | 2833:1660 | 2833:1660 | navigation-bar | none_of_the_above | 0.25 | navigation-bar |
| 5 | 2833:1693 | 2833:1693 | text-block | paragraph | 0.65 | heading |
| 5 | 2833:1729 | 2833:1729 | full-width-image | image | 0.49 | image |
| 5 | 2833:1732 | 2833:1732 | full-width-image | image | 0.54 | image |
| 5 | 2833:1735 | 2833:1735 | full-width-image | image | 0.57 | image |
| 6 | 2833:1442 | 2833:1442 | full-width-image | image | 0.52 | image |
| 6 | 2833:1445 | 2833:1445 | event-card | text-block | 0.67 | hero-block |
| 6 | 2833:1455 | 2833:1455 | cta-button | icon | 0.65 | icon |
| 6 | 2833:1460 | 2833:1460 | cta-button | icon | 0.56 | icon |
| 6 | 2833:1465 | 2833:1465 | cta-button | icon | 0.59 | icon |
| 6 | 2833:1470 | 2833:1470 | social-icons | icon | 0.66 | icon |
| 6 | 2833:1475 | 2833:1475 | social-icons | email-footer | 0.68 | email-footer |
| 7 | 2833:1870 | 2833:1870 | text-block | navigation-bar | 0.27 | preheader |
| 7 | 2833:1875 | 2833:1875 | full-width-image | image-grid | 0.53 | full-width-image |
| 7 | 2833:1904 | 2833:1904 | column-layout-2 | article-2 | 0.37 | article-card |
| 7 | 2833:1924 | 2833:1924 | column-layout-2 | article-2 | 0.27 | article-card |
| 7 | 2833:1942 | 2833:1942 | text-block | heading | 0.88 | heading |
| 7 | 2833:1946 | 2833:1946 | column-layout-2 | article-reverse | 0.35 | article-reverse |
| 7 | 2833:1969 | 2833:1969 | column-layout-2 | product-card | 0.45 | article-card |
| 7 | 2833:1992 | 2833:1992 | column-layout-2 | article-reverse | 0.26 | article-reverse |
| 7 | 2833:2015 | 2833:2015 | column-layout-2 | article-card | 0.31 | article-card |
| 7 | 2833:2057 | 2833:2057 | td | image-gallery | 0.36 | td |
| 7 | 2833:2067 | 2833:2067 | email-footer | footer | 0.80 | footer |
| 8 | 2833:2258 | 2833:2258 | full-width-image | image-grid | 0.49 | full-width-image |
| 8 | 2833:2348 | 2833:2348 | social-icons | email-footer | 0.79 | email-footer |
| 9 | 2833:2085 | 2833:2085 | text-block | heading | 0.89 | heading |
| 9 | 2833:2089 | 2833:2089 | column-layout-2 | icon | 0.47 | col-icon |
| 9 | 2833:2109 | 2833:2109 | col-icon | icon | 0.59 | icon |
| 9 | 2833:2117 | 2833:2117 | col-icon | article-reverse | 0.23 | hero-block |
| 9 | 2833:2132 | 2833:2132 | image-grid | hero-block | 0.28 | editorial-5 |
| 9 | 2833:2149 | 2833:2149 | social-icons | footer | 0.50 | email-footer |
| reframe | 2833:1497 | 2833:1497 | col-icon | article-reverse | 0.22 | hero-block |
| reframe | 2833:1553 | 2833:1553 | image-block | cta-button | 0.25 | cta-button |
| reframe | 2833:1566 | 2833:1566 | event-card | text-block | 0.61 | event-card |
| reframe | 2833:1589 | 2833:1589 | image-block | button | 0.25 | cta-button |
| reframe | 2833:1603 | 2833:1603 | text-block | paragraph | 0.99 | footer |

| t | fixes | breaks | n at >= t | Jev correct at >= t | Wilson 95% lower |
|---|---|---|---|---|---|
| 0.5 | 19 | 2 | 70 | 49 | 0.585 |
| 0.6 | 11 | 1 | 54 | 40 | 0.611 |
| 0.7 | 8 | 0 | 44 | 37 | 0.706 |
| 0.8 | 5 | 0 | 40 | 34 | 0.709 |
| 0.9 | 0 | 0 | 20 | 17 | 0.640 |

Leave-one-design-out (threshold picked on the other designs):

| held out | t | fixes | breaks |
|---|---|---|---|
| 10 | 0.7 | 2 | 0 |
| 5 | 0.7 | 2 | 0 |
| 6 | 0.7 | 0 | 0 |
| 7 | 0.7 | 2 | 0 |
| 8 | 0.7 | 1 | 0 |
| 9 | 0.7 | 1 | 0 |
| reframe | 0.6 | 0 | 1 |

Rule result: don't wire it in (no threshold meets breaks=0, fixes>=1, n>=16, Wilson>=0.80).

## o2_button_icon (n=5)

| n | agree | disagree | heuristic acc | Jev acc | mean conf right | mean conf wrong |
|---|---|---|---|---|---|---|
| 5 | 0 | 5 | 0/5 | 5/5 | 0.79 | nan |

| case | section | subject | heuristic | Jev | conf | label |
|---|---|---|---|---|---|---|
| 9 | 2833:2117 | 2833:2126 | content_image | button_icon | 0.85 | button_icon |
| 9 | 2833:2132 | 2833:2143 | content_image | button_icon | 0.80 | button_icon |
| reframe | 2833:1497 | 2833:1506 | content_image | button_icon | 0.76 | button_icon |
| reframe | 2833:1553 | 2833:1560 | content_image | button_icon | 0.78 | button_icon |
| reframe | 2833:1589 | 2833:1596 | content_image | button_icon | 0.77 | button_icon |

| t | fixes | breaks | n at >= t | Jev correct at >= t | Wilson 95% lower |
|---|---|---|---|---|---|
| 0.5 | 5 | 0 | 5 | 5 | 0.566 |
| 0.6 | 5 | 0 | 5 | 5 | 0.566 |
| 0.7 | 5 | 0 | 5 | 5 | 0.566 |
| 0.8 | 2 | 0 | 2 | 2 | 0.342 |
| 0.9 | 0 | 0 | 0 | 0 | 0.000 |

Leave-one-design-out (threshold picked on the other designs):

| held out | t | fixes | breaks |
|---|---|---|---|
| 9 | 0.5 | 2 | 0 |
| reframe | 0.5 | 3 | 0 |

Rule result: insufficient evidence (n < 16).

## o3_slot (n=20)

| n | agree | disagree | heuristic acc | Jev acc | mean conf right | mean conf wrong |
|---|---|---|---|---|---|---|
| 20 | 9 | 11 | 18/20 | 9/20 | 0.86 | 0.77 |

| case | section | subject | heuristic | Jev | conf | label |
|---|---|---|---|---|---|---|
| 5 | 2833:1697 | col_1 | 2833:1700 | none_of_the_above | 0.82 | 2833:1700 |
| 5 | 2833:1697 | col_2 | 2833:1704 | none_of_the_above | 0.65 | 2833:1704 |
| 5 | 2833:1697 | col_3 | 2833:1708 | none_of_the_above | 0.74 | 2833:1708 |
| 5 | 2833:1710 | col_1 | 2833:1713 | none_of_the_above | 0.88 | 2833:1713 |
| 5 | 2833:1710 | col_3 | 2833:1721 | none_of_the_above | 0.49 | 2833:1721 |
| 5 | 2833:1710 | col_4 | 2833:1725 | none_of_the_above | 0.68 | 2833:1725 |
| 6 | 2833:1445 | cta_text | 2833:1451 | none_of_the_above | 0.87 | 2833:1451 |
| 9 | 2833:2117 | heading_1 | 2833:2121 | none_of_the_above | 0.76 | 2833:2121 |
| 9 | 2833:2132 | image_2 | 2833:2143 | none_of_the_above | 0.66 | none_of_the_above |
| reframe | 2833:1497 | heading_1 | 2833:1501 | none_of_the_above | 0.77 | 2833:1501 |
| reframe | 2833:1566 | description | 2833:1574 | none_of_the_above | 0.98 | 2833:1574 |

| t | fixes | breaks | n at >= t | Jev correct at >= t | Wilson 95% lower |
|---|---|---|---|---|---|
| 0.5 | 1 | 9 | 19 | 9 | 0.273 |
| 0.6 | 1 | 9 | 19 | 9 | 0.273 |
| 0.7 | 0 | 7 | 15 | 7 | 0.248 |
| 0.8 | 0 | 4 | 11 | 6 | 0.280 |
| 0.9 | 0 | 1 | 7 | 6 | 0.487 |

Leave-one-design-out (threshold picked on the other designs):

| held out | t | fixes | breaks |
|---|---|---|---|
| 5 | none | - | - |
| 6 | none | - | - |
| 9 | none | - | - |
| reframe | none | - | - |

Rule result: don't wire it in (no threshold meets breaks=0, fixes>=1, n>=16, Wilson>=0.80).
