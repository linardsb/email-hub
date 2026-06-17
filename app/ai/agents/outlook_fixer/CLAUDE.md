# Outlook Fixer Agent

First agent built using the eval-first + skills workflow (Task 4.1 Priority 1).

## Architecture
- Progressive disclosure via SKILL.md (L1-L2) + skills/*.md (L3)
- Service detects VML/MSO/dark-mode patterns in input HTML to load relevant L3 files
- Blueprint node receives HTML from recovery router when QA detects Outlook failures
- Emits AgentHandoff with confidence score and fix decisions

## Skill Files
- `SKILL.md` — L1 metadata + L2 core instructions (always loaded)
- `skills/mso_bug_fixes.md` — 15 Outlook bug patterns with fixes
- `skills/vml_reference.md` — VML shapes, fills, textbox patterns
- `skills/mso_conditionals.md` — Version targeting, ghost tables, DPI
- `skills/diagnostic.md` — Symptom-to-fix lookup table
