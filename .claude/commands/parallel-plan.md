# Parallel Plan — Concurrent Research + Planning

Replaces the sequential `/be-prime` → `/be-planning` flow with parallel agent execution.
Three agents run simultaneously, then results merge into a single implementation plan.

## Input

The user provides:
- **Feature description** — what to build
- **Plan filename** — where to save (default: `.agents/plans/{feature-slug}.md`)

## Execution

Launch **three agents in parallel** using the Agent tool:

### Agent 1: Researcher (subagent_type: Explore)
```
Research the codebase for implementing: {feature description}

Using jCodeMunch (repo from list_repos):
1. get_file_tree({ "path_prefix": "app/" }) — map backend features
2. search_symbols for functions/classes related to: {feature keywords}
3. get_file_outline on the most relevant files found
4. find_references for key symbols that will need modification
5. get_file_outline on app/core/config.py, app/core/exceptions.py, app/shared/schemas.py

Using jDocMunch (repo: local/email-hub):
1. search_sections({ "query": "{feature keywords}", "doc_path": "CLAUDE.md" }) — architecture context
2. search_sections({ "query": "{feature keywords}", "doc_path": "TODO.md" }) — task context

Write a structured research summary including:
- Relevant files and their roles
- Key functions/classes to modify or extend
- Existing patterns to follow
- Config/settings that apply
- Dependencies and imports needed
```

### Agent 2: Test Scout (subagent_type: Explore)
```
Find all test files and patterns related to: {feature description}

1. Glob for test files in related feature directories: app/{feature}/tests/test_*.py
2. Read test conftest.py files for existing fixtures and factory functions
3. Search for test patterns using Grep:
   - Existing mock patterns for the feature area
   - Factory functions (make_*, create_*)
   - Integration test markers
4. Check app/ai/templates/library/ for golden templates relevant to this feature
5. Check app/components/data/seeds.py for relevant component seeds

Write a structured summary including:
- Related test files found
- Existing fixtures and factories available
- Mock patterns used in this area
- Golden templates / seed data that can be reused
- Test conventions specific to this feature area
```

### Agent 3: Pyright Baseline (subagent_type: general-purpose)
```
Run pyright baseline on files likely affected by: {feature description}

1. Identify the target directory: app/{feature}/
2. Run: uv run pyright app/{feature}/ 2>&1 | tail -20
3. Count current errors
4. Also run: uv run mypy app/{feature}/ 2>&1 | tail -20
5. Report the baseline error counts
```

## After All Agents Complete

Combine all three agent results and write the implementation plan following the `/be-planning` format:

```markdown
# Plan: {Feature Name}

## Context
{Why this change is needed — from user's feature description}

## Research Summary
{From Agent 1 — relevant files, patterns, dependencies}

## Test Landscape
{From Agent 2 — existing tests, fixtures, golden data}

## Type Check Baseline
{From Agent 3 — current pyright/mypy error counts for target files}

## Files to Create/Modify
- `app/{feature}/...` — {what changes}

## Implementation Steps
1. {Step with exact code or clear instructions}
2. ...

## Preflight Warnings
{Any hardcoded assertions, tuple unpacking, or fragile patterns found by Agent 2 in existing tests}

## Security Checklist
For every new/modified endpoint, address each item from the backend security checklist.

## Verification
- [ ] `make check` passes
- [ ] New endpoints have auth + rate limiting
- [ ] Error responses don't leak internal types
- [ ] Pyright errors ≤ baseline ({N} errors before)
```

Save to `.agents/plans/{feature-slug}.md`.

## Rules

- All three agents MUST run in parallel — do not wait for one before starting another
- The plan file must not exceed 700 lines (use compact descriptions, tables, `file:line` refs)
- Never fabricate synthetic email HTML — reference real golden templates and component seeds found by Agent 2
- Include the pyright baseline in the plan so `/be-execute` can compare against it
- Follow all conventions from @_shared/backend-conventions.md

@_shared/backend-conventions.md
@_shared/backend-security-scoped.md
@_shared/python-anti-patterns.md
