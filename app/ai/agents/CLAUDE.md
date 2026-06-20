# AI Agents

9 specialized agents under `app/ai/agents/`. Each agent has its own subdirectory with `prompt.py`, `schemas.py`, `service.py`.

## Implemented Agents (Sprint 2)
- **Scaffolder** (`scaffolder/`) — Brief to Maizzle HTML. Table-based layouts, MSO conditionals, VML, dark mode meta tags, accessibility.
- **Dark Mode** (`dark_mode/`) — Injects dark mode CSS, Outlook `[data-ogsc]`/`[data-ogsb]` selectors, `prefers-color-scheme` media queries, color remapping, image swap patterns.
- **Content** (`content/`) — 8 operations: subject_line, preheader, cta, body_copy, rewrite, shorten, tone_adjust, expand. Anti-spam rules, brand voice enforcement, PII detection.

## Implemented Agents (V2 — task 4.1, eval-first + skills workflow)
- **Outlook Fixer** (`outlook_fixer/`) — MSO conditionals, VML backgrounds/buttons, ghost tables, DPI scaling, font fallbacks. Progressive disclosure: SKILL.md (L1+L2) + 4 L3 skill files loaded on-demand. Blueprint node integrated with recovery router.
- **Accessibility Auditor** (`accessibility/`) — WCAG 2.1 AA compliance for email HTML: alt text, table roles, lang attributes, heading hierarchy, color contrast, screen reader compatibility. Progressive disclosure: SKILL.md (L1+L2) + 4 L3 skill files (wcag_email_mapping, alt_text_guidelines, color_contrast, screen_reader_behavior). Blueprint node integrated with recovery router.

- **Personalisation** (`personalisation/`) — Injects ESP-specific dynamic content syntax: Braze Liquid, SFMC AMPscript, Adobe Campaign JavaScript, Klaviyo Django, Mailchimp Merge Language, HubSpot HubL, Iterable Handlebars. Platform-based progressive disclosure: SKILL.md (L1+L2) + 8 L3 skill files (braze_liquid, sfmc_ampscript, adobe_campaign_js, klaviyo_django, mailchimp_merge, hubspot_hubl, iterable_handlebars, fallback_patterns). Blueprint node integrated with recovery router.

## Implemented Agents (V2 — task 4.1, eval-first + skills workflow, continued)
- **Code Reviewer** (`code_reviewer/`) — Static analysis of email HTML: redundant code, unsupported CSS per email client, invalid nesting, file size optimisation. Analysis-only agent (does NOT modify HTML — returns original with structured `CodeReviewIssue` annotations). Progressive disclosure: SKILL.md (L1+L2) + 4 L3 skill files (redundant_code, css_client_support, nesting_validation, file_size_optimization). Blueprint node passes HTML through unchanged; issues go into `AgentHandoff.warnings`. Recovery router routes `css_support` and `file_size` failures.

## Implemented Agents (V2 — task 4.1, eval-first + skills workflow, continued)
- **Knowledge** (`knowledge/`) — RAG-powered Q&A agent for email development questions. Searches Hub knowledge base (20 docs across css_support, best_practices, client_quirks), generates grounded answers with citations. **Not an HTML transformer** — receives question, returns answer with sources and confidence. Requires DB session for `KnowledgeService.search()`. Progressive disclosure: SKILL.md (L1+L2) + 4 L3 skill files (rag_strategies, email_client_engines, can_i_email_reference, citation_rules). Blueprint node is advisory (not in QA→recovery loop).

## Implemented Agents (V2 — task 4.1, eval-first + skills workflow, continued)
- **Innovation** (`innovation/`) — Prototypes experimental email techniques: CSS checkbox hacks (tabs, accordions, carousels), AMP for Email, CSS animations, progressive enhancement. **Generator agent** (produces new prototype code, not an HTML transformer). Provides feasibility assessment (risk level, client coverage %, recommendation), static fallback HTML, and known limitations. Progressive disclosure: SKILL.md (L1+L2) + 4 L3 skill files (css_checkbox_hacks, amp_email, css_animations, feasibility_framework). Blueprint node is advisory (not in QA→recovery loop).

## Evaluation Framework (`evals/`)

All 9 agents must pass evaluation before production. Based on [evals-skills methodology](https://github.com/hamelsmu/evals-skills).

### Files
- `dimensions.py` — Failure-prone axes per agent (e.g., layout_complexity, client_quirk for scaffolder; input_html_complexity, outlook_challenge for dark_mode; operation, industry, tone_target for content)
- `synthetic_data_scaffolder.py` — 12 test cases with real MSO/VML code, vague/contradictory briefs
- `synthetic_data_dark_mode.py` — 10 test cases with 5 real-world HTML templates (MSO ghost tables, VML, already-dark emails)
- `synthetic_data_content.py` — 14 test cases across all 8 operations, real spam trigger blocklists, PII edge cases
- `synthetic_data_outlook_fixer.py` — 12 test cases: ghost tables, VML backgrounds, bulletproof buttons, font fallbacks, DPI, broken MSO comments
- `synthetic_data_accessibility.py` — 10 test cases: missing alt text, table roles, lang/title, low contrast, heading hierarchy, link text, VML/ARIA, color-only info
- `synthetic_data_personalisation.py` — 12 test cases: 4 Braze (Liquid), 4 SFMC (AMPscript), 3 Adobe Campaign (JSSP), 1 mixed edge case
- `synthetic_data_code_reviewer.py` — 12 test cases: redundant code (3), CSS support (2), nesting (2), file size (2), mixed (1), clean/false-positive (2)
- `synthetic_data_knowledge.py` — 10 test cases: CSS property support, best practices, client quirks, comparisons, troubleshooting, edge cases
- `synthetic_data_innovation.py` — 10 test cases: CSS checkbox hacks (2), CSS animations (2), AMP for Email (2), progressive enhancement (2), accessibility innovation (1), edge case (1)
- `runner.py` — CLI: `python -m app.ai.agents.evals.runner --agent {scaffolder|dark_mode|content|outlook_fixer|accessibility|personalisation|code_reviewer|knowledge|innovation|all} --output traces/`
- `judges/` — Binary pass/fail LLM judges: `ScaffolderJudge` (5 criteria), `DarkModeJudge` (5 criteria), `ContentJudge` (5 criteria), `OutlookFixerJudge` (5 criteria), `AccessibilityJudge` (5 criteria), `PersonalisationJudge` (5 criteria), `CodeReviewerJudge` (5 criteria), `KnowledgeJudge` (5 criteria), `InnovationJudge` (5 criteria); `Judge` Protocol, `JUDGE_REGISTRY`
- `judge_runner.py` — CLI: `python -m app.ai.agents.evals.judge_runner --agent {agent} --traces X --output Y`

### Per-Agent Eval Requirements (mandatory for all 9)
1. Dimension-based synthetic test data (minimum 10 cases per agent)
2. Binary pass/fail judge prompts (one per quality dimension)
3. Eval runner traces (JSONL: input, output, timing, errors)
4. Error analysis (failure clustering, root cause identification)
5. Judge calibration (TPR/TNR against human labels)

### Current Status
| Agent | Synthetic Data | Judge Prompts | Traces | Error Analysis | Calibration |
|-------|---------------|---------------|--------|----------------|-------------|
| Scaffolder | 12 cases | 5 criteria | 12 traces | 46.7% pass | Pending (human labels needed) |
| Dark Mode | 10 cases | 5 criteria | 10 traces | 82% pass | Pending (human labels needed) |
| Content | 14 cases | 5 criteria | 14 traces | 85.7% pass | Pending (human labels needed) |
| Outlook Fixer | 12 cases | 5 criteria | Pending (live run needed) | — | — |
| Accessibility | 10 cases | 5 criteria | Pending (live run needed) | — | — |
| Personalisation | 12 cases | 5 criteria | Pending (live run needed) | — | — |
| Code Reviewer | 12 cases | 5 criteria | Pending (live run needed) | — | — |
| Knowledge | 10 cases | 5 criteria | Pending (live run needed) | — | — |
| Innovation | 10 cases | 5 criteria | Pending (live run needed) | — | — |
