# Innovation Agent

Prototypes experimental email techniques and assesses their feasibility. Handles CSS checkbox hacks (tabs, accordions, carousels), AMP for Email, CSS animations, and progressive enhancement patterns.

## Architecture
- **Generator agent** — Produces new prototype code from technique descriptions
- **No DB dependency** — Pure LLM generation (no RAG, no DB session)
- **Progressive disclosure** — SKILL.md (L1+L2) + 4 L3 skill files loaded on-demand
- **Uses complex model** — Creative work benefits from stronger reasoning

## Files
- `schemas.py` — `InnovationRequest`, `InnovationResponse`
- `prompt.py` — `detect_relevant_skills()`, `build_system_prompt()`
- `service.py` — `InnovationService.process()` (build prompt → LLM → parse sections)
- `SKILL.md` — Core instructions (categories, rules, output structure, confidence)
- `skills/` — 4 L3 files (css_checkbox_hacks, amp_email, css_animations, feasibility_framework)

## Eval
- 10 synthetic test cases in `evals/synthetic_data_innovation.py`
- 5-criteria judge in `evals/judges/innovation.py` (technique_correctness, fallback_quality, client_coverage_accuracy, feasibility_assessment, innovation_value)
