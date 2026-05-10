# Email Hub — Overview

A centralised email platform that turns design files, briefs, or raw HTML into client-ready, accessibility-compliant, ESP-ready email templates — with AI agents handling the parts a human would otherwise grind through manually.

Stack: FastAPI + PostgreSQL + Redis on the backend, Next.js 16 on the frontend, vertical-slice architecture (`app/{feature}/`).

---

## What it does

| Capability | What it gives you |
|---|---|
| **Visual builder + code editor** | Drag-drop component canvas with bidirectional sync to a Maizzle/MJML code view. Sandboxed preview, undo/redo, slot editors, palette-restricted color picker. |
| **Design import** | Figma + Penpot connectors and an HTML reverse-engineering pipeline. Real-time Figma webhooks. Bridges into the unified `EmailDesignDocument` schema. |
| **9 AI agents** | Each handles one well-scoped problem (see below). Composed by a blueprint engine. |
| **14-check QA gate** | HTML/CSS validation, file-size, link/spam/dark-mode/accessibility/MSO/image/brand/personalisation/Liquid checks, plus ISP-aware deliverability scoring. |
| **Approval workflow** | Per-template review portal: comments thread, decision bar, audit timeline, version-compare. Blocks export/push until approved. |
| **Pre-send rendering gate** | Visual rendering across 14 email clients with per-client confidence scoring. Traffic-light gate before export. |
| **ESP push** | Bidirectional sync with Klaviyo, HubSpot, Mailchimp, Salesforce. Credential pool with rotation/cooldowns. |
| **Real-time collaboration** | CRDT-based co-editing, presence panel, follow mode, conflict resolver. |
| **Translation (Tolgee)** | Per-locale preview, in-context overlay, per-locale QA matrix. |
| **Per-project design systems** | Frozen brand identities (palette, typography, logo, footer, social) injected as generation constraints. Agents are forced to honour them. |
| **Scheduling + notifications** | Cron jobs, multi-channel notifications, Redis-backed debouncer. |
| **Reports + Knowledge** | Typst PDF reports; RAG-powered knowledge agent over an internal email-development KB. |

---

## The 9 AI agents

| Agent | Role |
|---|---|
| **Scaffolder** | Brief → Maizzle HTML skeleton (table layouts, MSO/VML, dark-mode meta, accessibility baselines). |
| **Dark Mode** | Injects dark-mode CSS, Outlook `[data-ogsc]/[data-ogsb]` selectors, `prefers-color-scheme` media queries, image swap. |
| **Content** | 8 ops: `subject_line`, `preheader`, `cta`, `body_copy`, `rewrite`, `shorten`, `tone_adjust`, `expand`. Anti-spam, brand voice, PII detection. |
| **Outlook Fixer** | MSO conditionals, VML backgrounds/buttons, ghost tables, DPI, font fallbacks. |
| **Accessibility** | WCAG 2.1 AA: alt text, table roles, lang attrs, heading hierarchy, contrast, screen-reader compatibility. |
| **Personalisation** | ESP-specific dynamic syntax: Braze Liquid, SFMC AMPscript, Adobe Campaign JS, Klaviyo Django, Mailchimp Merge, HubSpot HubL, Iterable Handlebars. |
| **Code Reviewer** | Static analysis only (does not modify HTML): redundant code, CSS client support, nesting validity, file size. Returns structured findings. |
| **Knowledge** | RAG Q&A over an email-development KB with citations and confidence. Advisory, not transformative. |
| **Innovation** | Generates experimental email prototypes (CSS checkbox hacks, AMP for Email, animations, progressive enhancement) with feasibility + fallback. |

Each agent has:
- A 5-criterion **LLM judge** for binary pass/fail evaluation
- A **`SKILL.md` + tiered L3 skill files** (progressive disclosure — only the layers needed get loaded)
- **Per-agent sanitisation** profile (10 nh3 allowlists in `app/ai/shared.py`)
- **Prompt-injection scanning** on user-supplied inputs (5 pattern categories)

---

## How the agentic workflow runs

```
                ┌──────────────┐
brief / design ─┤ Scaffolder   │── HTML skeleton ──┐
                └──────────────┘                   │
                                                   ▼
                                          ┌────────────────────┐
                                          │ Blueprint Engine   │
                                          │ (state machine,    │
                                          │  max 2 self-correct│
                                          │  rounds, max 20    │
                                          │  steps, recovery   │
                                          │  router)           │
                                          └─────────┬──────────┘
                                                    │
                ┌─────────┬─────────┬───────────────┼──────────────┬──────────┐
                ▼         ▼         ▼               ▼              ▼          ▼
            DarkMode  Content  Outlook Fixer  Accessibility  Personalise  Reviewer*
                │         │         │               │              │          │
                └─────────┴─────────┴───────────────┴──────────────┴──────────┘
                                              │
                       structured "decision schemas" (no raw HTML)
                                              │
                                              ▼
                                   ┌──────────────────────┐
                                   │ plan_merger          │
                                   │ → EmailBuildPlan     │
                                   └──────────┬───────────┘
                                              ▼
                                   ┌──────────────────────┐
                                   │ TemplateAssembler    │ ← single HTML
                                   │                      │   generation point
                                   └──────────┬───────────┘
                                              ▼
                                       ┌────────────┐
                                       │ 14-check   │
                                       │ QA gate    │
                                       └─────┬──────┘
                                             │ fail → repair pipeline (8 stages,
                                             │         deterministic + agent fixes)
                                             ▼
                                   ┌──────────────────────┐
                                   │ VLM verification     │ ← render→compare→
                                   │ loop (Phase 47)      │   correct, ~99% fidelity
                                   └──────────┬───────────┘
                                              ▼
                                       ┌────────────┐
                                       │ Approval   │ ← comments + version compare
                                       │ workflow   │
                                       └─────┬──────┘
                                             ▼
                              Pre-send rendering gate (14 clients)
                                             │
                                             ▼
                                       Export / ESP push
```

*Code Reviewer is diagnostic-only — its findings go into `AgentHandoff.warnings`, not HTML mutations.

### Key design choices

- **Single HTML generation point.** Only `TemplateAssembler` writes HTML. Agents return *decisions*, not HTML — eliminating drift between agents.
- **Eval-driven iteration.** Every agent passes synthetic test cases (≥10 per agent) with binary LLM judges calibrated against human labels (TPR/TNR). Per-agent regression tolerance: 3pp. Calibration regression gate: 5pp TPR/TNR delta.
- **Production trace sampling.** Successful runs are probabilistically queued, judged offline, and merged with synthetic verdicts so agents learn from real failures.
- **Inline judges on retry.** When the blueprint recovers from a failure, judges run inline at lightweight tier to gate the retry.
- **Design-system constraints injected, not suggested.** Brand palette, fonts, logo dimensions, and footer text are locked into the `EmailBuildPlan` and enforced post-assembly by a deterministic `BrandRepair` stage in the QA pipeline.

---

## Surface area

- **29 API modules** under `/api/v1/*` (projects, components, email_engine, qa_engine, connectors, approval, templates, design_sync, workflows, scheduling, credentials, evals, reports, etc.)
- **~22k indexed code symbols**, ~1,400 backend Python files, 48 Alembic migrations
- **150 reusable email components** in the section library (P47 expansion)
- **Maizzle sidecar** for MJML compilation + PostCSS-based per-client CSS optimisation
- **MCP server interface** for agent tools (caching + schema compression)
