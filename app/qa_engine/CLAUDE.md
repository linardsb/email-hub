# QA Engine (`app/qa_engine/`)

14-point quality gate system. Each check in `checks/` implements `async run(html: str, config: QACheckConfig | None = None) -> QACheckResult`. Per-project config via `defaults.yaml` + `qa_profile` JSON column.

## Checks
1. `html_validation` — lxml DOM-parsed: 20 checks across 5 groups (skeleton, tag integrity, content, email structure, progressive enhancement); 17 configurable deductions
2. `css_support` — Ontology-powered client support scan (365 CSS properties, 25 clients) + cssutils syntax validation (vendor prefixes, external stylesheets, @import, !important overuse); 8 YAML rules via rule engine
3. `css_audit` — Per-build CSS compatibility matrix: runs `optimize_css()` + ontology scan, builds per-client property status (supported/converted/removed/partial), severity classification (error for no-fallback removals in tier-1 clients), JSON details with coverage scores; frontend `CSSAuditPanel` with coverage bars, filterable matrix table, conversion details
4. `file_size` — Gmail 102KB clipping threshold
5. `link_validation` — HTTPS enforcement
6. `spam_score` — 59 weighted triggers (7 categories), word-boundary matching, formatting heuristics (punctuation, all-caps, obfuscation), subject line 3x weight; 6 YAML rules via rule engine, `data/spam_triggers.yaml`
7. `dark_mode` — color-scheme meta, prefers-color-scheme, Outlook overrides
8. `accessibility` — WCAG AA: 24 DOM-parsed checks across 8 groups (language, tables, images, headings, links, content semantics, dark mode, AMP forms) via YAML rule engine; 21 custom check functions
9. `fallback` — MSO conditionals, VML namespaces
10. `image_optimization` — DOM-parsed: 10 rules across 6 groups (core attributes, format validation, dimension integrity, tracking pixels, rendering practices, summary) via YAML rule engine; 10 custom check functions; `image_analyzer.py` for cached DOM analysis
11. `brand_compliance` — Per-project brand rules (colors, typography, required elements, forbidden patterns) via YAML rule engine; 7 rules across 5 groups; `brand_analyzer.py` for CSS extraction
12. `personalisation_syntax` — ESP-specific syntax validation: platform detection (7 ESPs), delimiter balance, conditional block matching, fallback completeness, nesting depth; 12 YAML rules via rule engine; 12 custom check functions; `personalisation_validator.py` for cached analysis
13. `deliverability` — ISP-aware deliverability scoring (disabled by default)
14. `liquid_syntax` — Liquid template syntax validation

## Eval Calibration (Phase 5, Step 5.6)
QA gate thresholds must align with eval judge findings. After running agent evals (Step 5.4) and error analysis:
- Compare QA gate pass/fail decisions against judge verdicts
- Identify where QA checks are too lenient or too strict
- Tune thresholds and scoring weights based on real agent output patterns
- Ensure the QA gate catches the same failures that judges catch
- This prevents the blueprint self-correction loop from being miscalibrated
