# Backend Planning — Create Implementation Plan

Research the codebase and create a self-contained implementation plan.

## Process

1. **Understand the task** — Read the user's requirements carefully
2. **Check memory** — Read relevant memory files for domain patterns, past feedback, and conventions before writing any code or plans. Key memories to check:
   - Feedback memories — past corrections the user has given (e.g., HTML structure, fixture preferences)
   - Project memories — ongoing work context, deadlines, decisions

3. **Research existing code** — Read files you will modify AND discover related data assets.

   **jCodeMunch** (repo from `list_repos`):
   - `search_symbols(query, kind, file_pattern)` — find related functions/classes
   - `get_file_outline(file_path)` — understand file structure without reading
   - `get_symbol(symbol_name)` — read specific function/class code
   - `find_references(symbol_name)` — trace usage across codebase
   - `get_file_tree(path_prefix)` — discover feature layout

   **jDocMunch** (repo: `local/email-hub`):
   - `search_sections(query, doc_path)` → `get_section(section_id)` for CLAUDE.md architecture context and TODO.md task context
   - `get_document_outline(doc_path)` for smaller docs (<50 sections) when you need full structure

4. **Discover existing data assets** — Before writing test fixtures, seed data, or example code, ALWAYS check what already exists:
   - `app/ai/templates/library/*.html` — 15 golden email templates (real production HTML)
   - `app/ai/templates/library/_metadata/*.yaml` — template metadata with slots, tokens
   - `app/components/data/seeds.py` — 21 seeded components (`COMPONENT_SEEDS`) with production HTML
   - `app/*/tests/conftest.py` — existing test fixtures and factory functions
   - `alembic/versions/*seed*` — seed migrations with real data
   - **Read actual HTML** from these sources to verify structure — never assume, always verify counts and patterns
   - **Never fabricate synthetic email HTML** when real data exists — load from template library or component seeds

5. **Identify files to create/modify** — List every file that needs changes
6. **Write the plan** — Step-by-step instructions that another agent can follow. All code examples must follow the patterns found in Step 4 (e.g., table-based email HTML, not div-based)

## Plan Format

Save the plan to `.agents/plans/{feature-name}.md` with this structure:

```markdown
# Plan: {Feature Name}

## Context
{Why this change is needed}

## Files to Create/Modify
- `app/{feature}/models.py` — {what changes}
- ...

## Implementation Steps
1. {Step with exact code or clear instructions}
2. ...

## Security Checklist
For every new/modified endpoint in this plan, address each item from the backend security checklist below.

## Verification
- [ ] `make check` passes (26-rule ruff lint, mypy+pyright strict, tests, frontend lint+format+types, security-check)
- [ ] New endpoints have auth + rate limiting
- [ ] Error responses don't leak internal types
```

@_shared/backend-conventions.md
@_shared/backend-security-scoped.md
@_shared/python-anti-patterns.md
