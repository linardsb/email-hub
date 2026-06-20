# Blueprint Engine (`app/ai/blueprints/`)

State machine that orchestrates agents as pipeline nodes with deterministic gates.

## Flow
`Scaffolder → Repair → QA Gate → (pass) Maizzle Build → Export / (fail) Recovery Router → Fixer → Repair → QA Gate loop`

## Constraints
- `MAX_SELF_CORRECTION_ROUNDS = 2` — Fixer gets max 2 attempts per QA failure
- `MAX_TOTAL_STEPS = 25` — Hard limit prevents runaway pipelines (includes deterministic repair node steps)
- `CONFIDENCE_REVIEW_THRESHOLD = 0.5` — Below this, run status → `needs_review` instead of retrying
- Progressive context hydration — each node gets only relevant data

## Key Files
- `engine.py` — `BlueprintEngine.run()`, `_resolve_next_node()`, async `_build_node_context()`, `HandoffMemoryCallback`
- `protocols.py` — `NodeResult`, `AgentHandoff`, `ComponentMeta`, `ComponentResolver`, `BlueprintNode`
- `handoff_memory.py` — Bridge: auto-persists handoffs as episodic memories (`persist_handoff_to_memory`)
- `component_context.py` — `detect_component_refs()`, `format_component_context()`
- `resolvers.py` — `DbComponentResolver` (DB → `ComponentMeta`)
- `nodes/` — Node implementations (ScaffolderNode, DarkModeNode emit `AgentHandoff`)
- `definitions/` — Blueprint templates (which nodes in which order)
- `schemas.py` — API schemas including `HandoffSummary` + `handoff_history` on `BlueprintRunResponse`
- `service.py` — Wires `persist_handoff_to_memory` callback into engine construction

## Phase 7 Features (7.1 + 7.3 + 7.4 + 7.5 bridge)
- **Structured handoffs:** `AgentHandoff` frozen dataclass. Latest via `_last_handoff`, full chain via `_handoff_history`. Downstream nodes read `context.metadata["upstream_handoff"]` (latest) + `context.metadata["handoff_history"]` (all prior)
- **Handoff → Memory bridge:** `handoff_memory.py` auto-persists each handoff as episodic memory via `on_handoff` callback. Failure-safe (errors logged, never crash pipeline)
- **Confidence scoring:** Agents emit `<!-- CONFIDENCE: 0.XX -->` in HTML. Engine extracts, checks threshold, routes low-confidence to `needs_review`
- **Component context:** `ComponentResolver` Protocol detects `<component src="components/...">` refs in HTML, loads metadata from DB, injects into agentic node context

## Eval Integration (Phase 5, Step 5.7)
Blueprint pipeline evals test end-to-end multi-agent traces through the full state machine. These validate:
- Correct node sequencing and gate routing
- Self-correction loop behaviour (does the fixer actually fix?)
- Context hydration accuracy per node
- Total step count stays within bounds
- QA gate alignment with eval judge findings (Step 5.6)
