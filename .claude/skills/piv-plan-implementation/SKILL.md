---
name: piv-plan-implementation
description: Creates a comprehensive, context-rich implementation plan through deep codebase analysis and external research. Accepts a GitHub issue (#N or URL, fetched via the gh CLI) or a free-form feature request. Use when you have a ticket or feature and need a one-pass-ready plan before writing any code.
argument-hint: "[GitHub issue #N/URL, or a free-form feature description]"
---

# Plan a new task

## Feature: $ARGUMENTS

## Resolve the input first

`$ARGUMENTS` is either a **GitHub issue** (a number like `#30`, or an issue URL) or a
**free-form feature description**. Tell them apart and handle each:

- **An issue** (`#N` or an issue URL): **fetch it before you plan** via `gh issue view <N> --comments`.
  Read its summary, acceptance criteria, and per-ticket context. Then **follow its links up to the epic issue
  and the epic's linked architecture doc** (e.g. under `docs/`) and inherit those decisions (see "Inherit,
  don't re-decide" below). Never plan from the bare number;
  the issue body plus its epic and architecture are the real input.
- **A free-form description**: plan directly from it (greenfield or ad-hoc), asking clarifying questions as needed.

## Mission

Transform a feature request into a **comprehensive implementation plan** through systematic codebase analysis, external research, and strategic planning.

**Core Principle**: We do NOT write code in this phase. Our goal is to create a context-rich implementation plan that enables one-pass implementation success for ai agents.

**Key Philosophy**: Context is King. The plan must contain ALL information needed for implementation - patterns, mandatory reading, documentation, validation commands - so the execution agent succeeds on the first attempt.

**Inherit, don't re-decide**: This is a **per-ticket** plan. If the ticket belongs to an epic that already has architecture decisions — a **linked architecture doc** (e.g. one written by the `plan-architecture` skill, reached from the ticket's epic), an `## Architecture` / `## Engineering` section on the epic, or a local `architecture.md` / `engineering-plan.md` — **read it first** and treat its cross-cutting calls (stack & versions, data model, security boundaries, the seams new code plugs into) as **already decided**. Inherit them; don't reopen them. Plan only what's left at the ticket level: the specific files, the local patterns to mirror, the tests. If a ticket genuinely needs to break an epic-level decision, flag it in Open Questions rather than silently diverging.

## Planning Process

### Phase 1: Feature Understanding

**Deep Feature Analysis:**

- Extract the core problem being solved
- Identify user value and business impact
- Determine feature type: New Capability/Enhancement/Refactor/Bug Fix
- Assess complexity: Low/Medium/High
- Map affected systems and components

**Create User Story Format Or Refine If Story Was Provided By The User:**

```
As a <type of user>
I want to <action/goal>
So that <benefit/value>
```

### Phase 2: Codebase Intelligence Gathering

**Use specialized agents and parallel analysis:**

**1. Project Structure Analysis**

- Detect primary language(s), frameworks, and runtime versions
- Map directory structure and architectural patterns
- Identify service/component boundaries and integration points
- Locate configuration files (`pyproject.toml`, `Makefile`, `feature-flags.yaml`, `alembic/`, `cms/package.json`, etc.)
- Find environment setup and build processes

**2. Pattern Recognition** (Use specialized subagents when beneficial)

- Search for similar implementations in codebase
- Identify coding conventions:
  - Naming patterns (CamelCase, snake_case, kebab-case)
  - File organization and module structure
  - Error handling approaches
  - Logging patterns and standards
- Extract common patterns for the feature's domain
- Document anti-patterns to avoid
- Check CLAUDE.md for project-specific rules and conventions

**3. Dependency Analysis**

- Catalog external libraries relevant to feature
- Understand how libraries are integrated (check imports, configs)
- Find relevant documentation in `docs/`, `.claude/rules/`, `.claude/docs/`, `.claude/references/` if available
- Note library versions and compatibility requirements

**4. Testing Patterns**

- Identify test framework and structure: backend pytest (`asyncio_mode = "auto"`, markers `integration`,
  `benchmark`, `visual_regression`, `collab`, `snapshot` in `pyproject.toml:291-297`), tests in
  `app/{feature}/tests/` and `tests/`; frontend vitest in `cms/apps/web` (`vitest.config.ts`)
- Find similar test examples for reference
- Understand test organization (unit vs integration)
- Note coverage requirements and testing standards

**5. Integration Points**

- Identify existing files that need updates
- Determine new files that need creation and their locations
- Map router/API registration patterns
- Understand database/model patterns if applicable
- Identify authentication/authorization patterns if relevant
- **New settings / env vars**: config is nested Pydantic settings (`app/core/config/__init__.py:125`, `__`
  delimiter, e.g. `DESIGN_SYNC__X_ENABLED`). A new field needs `.env.example` regenerated (`make .env.example`) or `make check-env-drift`
  (`Makefile:28`) fails; a new feature flag must be registered in `feature-flags.yaml` or `make flag-audit`
  (`Makefile:209`) fails. Name both as tasks, not asides.

**6. Fact Verification**

- A fact this plan states about existing code is read out of the source, decorators included, and cited
  `file:line` — never from a comment, a sibling plan or memory. A plan that states a status code without
  opening the route decorator's `status_code=`, or a provider's behaviour without opening the provider, is
  planning from memory.
- A pattern this plan proposes is checked the same way against the config that lints it — backend
  `[tool.ruff.lint]` in `pyproject.toml:126` plus strict mypy/pyright (`make types`, `Makefile:133`);
  frontend `cms/apps/web/eslint.config.mjs` and `.claude/rules/frontend.md` — and the plan names the rule
  that would flag it, or that none does. One plan proposed `setState`-in-effect, which the frontend config
  and `.claude/rules/frontend.md` forbid.

**7. email-hub Plan Inputs** (verify each against the tree before relying on it)

- **Vertical slice**: a backend feature lives in `app/{feature}/` — `routes.py`, `service.py`,
  `repository.py`, `schemas.py`, `models.py`, `exceptions.py`, `tests/` (e.g. `app/approval/`); the router is
  registered in `app/main.py` (`app/main.py:35`, `:414` for approval). Layer rules: `.claude/rules/backend.md`.
- **Email HTML**: any task that emits or asserts email HTML follows CLAUDE.md §Ground rules ("Email HTML is table-only")
  (table/tr/td layout, no `<p>`/`<h1>`-`<h6>`); `sanitize_web_tags_for_email()` lives in
  `app/design_sync/sanitizers.py:60` and strips those tags, so an assertion on them is wrong. Structured
  output mode: `TemplateAssembler` is the single HTML generation point — no parallel path.
- **Feature flags**: new behaviour behind a flag → register it in `feature-flags.yaml` (name, owner,
  created, `removal_date` or `permanent_reason`); `make flag-audit` (`Makefile:209`) checks it.
- **Migrations**: a model change needs an alembic revision (`make db-revision m="..."`, `Makefile:266`);
  keep it additive (nullable columns, no drops/renames) — the dev DB is shared; `make migration-lint`
  (`Makefile:509`, squawk) and the CI `migrations` job (alembic upgrade + check) gate it.
- **Agents / judges**: a diff under `app/ai/agents/` or the judges adds the eval gate — `make eval-check`
  (`Makefile:338`), `make eval-golden` (`Makefile:440`) or `make eval-calibration-gate` (`Makefile:335`);
  per-agent regression tolerance is 3pp (`AGENT_REGRESSION_TOLERANCE`).
- **Converter / design-sync**: a diff under `app/design_sync/`, `email-templates/components/` or `data/debug/`
  names the target and non-target cases, the render path (default or tree-bridge, `DESIGN_SYNC__TREE_BRIDGE_ENABLED`
  off by default) and the expected baseline blast radius; the tasks follow `.claude/skills/converter-fix/SKILL.md`.

**8. Deferred-Items Grep (MANDATORY)**

Per `.claude/rules/deferred-items.md`, grep `.agents/deferred-items.json` (entries under `items`) before
writing tasks: match each entry's `phase` against this ticket's phase, and its `code_refs` against every path
in the plan's New Files to Create / files to modify. For example:

```bash
grep -n '"phase": "<N>' .agents/deferred-items.json
grep -n '<path/to/file.py>' .agents/deferred-items.json   # once per file to create/modify
```

Put every `status: deferred` match in the plan's **Deferred Items Touching This Plan** table with a decision
per row — **close** (a task in this plan retires it: apply the Close step of `.claude/skills/deferred-items/SKILL.md`), **avoid** (the
plan steers clear of the symptom) or **carry forward** (accepted debt). The table is written even when empty;
an absent table reads as "never checked".

**Clarify Ambiguities:**

- If requirements are unclear at this point, ask the user to clarify before you continue
- Get specific implementation preferences (libraries, approaches, patterns)
- Resolve architectural decisions before proceeding

### Phase 3: External Research & Documentation

**Use specialized subagents when beneficial for external research:**

**Documentation Gathering:**

- Research latest library versions and best practices
- Find official documentation with specific section anchors
- Locate implementation examples and tutorials
- Identify common gotchas and known issues
- Check for breaking changes and migration guides

**Technology Trends:**

- Research current best practices for the technology stack
- Find relevant blog posts, guides, or case studies
- Identify performance optimization patterns
- Document security considerations

**Compile Research References:**

```markdown
## Relevant Documentation

- [Library Official Docs](https://example.com/docs#section)
  - Specific feature implementation guide
  - Why: Needed for X functionality
- [Framework Guide](https://example.com/guide#integration)
  - Integration patterns section
  - Why: Shows how to connect components
```

### Phase 4: Deep Strategic Thinking

**Think Harder About:**

- How does this feature fit into the existing architecture?
- What are the critical dependencies and order of operations?
- What could go wrong? (Edge cases, race conditions, errors)
- How will this be tested comprehensively?
- What performance implications exist?
- Are there security considerations?
- How maintainable is this approach?

**Design Decisions:**

- Choose between alternative approaches with clear rationale
- Design for extensibility and future modifications
- Plan for backward compatibility if needed
- Consider scalability implications

**DB schema checklist** (run for any ticket that creates or alters tables — detail is not completeness):

- Unique indexes over nullable columns: does NULL-duplication matter? (`NULLS NOT DISTINCT` or a partial index)
- Mutable rows: does `updated_at` actually update? (inherit `TimestampMixin` from `app.shared.models`, whose `updated_at` sets `onupdate=utcnow` — `app/shared/models.py:50-56`)
- One index per *known* hot read path of this ticket's consumers; name the owning ticket for deferred ones
- Constraint-rejection tests: check how the ORM surfaces driver errors before specifying the assertion shape (SQLAlchemy wraps them in `sqlalchemy.exc.IntegrityError` — the driver error is on `.orig`)
- Migration: one additive alembic revision per schema change, never edit an applied revision; `alembic upgrade` only — `downgrade`, squash and `dropdb` are blocked by `.claude/hooks/pre_tool_use.py`

**Figures and enum-shaped sets:**

- Every figure this plan states carries its provenance where it is written: `observed` (name the run),
  `derived` (show the arithmetic and the condition it assumes) or `expected`. An untagged figure that
  enters at the plan stage gets inherited by every later artefact and is audited only at review.
- A set that must stay 1:1 with an enum is specified as a checked mapping, not a prose list — a
  `dict[MyEnum, X]` with a test asserting `set(mapping) == set(MyEnum)`, or a `match` ending in
  `assert_never()` so mypy/pyright flag a missing member.

### Phase 5: Plan Structure Generation

**Create comprehensive plan with the following structure:**

Whats below here is a template for you to fill for the implementation agent:

```markdown
# Feature: <feature-name>

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

<Detailed description of the feature, its purpose, and value to users>

## User Story

As a <type of user>
I want to <action/goal>
So that <benefit/value>

## Problem Statement

<Clearly define the specific problem or opportunity this feature addresses>

## Solution Statement

<Describe the proposed solution approach and how it solves the problem>

## Out of Scope / Non-Goals

<Explicitly bound the work: what this feature does NOT include. Name the things a reasonable reader might assume are in scope but aren't — this is what stops the agent from gold-plating or solving the wrong problem.>

- Not included: <thing> (defer to <later / separate ticket>)
- Not changing: <existing behavior to leave alone>

## Feature Metadata

**Feature Type**: [New Capability/Enhancement/Refactor/Bug Fix]
**Estimated Complexity**: [Low/Medium/High]
**Primary Systems Affected**: [List of main components/services]
**Dependencies**: [External libraries or services required]

## Related Work

<Links between this plan and the work around it. Distinct from CONTEXT REFERENCES below (which lists files/docs to read for *this* implementation) — this is the plan's place in the larger graph.>

**Implements**: <ticket id / link>   ·   **Epic**: <engineering-plan.md path or epic link — if this ticket inherits an epic's engineering plan (see Mission), record it here>

**Back-references** (plans this builds on or inherits decisions from):

- `.agents/plans/<prior-plan>.md` - Why: shares the auth seam / reuses the X service

**Forward-references** (plans that extend or supersede this — append as follow-ups get created):

- (none yet)

## Deferred Items Touching This Plan

<From Phase 2 step 8. Always present; write "none matched" under the header row when empty.>

| id | match (phase / code_ref) | decision (close / avoid / carry forward) | why |
|----|--------------------------|------------------------------------------|-----|

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

<List files with line numbers and relevance>

- `app/{feature}/service.py` (lines 15-45) - Why: Contains pattern for X that we'll mirror
- `app/{feature}/schemas.py` (lines 100-120) - Why: Pydantic request/response schema structure to follow
- `app/{feature}/models.py` - Why: SQLAlchemy model shape (`TimestampMixin`) to follow
- `app/{feature}/tests/test_service.py` - Why: Test pattern example

### New Files to Create

- `app/{feature}/service.py` - Service implementation for X functionality
- `app/{feature}/schemas.py` - Pydantic schemas for Y resource
- `app/{feature}/models.py` - SQLAlchemy model for Y (+ `alembic/versions/<rev>_<slug>.py` migration)
- `app/{feature}/tests/test_service.py` - Unit tests for new service (inside the slice)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Documentation Link 1](https://example.com/doc1#section)
  - Specific section: Authentication setup
  - Why: Required for implementing secure endpoints
- [Documentation Link 2](https://example.com/doc2#integration)
  - Specific section: Database integration
  - Why: Shows proper async database patterns

### Patterns to Follow

<Specific patterns extracted from codebase — cite them as `file:line` references with a one-line description, not
full code blocks (plans are capped at 700 lines). A short snippet only where the exact text is load-bearing.>

**Naming Conventions:** (for example)

**Error Handling:** (for example)

**Logging Pattern:** (for example)

**Other Relevant Patterns:** (for example)

---

## IMPLEMENTATION PLAN

Phases run **top to bottom by default** — each assumes the phase above it is done. Where that is NOT the true dependency, make it explicit with a `**Depends on:**` line under the phase header, and a `**Independent of:**` line where two phases don't block each other. Independent phases are candidates to run in **parallel** (e.g. separate worktrees / parallel loops). Only annotate where it changes execution order or unlocks parallelism — skip the obvious sequential case.

### Phase 1: Foundation

<Describe foundational work needed before main implementation>

**Tasks:**

- Set up base structures (schemas, types, interfaces)
- Configure necessary dependencies
- Create foundational utilities or helpers

### Phase 2: Core Implementation

**Depends on:** Phase 1 (needs the base schemas/types)

<Describe the main implementation work>

**Tasks:**

- Implement core business logic
- Create service layer components
- Add API endpoints or interfaces
- Implement data models

### Phase 3: Integration

<Describe how feature integrates with existing functionality>

**Tasks:**

- Connect to existing routers/handlers
- Register new components
- Update configuration files
- Add middleware or interceptors if needed

### Phase 4: Testing & Validation

<Describe testing approach>

**Tasks:**

- Implement unit tests for each component
- Create integration tests for feature workflow
- Add edge case tests
- Validate against acceptance criteria

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task Format Guidelines

Use information-dense keywords for clarity:

- **CREATE**: New files or components
- **UPDATE**: Modify existing files
- **ADD**: Insert new functionality into existing code
- **REMOVE**: Delete deprecated code
- **REFACTOR**: Restructure without changing behavior
- **MIRROR**: Copy pattern from elsewhere in codebase

### {ACTION} {target_file}

- **IMPLEMENT**: {Specific implementation detail}
- **PATTERN**: {Reference to existing pattern - file:line}
- **IMPORTS**: {Required imports and dependencies}
- **GOTCHA**: {Known issues or constraints to avoid}
  - When this GOTCHA forbids the shape IMPLEMENT sketches, the GOTCHA is binding and IMPLEMENT is a sketch —
    build to it and say so under Divergences from Plan.
- **VALIDATE**: `{executable validation command}`
  - **When a GOTCHA claims test A catches a mutation AND test B does not, VALIDATE runs BOTH under that
    mutation and records both results.** A step of the shape "revert X, watch A go red" proves only the
    half you already believed; the half asserting B stays green is the half that is wrong, and nothing
    executes it. A plan that says "test B stays green when X is deleted" and only ever runs test A lets
    the false half get copied into source comments and later plans until a review executes it.
- **SATISFIES**: {which acceptance criterion this task advances — e.g. AC #2 — so every task traces to a criterion}

<Continue with all tasks in dependency order...>

---

## TESTING STRATEGY

<Define testing approach based on project's test framework and patterns discovered during research>

### Unit Tests

<Scope and requirements based on project standards>

Design unit tests with fixtures and assertions following existing testing approaches

### Integration Tests

<Scope and requirements based on project standards>

**If the ticket touches a WebSocket, a room join, or anything under `app/streaming/websocket/`**, one
integration test here must **connect the client in the order the app actually does** (if the app creates
state first and connects after, the test does the same) and assert that an event *arrives*. A unit test
that replaces the socket with a handler map pins the wiring, not delivery — a screen can receive no events
at all while every such test is green. Name the test and the order it uses, so the reviewer can check it is
the app's order and not the harness's convenient one.

### Edge Cases

<List specific edge cases that must be tested for this feature. Every edge case must NAME where it is
verified — a test file, or a numbered step in Level 4 manual validation. If an edge case lands in a surface
with no test framework (e.g. an app validated only by typecheck/lint/build), say so explicitly and assign it
a manual step: an edge case owned by nobody silently fails to land.>

---

## VALIDATION COMMANDS

<Define validation commands based on project's tools discovered in Phase 2>

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

<Project-specific linting and formatting commands. email-hub defaults (non-mutating, safe per task):>

- `uv run ruff format --check <paths>` and `uv run ruff check --no-fix <paths>` (never `ruff --fix` with TC
  rules — CLAUDE.md §Ground rules "Linter safety"; `make lint` rewrites files)
- `uv run mypy app/` and `uv run pyright app/` (`make types`, `Makefile:133`)
- Frontend: `make ci-fe` (`Makefile:195`) — not `make check-fe`, whose lint and format:check steps are `|| true` (`Makefile:137-142`)

### Level 2: Unit Tests

<Project-specific unit test commands, e.g. `uv run pytest app/{feature}/tests -m "not integration"`; the
full suite is `make test` (`Makefile:85`: `-m "not integration and not benchmark and not visual_regression and
not collab"`). `make test` rewrites the `date:` in `app/ai/agents/*/skill-versions.yaml` — restore those
files before committing.>

### Level 3: Integration Tests

<Project-specific integration test commands, e.g. `uv run pytest -m integration <paths>` or
`make test-integration` (`Makefile:88`). Final backend gate: `make check-full` (`Makefile:182`); add the
eval gate when the diff touches `app/ai/agents/` or judges (Phase 2 step 7).>

### Level 4: Manual Validation

<Feature-specific manual testing steps - API calls, UI testing, etc.>

**Every step here must be PERFORMABLE with what this ticket ships and what the seed provides.**
Write each step, then ask: can a human actually reach this state? Two ways it fails, both seen:

- The step reads a signal the ticket does not emit ("poll twice, the logs must show no second
  route call" — when the slice has no logger at all).
- The step needs live state the seed cannot produce — a record or token that only an upstream
  flow or an external account mints, so "open the page" silently means running that whole chain
  first.

If a step needs state the seed lacks, the ticket must **ship the means to produce it** — a dev
script, a seed row, a dev-only route — or the step must be rewritten against state that exists.
Name that means as a task in this plan, not as an aside.

A step nobody can run is not validation deferred; it is validation that silently never happens.
It also tends to be the ticket's own success condition, because that is the interesting one.

### Level 5: Additional Validation (Optional)

<MCP servers or additional CLI tools if available>

---

## ACCEPTANCE CRITERIA

<List specific, measurable criteria that must be met for completion>

<An AC whose verification this machine cannot perform — hardware or credentials confirmed absent at planning time —
is not this ticket's AC. `gh issue create` now, put its number in the AC and mark it "owed by #N" — an unowned AC
silently never lands.>

<**Before writing that AC off, name the property and find the cheapest oracle for IT, not for the instrument.**
"Verified handset" is an instrument; "does a bare `host.tld/path` linkify" is the property. Write the property
first, then list what else could answer it — an emulator, a platform API the real client is built on, a local
harness, a fixture — and for each say in one clause why it does or does not answer the property. Only after
that list is empty is the AC unperformable here. (For email rendering, a real client is the instrument; the
property usually has a cheaper oracle — the rendering screenshots, the QA checks, a golden template.)
A substitute that answers the property closes the AC. One that answers it weakly closes the leg it covers and
names the legs it does not, which is still better than an unopened spike.>

- [ ] Feature implements all specified functionality
- [ ] All validation commands pass with zero errors
- [ ] Unit test coverage meets requirements (80%+)
- [ ] Integration tests verify end-to-end workflows
- [ ] Code follows project conventions and patterns
- [ ] No regressions in existing functionality
- [ ] Documentation is updated (if applicable)
- [ ] Performance meets requirements (if applicable)
- [ ] Security considerations addressed (if applicable)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting or type checking errors
- [ ] Manual testing confirms feature works
- [ ] Acceptance criteria all met
- [ ] Code reviewed for quality and maintainability

---

## OPEN QUESTIONS / ASSUMPTIONS

<Surface anything still uncertain instead of silently guessing. List the assumptions this plan makes, and any question that — if answered differently — would change the plan. Flag unresolved critical questions for the user before execution.

A question about ORDERING or TIMING — who connects first, what fires before what, which of two responses
wins, what a late arrival overwrites — must be answered with the WORST case, not the typical one. "A stale
first frame" and "never updates again" can be answers to the same ordering question; the implementation
follows whichever the plan wrote down.>


## NOTES (open canvas)

<No fixed shape. Reason freely here: alternatives you weighed and rejected and why, a tradeoff matrix, a sequencing or rollout risk, a data-flow sketch, open threads, links — whatever serves the plan. The sections above template the plan's *shape* so the trifecta and the implementation agent can consume it; this section keeps your *reasoning* unconstrained. Prose, lists, tables, code blocks all welcome.>

## AMENDMENTS

<Append-only history of changes made to this plan AFTER it was first approved/executed. Leave empty at creation; newest entry at the bottom. Each entry: date — what changed and why.>

- <ISO date> — <what changed and why, e.g. "scope cut: deferred bulk-import to a follow-up ticket after AC review">
```

## Output Format

**Filename**: `.agents/plans/{kebab-case-descriptive-name}.md`

- Replace `{kebab-case-descriptive-name}` with short, descriptive feature name
- Examples: `add-user-authentication.md`, `implement-search-api.md`, `refactor-database-layer.md`

**Directory**: `.agents/plans/` (create it if it doesn't exist)

**Length cap**: 700 lines (CLAUDE.md §Workflow (PIV loop)). Use compact descriptions, tables and `file:line`
references rather than full code blocks; if the plan would exceed the cap, split the ticket.

## Quality Criteria

### Context Completeness ✓

- [ ] All necessary patterns identified and documented
- [ ] External library usage documented with links
- [ ] Integration points clearly mapped
- [ ] Gotchas and anti-patterns captured
- [ ] Every task has executable validation command
- [ ] Deferred Items Touching This Plan table present (even if empty), one decision per row

### Implementation Ready ✓

- [ ] Another developer could execute without additional context
- [ ] Tasks ordered by dependency (can execute top-to-bottom)
- [ ] Each task is atomic and independently testable
- [ ] Pattern references include specific file:line numbers

### Pattern Consistency ✓

- [ ] Tasks follow existing codebase conventions
- [ ] New patterns justified with clear rationale
- [ ] No reinvention of existing patterns or utils
- [ ] Testing approach matches project standards

### Information Density ✓

- [ ] No generic references (all specific and actionable)
- [ ] URLs include section anchors when applicable
- [ ] Task descriptions use codebase keywords
- [ ] Validation commands are non interactive executable
- [ ] Every figure carries its provenance — `observed` (which run) / `derived` (arithmetic) / `expected`
- [ ] Plan is 700 lines or fewer; patterns cited as `file:line`, not pasted code

## Success Metrics

**One-Pass Implementation**: Execution agent can complete feature without additional research or clarification

**Validation Complete**: Every task has at least one working validation command

**Context Rich**: The Plan passes "No Prior Knowledge Test" - someone unfamiliar with codebase can implement using only Plan content

**Confidence Score**: #/10 that execution will succeed on first attempt

## Report

After creating the Plan, provide:

- Summary of feature and approach
- Full path to created Plan file
- Complexity assessment
- Key implementation risks or considerations
- Estimated confidence score for one-pass success
