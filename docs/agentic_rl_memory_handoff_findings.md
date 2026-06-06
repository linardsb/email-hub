# Agentic RL, Persistent Memory & Handoff Pipelines — Findings for email-hub

**Date:** 2026-06-05 · **Branch:** `tech-debt/phase-52-converter-foundation` · **Type:** research only, no code changed.

**Question asked:** *"What are the actual RL best practices to implement in an agentic workflow like email-hub — so agents are consistent, with persistent memory across tasks — and are there handoff pipelines so the converter engine is prompted properly by the autonomous agents we've built?"* Plus two steering follow-ups: *(Q1)* is targeting the converter even the right approach under that premise, and *(Q2)* the design→HTML solution should be **model-agnostic**.

Method: 5 parallel read-only audits over `app/ai/`, `app/memory/`, `app/knowledge/`, `app/design_sync/`, cross-checked against current 2024–2026 literature (sources in Appendix A). Every "live vs. inert" claim is grounded at `file:line` (Appendix B). Surprising claims were spot-verified by hand.

---

## 0. TL;DR

**On "RL":** We orchestrate *frozen hosted Claude models* over an API. Literal training-time RL (PPO, RLHF/RLAIF, reward modeling with gradient updates) is **inapplicable** — we have no gradient access to the policy. Everything actionable is **RL-*inspired* inference-time orchestration**: verifier/judge "rewards" used to gate/select/route, episodic/semantic/procedural memory, and *offline, human-gated* self-improvement. The user's own elaboration ("consistent, persistent memory, handoff pipelines") is exactly this reading.

**On the codebase:** email-hub has an unusually **complete RL-adjacent architecture — and almost all of it is built-but-inert.** The orchestration spine is genuinely live; the learning/memory loops around it are off-by-default, structurally unwired, or dead-on-read. Four headline findings:

1. **Memory recall is dead-on-read.** Every `MemoryService.recall()` call path opens an *unstamped* `get_db_context()` session; `MemoryRepository.similarity_search` calls `scoped_access()` unconditionally (`repository.py:56`), which **raises `RuntimeError`** on an unstamped session (`scoped_db.py:176` — *"failing loud is the point"*), and each caller swallows it → returns `[]`. The entire `app/memory` recall-into-context layer silently returns nothing. *(Hand-verified.)*
2. **Every online learning loop ships OFF.** `BLUEPRINT__JUDGE_ON_RETRY`, `__JUDGE_AGGREGATION_ENABLED`, `__RECOVERY_LEDGER_ENABLED`, `__CONFIDENCE_CALIBRATION_ENABLED`, `__INSIGHT_PROPAGATION_ENABLED`, `AI__ADAPTIVE_ROUTING_ENABLED` all default **False**.
3. **The "structured decisions → `plan_merger` → `TemplateAssembler` single-HTML-point" architecture is dead in the blueprint.** `build_plan` never threads between nodes (a fresh `NodeContext` is built per node; `build_plan` isn't in `RESERVED_FIELD_KEYS`), so downstream agents always see `build_plan=None` and `merge_*` is never called — *regardless of any flag*.
4. **The reward corpus is inert and partly circular.** The production reward sampler is off (`EVAL__PRODUCTION_SAMPLE_RATE=0.0`) and `traces/` is gitignored, so a fresh deploy has no `analysis.json` for `failure_warnings` to inject; and the converter's own regression gate is **self-referential** — it grades the converter against a snapshot of its own output.

### Direct answer — Q1: *Is targeting the converter the right approach under the goal's premise?*

**Mostly no — the premise contains a false assumption.** The converter is **not** "prompted by autonomous agents." It is a standalone **deterministic** engine — the default conversion path makes **zero LLM calls** — and it sits **outside the agent loop in both directions** (no import edge `app/ai/ → converter`, and the converter does not import `app.ai`). The fidelity gap you're chasing originates in **deterministic segmentation/render code** (`_expand_container_wrappers` / `_is_container_wrapper`, `figma/layout_analyzer.py`), already scoped as Phase 53. **No amount of agent RL / memory / handoff plumbing will move that gap** — it's a category error. Better handoffs and memory improve the *agent pipeline's* consistency; they do not reach the converter.

So: **split the goal.** "RL/memory/handoffs for agent consistency" and "fix the converter's design→HTML fidelity" are *two independent programs*. Pursuing the first as a means to the second will not work.

### Direct answer — Q2: *Make the design→HTML solution model-agnostic*

This instinct is correct and it **reinforces** the split above. The converter is *already* model-agnostic (deterministic, reproducible, no model dependency). The way to *improve* it without breaking that property is the RL-inspired pattern that is itself model-agnostic: **verifiable rewards + distilled deterministic rules**, not model-specific prompting.

- Use a **real fidelity metric** (rendered output vs. the reference design image) as a *verifiable reward* — model-agnostic by construction.
- Distill recurring corrections into **deterministic rules** (the `ConverterRuleSuggestion` seam) — a policy expressed as code, portable across any model and any session.
- Where an LLM genuinely helps (suggesting a rule from observed diffs; classifying a structurally ambiguous layout), keep it **behind a verifier gate** and behind the existing `resolve_model()` provider abstraction, so the model is swappable and never load-bearing for correctness.
- **Anti-pattern to avoid:** baking design-fidelity knowledge into one model's prompt or weights — non-portable, non-reproducible, and exactly what "model-agnostic" rules out.

---

## 1. Scope & interpretation (stated, not assumed)

**"RL" — two readings:**

| Reading | Applies here? | Why |
|---|---|---|
| Training-time RL (PPO/RLHF/RLAIF, reward-model gradient updates) | **No** | We call hosted models; no weight access. Included below only as contrast. |
| RL-*inspired* inference-time orchestration (verifier/judge rewards as gates+selection; episodic/semantic/procedural memory; Reflexion/Voyager/DSPy-style self-improvement; offline human-gated policy updates) | **Yes** | This is what "consistent + persistent memory + handoffs" actually requires. |

**"Model-agnostic" — three readings (I proceed on the third; flag if you meant another):** (a) portable across LLM *providers*; (b) *no* LLM dependence at all (pure-deterministic); (c) the *improvement signal* is independent of which model produced the output (verifier-based). The converter already satisfies (b) on its default path; the recommendations below preserve (b) where possible and fall back to (a)+(c) — a deterministic engine, a verifier reward, swappable LLM assist behind an interface.

---

## 2. RL-inspired best practices (current literature)

Condensed from primary sources (Appendix A). Each line names the load-bearing practice and the anti-pattern.

**2.1 Reward / feedback without training.** Convert "reward" into **gates and selection**: generate candidates → score with verifiers/judges → keep or reject.
- Prefer **verifiable rewards** (RLVR framing, Tülu 3): deterministic checkers (schema validators, linters, unit tests, a QA gate, a pixel metric) over learned reward models wherever output is checkable. *Most model-agnostic option.*
- **LLM-as-judge** reaches >80% human agreement but has position/verbosity/self-enhancement bias (Zheng 2023) — **calibrate against a small human-labeled set**, and never let a judge grade its own generator.
- **Process > outcome** supervision for multi-step work (Lightman 2023). **Best-of-N / self-consistency** are the cheapest reliability wins (Wang 2022).
- **Anti-pattern:** circular/self-referential evaluation and Goodharting a proxy metric (Gao 2022 reward-overoptimization).

**2.2 Persistent agent memory.** Organize by the **episodic / semantic / procedural** taxonomy (CoALA, Sumers/Yao 2023).
- **Reflection/summarization** turns raw logs into retrievable insights (Generative Agents, Park 2023). **Virtual-context paging** tiers memory like an OS (MemGPT/Letta, Packer 2023).
- **Curate, don't accumulate** — "context rot" degrades long-context precision (Anthropic, *Effective context engineering*). Write on salient events; retrieve by recency+importance+similarity; **compact periodically**.
- **Anti-pattern:** *write-only memory* — append everything, never read back / compact / scope.

**2.3 Multi-agent handoff & orchestration.** **Start single-agent; add agents only when the path can't be predicted** (Anthropic, *Building effective agents*). Distinguish **workflows** (deterministic code paths) from **agents** (model-directed).
- **Orchestrator-worker** scales breadth-first tasks (+90.2% vs single-agent) but ~15× tokens — reserve for high-value work (Anthropic multi-agent system).
- **Handoffs-as-tools** with **structured (JSON-schema) payloads, not free text**; isolate each agent's context; persist state with a **checkpointer** for resumable, human-gated flows (LangGraph). Consistency levers: low temperature, structured outputs, validators + retry.
- **Anti-pattern:** premature multi-agent — coordination cost with no accuracy gain.

**2.4 Self-improvement loops.** Keep them **offline and gated**.
- **Reflexion** (verbal self-reflection → episodic memory) and **Voyager** (skill library = procedural memory accretion) improve later trials with no weight updates. **Self-Refine helps only with a *real* critique signal** — pure self-grading can be net-negative (Madaan 2023).
- **Automatic prompt optimization** against a metric (DSPy / MIPRO) — offline. **Gate every update with golden-set regression + human approval.** Autonomous *online* self-improvement remains experimental.
- **Anti-pattern:** self-refinement with no external verifier; shipping prompt/skill changes with no regression gate.

---

## 3. Current-state map — what email-hub actually has (exists vs. live)

### 3.1 Orchestration & handoffs — *live spine, inert learning layer*

A genuine **bounded cyclic state machine** runs on every `/blueprints/run`: `scaffolder → repair → visual_precheck → qa_gate →(success) maizzle_build → visual_comparison → export`, with a self-correction loop `qa_gate →(qa_fail) recovery_router →(route_to) {dark_mode|outlook_fixer|accessibility|personalisation|code_reviewer|scaffolder} → repair → qa_gate`. Bounds: ≤2 self-correction rounds, ≤25 steps. What flows between agents is a **raw HTML string** plus a side-channel `AgentHandoff`. The deterministic guards are real and effective: `sanitize_html_xss()` on every output, the 14-check QA gate, `scope_validator` (reverts out-of-scope diffs), low-confidence → `needs_review`.

**But the RL-adjacent layer is off or unwired:**

| Mechanism | Status | Evidence |
|---|---|---|
| Adaptive model-tier routing (RL loop) | **Inert even when enabled** — `effective_tier` computed (layer_20) but no node reads it; nodes hardcode `resolve_model("complex"|"standard")`; `routing_history` always keyed on constant `"standard"` | `AI__ADAPTIVE_ROUTING_ENABLED=False` |
| Structured decisions → `plan_merger` → `TemplateAssembler` | **Dead in blueprint** — `build_plan` never threads between nodes; `merge_*` has no live caller; `output_mode="structured"` never set in engine path | `protocols.py:69`, `engine.py:852` |
| `format_upstream_constraints` / `upstream_learnings` | **Written, never read** — only `upstream_handoff.warnings` is consumed by nodes | `engine.py:923-927` |
| insight_bus, judge_aggregation, correction_examples, recovery_ledger, confidence_calibration, checkpoints, knowledge_prefetch | All **default OFF** | `config/blueprint.py:10-17`, `knowledge.py:75` |
| Generation temperature | **Unset** → provider default → non-deterministic; `temperature=0.0` only in eval/judge paths | — |
| route_advisor (skip/prioritise nodes) | **Live, static rules** (no feedback) | `route_advisor.py:82` |

> Three meanings of "handoff" are conflated in the code: **within-run** agent→agent context (in practice only the `warnings` channel is consumed); **across-run** agent→memory (`handoff_memory.py`, but see 3.2); and agent→agent-via-memory (`insight_bus`, gated off). None is model→model.

### 3.2 Persistent memory — *write-mostly, read-never*

`app/memory/` is a pgvector store unifying all three RL memory classes (`memory_type ∈ {episodic, semantic, procedural}`). It *looks* like a closed loop — 18 write/read sites across engine, scaffolder, judges, converter. **It is not closed.**

- **Dead-on-read (the headline):** every `recall()` caller uses `get_db_context()` (unstamped); `similarity_search` → `scoped_access()` **raises** → swallowed → `[]`. *Hand-verified at* `repository.py:56`, `scoped_db.py:176-181`, `database.py:83`. Even the on-by-default **converter→scaffolder quality-memory loop** dies here (writes succeed via `get_system_db_context`; the reader uses `get_db_context` and gets nothing — the "cruelest inert loop").
- **Compaction never runs:** `MemoryCompactionPoller` is not registered in `app/main.py` → no decay/summarization → unbounded growth (the write-only anti-pattern, latent).
- **Checkpoints are per-run only** (crash-recovery, keyed by `run_id`); **no cross-run learning**, and gated off.
- **Knowledge RAG (`app/knowledge/`) is the one genuinely live store** — hybrid vector+fulltext retrieval injected into the Knowledge agent's prompt. It works *because* it deliberately bypasses tenant scoping. **But its write-back loop is open:** `make eval-knowledge` writes `judge_calibration_insights.md` to disk, and nothing ingests it (not in `SEED_MANIFEST`).
- **prompt_store** is versioned + A/B-capable but selection is a **manual `active` flag** — no outcome signal picks the "best" prompt — and it's gated off.

**Net:** of the three memory classes, only **semantic** exists in practice (a static, human-seeded RAG corpus). **Episodic and procedural cross-task memory are effectively missing/inert.**

### 3.3 Feedback / eval / learning loops — *well-built, offline, human-gated*

The reward signal is **binary pass/fail LLM judges** (5 criteria/agent), calibrated **TPR≥0.85 / TNR≥0.80** against human labels. The architecture is mature; the wiring is conservative:

- **Online reward exists but ships off:** `inline_judge` on recovery retry (`BLUEPRINT__JUDGE_ON_RETRY=False`) is the only online reward; `judge_aggregation`, `recovery_ledger` (contextual-bandit fixer reroute), `confidence_calibration` are all online-capable but **default off**.
- **Policy updates are human-in-the-loop:** `skill_updater` opens a git branch/commit; `amendment_suggester` writes a `.md` stamped *"Do NOT auto-merge"*; `skill_ab` is a pre-merge gate. Nothing self-applies to the runtime. The one auto-closed loop (`judge_corrections`) corrects the **reward model**, not the policy.
- **The only always-on agent-behavior loop** is `failure_warnings`: `analysis.json` → "KNOWN FAILURE PATTERNS" block in every system prompt. **But it's doubly defeated:** production sampler inert (`EVAL__PRODUCTION_SAMPLE_RATE=0.0`) *and* `traces/` gitignored, so a fresh checkout has no `analysis.json` to inject.
- **Two measurement-validity holes:** the converter regression gate is **circular** (grades the converter against its own self-reported score snapshot — green ≠ correct); and the agent judges, though human-calibrated *in principle*, run on **synthetic inputs** with human-label files mostly absent/empty.

### 3.4 Converter coupling — *outside the agent loop, deterministic*

| Mechanism | Status |
|---|---|
| Deterministic core (`analyze_layout → matcher → renderer → assemble`) | **Live, default, zero LLM calls** (`converter_enabled=True`); output persisted directly as the template ("converter passthrough") |
| AI layout classifier / content detector | Exist but **no live caller** (only tests); `enhance_layout_with_ai` is dead in prod |
| Custom-component generator (Scaffolder fallback) | Wired but **off** (`custom_component_enabled=False`) |
| Scaffolder agent generating HTML | Runs **only on the fallback branch** (converter disabled / 0 sections) |
| Rule-learning seam (`CorrectionTracker → ConverterRuleSuggestion → RuleStatus`) | **Inert** — records to JSONL (gated off), aggregates into *human-paste Python snippets* in an admin API; `approve_rule` only flips a status string; **no "apply" path exists** |
| VLM verify loop (P47-era) | **Doubly dead** (`vlm_verify_enabled=False` *and* `design_screenshots` never passed) |
| Fidelity metric (`fidelity_service`) | **Blind/non-gating** — double-gated off, scores nothing in CI, gates nothing |

**Coupling, both directions:** zero imports of `converter_service`/`design_sync.converter` anywhere in `app/ai/`; the converter does not import `app.ai`. The only edges are *design_sync → ai* (the converter is a downstream *caller* of the Scaffolder on its fallback path) plus a fire-and-forget advisory memory hint. **The converter is unambiguously outside the agent loop.**

---

## 4. Gap analysis (against the user's three pillars)

| Pillar | Best practice (§2) | email-hub today | Gap |
|---|---|---|---|
| **Consistent agents** | Low temp, structured outputs, validators+retry, calibrated judges | Strong *structural* determinism (sanitize, QA gate, scope validator, bounded loops); but generation temperature unset, structured-decision path dead, judges run on synthetic data | Pin determinism; either revive or remove the structured path; calibrate judges on real labels |
| **Persistent memory across tasks** | Episodic+semantic+procedural, reflection, compaction, read-back | Only semantic (static RAG) is live; episodic/procedural **dead-on-read**; no compaction | **Fix the dead-on-read bug first** — until then "persistent memory" does not exist at the agent-context layer |
| **Handoff pipelines (→ converter)** | Structured payloads, consumed; checkpointed | Within-run handoff mostly reduces to a `warnings` string; structured constraints written-but-unread; **converter not in the pipeline at all** | Consume the structured handoff or drop it; and **do not expect handoffs to reach the converter — they don't and shouldn't** |

---

## 5. Recommendations — two independent tracks

> **A and B are independent.** Track B does **not** fix the converter; Track A does **not** need the agent pipeline. Sequencing them as "B in order to get A" (the original premise) is the thing to avoid.

### Track A — Converter (design→HTML), model-agnostic *(this is what fixes fidelity)*

- **A1 — Fix the deterministic segmentation/render bug (Phase 53).** This is the actual fidelity fix. `_expand_container_wrappers`/`_is_container_wrapper` over-/under-split wrapper sections; the inert serializer bridge dropped properties (RC-A/RC-B, now mostly fixed). No agents involved.
- **A2 — Wire a *real, non-circular, model-agnostic* fidelity metric** (rendered HTML vs. the reference design PNG, not vs. the converter's own output). This is the *verifiable reward* (RLVR-style) and the precondition for any converter learning loop. *Known blocker from prior audits: asset resolution — the metric is inverted until the ~22 images resolve; do not gate CI on a blind metric.*
- **A3 — Close the rule-learning loop *deterministically*.** `CorrectionTracker → ConverterRuleSuggestion → human approve → **apply** (the missing step) → regression-gate against A2`. Rules are deterministic code = **model-agnostic policy** that improves the engine over time without touching any model. This is the legitimate RL-inspired play for the converter (a verifiable-reward, human-gated, offline improvement loop — exactly §2.1+§2.4).
- **A4 — If LLM assist is used at all** (rule *suggestion* from diffs; classifying genuinely ambiguous layouts), keep it **behind A2's verifier gate** and behind `resolve_model()` so any provider swaps in. Never let model output be load-bearing for correctness — that's what keeps it model-agnostic.

### Track B — Agent pipeline (consistency + persistent memory + handoffs)

- **B1 — Fix dead-on-read memory *(highest leverage for "persistent memory across tasks")*.** Recall callers must use a tenant-stamped session (`get_scoped_db`/`get_system_db_context`) or `similarity_search` must accept an explicit access scope. Until this lands, **all** episodic/procedural recall is inert. *(Add a test that exercises the real `scoped_access` path — the current test mocks it away, so CI is green on a broken loop.)*
- **B2 — Decide the off-by-default online loops.** `judge_on_retry`, `recovery_ledger`, `confidence_calibration` are real RL-inspired loops (online reward, contextual-bandit reroute, reward-calibrated gating). Either enable them with guardrails and measure, or delete them — "built-but-inert" is the worst state (maintenance cost, false sense of capability). Recommend enabling `judge_on_retry` + `recovery_ledger` behind a measured rollout first.
- **B3 — Make the reward corpus real.** Stop gitignoring (or seed-commit) the eval corpus so `failure_warnings` injects on fresh deploys; populate the human-label files so judges are actually calibrated, not just human-calibrated *in principle*; turn on a small `EVAL__PRODUCTION_SAMPLE_RATE` to collect on-policy data.
- **B4 — Structured, consumed handoffs.** Either thread `build_plan` between nodes and consume the structured decision schemas (revive `plan_merger`/`TemplateAssembler` as the single HTML point), or remove that dead path; and make nodes read `upstream_constraints`/`upstream_learnings` rather than only `warnings`.
- **B5 — Pin determinism for consistency.** Set explicit low `temperature` on generation calls (or document why not); the structured-output path also adds determinism if revived (B4).
- **B6 — Register the memory compaction poller** before turning memory writes on at scale, or memory grows unbounded (the write-only anti-pattern). Also close the Knowledge-RAG write-back loop (ingest `judge_calibration_insights.md` into the seeded corpus).

**Priority order:** A1 + A2 (converter fidelity) and B1 (memory) are the highest-leverage, lowest-regret moves. A2 + A3 turn the converter into a model-agnostic self-improving engine; B1 is the one change that makes "persistent memory across tasks" go from *false* to *true*.

---

## 6. Anti-patterns email-hub already exhibits (mapped to §2)

- **Write-only / dead-on-read memory** (§2.2) — memory written, never read back. *The single biggest gap.*
- **Circular evaluation** (§2.1) — converter regression gate grades the converter against its own snapshot; green ≠ correct.
- **Built-but-inert machinery** — off-by-default loops + structurally unwired structured path. Matches this repo's own documented history (the inert serializer bridge, the never-running fidelity metric).
- **Self-graded without external verifier** (§2.4) — improvement loops driven by judges on synthetic inputs with absent human labels.
- **Premature/illusory pipeline coupling** — the goal's premise assumes agents prompt the converter; they don't. Avoid building handoff plumbing toward a deterministic engine that neither needs nor consumes it.

---

## 7. Reconciliation with the backlog — does any of this belong in TODO.md?

*(Cross-referenced against `TODO.md` Phases 50/51/52-53, the active plan `.agents/plans/53-converter-engine-fix.md` (2026-06-02), and `.agents/deferred-items.json` per `.claude/rules/deferred-items.md`.)*

### 7.1 Converter fidelity — already planned; my findings only *validate* it

Phase 52–53 already covers **every** converter point in this doc, in more depth. I did **not** find new converter gaps — I independently re-confirmed the existing diagnosis (third-party cross-validation). Two were closed in the last 48 h.

| This doc's converter finding (§3.4) | Already tracked as | Status |
|---|---|---|
| Circular regression gate (grades converter vs. its own output) | Phase 53 **A2** "un-circular the gate" → `target_sections` | ✅ **Done 2026-06-05** + deferred `phase-53-a2-advisory-section-gate` |
| Blind / non-gating fidelity metric | Phase 53 **A3** (case-5 pixel metric, advisory) + **A4** (asset re-export) | Plan Ready; **A4 = USER action** |
| Deterministic segmentation bug (`_expand_container_wrappers`) | Phase 53 **Track C** (C1/C2 spike) | Plan Ready (spike) |
| Per-section render bugs | Phase 53 **Track B** (B1–B8) | Plan Ready (~1 wk) |
| VLM verify loop dead | Phase 53 **53.4** "revive or honestly RETIRE" | ⏳ post-fork |
| Rule-learning seam inert (no apply path) | *(not in the plan — see note)* | candidate item |
| "100% impossible / honest ceiling" | Plan **§1** + **53.7** honest-ceiling doc | Plan Ready |

**Verdict: add nothing new for the converter.** The plan is more detailed than this doc and the ladder harness (A1) + un-circular gate (A2) shipped on 2026-06-04/05. The one converter item *not* in the plan is the **rule-learning "apply" path** (§3.4 / Track A3) — but that is a *future* model-agnostic improvement, correctly deferred until the metric is trustworthy; do not pull it forward.

### 7.2 The one genuinely NEW, untracked gap — memory dead-on-read

Not in Phase 50/51/52-53; not in `deferred-items.json` (the nearest, `tech-debt-03-memory-isolation-embedding-stub`, is a *closed test-harness* item about embedding providers — different bug). This is a confirmed, live-path defect: every `MemoryService.recall()` raises and returns `[]` (`repository.py:56` + unstamped `get_db_context` at `engine.py:1501`/`pipeline.py:311`). **Recommended home:** a `deferred-items.json` entry now (known-by-inspection gap), promoted to a **Phase 50 (Tech Debt) subtask** if you want it fixed. **Cross-ref to verify:** Phase 51.2 "Safe Compaction" plans to *harden* compaction — but this audit found `MemoryCompactionPoller` is **never registered** in `app/main.py`; confirm it's wired before hardening dead code.

### 7.3 Built-but-inert loops — a strategic DECISION, not a bug to file

The inert machinery maps to *completed* phases: **P15** (adaptive routing, phase-aware memory, prompt amendments, knowledge prefetch), **P32** (cross-agent insight propagation, eval-driven skill updates, visual-QA feedback), **P43** (judge feedback loop & self-improving calibration), **P48** (agent pipeline DAG — *parked to `prototypes/`*). The machinery shipped; it's gated off. Whether to **activate** it is a product call, not tech debt. If yes → a new phase (e.g. *"P54 — Activate & validate the agent self-improvement loops"*) with a **hard prerequisite: build the reward corpus first** (commit `traces/`, populate human labels, set a small `EVAL__PRODUCTION_SAMPLE_RATE`). Enabling uncalibrated loops on an empty corpus would make agent output *worse*. Don't file as work yet — decide first (§7.5).

### 7.4 Will any of this finally solve the months-long fidelity problem?

- **100% is physically impossible.** The plan's §1 and this research agree: Outlook ~95% floor; shadows/blur/gradients/rotation/overlap/SVG are not expressible in `table`+inline-CSS+MSO. "As close as possible," with a documented per-client ceiling (53.7), is the honest target.
- **The path to "as close as possible" already exists and is well-built:** Phase 53 **Track B + Track C** + the trustworthy metric (**A3/A4**) → **fork gate (53.1)**. No new technique, and no agentic/RL layer, is required.
- **The actual long pole is A4 — the node-id-keyed Figma re-export — which needs YOUR Figma access.** Without it the metric binds only on case-5 (an under-segmenter), so the fork decision rests on a single fixture. This is the highest-leverage thing a *person* (not the code) can unblock.
- **Agent RL / memory will not move converter fidelity** — category error (deterministic engine, outside the agent loop).

### 7.5 Recommended actions (surgical)

1. **Converter:** execute Phase 53 **Track B + Track C**; **unblock A4 (Figma re-export)** — the real bottleneck, user action. *No new backlog items.*
2. **File ONE deferred-item:** memory dead-on-read (§7.2). Ready to draft on request.
3. **Decide, don't pre-file:** do you want the agent self-improvement loops live? Yes → new phase, **corpus-first**. "Good enough" → *delete* the inert machinery (it's maintenance cost + false capability).
4. **Optional:** if memory is meant to be live, fixing §7.2 is the single change that makes "persistent memory across tasks" *true* — but it improves *agent-generated* emails, not the converter.

---

## Appendix A — Sources (2024–2026, primary)

**Reward without training:** Zheng *Judging LLM-as-a-Judge* arXiv:2306.05685 · Lightman *Let's Verify Step by Step* arXiv:2305.20050 · Wang *Self-Consistency* arXiv:2203.11171 · Gao *Reward Model Overoptimization* arXiv:2210.10760 · Snell *Test-Time Compute* arXiv:2408.03314 · Lambert *Tülu 3 (RLVR)* arXiv:2411.15124.
**Memory:** Sumers/Yao *CoALA* arXiv:2309.02427 · Park *Generative Agents* arXiv:2304.03442 · Packer *MemGPT* arXiv:2310.08560 · Anthropic *Effective context engineering for AI agents*.
**Orchestration/handoffs:** Anthropic *Building effective agents* · Anthropic *Building a multi-agent research system* · OpenAI *Agents SDK / Swarm* (handoffs) · Wu *AutoGen* arXiv:2308.08155 · LangGraph docs (checkpointing/HITL) · CrewAI docs.
**Self-improvement:** Shinn *Reflexion* arXiv:2303.11366 · Wang *Voyager* arXiv:2305.16291 · Madaan *Self-Refine* arXiv:2303.17651 · Khattab *DSPy* arXiv:2310.03714 · Opsahl-Ong *MIPRO* arXiv:2406.11695.

## Appendix B — Key evidence index (`file:line`)

- Memory dead-on-read — *mechanism:* `app/memory/repository.py:56` (unconditional `scoped_access`) · `app/core/scoped_db.py:176-181` (raises on unstamped) · `app/core/database.py:74-87` (`get_db_context` does **not** stamp; cf. `get_system_db_context` stamps at `scoped_db.py:161-164`). *Caller side (hand-verified):* `app/ai/blueprints/engine.py:1501` and `app/ai/agents/scaffolder/pipeline.py:311` both open `get_db_context()` then call `.recall()` → the raise fires on the live path.
- Compaction never registered: `app/memory/compaction.py` (no `MemoryCompactionPoller` in `app/main.py`).
- Off-by-default loops: `app/config/blueprint.py:10-17` · `app/config/ai.py:24` · `app/config/knowledge.py:75`.
- `build_plan` doesn't thread: `app/ai/blueprints/protocols.py:69` · `engine.py:852` · `scaffolder_node.py:213`.
- Production sampler inert: `app/ai/agents/evals/production_sampler.py:54` · `EVAL__PRODUCTION_SAMPLE_RATE` default in `app/config/blueprint.py:27` · `.gitignore:67-68` (traces).
- Converter regression circular: `app/design_sync/traces/regression.py:93-134` · `traces/converter.py:40,83`.
- Converter outside agent loop: no `converter_service` import in `app/ai/` (grep) · `import_service.py:192,360-377,415`.
- Rule-learning seam inert: `app/design_sync/traces/correction.py:380,522` · `routes.py:737` (`approve_rule` flips status only).
- Knowledge RAG (live read-back): `app/knowledge/repository.py:5-8,269,307` · `app/ai/agents/knowledge/service.py:55,93`.
