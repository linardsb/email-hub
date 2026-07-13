# EmailForge — HTML Email Innovation Hub

## Strategic Architecture & Implementation Plan

**Version 1.2 | March 2026** (Updated 2026-03-09)
**Classification: Internal / Confidential**
Built on a production-ready full-stack architecture (FastAPI + Next.js)

---

# 1. Executive Summary

This document defines the complete architecture and implementation plan for the HTML Email Innovation Hub — a self-hosted, CMS-agnostic platform that centralises email innovation, prototyping, AI-assisted development, design tool integration, and cross-client QA into a single unified workflow. The Hub is designed to operate independently on internal infrastructure while connecting seamlessly to any client tech stack including Braze, Salesforce Marketing Cloud, Adobe Campaign, and Taxi for Email.

The Innovation Hub addresses a challenge specific to how the agency operates: we serve clients across diverse martech ecosystems — Braze, Salesforce, Adobe, Taxi — yet the email development process remains fragmented, manual, and siloed between engagements. No off-the-shelf tool is designed for this multi-client, multi-platform agency model. By building a centralised innovation engine with an agnostic connector architecture, we create compound value — every innovation, component, and pattern built for one client becomes available to all.

## 1.1 Strategic Objectives

- **100% Organisation-Owned IP:** The Hub is built entirely on open-source technologies with no SaaS platform dependencies. Every line of code, every component, every AI skill definition is fully owned intellectual property — a growing strategic asset, not a rented service.
- **Centralise Innovation:** Single platform for HTML email R&D, prototyping, and production across all clients.
- **CMS-Agnostic Pipeline:** Modular connector architecture supporting Braze, Salesforce MC, Adobe Campaign, Taxi for Email, and future platforms.
- **AI-Powered Development:** Integrated AI coding assistant with sub-agents for scaffolding, QA, accessibility, dark mode, and cross-client compatibility. Local-first model strategy minimises API costs.
- **Cost-Optimised Operations:** Local LLMs handle 70–90% of AI tasks at zero API cost. Entire stack runs on open-source software with zero licence fees. Self-hosted infrastructure eliminates per-seat SaaS pricing.
- **Design-to-Code Bridge:** Native Figma integration via API and plugin ecosystem (Emailify, Email Love) for frictionless design handoff.
- **GDPR-First Security:** Zero PII in the Hub. All data flows anonymised. API design follows privacy-by-design principles.
- **Fallback-First QA:** Every innovation ships with a bulletproof HTML fallback. Automated rendering checks before any code leaves the system.

## 1.2 Technology Foundation

The Hub is built entirely on open-source technologies — zero licence fees, zero per-seat pricing, zero vendor lock-in. The organisation owns every component of the stack:

- **Backend:** FastAPI + async SQLAlchemy + PostgreSQL + Redis — all open-source, production-grade, high-performance async API layer
- **Frontend:** Next.js 16 + React 19 + Tailwind CSS + shadcn/ui — open-source component architecture (shadcn/ui is copy-paste, not a library dependency)
- **Auth:** JWT with RBAC, brute-force protection, token revocation — built in-house, no Auth0/Okta dependency
- **AI Layer:** Local-first with Ollama/vLLM (zero API cost for 70–90% of tasks) + Protocol-based cloud LLM integration for frontier reasoning. RAG pipeline with pgvector (open-source vector search, no Pinecone/Weaviate fees)
- **Infrastructure:** Docker Compose, nginx reverse proxy, Alembic migrations — self-hosted on company servers, no AWS/Azure managed service fees
- **Email Frameworks:** Maizzle (open-source, Tailwind-native email framework) as primary build engine, with MJML (open-source) support for legacy compatibility
- **Total software licence cost: £0.** The only recurring costs are infrastructure (servers, GPU for local LLMs) and optional cloud AI API usage for frontier tasks.

---

# 2. System Architecture

## 2.1 High-Level Architecture

The Innovation Hub follows a Vertical Slice Architecture where each feature owns its full stack. The system is composed of five core layers:

| Layer | Components | Purpose |
|-------|-----------|---------|
| **Presentation** | Next.js 16 + React 19 + Tailwind + shadcn/ui | Hub UI: project workspace, code editor, live preview, AI chat, QA dashboard |
| **API Gateway** | FastAPI + async endpoints + WebSocket | RESTful + real-time API layer, RBAC, rate limiting, GDPR compliance |
| **Core Services** | Email Engine, AI Orchestrator, Design Sync, QA Engine, Connector Pipeline | Business logic: build, test, validate, export email HTML |
| **Data Layer** | PostgreSQL + pgvector + Redis | Projects, components, templates, AI embeddings, cache, sessions |
| **Integration Layer** | CMS Connectors, Figma API, Litmus/EoA API, GitHub | Bidirectional sync with external tools and client platforms |

## 2.2 Vertical Slice Structure

Following the Vertical Slice pattern, each feature module is self-contained:

| File | Responsibility |
|------|---------------|
| `app/{feature}/models.py` | SQLAlchemy models for the feature domain |
| `app/{feature}/schemas.py` | Pydantic request/response schemas (input validation, serialisation) |
| `app/{feature}/repository.py` | Database operations (queries, CRUD) |
| `app/{feature}/service.py` | Business logic, orchestration, external API calls |
| `app/{feature}/routes.py` | FastAPI endpoints (HTTP + WebSocket) |
| `app/{feature}/exceptions.py` | Feature-specific error types |
| `app/{feature}/tests/` | Unit and integration tests |

## 2.3 Core Feature Modules

| Module | Description | Key Endpoints |
|--------|------------|---------------|
| **email_engine** | Maizzle/MJML build pipeline, HTML compilation, inline CSS, responsive transforms, dark mode injection | `POST /build`, `POST /preview`, `POST /validate` |
| **ai_assistant** | AI orchestrator with sub-agents: scaffolding, code review, accessibility audit, Outlook fix, dark mode, personalisation logic | `POST /chat`, `POST /generate`, `WS /stream` |
| **design_sync** | Figma API integration, design token extraction, component mapping, image asset pipeline | `POST /import`, `GET /tokens`, `POST /sync` |
| **qa_engine** | Cross-client rendering tests (Litmus/EoA API), HTML validation, accessibility checker, fallback verification | `POST /test`, `GET /results`, `POST /validate` |
| **connector_pipeline** | CMS-agnostic export: Braze Content Blocks, SFMC Content Builder, Adobe, Taxi for Email, raw HTML | `POST /export/{platform}`, `GET /status` |
| **component_library** | Versioned, tested email components with compatibility matrices, dark mode variants, and usage docs | `CRUD /components`, `POST /test` |
| **projects** | Workspace management, client configurations, template versioning, collaboration | `CRUD /projects` |
| **knowledge** | RAG pipeline: email dev best practices, client quirks database, community updates (pgvector) | `POST /search`, `POST /ingest` |

## 2.4 Multi-Tenancy & Data Isolation

The Hub enforces strict client-level data isolation from day one — a requirement unique to the agency model, where multiple competing brands may be served simultaneously. This is an architectural decision, not a post-launch addition.

| Principle | Implementation |
|-----------|---------------|
| **Client A cannot see Client B's work** | Every project is scoped to a client. RBAC enforces visibility — developers are assigned to client workspaces during briefing/discovery. No cross-client data leakage. |
| **Shared component library, private customisations** | The global component library (organisation-owned patterns, tested modules) is available to all projects. Client-specific customisations (branded variants, custom templates) are private to that client's workspace. |
| **Project scoping during briefing** | Client workspace permissions are configured during the briefing and discovery phase. Project leads assign team members, set brand guardrails, and configure which connectors are active. |
| **Database-level isolation** | Client data is partitioned by `client_id` foreign key across all tables. Row-level security in PostgreSQL enforces isolation at the database layer — even a bug in the application layer cannot leak data across clients. |
| **Component inheritance model** | Global library → Client library → Project templates. Components cascade downward. A global update propagates to all clients. A client-specific override stays private. |

---

# 3. CMS-Agnostic Connector Pipeline

The connector pipeline is the system that makes the Hub truly platform-agnostic. It decouples email creation from email delivery, allowing teams to build once and deploy anywhere.

## 3.1 Connector Architecture

Each connector implements a common interface (Python Protocol) with platform-specific adapters:

| Platform | Export Format | API Method | Auth |
|----------|-------------|-----------|------|
| **Braze** | Content Blocks + Liquid templates + campaign HTML | Braze REST API v2 | Bearer token (API key) |
| **Salesforce MC** | Content Builder assets + AMPscript templates | SFMC REST API + SOAP (legacy) | OAuth 2.0 server-to-server |
| **Adobe Campaign** | Email deliveries + content fragments | Adobe Campaign Standard API | Adobe IMS OAuth |
| **Taxi for Email** | Taxi Syntax-wrapped HTML + Email Design Systems | Taxi API / manual export (HTML zip) | API key + workspace auth |
| **Raw HTML** | Production-ready HTML, inlined CSS, images CDN-hosted | File download / GitHub push | N/A / GitHub token |

## 3.2 Existing OTT Streaming Client as Reference Architecture

A recent agency engagement for a major European OTT streaming platform provides a proven reference for how the connector pipeline should work. Key patterns to adopt:

- **mParticle → Braze data flow:** The SDH Events feed pattern (server-to-server event forwarding with attribute filtering) demonstrates how to selectively push data downstream without exposing full user profiles.
- **Connected Content pattern:** The client's content catalogue API integration in Braze (with 15-minute caching and territory-based cache keys) is an exemplary pattern for real-time content personalisation that the Hub should support as a template.
- **Liquid template architecture:** The catalog-driven content block pattern shows sophisticated localised personalisation with fallback logic — exactly the kind of pattern the Hub's component library should include.
- **Currents data pipeline:** The Braze → mParticle → GCS → BigQuery flow for engagement data is a model for how the Hub should track email performance across platforms.

## 3.3 Taxi for Email Integration

Taxi for Email is a key tool in the agency's tool ecosystem. The Hub integrates with Taxi at two levels:

- **Taxi Syntax injection:** The Hub can wrap its compiled HTML in Taxi Syntax tags to make components editable within the Taxi CMS. This allows the Hub to produce Email Design Systems that non-developers can assemble in Taxi.
- **Bidirectional sync:** Templates built in the Hub can be pushed to Taxi, and Taxi templates can be imported into the Hub for innovation and enhancement before being pushed back.

---

# 4. Design Tool Integration

The design-to-code bridge is one of the highest-value capabilities of the Hub. The goal is zero-loss translation from design intent to production HTML email.

## 4.1 Figma Integration Strategy

Figma is the primary design tool. Integration operates at three levels:

### 4.1.1 Figma REST API (Direct)

The Hub connects to the Figma REST API to pull design data programmatically. This enables automated token extraction, component mapping, and change detection.

- **Design token sync:** Colours, typography, spacing values extracted from Figma Styles and Variables, mapped to the Hub's email-safe token system (hex colours, px units, system font stacks).
- **Component structure:** Figma component sets are mapped to email module definitions. Auto-detection of headers, CTAs, product cards, footers based on naming conventions.
- **Change webhooks:** Figma file change events trigger re-sync, keeping the Hub's design tokens current with the latest design updates.

### 4.1.2 Plugin Ecosystem

The Hub leverages existing Figma plugins for design-to-email conversion:

| Plugin | Capability | Integration Path |
|--------|-----------|-----------------|
| **Emailify** | Full Figma-to-HTML conversion, responsive, cross-client tested, exports to 30+ ESPs | Direct export to Hub via webhook or import HTML output for refinement |
| **Email Love** | MJML-based conversion, component library, accessibility built-in, enterprise integrations | Import MJML output into Hub's build pipeline for further processing |
| **MigmaAI** | AI-powered design analysis, 95%+ fidelity, auto-responsive | API integration for automated batch conversion |

### 4.1.3 Design Framework Pipeline

The complete design-to-production flow:

1. Designer creates email layout in Figma using brand component library
2. Figma API extracts design tokens + structure (or plugin exports HTML/MJML)
3. Hub's design_sync module maps Figma layers to email component definitions
4. AI assistant reviews mapping, suggests optimisations for email constraints (Outlook, dark mode)
5. Maizzle build pipeline compiles to production HTML with Tailwind utilities inlined
6. QA engine runs cross-client tests (Litmus/Email on Acid API)
7. Approved HTML exported to target CMS via connector pipeline

---

# 5. AI-Powered Development Assistant

The AI assistant is not a chatbot — it is an orchestration layer with specialised sub-agents, each optimised for a specific aspect of email development. The developer is always in control: every agent can be individually enabled or disabled depending on the task, and the AI Orchestrator itself is optional — developers can invoke any sub-agent directly or let the Orchestrator route and chain tasks automatically. The developer can oversee every aspect of the development process, review all AI outputs before they are applied, and manually intervene or take over at any point.

## 5.1 Agent Architecture

| Agent | Capability | Status | Triggered By |
|-------|-----------|--------|-------------|
| **AI Orchestrator** *(Blueprint Engine)* | Routes tasks via state machine with bounded self-correction, QA gating, recovery routing. Manages structured handoffs between agents. | **Delivered** (Phase 4.13 + 7.1-7.4) | Blueprint `POST /api/v1/blueprints/run` |
| **Scaffolder** | Generates email HTML structure from design specs or text prompts. Outputs Maizzle templates with Tailwind classes, MSO conditionals, responsive stacking. SKILL.md + 4 L3 skill files with progressive disclosure. | **Delivered** (Sprint 2 + SKILL.md) | New project, design import, user prompt |
| **Outlook Fixer** | Analyses HTML and inserts Outlook-specific conditional comments, VML backgrounds, table-based fallbacks for the Word rendering engine. Progressive disclosure SKILL.md + 4 L3 skill files. | **Delivered** (V2 Phase 4.1) | Build pipeline, manual trigger, QA failure, recovery router |
| **Dark Mode Agent** | Injects `@media (prefers-color-scheme: dark)` rules, `[data-ogsc]`/`[data-ogsb]` selectors, transparent PNG suggestions, colour token remapping. SKILL.md + 3 L3 skill files with progressive disclosure. | **Delivered** (Sprint 2 + SKILL.md) | Build pipeline, design token change |
| **Accessibility Auditor** | Runs WCAG AA checks: contrast ratios, semantic structure, alt text, touch targets (44x44px min), lang attributes, screen reader simulation. Generates AI alt text for images using vision model analysis. | **Next** (eval-first build) | QA pipeline, pre-export check |
| **Content Agent** | Generates and refines email marketing copy: subject lines, preheaders, CTA text, body copy. Supports rewrite, shorten, expand, and tone adjustment. Brand voice constraints applied per client. | **Delivered** (Sprint 2) | Editor context menu, user prompt, template refinement |
| **Personalisation Agent** | Generates Liquid (Braze), AMPscript (SFMC), or platform-specific dynamic content logic from natural language requirements. | Planned | User prompt, template configuration |
| **Code Reviewer** | Static analysis of email HTML: redundant code, invalid nesting, unsupported CSS properties per client, file size optimisation. | Planned | Pre-build, pre-export gate |
| **Knowledge Agent** | RAG-powered answers from email dev knowledge base: client quirks, CSS support tables, community best practices, rendering engine updates. | Planned | User question, diagnostic context |
| **Innovation Agent** | Explores and prototypes new email techniques — AMP carousels, interactive CSS, kinetic elements, CSS animations. Cross-references rendering intelligence data to assess feasibility for a client's specific audience. Generates automatic fallback strategies and produces capability reports showing what works where. | Planned | Innovation R&D sessions, client pitch preparation, new technique evaluation |

### Four Disciplines Applied to Each Agent

Each agent operates within a cumulative four-discipline framework. Higher-layer capabilities build on the foundations below:

1. **Prompt Craft** — "What should I say?" — Table stakes: output formats, guardrails, anti-patterns, counter-examples.
2. **Context Engineering** — "What does it need to know?" — Memory systems, RAG pipelines, project conventions, Can I Email data loaded at runtime.
3. **Intent Engineering** — "What should the AI want?" — Trade-off hierarchies, decision boundaries, brand priorities, risk thresholds per client.
4. **Specification Engineering** — "What does done look like?" — Self-contained problem statements, acceptance criteria, constraint architecture, decomposition into <2hr subtasks, evaluation design.

| Agent | Prompt Craft | Context Engineering | Intent Engineering | Specification Engineering |
|-------|-------------|--------------------|--------------------|--------------------------|
| **Orchestrator** | — | — | — | Decomposes briefs into <2hr executable subtasks |
| **Scaffolder** | Standardised SKILL.md with output format | Project conventions + brand CSS loaded at runtime | Layout vs performance trade-offs per client | Self-contained specs: agent never fetches extra context mid-run |
| **Outlook Fixer** | Counter-examples ("don't use div where table required") | Can I Email data + learned client quirks auto-loaded | — | Must-Nots: never modify master reset styles |
| **Dark Mode Agent** | Best-performing prompt variants tracked | Brand colour tokens + client dark mode preferences | Never modify brand-reserved hex codes | Acceptance criteria: what constitutes correct dark mode CSS |
| **Accessibility Auditor** | Explicit check output formats | WCAG AA reference tables + past audit results | Risk threshold: block vs warn per severity | 3–5 test cases with known-good outputs per check |
| **Content Agent** | Brand voice examples + anti-patterns | Client tone guides + previous campaign copy | Priority: brand voice > character count | — |
| **Personalisation Agent** | Liquid/AMPscript syntax templates | ESP platform docs + Connected Content patterns | — | Escalation triggers for complex nested logic |
| **Code Reviewer** | Code quality scoring rubric | Client CSS support matrix + Gmail 102KB threshold | — | Pre-defined quality gates with measurable pass/fail |
| **Knowledge Agent** | — | Auto-hydrates with project files + client conventions | — | — |
| **Innovation Agent** | — | Rendering intelligence data + feasibility databases | Fallback reliability > visual complexity | Capability reports with quantified audience coverage |

## 5.2 Agent Hierarchy

The Orchestrator is an optional coordination layer — when enabled, it analyses the request, selects the appropriate sub-agent(s), and chains them for multi-step workflows. Developers can also invoke any agent directly, bypassing the Orchestrator entirely. The developer oversees all AI output and can manually intervene at any stage.

```mermaid
flowchart TB
    ORCH["🧠 AI Orchestrator<br/>Task routing · Agent chaining · Model selection"]
    subgraph BUILD["🔧 BUILD & STRUCTURE"]
        direction LR
        SCAF[Scaffolder]
        OUTL[Outlook Fixer]
        DARK[Dark Mode Agent]
    end
    subgraph QUALITY["✅ QUALITY & COMPLIANCE"]
        direction LR
        A11Y[Accessibility Auditor]
        CODE[Code Reviewer]
    end
    subgraph CONTENT["✍️ CONTENT & PERSONALISATION"]
        direction LR
        CONT[Content Agent]
        PERS[Personalisation Agent]
    end
    subgraph KNOWLEDGE["📚 KNOWLEDGE & INNOVATION"]
        direction LR
        KNOW[Knowledge Agent]
        INNO[Innovation Agent]
    end
    ORCH --> BUILD
    ORCH --> QUALITY
    ORCH --> CONTENT
    ORCH --> KNOWLEDGE
    KNOW -->|context| ORCH
    style ORCH fill:#e94560,stroke:#1a1a2e,color:#fff
    style BUILD fill:#0f3460,stroke:#6e87a8,color:#fff
    style QUALITY fill:#16213e,stroke:#6e87a8,color:#fff
    style CONTENT fill:#1a1a2e,stroke:#6e87a8,color:#fff
    style KNOWLEDGE fill:#0f3460,stroke:#533483,color:#fff
```

## 5.3 Agent Orchestration via UI

The Hub UI provides a unified orchestration panel where developers remain in full control:

- **Enable / disable any agent** per task — use only the agents relevant to the current job
- **Deploy the Orchestrator optionally** — let it route and chain agents automatically, or bypass it and invoke agents directly
- Provide detailed natural-language briefs that get decomposed into agent-specific instructions
- **Review all agent outputs** individually before merging into the main template — nothing is applied without developer approval
- **Manually intervene** at any point — edit AI-generated code, override suggestions, or take over entirely
- Configure agent behaviour per project (e.g., disable AMP agent for Outlook-heavy audiences)
- Chain agents in custom workflows (e.g., Scaffolder → Outlook Fixer → Dark Mode → Accessibility Audit → Code Review)

## 5.4 AI Skills System

Each agent has a SKILL.md file defining its expertise, constraints, and output format. Skills are versioned and can be updated independently:

- Skills are stored in the Hub's knowledge base and loaded into the AI context at runtime
- New skills can be authored by senior developers and deployed without code changes
- Skill performance is benchmarked using eval suites specific to email HTML quality

### SKILL.md Structure — Four Discipline Sections

Each SKILL.md is organised around the four disciplines, ensuring agents have complete operating context:

**1. Prompt Craft** — The agent's instruction layer:
- Best-performing system prompts (curated with success metrics)
- Failure examples and counter-examples ("don't do X because Y")
- Output format specifications (HTML structure, markdown, JSON schema)
- Anti-patterns specific to this agent's domain

**2. Context Engineering** — Required context checklist:
- Data sources that must be loaded before invocation (Can I Email, client brand guides, component library)
- Project conventions auto-injected at runtime
- RAG knowledge base queries that improve output quality
- Memory entries from previous sessions relevant to this task type

**3. Intent Engineering** — Decision framework:
- Trade-off hierarchies per client (e.g., accessibility > file size)
- Decision boundaries for autonomous action vs escalation
- Brand priority rules that override default optimisation
- Risk threshold definitions (block vs warn vs ignore)

**4. Specification Engineering** — Definition of "done":
- Output schema and validation rules
- Acceptance criteria (concrete pass/fail conditions)
- Constraint architecture: Musts, Must-Nots, preferences, escalation triggers
- Eval suite: 3–5 test cases with known-good outputs per task type

## 5.5 AI Model Selection

The Hub's AI agents are powered by frontier coding models, selected based on task complexity and latency requirements. The architecture is model-agnostic — any OpenAI-compatible API can be swapped in — but the recommended configuration uses the most capable models available:

| Tier | Model | Use Case | Latency | Strengths |
|------|-------|----------|---------|-----------|
| **Primary (Complex)** | Claude Opus 4.6 | Scaffolding from briefs, complex code review, architecture decisions, multi-step Outlook/dark mode fixes | Higher | Strongest reasoning, best at email HTML edge cases, longest context window |
| **Primary (Fast)** | Claude Sonnet 4.6 | Dark mode injection, accessibility audits, personalisation code generation, real-time coding assistance | Low | Near-Opus quality at 5× speed, ideal for interactive workflows |
| **Lightweight** | Claude Haiku 4.5 | Validation checks, simple fixes, knowledge lookups, template classification | Very low | Cost-efficient for high-volume automated tasks |
| **Alternative** | GPT-4o (OpenAI) | Fallback option, comparative benchmarking | Low | Strong general coding, different failure modes for ensemble validation |
| **Alternative** | Gemini 2.0 (Google) | Secondary fallback, long-context document analysis | Low | 1M+ token context for large template batch analysis |
| **Local (Dev)** | Qwen 2.5 Coder 32B / DeepSeek Coder V3 | Day-to-day development tasks, rapid iteration, boilerplate generation | Very low | Zero API cost, full data privacy, runs on internal infrastructure via Ollama/vLLM |
| **Local (Fast)** | Llama 3.3 70B / Codestral | Autocomplete, inline suggestions, quick fixes during active coding sessions | Instant | Sub-200ms responses for real-time editor integration, no network dependency |

### Local Model Strategy

For day-to-day development work where latency and API costs matter most, the Hub supports local LLM deployment:

- **Ollama / vLLM deployment:** Self-hosted models running on company GPU infrastructure (single A100 or equivalent handles 32B–70B parameter models comfortably)
- **Zero API cost:** Local models handle the high-volume, lower-complexity tasks — boilerplate generation, code completion, template modification, quick Q&A — that would otherwise burn significant API budget
- **Data sovereignty:** All code and templates stay on internal infrastructure, never leaving the network. Ideal for client-confidential work
- **Fallback to cloud:** When a task exceeds local model capability (complex multi-step reasoning, novel architecture decisions), the orchestrator automatically escalates to Claude Opus/Sonnet via API
- **Hybrid routing:** The system monitors task complexity and routes accordingly — local models for 70–90% of routine tasks, cloud APIs for the remaining 10–30% that require frontier reasoning
- **Open recommendation:** The local model tier is deliberately kept flexible. As the self-hosted LLM landscape evolves rapidly, the Hub's model-agnostic architecture allows swapping in newer or more capable local models without code changes. The models listed above are current best-in-class for HTML/CSS code generation but should be re-evaluated quarterly.

### Model Routing Strategy

The AI Orchestrator routes tasks to models dynamically based on complexity:

- **Scaffolder Agent:** Opus 4.6 for brief-to-email generation (requires deep reasoning about layout, responsiveness, and client constraints). Sonnet 4.6 for iterative refinements.
- **Outlook Fixer / Dark Mode:** Sonnet 4.6 for standard patterns. Escalates to Opus 4.6 for novel edge cases (e.g., Outlook 2016 + VML + dark mode interaction).
- **Code Reviewer / Accessibility:** Sonnet 4.6 for automated pipeline checks. Opus 4.6 for detailed architecture reviews.
- **Content Agent:** Local LLMs for basic rewrites, grammar fixes, and tone adjustments (70–90% of requests). Sonnet 4.6 for creative generation (subject lines, CTAs). Opus 4.6 for brand voice calibration on new clients.
- **Knowledge Agent:** Haiku 4.5 for RAG retrieval and simple lookups. Sonnet 4.6 for synthesising complex answers from multiple sources.
- **Personalisation Agent:** Sonnet 4.6 for Liquid/AMPscript generation. Opus 4.6 for complex conditional logic with nested Connected Content.

### Why Claude as Primary

Claude models are the recommended primary for the Hub because:

- **Instruction following:** Email HTML requires precise adherence to constraints (table-based layout, inline CSS, MSO conditionals). Claude models lead in instruction-following benchmarks.
- **Code quality:** Produces production-ready HTML with correct nesting, valid attributes, and email-safe CSS — reducing the review burden on developers.
- **Extended thinking:** Opus 4.6's extended thinking capability is critical for multi-step problems like "generate a responsive 3-column layout that degrades gracefully in Outlook 2016 Word rendering engine with dark mode support for Apple Mail and Gmail."
- **Tool use:** Native tool use enables agents to call the Hub's build pipeline, QA engine, and Can I Email API mid-conversation.

The architecture ensures no vendor lock-in — the Protocol-based LLM integration means swapping to a different provider requires only a configuration change, not a code rewrite.

## 5.6 Smart Agent Memory System ✅ DELIVERED (Phase 7.5, extended 2026-03-09)

> **Implementation:** `app/memory/` VSA module — pgvector Vector(1024) embeddings, HNSW similarity search, temporal decay, 3 memory types (procedural/episodic/semantic), DCG promotion bridge, `MemoryCompactionPoller`, 5 REST endpoints, 19 unit tests. Delivered 2026-03-07. **Extended 2026-03-09:** Blueprint handoffs auto-persisted as episodic memories via `handoff_memory.py` bridge — every agentic node's structured decisions become searchable cross-session knowledge. Full handoff history (`_handoff_history`) available to all downstream nodes.

The Hub's AI agents are not stateless tools — they learn, remember, and compound knowledge across sessions, projects, and clients. The Smart Agent Memory System is the infrastructure that enables the compound innovation effect described in Section 12.6. Without persistent memory, every agent invocation starts from zero. With it, the Hub gets smarter with every interaction.

### Memory Architecture

The system implements a 3-tier memory model, inspired by modern agentic AI architectures but purpose-built for the Hub's multi-agent, multi-tenant, email development context:

| Tier | Type | Scope | Storage | Lifecycle |
|------|------|-------|---------|-----------|
| **Working Memory** | Current conversation context | Session | In-memory (Redis) | Session duration |
| **Episodic Memory** | Session logs, interaction history | Agent + Project | PostgreSQL | Temporal decay (30-day half-life) |
| **Semantic Memory** | Durable facts, learned patterns, client preferences | Agent + Project + Org | PostgreSQL + pgvector | Evergreen (no decay) |

### Implementation Layers

#### 1. Conversation Persistence (Foundation)

Thread-based conversation storage gives agents multi-turn context. Every agent interaction is stored as a searchable, project-scoped conversation thread with full message history.

**Data Model:**
- `Conversation` — thread ID, user, project, agent type, created/updated timestamps
- `ConversationMessage` — role, content, token count, tool calls, citations, metadata
- `ConversationSummary` — compressed representation for long threads

**Key Behaviour:**
- Developers resume conversations from previous sessions with full context preserved
- Conversations are project-scoped: Client A threads invisible to Client B users
- Searchable by content, agent type, project, and date range

#### 2. RAG-Augmented Chat (Highest Impact)

Every chat completion query searches the knowledge base (`app/knowledge/`) before responding. This wires the existing RAG pipeline directly into agent conversations — the single highest-impact integration.

**How It Works:**
1. User sends message to agent
2. Agent extracts search intent from the message
3. Knowledge base queried via existing hybrid search (vector + full-text + RRF fusion + reranker)
4. Top-K relevant chunks injected as system context
5. Agent responds with knowledge-grounded answer + source citations

**Result:** An agent asked about "Outlook dark mode rendering" automatically retrieves Can I Email data, past rendering fixes, and team documentation — without the developer needing to search manually.

#### 3. Agent Memory Entries (Learned Knowledge)

Per-agent-type learned facts stored as embedded entries in pgvector. This is how agents accumulate expertise over time.

**Memory Types:**
- **Procedural** — learned patterns: "Samsung Mail 14+ clips `max-width` on `<div>` inside `<td>`. Use `width` attribute instead."
- **Episodic** — session summaries: "Developer X spent 2 hours debugging VML fallback for rounded corners in Outlook 2019."
- **Semantic** — durable facts: "Client Y requires all CTAs in #E84E0F (Brand Orange). Brand guidelines v3.2."

**Storage:** `memory_entries` table leveraging existing pgvector infrastructure (Alembic migration `f1a2b3c4d5e6`):
```
id | agent_type | memory_type | content | embedding(1024) | project_id | metadata(jsonb) | decay_weight | source | source_agent | is_evergreen | created_at | updated_at
```

**Indexes:** `ix_memory_project_agent` on (project_id, agent_type), `ix_memory_type_decay` on (memory_type, decay_weight), pgvector HNSW on embedding column.

**REST API (all require admin/developer role):**
```
POST   /api/v1/memory/         → store memory entry (10/min rate limit)
POST   /api/v1/memory/search   → similarity search with decay weighting (30/min)
GET    /api/v1/memory/{id}     → get single entry (30/min)
DELETE /api/v1/memory/{id}     → delete entry (10/min)
POST   /api/v1/memory/promote  → promote DCG note to Hub memory (10/min)
```

**Compound Effect:** Dark Mode Agent discovers a Samsung Mail fix → stores as procedural memory → next time *any* agent encounters Samsung Mail, the fix is retrieved automatically. This is the compound innovation effect at the infrastructure level.

**Cross-Agent Pattern:** Memories are tagged with `source_agent` but universally readable. Scaffolder stores a rendering insight → Dark Mode agent recalls it in a later session → Outlook Fixer inherits it when working on the same project. The `source` field tracks provenance: "agent" (self-stored), "dcg" (promoted from DCG), "compaction" (merged by background job).

#### 4. Context Windowing & Summarisation

Token budget management prevents context overflow on long conversations:

- Configurable context window per agent (default: 8K tokens)
- Automatic summarisation when context approaches limit
- Summary chain: full messages → compressed summary → archived (searchable but not in active context)
- Priority retention: system prompts and recent user messages always preserved; middle messages summarised first
- A 50-message conversation maintains coherent context without degradation

#### 5. Temporal Decay & Memory Compaction

Not all memories are equally valuable. The system implements intelligent lifecycle management:

- **Temporal decay:** Configurable half-life per memory type (30 days for episodic, never for procedural/semantic)
- **Down-ranking, not deletion:** Stale memories rank lower in retrieval but remain searchable
- **Compaction:** Background job merges redundant memories (10 similar Outlook fixes → 1 consolidated entry)
- **Evergreen tagging:** Client preferences, architectural decisions, and verified rendering fixes exempt from decay
- **Infrastructure:** Runs on existing `DataPoller` background task system with Redis leader election

#### 6. Cross-Agent Memory Sharing

The compound knowledge effect requires agents to share what they learn:

- **Project-scoped memory pool:** All agents within a project read from the same memory store
- **Agent-tagged, universally readable:** Memories tagged by source agent but accessible to all agents in the project
- **Propagation chain:** Scaffolder learns a layout pattern → QA Agent knows to test for it → Dark Mode Agent knows how to adapt it
- **Organisation-level patterns:** Universal truths (e.g., "Outlook clips at 102KB", "Gmail strips `<style>` in non-embedded contexts") available across all projects
- **Isolation preserved:** Client-specific preferences and brand guidelines never leak across project boundaries

### Memory vs. Knowledge Base

The memory system complements — not replaces — the existing RAG knowledge base:

| Aspect | Knowledge Base (`app/knowledge/`) | Agent Memory (`app/memory/`) |
|--------|-----------------------------------|------------------------------|
| **Content** | Documents, guides, reference material | Learned facts, patterns, preferences |
| **Source** | Manually ingested (uploaded files, web scrapes) | Automatically captured from agent interactions |
| **Lifecycle** | Static until re-ingested | Dynamic with temporal decay |
| **Scope** | Global (all users, all agents) | Scoped by agent type + project |
| **Search** | User-initiated queries | Automatically injected into agent context |

### Why This Matters

Without persistent memory, the Hub's 9 agents are sophisticated but amnesiac — every session starts without context. With the Smart Agent Memory System:

- **Individual agent sessions** become continuous conversations (Tier 1)
- **Agent responses** are grounded in the Hub's accumulated knowledge (Tier 2)
- **Agent expertise** compounds with every interaction (Tier 3)
- **Long conversations** remain coherent and efficient (Tier 4)
- **Stale knowledge** is automatically managed (Tier 5)
- **All agents benefit** from any agent's discoveries (Tier 6)

This transforms the Hub from a collection of AI tools into an AI system that genuinely gets smarter the more it's used — the infrastructure-level implementation of the compound innovation effect.

### Four Disciplines Applied to Agent Memory

The memory system maps directly to the four-discipline framework, creating a self-improving loop where each discipline's memories compound over time:

| Discipline | Memory Type | What Gets Stored | Compound Effect |
|-----------|------------|-----------------|-----------------|
| **Prompt Craft** | Procedural | High-performing system prompts ranked by output quality metrics | Best prompts automatically promoted to SKILL.md; failure patterns flagged for avoidance |
| **Context Engineering** | Semantic | Effective context patterns tracked per agent (e.g., "Scaffolder + Can I Email data → 40% higher code quality") | Agents learn which context sources improve their own output and prioritise retrieval accordingly |
| **Intent Engineering** | Episodic | Decomposition patterns and trade-off resolutions from past sessions | Agents reuse proven decomposition strategies: "Add dark mode" → [Identify colours → Extract selectors → Generate queries → Test fallbacks] |
| **Specification Engineering** | Procedural + Semantic | Output schemas that produce highest client approval rates; validated acceptance criteria per task type | Prevents specification drift after model updates by comparing new outputs against proven-good baselines |

## 5.8 Knowledge Graph Integration (Cognee) — PLANNED (Phase 8)

> **Prerequisites met:** Phase 7 infrastructure (structured handoffs, confidence scoring, component context) is complete. Agent memory system (5.6) is live. Eval system (Phase 5) has established baselines. Cognee integration is next after remaining agents are built.

The Smart Agent Memory System (Section 5.6) gives agents persistent memory. The RAG pipeline (`app/knowledge/`) gives agents grounded retrieval. But both operate on flat text — chunks of documents ranked by similarity. Knowledge graphs add a third dimension: **structured relationships between domain entities**.

[Cognee](https://github.com/topoteretes/cognee) is an open-source AI memory platform that transforms raw data into persistent knowledge graphs using an ECL (Extract, Cognify, Load) pipeline. It combines vector search, graph databases, and LLM-powered entity extraction to build queryable knowledge structures.

### Why Knowledge Graphs for Email Development

Email development is inherently relational. "Outlook 2019 does not support CSS Grid" is not just a fact — it implies a fallback chain (use MSO conditional tables), affects component selection (avoid grid-based layouts for Outlook targets), and connects to dark mode behaviour (VML fallbacks don't inherit `prefers-color-scheme`). Flat RAG retrieves similar text. A knowledge graph traverses these connections.

| Retrieval Type | What Agents Get | Example |
|---------------|----------------|---------|
| **Current (RAG chunks)** | 5 similar paragraphs about Outlook dark mode | "Outlook 2019 has limited dark mode support... CSS variables are not supported..." |
| **With Knowledge Graph** | Structured entity chain with relationships | `Outlook 2019 → does_not_support → CSS_variables → fallback → MSO_conditional_VML → requires → VML_namespace_declaration` |

### Integration Architecture

Cognee runs alongside the existing RAG pipeline — additive, not replacement. Both search modes are available to agents.

```
Agent Query
    ├── Existing: Hybrid Search (vector + fulltext + RRF + reranker)
    │   └── Returns: ranked text chunks with citations
    └── New: Graph Search (Cognee GRAPH_COMPLETION / TRIPLET_COMPLETION)
        └── Returns: structured entity relationships (subject → predicate → object)
```

**Technology choices (decided):**
- **Graph DB:** Kuzu (file-based — zero extra infrastructure, sub-millisecond traversals, stored in `DATA_ROOT_DIRECTORY`)
- **Deployment:** Background worker pattern — graph search in-process, heavy `cognify()` operations via `DataPoller` background tasks with Redis queue
- **Ontology:** Custom OWL file — full granularity (300+ CSS properties from Can I Email, all client versions, all rendering engines)

### Implementation Layers

#### 1. Graph Knowledge Provider
Protocol-based adapter in `app/knowledge/graph/` wrapping Cognee's async API. Consistent with Hub's interface patterns. Configurable per environment.

#### 2. Knowledge Graph Seeding
Existing knowledge base documents (Can I Email data, email dev guides, client quirks from `make seed-knowledge`) processed through Cognee's ECL pipeline. Extracts entities and relationships automatically, grounded by the email development ontology.

#### 3. Graph Context in Blueprint Nodes
The blueprint engine's `_build_node_context()` queries the knowledge graph for structured relationships relevant to the current task. Agents receive entity chains alongside RAG chunks. Progressive disclosure ensures only relevant graph context is loaded (e.g., only query client compatibility when the task involves rendering).

#### 4. Outcome Logging / Institutional Memory
Completed blueprint run outcomes (QA verdicts, recovery paths, which patterns succeeded) feed back into Cognee. Over time, agents can query real outcome data: "What fixes have worked when QA fails for VML backgrounds?" — answered from institutional memory, not LLM guessing.

#### 5. Per-Agent Domain SKILL.md Files
Each agent gets a SKILL.md file following the Four Discipline structure (Section 5.4), with domain-specific rules grounded by the knowledge graph. Skills reference canonical entity types from the ontology for precise, consistent constraints. Versionable, updatable without code changes, benchmarkable via eval system.

#### 6. Email Development Ontology
OWL ontology defining canonical entity types for the email domain. Ensures Cognee's entity extraction produces consistent names ("Outlook 2019" and "Microsoft Outlook 2019" resolve to the same entity). Covers 20+ email clients, 50+ CSS properties, 5 rendering engines, and the component taxonomy from `app/components/`.

### Impact on Agent Precision

| Agent | Current Context | With Knowledge Graph |
|-------|----------------|---------------------|
| **Scaffolder** | RAG chunks about layout patterns | Structured compatibility chain for target clients + component metadata + proven patterns from past runs |
| **Dark Mode** | RAG chunks about dark mode CSS | Entity graph: which clients support `prefers-color-scheme`, which need MSO overrides, which components already have dark variants |
| **QA Gate** | Static check rules | Graph-informed checks: "this CSS property is unsupported in 3 of the 5 target clients" with specific fallback recommendations |
| **Recovery Router** | Generic LLM-based recovery | Evidence-based: "this failure pattern was resolved by X in 8 of 10 previous runs" |

### Four Disciplines Applied to Knowledge Graphs

| Discipline | How Knowledge Graphs Help |
|-----------|--------------------------|
| **Prompt Craft** | Agent prompts reference verified entity relationships, not LLM training data. "Outlook 2019 does not support X" comes from the graph, not hallucination. |
| **Context Engineering** | Graph traversal provides precisely the context chain needed — not "top 5 similar chunks" but "the specific compatibility path from this CSS property to this email client's fallback." |
| **Intent Engineering** | Graph structure encodes trade-off relationships explicitly. Agents can traverse "if accessibility > file size, then prefer semantic HTML over image-based fallback" as graph paths. |
| **Specification Engineering** | Ontology-defined entity types become the vocabulary for output specifications. Agent acceptance criteria reference canonical entities, not ambiguous free text. |

### Graph-Driven Intelligence Layer (Phase 9)

Once the core knowledge graph is operational (Phase 8), it becomes the foundation for a self-improving intelligence layer that connects every part of the Hub.

#### Graph-Powered Client Audience Profiles

The Test Persona Engine (Section 9.1) currently provides device/client context for previews. With the knowledge graph, persona selection triggers a graph traversal: `iPhone 15 + Apple Mail 18 + Dark Mode` → which CSS properties are safe → which components have tested dark mode variants → which workarounds are needed. Agents receive pre-filtered compatibility context *before generation*, eliminating the "generate → QA fail → retry" loop for known compatibility issues.

#### Can I Email Live Sync

The knowledge base is currently seeded once via `make seed-knowledge`. Can I Email updates their database regularly — new client versions, updated CSS support data. A periodic sync job pulls fresh data, diffs against existing graph entities, and updates automatically. Agents always work with current compatibility data without manual re-seeding. Configurable sync interval (weekly default).

#### Component-to-Graph Bidirectional Linking

When a component is created, updated, or QA-tested in `app/components/`, its graph entity updates automatically with: supported email clients (from QA test results), known quirks (from QA failures), dark mode variant status. The component browser UI shows graph-derived compatibility badges (green/amber/red per client). Agents using components get real test data, not just static descriptions.

#### Failure Pattern Propagation Across Agents

When any agent discovers a failure pattern (e.g., "Samsung Mail strips `color-scheme` meta tag"), it becomes a typed graph relationship: `Samsung_Mail_14 → strips → color-scheme_meta`. Every agent that subsequently touches Samsung Mail compatibility gets this knowledge automatically through graph context — no explicit cross-agent sharing logic needed. The graph's structure makes propagation inherent in the data model, implementing Section 5.6 Layer 6 (Cross-Agent Memory Sharing) more elegantly than memory entry replication.

#### Client-Specific Subgraphs for Project Onboarding

When a new project is created, the system auto-generates a project-specific subgraph from persona selections: target email clients → CSS support matrix → compatible components → known workarounds → historical outcomes from similar projects. This "compatibility brief" gives new developers instant context and provides agents with pre-loaded domain knowledge specific to the project's requirements.

#### Graph-Informed Blueprint Route Selection

The blueprint engine currently follows a fixed node sequence. With graph data about the target audience and template content, the engine dynamically adjusts: skip the Outlook Fixer node if no Microsoft clients in project personas, add an AMP validation node if the template contains AMP components, prioritise nodes based on audience coverage. Blueprints become adaptive to actual requirements rather than running every check for every template.

#### Competitive Intelligence Graph

Extending the ontology to include competitor capabilities (Stripo, Parcel, Chamaileon — Section 15.4) lets the Innovation Agent answer: "Is this technique feasible for the client's audience AND do competitors support it?" This powers the capability reports described in Section 12.2 with structured, graph-backed data instead of manual research.

#### SKILL.md A/B Testing

When the skill growth system (Phase 8, Layer 5) proposes a SKILL.md update, it runs through the eval suite twice — current version vs proposed update — comparing per-criterion pass rates. Only updates that perform equal or better get recommended for merge. This closes the full loop: knowledge graph → skill proposal → eval validation → merge. Fully evidence-based skill evolution with zero risk of regression.

### The Compound Effect: Graph + Memory + Harness

The knowledge graph (Phase 8), agent memory (Section 5.6), and agent harness (Section 5.7) compound multiplicatively:

| Layer | Individual Value | Compound Value with Graph |
|-------|-----------------|--------------------------|
| **RAG Knowledge Base** | Similar text chunks | + Structured entity relationships + compatibility chains |
| **Agent Memory** | Learned facts per agent | + Graph-propagated knowledge across all agents automatically |
| **Agent Harness** | Bounded self-correction | + Graph-informed routing (skip/add nodes) + evidence-based recovery |
| **Eval System** | Pass/fail metrics | + Skill evolution proposals + A/B tested prompt improvements |
| **Component Library** | Versioned components | + Live compatibility badges from QA graph data |
| **Test Personas** | Device/client preview | + Pre-filtered compatibility context eliminates known failures before generation |
| **Blueprint Engine** | Fixed node sequence | + Adaptive routing based on audience + structured inter-agent context |

This is the infrastructure-level implementation of the compound innovation effect described in Section 12.6 — every interaction makes every subsequent interaction more informed, more precise, and less error-prone.

### Relationship to Phase 7 (✅ Complete)

Phase 7 (Agent Capability Improvements) built the infrastructure that Phase 8 leverages. **All prerequisites are met:**
- **7.1 Structured Handoffs** ✅ — `AgentHandoff` frozen dataclass propagated via `BlueprintRun._last_handoff`, exposed in API as `HandoffSummary`
- **7.3 Confidence Scoring** ✅ — 0-1 via `<!-- CONFIDENCE: X.XX -->` HTML comment, threshold 0.5 → `needs_review` status
- **7.4 Component Context** ✅ — `ComponentResolver` Protocol, `DbComponentResolver`, auto-detect `<component>` refs, inject metadata into agentic node context
- **7.5 Agent Memory** ✅ — `app/memory/` VSA module with pgvector, temporal decay, DCG promotion bridge, 5 REST endpoints
- **7.2 Eval-Informed Prompts** ⏳ — Unblocked (real failure data from Phase 5.4-5.8), not yet implemented

Phase 8 is ready to begin — all infrastructure integration points are available. Phase 9 extends the graph across the entire Hub once Phase 8 is operational.

## 5.7 Agent Harness Architecture (Phase 1: Blueprint Engine ✅ DELIVERED)

> **Implementation Status:** Phase 1 (Blueprint State Machine) delivered as `app/ai/blueprints/`. Interleaves deterministic nodes (QA gate, Maizzle build, export) with agentic nodes (scaffolder, dark mode, outlook fixer). Bounded self-correction (max 2 rounds), recovery routing, structured handoffs (`AgentHandoff`), confidence scoring, component context injection. Phase 7.1-7.4 infrastructure complete. Remaining harness patterns (TAOR loop, PreCompletionChecklist, Progressive Disclosure, Linter Gates, Progress Log, Model Escalation) are Phase 2 — spec'd below.

> "The model is the engine. The harness is the car. Nobody buys an engine."

Industry research across production AI agent systems — Claude Code, Cursor, Manus, SWE-Agent, Devin — converges on a consistent finding: **the same model scores 42% with one scaffold and 78% with another** (CORE-Bench). The engineering that separates working agents from impressive demos isn't in the model — it's in the harness: the execution loop, tool definitions, error recovery, state management, and information flow that surround it.

The Hub's harness layer applies these proven patterns specifically to email QA agents, turning single-pass generators into iterative, self-correcting production workers.

### The TAOR Execution Loop

Every production agent converges on the same core loop. The Hub implements **Think-Act-Observe-Repeat** — agents don't declare victory after a single pass. They iterate until their output passes verification or reaches a configurable iteration limit.

```
while (not verified and iterations < max_iterations):
    THINK  → Agent analyses task, decomposes into subtasks, plans approach against specification
    ACT    → Agent generates output (HTML, CSS, dark mode tokens, accessibility fixes, content)
    OBSERVE → Harness runs deterministic validation: linter, QA checks, brand compliance, spec match
    REPEAT → If validation fails, error logs injected into context. Agent hill-climbs toward correctness.
```

This is the "model controls the loop" pattern used by Claude Code — no DAG orchestration, no competing agent personas. The agent receives messages and tools, returns text (loop ends) or tool calls (loop continues). The harness decides what the agent can see, what tools it can use, and what happens when it fails.

### Five Harness Engineering Patterns

#### 1. PreCompletion Checklist Middleware

Middleware intercepts the agent's "done" signal and forces a final verification pass against the original task specification. This prevents the most common failure mode — agents that produce plausible-looking output without actually testing it.

**How it works:** Agent signals completion → harness runs the 10-point QA gate, linter, and brand compliance checks against the spec → if any check fails, the harness rejects the "done" signal, packages error logs as structured feedback, and returns the agent to the TAOR loop → agent receives "You reported completion but 2 checks failed: [accessibility: missing alt on hero image], [dark mode: no prefers-color-scheme fallback]" → agent fixes and re-submits.

**Client impact — Holiday Campaign Rush:** A retail client submits 12 campaign variants for Black Friday with a 48-hour turnaround. Without the harness, each email goes through one AI pass, then a developer manually reviews QA failures, feeds corrections back, and re-runs — 30–45 minutes per variant. With the harness, the TAOR loop catches 3 accessibility failures and 1 dark mode issue per variant automatically. **12 variants completed in hours, not days.** The developer's role shifts from fixing mechanical issues to reviewing strategic creative choices.

#### 2. Progressive Disclosure (Context Economy)

Agents discover context incrementally instead of drowning in everything upfront. This is the single most impactful harness pattern for token efficiency and output quality.

**Implementation:**
- Agent receives only tool names as static context; full tool definitions fetched on-demand when the agent selects a tool (Cursor's approach: 46.9% token reduction)
- Knowledge base queries scoped to the current check/task, not the entire 20-document corpus
- Agent "skills" stored as `.claude/skills/` files — NOT preloaded into every conversation. Skills load only when the agent detects relevance
- Observation compression: all observations except the last 5 collapsed to one-line summaries (SWE-Agent pattern)

**Evidence:**
- Static loading: ~25,000 tokens at 0.8% relevance. Progressive disclosure: ~955 tokens at 100% relevance. **26x improvement.**
- Cursor's lazy MCP tool loading: 46.9% token reduction (statistically significant A/B test)
- Vercel case study: removing 80% of tools dropped tokens from 145,463 to 67,483, steps from 100 to 19, latency from 724 to 141 seconds — and the agent went from failing to succeeding
- Liu et al. (TACL 2024): LLM performance follows a U-shaped curve — highest at beginning/end of input, degraded in the middle. Progressive disclosure keeps inputs small (less curve distortion) and places freshly-retrieved information at the end (the high-attention zone)

**Client impact — Complex Outlook + Dark Mode Rendering:** A B2B client's audience is 60% Outlook desktop. A promotional email with layered backgrounds, gradient CTAs, and responsive stacking needs VML fallbacks, MSO conditionals, and dark mode colour remapping. Progressive Disclosure loads only the Outlook-specific knowledge module when the agent detects VML requirements — not the entire knowledge base. Each sub-task gets precisely the context it needs: structure → VML fallbacks → dark mode tokens → final QA.

#### 3. Linter-Gated Guardrails (Deterministic Safety Nets)

Safety nets that don't rely on LLM reasoning. These are deterministic — the harness enforces them regardless of what the model wants to do.

**Implementation:**
- HTML linter runs automatically on every agent file save. If the structure is invalid, the edit is rejected and the agent must retry (SWE-Agent pattern: 3% performance improvement from this single guardrail)
- Brand compliance rules loaded as "Must-Nots" — hard constraints that no LLM reasoning can override (e.g., "never modify brand-reserved hex codes")
- Risk classification: lightweight model (Claude Haiku) audits commands before execution, flagging high-risk actions for human approval
- QA gate results fed back as harness-level rejections, not suggestions

**Client impact — Regulated Financial Services:** A banking client requires WCAG AA accessibility, mandatory disclaimers, and restricted terminology enforcement. Previously, compliance review added 1–2 days per campaign. With linter-gated guardrails, compliance is enforced as hard constraints — not suggestions the agent might ignore. The PreCompletion Checklist verifies every disclaimer is present, every image has alt text, and no restricted terms appear. **Compliance review drops from days to minutes** because the harness guarantees adherence deterministically.

**Client impact — Multi-Brand Agency Portfolio:** An agency manages 8 client brands. The Constraint Architecture loads each client's brand rules as "Must-Nots." The Dark Mode Agent can never substitute Brand B's reserved navy for a similar dark blue. The Content Agent can never adopt Brand A's casual tone for Brand B's luxury positioning. **100% brand isolation across the portfolio**, enforced by infrastructure rather than relying on the model to "remember" which brand it's working on.

#### 4. Task Decomposition & Progress Anchoring

Long tasks decomposed into independently verifiable sub-tasks. A progress log serves as an attention anchor that prevents "lost in the middle" degradation.

**Implementation:**
- `agent-progress.json` per session records features tested, bugs fixed, decisions made, and current sub-task
- Long tasks (>30 minutes) automatically decomposed into 2-hour sub-tasks with independent acceptance criteria
- Progress log pushed into the model's recent attention span after each tool execution (counteracts "lost in the middle" effect — the TodoWrite pattern from Claude Code)
- Each sub-task validates independently before the next begins

**Evidence:** LangChain's analysis explicitly identifies Claude Code's TodoWrite tool as a "no-op tool that forces the agent to articulate and track its plan, keeping it on course over long trajectories." It does nothing functionally — it's purely a harness-level trick.

#### 5. Model-Agnostic Escalation

The harness routes tasks to the right model tier, making the system's AI economics dramatically more efficient.

**Implementation:**
- Local LLMs (Ollama/vLLM) handle 70–90% of routine QA at zero API cost
- Harness monitors output confidence and auto-escalates to frontier models (Claude Opus) when:
  - Confidence drops below configurable threshold
  - Multi-step rendering conflicts detected (e.g., VML + dark mode + responsive)
  - Local model produces output that fails QA gate on first iteration
- Provider registry enables model swapping without code changes
- Different models can receive different tool names and prompt instructions (Cursor's approach: model-specific harness tuning)

**Client impact — Institutional Knowledge Retention:** A senior developer who has spent 18 months learning a client's rendering quirks moves teams. With the harness, every agent iteration is logged. When the Outlook Fixer discovers that Samsung Mail 14+ clips `max-width` on `<div>` inside `<td>`, the harness stores this as a Semantic Memory entry — permanent, available to all agents, all projects. New team members inherit the full accumulated expertise from day one. **Institutional knowledge compounds in the system, not in individuals.**

### The Compound Effect: Harness + Four Disciplines

The harness layer amplifies everything the Four Disciplines Framework delivers. Each discipline becomes more effective when backed by deterministic infrastructure:

| Discipline | Without Harness | With Harness |
|-----------|----------------|--------------|
| **Prompt Craft** | Defines output formats, but agents may not follow them consistently across long sessions | + Linter Gates: format compliance verified deterministically, not trusted |
| **Context Engineering** | Curates knowledge, but agents receive everything at once — relevant and irrelevant | + Progressive Disclosure: knowledge loaded precisely when needed, 26x more efficiently |
| **Intent Engineering** | Encodes priorities, but agents may drift from intent mid-task | + Constraint Architecture: priorities enforced as hard "Must-Nots," not soft guidance |
| **Specification Engineering** | Defines acceptance criteria, but agents self-report completion without independent verification | + TAOR Loop: criteria tested automatically on every iteration; agent can't exit until they pass |

### Harness Impact Summary

| Harness Pattern | QA Agent Impact | Strategic Value |
|-----------------|----------------|-----------------|
| **TAOR Loop** | Agents iterate on bug fixes autonomously until validation passes | Reduces manual developer rework by 60–80% |
| **Progressive Disclosure** | Agents only see tokens needed for current test | 26x improvement in token efficiency |
| **Constraint Architecture** | Brand rules, accessibility requirements enforced deterministically | 100% brand and compliance adherence |
| **Task Decomposition** | Full-campaign audits broken into verifiable sub-tasks | Increases reliability and execution speed |
| **Model Escalation** | Routine checks local; complex conflicts escalate to cloud | 70–90% reduction in API costs |

### Industry Sources

- Anthropic — "Effective Harnesses for Long-Running Agents"; Claude Code architecture (reverse-engineered by Vrungta, PromptLayer)
- LangChain — "Improving Deep Agents with Harness Engineering"; "Deep Agents" (TerminalBench: 52.8% → 66.5% from harness changes only)
- Cursor — "Dynamic Context Discovery"; "Improving Agent with Semantic Search"; "Improving Cursor's Agent for OpenAI Codex Models"
- Manus — "Context Engineering for AI Agents: Lessons from Building Manus" (5 rewrites, each removing complexity)
- Princeton/NeurIPS 2024 — Yang et al., "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering"
- Cognition — "Devin's 2025 Performance Review" (67% PR merge rate, up from 34%)
- Liu et al. — "Lost in the Middle: How Language Models Use Long Contexts" (TACL 2024)
- Phil Schmid — "Context Engineering for AI Agents: Part 2" (Vercel case study)
- Dex Horthy — "12 Factor Agents" (40% input capacity threshold for the "dumb zone")

---

# 6. Email Build Framework

The Hub uses a dual-framework approach to maximise flexibility while maintaining quality:

## 6.1 Maizzle as Primary Framework

Maizzle is the recommended primary framework for the Hub because:

- **Tailwind CSS native:** Developers use familiar utility classes. The Hub's frontend already uses Tailwind, creating consistency across the stack.
- **Full HTML control:** Unlike MJML, Maizzle does not abstract away the HTML structure. Developers write real table-based email markup and style it with Tailwind. This is critical for edge-case handling.
- **Build pipeline:** Maizzle's Node.js build system handles CSS inlining, unused class purging, responsive transforms, and plaintext generation automatically.
- **AMP support:** Maizzle has built-in AMP for Email configuration, enabling interactive email prototyping.
- **Environment configs:** Different build configs for development (verbose, unminified) vs. production (inlined, optimised, minified).

## 6.2 MJML as Secondary/Legacy Framework

MJML remains available for teams that prefer abstraction or for importing designs from Figma plugins that output MJML (e.g., Email Love). The Hub can compile MJML to HTML and then pass it through the Maizzle pipeline for further optimisation.

## 6.3 Build Pipeline

Every email passes through a standardised build pipeline:

| # | Stage | Action | Output |
|---|-------|--------|--------|
| 1 | **Author** | Write Maizzle/MJML template or import from Figma/AI | Source template |
| 2 | **Compile** | Maizzle build: Tailwind → inline CSS, purge unused, responsive | Compiled HTML |
| 3 | **Enhance** | AI agents: dark mode injection, Outlook conditionals, accessibility | Enhanced HTML |
| 4 | **Validate** | HTML validation, CSS support check, file size check, link validation | Validation report |
| 5 | **Test** | Cross-client rendering via Litmus/EoA API, visual diff | Rendering report |
| 6 | **Fallback Check** | Verify graceful degradation in non-supporting clients | Fallback validation |
| 7 | **Export** | Package for target CMS via connector pipeline | Platform-ready asset |

---

# 7. QA & Innovation Fallback System

This is the safety net that makes innovation possible. Every experimental feature must pass through this system before it reaches a real inbox.

## 7.1 Fallback-First Principle

The Hub enforces a strict rule: no email leaves the system without a verified fallback. Every interactive or advanced feature (AMP, CSS animations, interactive CSS, live content) must have a static HTML equivalent that renders correctly in the lowest-common-denominator client (Outlook 2016 + Word rendering engine).

## 7.2 QA Pipeline

| Check | Description | Tool |
|-------|------------|------|
| **HTML Validation** | W3C validation adapted for email (table layouts, inline styles, deprecated but necessary attributes) | Built-in validator |
| **CSS Support Matrix** | Every CSS property checked against Can I Email database for target client list | caniemail.com API |
| **Cross-Client Render** | Automated screenshot comparison across 20+ client/device combos | Litmus API / Email on Acid API |
| **Dark Mode Audit** | Verify colour tokens work in both light and dark contexts, check forced dark mode behaviour | AI Dark Mode Agent |
| **Accessibility Scan** | WCAG AA contrast, semantic structure, alt text, touch targets, lang attribute, role attributes | AI Accessibility Auditor |
| **Fallback Verification** | Strip all progressive enhancements, verify base email is complete and readable | Built-in stripper + render |
| **Link Validation** | Check all URLs resolve, UTM parameters are correct, unsubscribe links present | Built-in link checker |
| **File Size Check** | Ensure total HTML < 102KB (Gmail clipping threshold), images optimised | Built-in analyser |
| **Spam Score** | Content analysis for spam triggers, image-to-text ratio, authentication headers | SpamAssassin / Mail-Tester API |

## 7.3 Gate System

The QA pipeline operates as a gate: emails cannot be exported to a CMS until all mandatory checks pass. Optional checks can be overridden by senior team members with documented justification. Every override is logged for audit.

---

# 8. GDPR-First API Design & Security

## 8.1 Privacy by Design

The Hub processes email templates, components, and design assets — never subscriber data. This is a deliberate architectural decision:

- **Zero PII:** The Hub never stores, processes, or transmits personally identifiable information. Subscriber data lives in the CMS (Braze, SFMC, etc.) and never enters the Hub.
- **Template-only scope:** The Hub's connector pipeline pushes template code to the CMS. The CMS handles all personalisation token resolution at send time.
- **Rendering & Quality Analytics:** The Hub tracks email client support matrices, rendering quality scores, innovation compatibility data, and template performance benchmarks — never campaign engagement metrics (open rates, clicks), which remain in the CMS.

## 8.2 API Security Architecture

- **Authentication:** JWT with RS256 signing. Tokens include RBAC claims (admin, developer, designer, viewer). Brute-force protection with exponential backoff.
- **Token lifecycle:** Short-lived access tokens (15 min) + long-lived refresh tokens (7 days). Revocation list in Redis for immediate invalidation.
- **API key management:** External platform credentials (Braze API keys, SFMC OAuth tokens, Figma tokens) encrypted at rest using AES-256. Keys are never logged, never included in error responses, and scoped to minimum required permissions.
- **Rate limiting:** Per-user and per-endpoint rate limits via Redis. AI endpoints have separate, higher limits for streaming responses.
- **Audit logging:** Every API call logged with timestamp, user, endpoint, and action (but never request/response bodies containing credentials).
- **Network isolation:** Hub hosted on isolated internal infrastructure. No inbound connections from client systems — all integrations are outbound (Hub pushes to CMS, Hub pulls from Figma).

## 8.3 Data Classification

| Data Type | Classification | Handling |
|-----------|---------------|---------|
| Email HTML templates | Internal / Client-Confidential | Encrypted at rest, access-controlled per project |
| Design tokens | Internal | Stored in Hub DB, versioned |
| API credentials | Secret | AES-256 encrypted, never logged, scoped permissions |
| AI conversation logs | Internal | Retained 90 days for improvement, no PII |
| Rendering & quality analytics | Internal | Client support matrices, template quality scores, innovation compatibility data |
| Campaign engagement metrics | **PROHIBITED** | **Open rates, clicks, CTR stay in the CMS. Never enters the Hub.** |
| Subscriber/user data | **PROHIBITED** | **Never enters the Hub. Period.** |

---

# 9. Frontend Architecture & Hub UI

## 9.1 Technology Stack

The Hub frontend uses Next.js 16 + React 19 + Tailwind CSS + shadcn/ui. This provides:

- **App Router:** Next.js App Router with server components for fast initial loads, client components for interactive features.
- **shadcn/ui:** Accessible, customisable component primitives that avoid framework lock-in (they're your code, not a library dependency).
- **Real-time:** WebSocket integration for live AI responses, collaborative editing, and build status updates.
- **Monaco Editor:** Embedded VS Code editor for HTML/CSS/Liquid editing with email-specific syntax highlighting and autocompletion.

## 9.2 Key UI Screens

- **Dashboard:** Project overview, recent activity, team workload, QA status at a glance.
- **Project Workspace:** Split-pane layout: code editor (left), live preview (right), AI assistant (bottom panel). Toggle between source, compiled, and rendered views.
- **Component Library:** Browse, search, and test email components. Each component shows compatibility matrix, dark mode preview, and usage documentation.
- **AI Orchestrator:** Agent selection panel, natural language brief input, agent output review, merge controls. Visual workflow builder for chaining agents.
- **Design Sync:** Figma file browser, design token diff view, component mapping editor, one-click sync.
- **QA Dashboard:** Test results grid, cross-client screenshots, accessibility report, fallback comparison, approval workflow.
- **Export Console:** Platform selector, connector status, export preview, deployment history.

---

# 10. Email Development Resources & Community Intelligence

The Hub's knowledge base is continuously updated with insights from the email development community. These are the authoritative sources the system monitors:

## 10.1 Community & Forums

- **Email Geeks Slack:** email.geeks.chat — 16,000+ members. The primary real-time community for email developers, designers, and strategists. Channels for dev, design, deliverability, ESP-specific help.
- **#emailgeeks (X/Twitter):** Active hashtag for sharing techniques, rendering discoveries, and industry news.
- **Litmus Community:** community.litmus.com — Official forum for rendering questions, best practices, and Litmus-specific tooling.
- **Really Good Emails:** reallygoodemails.com — Curated gallery of email designs with source code inspection.
- **Email on Acid Blog:** emailonacid.com/blog — Technical deep-dives on rendering, frameworks, and email development.
- **Can I Email:** caniemail.com — The definitive CSS/HTML support reference for email clients (like caniuse.com for email).

## 10.2 Technical References

- **Maizzle Docs:** maizzle.com — Framework documentation, starter projects, premium templates.
- **MJML Docs:** mjml.io — Component reference, online editor, template gallery.
- **Parcel (email code editor):** parcel.io — Browser-based email code editor with live preview.
- **Cerberus:** tedgoas.github.io/Cerberus — Responsive email patterns and boilerplates.
- **Good Email Code:** goodemailcode.com — Mark Robbins' reference for accessible, standards-compliant email HTML.
- **FreshInbox:** freshinbox.com — Interactive and kinetic email techniques.

## 10.3 Industry Intelligence

- **Litmus State of Email:** Annual survey of email marketing trends, client market share, and technology adoption.
- **Email Client Market Share:** litmus.com/email-client-market-share — Live data on which clients are most used.
- **Google Postmaster Tools:** Deliverability and reputation monitoring for Gmail.
- **Apple MPP tracking:** Monitoring the impact of Mail Privacy Protection on open rate reliability.

---

# 11. Repository Structure

Based on a production-ready full-stack architecture, adapted for the Innovation Hub:

```
email-innovation-hub/
├── backend/                          # FastAPI application
│   ├── app/
│   │   ├── email_engine/             # Maizzle/MJML build pipeline
│   │   ├── ai_assistant/             # AI orchestrator + sub-agents
│   │   ├── design_sync/              # Figma API integration
│   │   ├── qa_engine/                # Cross-client testing + validation
│   │   ├── connector_pipeline/       # CMS export adapters
│   │   ├── component_library/        # Versioned email components
│   │   ├── projects/                 # Workspace management
│   │   ├── knowledge/                # RAG pipeline + pgvector
│   │   ├── auth/                     # JWT + RBAC
│   │   └── core/                     # Shared config, DB, middleware
│   ├── skills/                       # AI agent skill definitions
│   ├── connectors/                   # Platform-specific adapters
│   └── tests/
├── frontend/                         # Next.js application
│   ├── app/                          # App Router pages
│   ├── components/                   # React components + shadcn/ui
│   └── lib/                          # Utilities, API clients, hooks
├── email-templates/                  # Maizzle project (email source files)
│   ├── src/                          # Template source (HTML + Tailwind)
│   ├── components/                   # Reusable email partials
│   └── config.*.js                   # Maizzle env configs
├── infrastructure/                   # Docker, nginx, deployment
├── docs/                             # Architecture docs, ADRs
└── docker-compose.yml
```

---

# 12. Email Innovation Framework — How It All Fits Together

The Innovation Hub is not just a development tool — it is the engine that operationalises every email innovation initiative. This section maps the ten core email innovation areas to the Hub platform, shows end-to-end user flows, and demonstrates how an innovation moves from idea through prototyping to production deployment across any CMS.

## 12.1 Innovation-to-Hub Mapping

Each email innovation initiative has a natural home within the Hub's architecture. The table below maps every innovation to the Hub module that powers it, the AI agents that assist it, and the output it produces.

| Innovation Initiative | Priority | Hub Module | AI Agent(s) | Output |
|----------------------|----------|-----------|-------------|--------|
| **Dark Mode Design System** | P1 | Component Library + Email Engine | Dark Mode Agent | Colour token system, tested CSS patterns, light/dark style guide |
| **Modular Email Component Library** | P1 | Component Library | Scaffolder, Code Reviewer | 30+ reusable components with compatibility matrices |
| **AMP for Email Prototyping** | P1 | Email Engine + QA Engine | Scaffolder, Knowledge Agent | AMP prototypes with HTML fallbacks, feasibility report |
| **AI-Assisted Email Coding** | P1 | AI Assistant (all agents) | AI Orchestrator + 9 specialised sub-agents | AI workflows, prompt library, benchmarked time savings |
| **BIMI & Authentication Audit** | P2 | Knowledge Base + QA Engine | Knowledge Agent | Authentication audit report, BIMI implementation roadmap |
| **Accessibility Compliance** | P2 | QA Engine + Component Library | Accessibility Auditor | WCAG-compliant patterns, automated a11y test suite |
| **Interactive CSS Techniques** | P2 | Email Engine + QA Engine | Innovation Agent, Scaffolder, Dark Mode Agent | CSS interaction showcase, support matrix, fallback patterns |
| **Braze Liquid Advanced Patterns** | P2 | Connector Pipeline + Knowledge Base | Personalisation Agent | Liquid cookbook, Connected Content patterns, catalog templates |
| **Email Performance Benchmarking** | P3 | QA Engine | Code Reviewer | Benchmark framework, scoring dashboard, optimisation playbook |
| **Cross-Client Testing Automation** | P3 | QA Engine | Code Reviewer | Automated test suite, client coverage matrix, regression detection |

## 12.2 Master Innovation Flow

The following diagram shows the complete lifecycle of an email innovation — from initial concept through Hub development to production deployment across client platforms.

```mermaid
flowchart TB
    subgraph IDEATION["💡 IDEATION"]
        direction TB
        A1[Innovation Brief] --> A2[Select Innovation Track]
        A2 --> A3{Innovation Type?}
    end

    subgraph HUB["⚡ INNOVATION HUB"]
        direction TB
        B1[🎨 Design Sync<br/>Import from Figma /<br/>Design Tokens]
        B2[🤖 AI Orchestrator + 9 Agents<br/>Scaffolding / Review /<br/>Content / Innovation]
        B3[🔧 Email Engine<br/>Maizzle Build Pipeline /<br/>Dark Mode / AMP]
        B4[📦 Component Library<br/>Version / Test /<br/>Document]
        B5[✅ QA Engine<br/>Cross-Client Render /<br/>Accessibility / Fallback Gate]
    end

    subgraph PRODUCTION["🚀 PRODUCTION"]
        direction TB
        C1[Braze<br/>Content Blocks + Liquid]
        C2[Salesforce MC<br/>Content Builder + AMPscript]
        C3[Adobe Campaign<br/>Fragments + Delivery]
        C4[Taxi for Email<br/>Design System + Syntax]
        C5[Raw HTML<br/>CDN / GitHub / Download]
    end

    A3 -->|Component| B4
    A3 -->|Template| B1
    A3 -->|Technique| B3
    A3 -->|Pattern| B2

    B1 --> B2
    B2 --> B3
    B3 --> B4
    B4 --> B5

    subgraph MEASURE["📊 RENDERING & QUALITY INTELLIGENCE"]
        direction TB
        D1[Client Support Matrices<br/>Which clients support<br/>which innovations]
        D2[Rendering Quality Scores<br/>Per template, per client<br/>visual regression tracking]
        D3[Template Performance<br/>File size / code quality /<br/>accessibility scores]
        D4[Feed Back into Hub<br/>Knowledge Base +<br/>QA prioritisation]
    end

    B5 -->|Pass All Gates| C1
    B5 -->|Pass All Gates| C2
    B5 -->|Pass All Gates| C3
    B5 -->|Pass All Gates| C4
    B5 -->|Pass All Gates| C5

    B5 --> D1
    D1 --> D2
    D2 --> D3
    D3 --> D4
    D4 --> B4

    style IDEATION fill:#1a1a2e,stroke:#e94560,color:#fff
    style HUB fill:#0f3460,stroke:#e94560,color:#fff
    style PRODUCTION fill:#16213e,stroke:#e94560,color:#fff
    style MEASURE fill:#1a1a2e,stroke:#533483,color:#fff
```

## 12.3 User Journey: Developer Workflow

This is the step-by-step flow an email developer follows when working on any innovation within the Hub.

```mermaid
flowchart LR
    subgraph START["1️⃣ START"]
        S1[Open Hub Dashboard]
        S2[Select / Create Project]
    end

    subgraph BUILD["2️⃣ BUILD"]
        B1[Choose Starting Point]
        B2[Import from Figma]
        B3[Select from Component Library]
        B4[Start from AI Scaffold]
        B5[Blank Template]
    end

    subgraph DEVELOP["3️⃣ DEVELOP"]
        D1[Code in Monaco Editor]
        D2[Live Preview<br/>Desktop / Mobile / Dark Mode]
        D3[AI Agents<br/>Review / Fix / Optimise]
        D4[Hot Reload on Save]
    end

    subgraph TEST["4️⃣ TEST"]
        T1[Run QA Pipeline<br/>10-Point Check]
        T2[Cross-Client Renders<br/>20+ Clients]
        T3[Accessibility Audit<br/>WCAG AA]
        T4[Fallback Verification<br/>Outlook / Gmail / Apple]
    end

    subgraph SHIP["5️⃣ SHIP"]
        X1{All Gates Pass?}
        X2[Select Target CMS]
        X3[Export via Connector]
        X4[Deployment History Logged]
    end

    S1 --> S2
    S2 --> B1
    B1 --> B2
    B1 --> B3
    B1 --> B4
    B1 --> B5
    B2 --> D1
    B3 --> D1
    B4 --> D1
    B5 --> D1
    D1 <--> D2
    D1 <--> D3
    D1 --> D4
    D4 --> D2
    D1 --> T1
    T1 --> T2
    T2 --> T3
    T3 --> T4
    T4 --> X1
    X1 -->|Yes| X2
    X1 -->|No — Fix Issues| D1
    X2 --> X3
    X3 --> X4

    style START fill:#0d1b2a,stroke:#778da9,color:#fff
    style BUILD fill:#1b263b,stroke:#778da9,color:#fff
    style DEVELOP fill:#415a77,stroke:#e0e1dd,color:#fff
    style TEST fill:#1b263b,stroke:#778da9,color:#fff
    style SHIP fill:#0d1b2a,stroke:#778da9,color:#fff
```

## 12.4 Innovation Track Deep-Dives

Each of the ten innovation initiatives follows a specific flow through the Hub. Below are the four P1 (highest priority) innovation flows in detail, followed by summaries for P2 and P3 initiatives.

### 12.4.1 Dark Mode Design System Flow

The dark mode innovation creates a comprehensive, reusable design system — not just individual fixes.

```mermaid
flowchart TB
    subgraph AUDIT["PHASE 1: AUDIT"]
        A1[Import existing templates<br/>into Hub] --> A2[AI Dark Mode Agent<br/>scans for issues]
        A2 --> A3[Generate dark mode<br/>audit report]
        A3 --> A4[Categorise issues by<br/>client and severity]
    end

    subgraph DESIGN["PHASE 2: DESIGN SYSTEM"]
        B1[Define colour tokens<br/>light + dark pairs] --> B2[Create CSS custom<br/>property patterns]
        B2 --> B3[Build meta theme<br/>colour declarations]
        B3 --> B4[Document client-specific<br/>quirks database]
    end

    subgraph BUILD["PHASE 3: BUILD COMPONENTS"]
        C1[Create dark-mode-safe<br/>header component] --> C2[Create dark-mode-safe<br/>CTA component]
        C2 --> C3[Create dark-mode-safe<br/>image treatment component]
        C3 --> C4[Version and publish to<br/>Component Library]
    end

    subgraph TEST["PHASE 4: VALIDATE"]
        D1[QA Engine renders in<br/>light + dark across 20 clients] --> D2[AI Code Reviewer checks<br/>for forced colour overrides]
        D2 --> D3[Side-by-side dark / light<br/>comparison screenshots]
        D3 --> D4[Publish Dark Mode<br/>Style Guide to Knowledge Base]
    end

    AUDIT --> DESIGN
    DESIGN --> BUILD
    BUILD --> TEST

    style AUDIT fill:#1a1a2e,stroke:#e94560,color:#fff
    style DESIGN fill:#16213e,stroke:#0f3460,color:#fff
    style BUILD fill:#0f3460,stroke:#533483,color:#fff
    style TEST fill:#533483,stroke:#e94560,color:#fff
```

**Hub outputs:** Dark mode colour token system, tested CSS patterns for 6 major clients, reusable dark-mode-safe components, living style guide in Knowledge Base.

### 12.4.2 Modular Component Library Flow

The component library initiative turns individual template code into a scalable, cross-client-tested asset library.

```mermaid
flowchart TB
    subgraph INVENTORY["PHASE 1: INVENTORY"]
        A1[Collect all existing<br/>email patterns across clients] --> A2[AI Code Reviewer<br/>analyses and categorises]
        A2 --> A3[Identify reusable<br/>patterns vs one-offs]
        A3 --> A4[Define component<br/>architecture spec]
    end

    subgraph DEVELOP["PHASE 2: BUILD COMPONENTS"]
        B1[Build each component<br/>in Maizzle] --> B2[Add responsive<br/>breakpoints]
        B2 --> B3[Add dark mode<br/>variant]
        B3 --> B4[Add Outlook<br/>conditional fallback]
        B4 --> B5[Write documentation<br/>+ usage examples]
    end

    subgraph VALIDATE["PHASE 3: QA EACH COMPONENT"]
        C1[QA Engine: Render<br/>across 20+ clients] --> C2[Build compatibility<br/>matrix per component]
        C2 --> C3[Accessibility audit<br/>per component]
        C3 --> C4[Version tag + publish<br/>to Component Library]
    end

    subgraph INTEGRATE["PHASE 4: CMS INTEGRATION"]
        D1[Map components to<br/>Braze Content Blocks] --> D2[Map components to<br/>SFMC Content Builder]
        D2 --> D3[Map components to<br/>Taxi Email Design System]
        D3 --> D4[Generate CMS-specific<br/>export packages]
    end

    INVENTORY --> DEVELOP
    DEVELOP --> VALIDATE
    VALIDATE --> INTEGRATE

    style INVENTORY fill:#0d1b2a,stroke:#415a77,color:#fff
    style DEVELOP fill:#1b263b,stroke:#778da9,color:#fff
    style VALIDATE fill:#415a77,stroke:#e0e1dd,color:#fff
    style INTEGRATE fill:#1b263b,stroke:#778da9,color:#fff
```

**Hub outputs:** 30+ versioned components, per-component compatibility matrix, Braze/SFMC/Taxi export packages, searchable component browser UI.

### 12.4.3 AMP for Email Prototyping Flow

AMP prototyping uses the Hub to prove feasibility and quantify the cost/benefit of dual-format development.

```mermaid
flowchart TB
    subgraph SETUP["PHASE 1: ENVIRONMENT"]
        A1[Configure AMP build<br/>pipeline in Email Engine] --> A2[Register AMP sender<br/>with Gmail / Yahoo]
        A2 --> A3[Set up AMP<br/>testing environment]
    end

    subgraph PROTOTYPE["PHASE 2: BUILD 3 PROTOTYPES"]
        B1[📋 Prototype 1:<br/>In-Email Survey] --> B2[🎠 Prototype 2:<br/>Product Carousel]
        B2 --> B3[📂 Prototype 3:<br/>Accordion FAQ]
        B1 --> B4[Build HTML fallback<br/>for each prototype]
        B2 --> B4
        B3 --> B4
    end

    subgraph TEST["PHASE 3: DUAL-FORMAT QA"]
        C1[QA Engine: Render AMP<br/>in Gmail + Yahoo] --> C2[QA Engine: Render HTML<br/>fallback in all other clients]
        C2 --> C3[Fallback Gate:<br/>verify complete experience<br/>without AMP]
        C3 --> C4[Measure build time:<br/>AMP vs HTML-only]
    end

    subgraph REPORT["PHASE 4: FEASIBILITY REPORT"]
        D1[Document development<br/>overhead per prototype] --> D2[Project engagement<br/>uplift from industry data]
        D2 --> D3[Recommend use cases<br/>worth AMP investment]
        D3 --> D4[Publish prototypes +<br/>report to Knowledge Base]
    end

    SETUP --> PROTOTYPE
    PROTOTYPE --> TEST
    TEST --> REPORT

    style SETUP fill:#1a1a2e,stroke:#e94560,color:#fff
    style PROTOTYPE fill:#16213e,stroke:#0f3460,color:#fff
    style TEST fill:#0f3460,stroke:#533483,color:#fff
    style REPORT fill:#533483,stroke:#e94560,color:#fff
```

**Hub outputs:** 3 working AMP prototypes with HTML fallbacks, AMP/HTML build time comparison, feasibility report, go/no-go recommendation per use case.

### 12.4.4 AI-Assisted Email Coding Workflow Flow

This initiative evaluates and benchmarks AI tools, then embeds the best workflows into the Hub permanently.

```mermaid
flowchart TB
    subgraph EVALUATE["PHASE 1: TOOL EVALUATION"]
        A1[Trial AI scaffolding<br/>from design files] --> A2[Trial LLM-assisted<br/>email coding — Claude / Copilot]
        A2 --> A3[Trial Figma-to-HTML<br/>converters — Kombai / Emailify]
        A3 --> A4[Benchmark each tool<br/>against real templates]
    end

    subgraph BENCHMARK["PHASE 2: MEASURE IMPACT"]
        B1[Time: Manual build<br/>of 5 templates] --> B2[Time: AI-assisted build<br/>of same 5 templates]
        B2 --> B3[Quality: Compare output<br/>across 20 email clients]
        B3 --> B4[Calculate % time<br/>saved per template type]
    end

    subgraph INTEGRATE["PHASE 3: EMBED IN HUB"]
        C1[Configure winning AI<br/>tools as Hub agents] --> C2[Write optimised prompts<br/>for email-specific output]
        C2 --> C3[Build quality review<br/>checklist for AI output]
        C3 --> C4[Create AI Skills library<br/>in Hub knowledge base]
    end

    subgraph SHARE["PHASE 4: TEAM ENABLEMENT"]
        D1[Document best prompting<br/>strategies for email HTML] --> D2[Run team workshop<br/>on AI-assisted workflow]
        D2 --> D3[Publish prompt cookbook<br/>to Knowledge Base]
        D3 --> D4[Ongoing: Measure team<br/>velocity improvement]
    end

    EVALUATE --> BENCHMARK
    BENCHMARK --> INTEGRATE
    INTEGRATE --> SHARE

    style EVALUATE fill:#0d1b2a,stroke:#415a77,color:#fff
    style BENCHMARK fill:#1b263b,stroke:#778da9,color:#fff
    style INTEGRATE fill:#415a77,stroke:#e0e1dd,color:#fff
    style SHARE fill:#1b263b,stroke:#778da9,color:#fff
```

**Hub outputs:** AI tool comparison report, prompt cookbook, integrated AI agents with optimised skills, team-wide velocity benchmarks, ongoing measurement dashboard.

### 12.4.5 P2 Innovation Flows (Summary)

| Innovation | Hub Flow Summary |
|-----------|-----------------|
| **BIMI & Authentication Audit** | Knowledge Agent pulls current SPF/DKIM/DMARC configuration → QA Engine validates DNS records → Knowledge Base stores audit findings → Hub generates implementation roadmap document with SVG logo spec and VMC requirements. |
| **Accessibility Compliance (WCAG)** | Import templates → Accessibility Auditor AI agent runs automated scan → generates issue report with severity ratings → developer fixes in Monaco editor with real-time a11y feedback → QA Engine validates contrast ratios, semantic structure, screen reader compatibility → compliant patterns saved to Component Library. |
| **Interactive CSS Techniques** | Scaffolder AI generates CSS-only interactive patterns (hover effects, checkbox hacks, CSS animations) → Email Engine compiles with Maizzle → QA Engine tests across client matrix → builds support/degradation table per technique → best candidates flagged for production use → patterns + fallbacks published to Component Library. |
| **Braze Liquid Advanced Patterns** | Personalisation Agent generates Liquid code for catalog-based localisation, conditional logic, Connected Content calls → developer tests in Hub preview with mock data → Braze Connector validates syntax → patterns published as "Liquid Cookbook" in Knowledge Base → exportable directly as Braze Content Blocks. |

### 12.4.6 P3 Innovation Flows (Summary)

| Innovation | Hub Flow Summary |
|-----------|-----------------|
| **Email Performance Benchmarking** | QA Engine collects file size, load time, rendering speed, and image weight data per template → Code Reviewer AI analyses optimisation opportunities → benchmark scores displayed on Hub dashboard → historical tracking enables team to see improvement over time → optimisation playbook published to Knowledge Base. |
| **Cross-Client Testing Automation** | QA Engine integrates with Litmus/Email on Acid API → automated test runs triggered on every build → visual regression detection flags rendering changes → client coverage matrix shows which clients are tested for each project → results feed into the Gate System to block exports with rendering failures. |

## 12.5 End-to-End Innovation Lifecycle

The following diagram shows how a single innovation (using Dark Mode as an example) flows through every layer of the Hub from start to finish, ending in production deployment.

```mermaid
flowchart TB
    subgraph LAYER1["LAYER 1: INNOVATION BRIEF"]
        L1A[Developer identifies<br/>dark mode rendering<br/>issues across clients]
        L1B[Creates Innovation Brief<br/>in Hub project workspace]
    end

    subgraph LAYER2["LAYER 2: DESIGN"]
        L2A[Import existing brand<br/>colour tokens from Figma]
        L2B[Define light/dark<br/>colour pairs]
        L2C[AI Dark Mode Agent<br/>suggests optimal mappings]
    end

    subgraph LAYER3["LAYER 3: DEVELOPMENT"]
        L3A[Build in Monaco Editor<br/>with live dark mode preview]
        L3B[AI reviews code for<br/>client-specific pitfalls]
        L3C[Maizzle compiles with<br/>inline CSS + dark mode<br/>media queries]
    end

    subgraph LAYER4["LAYER 4: QA & VALIDATION"]
        L4A[QA Pipeline runs<br/>10-point check]
        L4B[Cross-client renders in<br/>light AND dark mode]
        L4C[Accessibility audit<br/>checks contrast in<br/>both modes]
        L4D[Fallback Gate verifies<br/>Outlook still renders<br/>correctly]
    end

    subgraph LAYER5["LAYER 5: PUBLISH TO LIBRARY"]
        L5A[Dark mode component<br/>versioned + tagged]
        L5B[Compatibility matrix<br/>generated from QA data]
        L5C[Usage documentation<br/>auto-generated]
        L5D[Added to searchable<br/>Component Library]
    end

    subgraph LAYER6["LAYER 6: DEPLOY TO CMS"]
        L6A["Connector exports to<br/>Braze (Content Block)"]
        L6B["Connector exports to<br/>SFMC (Content Builder)"]
        L6C["Connector exports to<br/>Taxi (Design System)"]
        L6D[Deployment logged<br/>with version + timestamp]
    end

    subgraph LAYER7["LAYER 7: KNOWLEDGE CAPTURE"]
        L7A[Dark mode style guide<br/>published to Knowledge Base]
        L7B[Client-specific quirks<br/>added to RAG index]
        L7C[AI agents learn from<br/>new patterns for<br/>future suggestions]
    end

    L1A --> L1B
    L1B --> L2A
    L2A --> L2B
    L2B --> L2C
    L2C --> L3A
    L3A --> L3B
    L3B --> L3C
    L3C --> L4A
    L4A --> L4B
    L4B --> L4C
    L4C --> L4D
    L4D --> L5A
    L5A --> L5B
    L5B --> L5C
    L5C --> L5D
    L5D --> L6A
    L5D --> L6B
    L5D --> L6C
    L6A --> L6D
    L6B --> L6D
    L6C --> L6D
    L6D --> L7A
    L7A --> L7B
    L7B --> L7C

    style LAYER1 fill:#0d1b2a,stroke:#778da9,color:#fff
    style LAYER2 fill:#1b263b,stroke:#778da9,color:#fff
    style LAYER3 fill:#415a77,stroke:#e0e1dd,color:#fff
    style LAYER4 fill:#1b263b,stroke:#778da9,color:#fff
    style LAYER5 fill:#0d1b2a,stroke:#778da9,color:#fff
    style LAYER6 fill:#1b263b,stroke:#778da9,color:#fff
    style LAYER7 fill:#415a77,stroke:#e0e1dd,color:#fff
```

## 12.6 The Compound Innovation Effect

The most important aspect of the Hub is that innovations are not isolated — they compound. Every component, pattern, and piece of knowledge created for one initiative feeds into the others.

```mermaid
flowchart LR
    DM[Dark Mode<br/>Design System] -->|colour tokens| CL[Component<br/>Library]
    CL -->|tested components| AMP[AMP<br/>Prototyping]
    AMP -->|fallback patterns| QA[Cross-Client<br/>Testing]
    QA -->|rendering data| PB[Performance<br/>Benchmarking]
    AI[AI-Assisted<br/>Coding] -->|scaffolds| CL
    AI -->|generates| DM
    AI -->|reviews| A11Y[Accessibility<br/>Compliance]
    AI -->|copy| CONT[Content<br/>Agent]
    AI -->|explores| INNO[Innovation<br/>Agent]
    CONT -->|subject lines| CL
    CONT -->|alt text| A11Y
    INNO -->|prototypes| CSS
    INNO -->|techniques| CL
    INNO -->|feasibility| QA
    A11Y -->|compliant patterns| CL
    CSS[Interactive<br/>CSS] -->|techniques| CL
    CSS -->|support matrix| QA
    BIMI[BIMI &<br/>Auth Audit] -->|trust signals| PB
    LIQ[Braze Liquid<br/>Patterns] -->|personalisation| CL
    CL -->|universal library| EXPORT[Export to<br/>Any CMS]

    style DM fill:#e94560,stroke:#1a1a2e,color:#fff
    style CL fill:#0f3460,stroke:#e94560,color:#fff
    style AMP fill:#533483,stroke:#e94560,color:#fff
    style QA fill:#16213e,stroke:#533483,color:#fff
    style PB fill:#1a1a2e,stroke:#533483,color:#fff
    style AI fill:#e94560,stroke:#1a1a2e,color:#fff
    style CONT fill:#e94560,stroke:#1a1a2e,color:#fff
    style INNO fill:#e94560,stroke:#1a1a2e,color:#fff
    style A11Y fill:#533483,stroke:#e94560,color:#fff
    style CSS fill:#16213e,stroke:#533483,color:#fff
    style BIMI fill:#1a1a2e,stroke:#533483,color:#fff
    style LIQ fill:#0f3460,stroke:#e94560,color:#fff
    style EXPORT fill:#e94560,stroke:#fff,color:#fff
```

This compound effect means:

- A dark mode colour token created in Week 2 is automatically used by every component built in Weeks 3–18.
- An Outlook fallback pattern discovered during AMP prototyping feeds back into the component library for all future templates.
- AI agents get smarter over time because every QA result, every client-specific quirk, and every successful pattern is indexed in the RAG knowledge base.
- A Braze Liquid pattern built for one client's Connected Content is immediately available (with appropriate anonymisation) as a template for every other client.
- Cross-client test results accumulated across hundreds of builds create an unmatched compatibility database that no individual developer could maintain alone.

This is the core value proposition: the Hub ensures that no innovation is ever a one-off. Every piece of work compounds into a growing competitive advantage.

---

# 13. Implementation Roadmap

| Phase | Timeline | Deliverables | Dependencies |
|-------|----------|-------------|-------------|
| **0: Foundation** | Weeks 1-2 | Set up internal infrastructure, Docker deployment, CI/CD pipeline, RBAC auth, base application scaffolding | Server provisioning, domain, SSL |
| **1: Email Engine** | Weeks 3-5 | Maizzle integration, build pipeline, live preview, component library v1 (15 core components), HTML validation | Phase 0 complete |
| **2: AI Layer** | Weeks 6-8 | AI orchestrator, Scaffolder + Outlook Fixer + Dark Mode agents, skills system, RAG knowledge base | Claude API access, Phase 1 |
| **3: Design Bridge** | Weeks 9-10 | Figma API integration, design token sync, plugin import pipeline (Emailify/Email Love output) | Figma API token, Phase 1 |
| **4: QA System** | Weeks 11-12 | Litmus/EoA API integration, cross-client test automation, fallback verification engine, gate system | Litmus/EoA license, Phase 1 |
| **5: Connectors** | Weeks 13-15 | Braze connector, SFMC connector, Taxi connector, raw HTML export, deployment history | Platform API credentials, Phase 1 |
| **6: Polish & Launch** | Weeks 16-18 | Full UI polish, documentation, team onboarding, performance optimisation, security audit | All phases, pen test |
| **5: Agent Evaluation** | Post-V1 | Synthetic test data, LLM judges, trace runner, error analysis, calibration, blueprint evals, regression suite | Phase 2 agents | **✅ DONE** — 36 live traces, 16.7% baseline, 4 judges, full pipeline |
| **6: OWASP Hardening** | Post-V1 | BOLA fixes, error sanitisation, rate limiting, business logic hardening, SDC improvements | Phase 2, security audit | **✅ DONE** — All 6.1-6.5 items complete |
| **7: Agent Capability** | Post-V1 | Structured handoff schemas, confidence scoring, component context, agent memory, eval-informed prompts | Phase 5 evals, Phase 6 | **✅ DONE** (7.1-7.5), 7.2 unblocked |
| **8: Knowledge Graph (Cognee)** | Post-Phase 7 | Cognee integration, knowledge graph seeding, graph context for agents, outcome logging, per-agent SKILL.md files, email ontology | Phase 7 infrastructure | **Ready to begin** — all prerequisites met |
| **9: Graph Intelligence** | Post-Phase 8 | Persona-graph profiles, Can I Email live sync, component-graph linking, failure propagation, project subgraphs, adaptive blueprints, competitive intelligence, SKILL.md A/B testing | Phase 8 operational | Not started |

Total estimated timeline: 18 weeks (4.5 months) to V1 with core functionality. **V1 has been delivered.** V2 features (Phases 4-7) are substantially complete. Active work: remaining 5 agents (eval-first + skills workflow), knowledge graph integration (Phase 8).

## 13.2 Adoption & Change Management

The Hub only delivers value if the team uses it. Adoption is planned alongside development, not as an afterthought.

| Phase | Activity | Who |
|-------|----------|-----|
| **During V1 Build** ✅ | Build team used the Hub daily, documenting patterns and workflows as they emerged. Documentation generated live — every AI agent conversation can produce docs via a `/document` slash command in the agent chat. | Build team (2–3 developers) |
| **Early Adopters** | Build team + 2–3 volunteer colleagues begin using the Hub on real client work during Sprint 2. These champions provide daily feedback and become trainers for the wider team. | Core team (4–6 people) |
| **Team Workshop** | Hands-on workshop to migrate current workflows into the Hub. Developers bring a real template they built recently and rebuild it using the Hub's tools, side by side. Concrete, not theoretical. | Full email dev team |
| **Ongoing Feedback** | Continuous feedback loop from the team: weekly 15-min retros during first month, Slack channel for issues, feature request board in the Hub itself. | All users |
| **Documentation** | Auto-generated as developers work — the Hub's AI agents document components, patterns, and decisions via slash commands. Living documentation, not static PDFs that go stale. | Automated + team |

## 13.3 Data Bootstrapping Plan

The Hub's component library and knowledge base are seeded with existing assets, not built from zero.

| Asset | Source | Import Method | Timeline |
|-------|--------|--------------|----------|
| **Core components (15–30)** | Existing manually-tested component library already maintained by the team | Import into Hub component library, add compatibility metadata, run through QA pipeline to generate automated test baselines | Phase 1 (Weeks 3–5) |
| **Knowledge base (email dev)** | Can I Email database, Email Geeks community patterns, internal documentation, client quirks accumulated by the team | Automated crawling of public sources (Can I Email, Good Email Code) + manual ingestion of proprietary internal knowledge | Phase 2 (Weeks 6–8) |
| **Existing templates** | Current "best of" template backlog from recent client engagements | Drag-and-drop import to Hub editor or file upload. AI agents analyse imported HTML and extract reusable patterns into the component library. | Ongoing from Phase 1 |
| **Client quirks database** | Tribal knowledge from senior developers — rendering fixes, Outlook workarounds, client-specific CSS hacks | Structured capture sessions during team workshop. AI Knowledge Agent indexes and makes searchable. | Phase 2 + Workshop |

---

# 14. Risk Assessment & Operational Readiness

## 14.1 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Key person dependency during V1 build** | Medium | High | **Mitigated.** V1 was developed collaboratively with knowledge distributed from day one. All code hosted on private GitHub with full documentation. AI-assisted coding tools reduce individual dependency — the architectural blueprint in this document means any competent developer can pick up any module. |
| **Timeline overrun (build takes longer than 5–7 weeks)** | Medium | Low | **Resolved.** V1 delivered on schedule. Each sprint delivered a usable increment — Sprint 1 produced a working editor and build pipeline, Sprint 2 added AI intelligence and export, Sprint 3 completed client handoff and polish. |
| **AI model quality / hallucination risk** | Medium | Medium | Mitigated by architecture: RAG knowledge base grounds AI responses in verified email development data, agent skill definitions constrain output format and scope, and agent command chaining ensures multi-step validation. Developers review all AI output before it enters the build pipeline — AI suggests, humans approve. |
| **Developer adoption resistance** | Low | Medium | The Hub enhances existing developer workflows rather than replacing them — it automates the repetitive work (CSS inlining, cross-client testing, Outlook fixes) that developers find tedious. Training was integrated into the V1 build process, and early adopters became internal champions. The broader industry trajectory is clear: AI-assisted development is the standard workflow for modern engineering teams, and the Hub positions the team's email developers at the forefront of that shift. |
| **Client data isolation failure** | Very Low | High | The Hub processes email templates and components — never subscriber data, never PII. Client isolation is enforced at the database layer (PostgreSQL row-level security by `client_id`) and at the application layer (RBAC). Even a complete application-layer bug cannot leak data across clients because the database enforces isolation independently. |
| **Cloud AI API cost overrun** | Low | Low | Local LLMs handle 70–90% of requests at zero API cost. Cloud usage is monitored and capped. The AI Orchestrator routes by task complexity — only tasks requiring frontier reasoning reach the cloud API. Monthly spend is visible in the rendering intelligence dashboard. See Section 15.5 for detailed cost projections. |
| **Infrastructure availability** | Very Low | Medium | The organisation operates enterprise-grade infrastructure. The Hub runs on Docker Compose with versioned deployments and automated database backups. Recovery from a full system failure is a container restart — measured in minutes, not hours. |

## 14.2 Success Metrics

The following metrics will be tracked from launch to measure the Hub's impact and guide post-V1 investment decisions.

| Metric | Baseline (Current) | Target (3 Months Post-Launch) | Target (6 Months) | How Measured |
|--------|-------------------|-------------------------------|-------------------|--------------|
| **Campaign build time** | 3–5 days per template | 1–2 days | Under 1 day for component-based builds | Time from project creation to export-ready, tracked by Hub |
| **Cross-client rendering defects** | Discovered in client review or post-send | Caught before export by QA gate | Near-zero defects reaching client review | QA gate pass/fail rate per template |
| **Component reuse rate** | 0% (no shared library) | 30–40% of template elements from library | 60%+ | Component usage tracking in Hub |
| **AI agent adoption** | N/A | Team actively using Scaffolder + Dark Mode + Content agents | Agents embedded in daily workflow, new agents requested | Agent usage logs |
| **Knowledge base growth** | Tribal knowledge only | 200+ indexed entries (Can I Email + team quirks) | 500+ entries, team contributing regularly | Knowledge base entry count and query frequency |
| **Cloud AI API spend** | N/A | Under £600/month | Under £600/month (stable as local routing improves) | Monthly API billing |

## 14.3 Governance & Ownership

| Area | Responsibility | Notes |
|------|---------------|-------|
| **Product ownership** | Email development leadership | Feature prioritisation, roadmap decisions, budget approval |
| **Technical ownership** | Development team | Code quality, architecture decisions, security, deployments |
| **Post-V1 maintenance** | The development team | Bug fixes, infrastructure, iterative improvements — part of ongoing operations |
| **Post-V1 feature development** | The development team | New connectors, additional agents, and V2 features built incrementally |
| **Infrastructure & budget** | The organisation | Server provisioning, GPU allocation, cloud AI API budget |
| **Support model** | Versioned deployments with automated rollback | System deployed via Docker Compose with tagged versions. If an issue occurs, rollback to the previous stable version is a single command. Database backups run on schedule. |

## 14.4 Monitoring & Operational Resilience

The Hub will include production-grade monitoring aligned with existing operational standards:

- **Error tracking:** Integrated error tracking (Sentry or equivalent from existing company tooling) for real-time visibility into application failures
- **Performance monitoring:** Build times, API latency, and AI agent response times tracked and surfaced in the rendering intelligence dashboard
- **Alerting:** SLO-based alerting on user-facing symptoms — build failures, API errors, connector timeouts. Alert on leading indicators (resource saturation, dependency health) to catch issues before they affect users
- **Graceful degradation:** Circuit breakers on external dependencies (Braze API, Litmus, cloud AI). If a cloud AI model is unavailable, the Orchestrator routes to local LLMs. If Litmus is down, built-in Playwright testing continues
- **Log aggregation:** Structured logging across all services, feeding into the RAG knowledge base — the system learns from its own error patterns over time
- **Backup & recovery:** Automated PostgreSQL backups on schedule, Docker volume snapshots, version-tagged deployments. Full system recovery is a container redeploy from the latest stable image

## 14.5 Change Management & Rollout

| Phase | Activity | Detail |
|-------|---------|--------|
| **During V1 build** ✅ | Training built alongside product | Documentation auto-generated as features were developed. Build team members became the first trainers. |
| **V1 complete** ✅ | Controlled pilot | Build team + 2–3 volunteers use Hub on real client work. Parallel workflow — existing tools remain available. Nothing is removed or replaced. |
| **Weeks 2–4 post-launch** | Team onboarding | Structured training sessions (estimated 2–3 hours per developer). Hub used alongside existing workflow during transition. |
| **Month 2+** | Full adoption | Team migrates primary workflow to Hub. Existing tools remain as fallback — no data is deleted, no processes are removed. Transition timeline depends on team comfort and workflow complexity. |
| **Rollback plan** | Zero-risk transition | The Hub is additive. If it doesn't work for a particular use case, the team reverts to their existing workflow immediately. No migration is irreversible. |

## 14.6 Decisions for Senior Leadership

The following questions benefit from senior director-level input before or during implementation:

1. **Hosting environment:** Which server environment will host the Hub — on-prem or company-managed cloud?
2. **AI provider approval:** Which LLM providers are approved for use? Is there a data processing agreement for sending non-PII email HTML to external AI APIs?
3. **Initial client targets:** Which clients should be the first to benefit from Hub-built campaigns? This determines which CMS connectors to prioritise after Braze.
4. **Build team allocation:** The recommended approach is a collaborative team of 2–3 developers. Which team members should be allocated, and can they be dedicated full-time for the build period?

---

# 15. Business Case

## 15.1 The Problem We're Solving

An Outlook rendering fix discovered on Client A's campaign is invisible to the team working on Client B. A dark mode solution built in January is rebuilt from memory in June. We have no system for compounding the work we've already done.

This is not an innovation problem. It is an operational pattern inherent to how agencies work — knowledge fragments across client engagements, and the more clients the agency serves, the more duplication occurs. The tools available on the market are built for individual brands managing their own email programmes, not for agencies that need to compound expertise across dozens of client ecosystems simultaneously.

## 15.2 What the Hub Changes

The Innovation Hub converts every piece of email development work into a reusable, testable, deployable asset. Build it once, use it everywhere, improve it continuously.

| Without Hub | With Hub |
|------------|----------|
| Templates assembled manually from modular blocks per campaign | Templates assembled from pre-tested, versioned components with automated pipeline |
| Dark mode fixes applied per template, per client | Dark mode solved at the design system level — near-zero marginal cost |
| Cross-client QA is manual: 2-3 hours per template | Automated rendering across 20+ clients in minutes |
| AI tools used ad hoc with no quality control | AI agents embedded in workflow with enforced review gates |
| Patterns and fixes live in developers' heads | Knowledge captured in searchable, RAG-indexed system |
| Export to each CMS requires manual reformatting | One-click export to Braze, SFMC, Adobe Campaign, Taxi |
| New developer onboarding: weeks of tribal knowledge transfer | New developer productive in days — documented components, patterns, guides |

## 15.3 Client Value Proposition

The Hub doesn't just make the agency faster — it makes clients more successful. Every capability in the Hub translates directly into measurable client outcomes.

### What Clients Actually Get

| # | Client Benefit | Without the Hub | With the Hub | Measurable Outcome |
|---|---------------|----------------|-------------|-------------------|
| 1 | **Faster Campaign Turnaround** | Templates assembled manually from modular blocks per campaign. Manual CSS inlining. Manual QA across devices. Copy-paste into CMS. Typical timeline: 3–5 days per campaign. | AI scaffolds first draft in minutes. Components pre-tested. Automated QA in minutes. One-click CMS export. | **Campaign delivery reduced from 3–5 days to 1–2 days.** Clients can react to market moments, run more A/B variants, and launch seasonal campaigns faster than competitors. |
| 2 | **Pixel-Perfect Rendering Across Every Client** | Developer checks 3–4 email clients manually. Outlook issues found after client sees them. Dark mode tested inconsistently. | 10-point QA gate catches every rendering issue before export. CSS support matrix checked against target audience's email clients. Dark mode automated. | **Near-zero rendering defects reaching client inboxes.** Clients stop seeing broken emails in Outlook or dark mode. Fewer revision rounds. Approval cycles shortened. |
| 3 | **Innovation That's Proven, Not Promised** | Innovation pitched via slides. Client asks "will this actually work in our audience's email clients?" and the answer is "probably." | Hub produces rendering intelligence reports: tested compatibility data showing exactly which innovations work in which email clients for the client's specific audience. | **Clients see evidence before committing.** "AMP carousels work in 68% of your audience's email clients, with a static fallback for the rest" — backed by tested data, not opinions. This sells innovation. |
| 4 | **Interactive & Advanced Email Capabilities** | AMP, kinetic CSS, gamification are theoretical. No safe way to prototype, test, or deploy them. | Hub provides AMP prototyping with automatic fallbacks, kinetic CSS with client support matrices, gamification elements — all gate-tested before deployment. | **2–5× engagement uplift from interactive elements** (industry benchmarks). Dark mode optimisation alone prevents the ~35% of email opens that currently render with broken colours. |
| 5 | **Faster Client Review & Approval** | Approval via screenshot email chains. Client receives static images, gives ambiguous feedback. Multiple revision rounds over days. | Client review portal: live preview URLs, section-level feedback, annotation tools, clear audit trail. Multiple stakeholders review simultaneously. | **Approval cycle reduced from days to hours.** Client sees the actual email, not a screenshot. Feedback is specific and actionable. Sign-off is documented. |
| 6 | **Consistent Brand Experience** | Brand guidelines applied manually. Colours, fonts, spacing drift across campaigns. Dark mode breaks brand colours. | Component library enforces brand standards. Design tokens from Figma sync automatically. Brand compliance checked by QA gate. Dark mode variants maintain brand integrity. | **Every email is on-brand, every time.** No more "why does this CTA look different from last month's campaign?" Client trust in quality increases. |
| 7 | **More Campaigns for the Same Budget** | Each template is bespoke. Developer time is the bottleneck. Retainer hours consumed by repetitive builds. | Components reused across campaigns. AI handles first drafts. Automated QA replaces manual testing hours. | **Clients get 2–3× more campaigns within the same retainer.** Or the same number of campaigns at higher quality with faster turnaround. Either way, better value for money. |
| 8 | **Multi-Market Consistency** | Separate templates per locale. Inconsistent cross-market experience. Translation coordination manual. | Single template with locale variants via localisation engine. AI-powered translation preserving brand voice. Shared components across markets. | **One source of truth across all markets.** Campaign launched in 20+ locales from a single build, not 20 separate builds. |
| 9 | **Future-Proofed Email Programme** | Tied to one CMS. Migration would mean rebuilding everything. Innovation dependent on individual developer knowledge. | CMS-agnostic architecture. Knowledge base compounds. Innovation R&D pipeline continuously tests new techniques. | **Client's email programme improves over time without extra cost.** Every campaign adds to the component library and knowledge base. Switching CMS doesn't mean starting over. |

### Real-World Client Scenarios

#### Scenario 1: Retail Client — Peak Season Under Pressure

A fashion retail client needs 30 email campaign variants for Black Friday across 5 markets in 2 weeks. Currently, this requires the full email team working overtime with manual QA and late-night Outlook fixes.

**With the Hub:**
- AI Scaffolder generates base templates from campaign briefs in minutes
- Component library provides pre-tested hero blocks, product grids, CTAs, and countdown timers — all with dark mode and Outlook fallbacks already built in
- Content Agent generates localised subject lines and CTA copy per market with brand voice constraints
- QA gate validates all 30 variants automatically — CSS support, file size, spam score, accessibility, dark mode
- Test persona engine previews each variant as different subscriber segments (mobile/desktop, dark mode, loyalty tier)
- Braze connector pushes directly — no manual Content Block creation
- Client review portal lets the brand team approve all variants simultaneously

**Result:** 30 variants delivered in 3 days instead of 14. Client runs twice as many A/B tests. Higher-performing creative wins. Revenue impact measurable.

#### Scenario 2: Financial Services Client — Compliance and Accessibility

A banking client requires WCAG AA accessibility in every email, strict brand governance across product lines (mortgages, current accounts, investments), and an audit trail for regulatory compliance.

**With the Hub:**
- Accessibility Agent audits every email for contrast ratios, semantic structure, alt text, touch targets, screen reader compatibility
- AI Alt Text generation describes every image contextually
- Brand compliance gate enforces colour palette, typography, logo placement, and disclaimer positioning per product line
- QA gate prevents any email from exporting without passing all accessibility and compliance checks
- Client review portal provides time-stamped approval records for audit purposes
- Knowledge base stores all compliance requirements and flags any deviation

**Result:** Zero accessibility failures reaching inboxes. Audit trail satisfies regulatory review. Client reduces compliance risk and avoids potential fines or brand damage. Approval process has documented sign-off.

#### Scenario 3: Tech Client — Wants to Stand Out in the Inbox

A SaaS client wants to differentiate through innovative email experiences — interactive product tours, in-email booking, CSS animations — but is nervous about rendering issues and doesn't want to alienate subscribers on older email clients.

**With the Hub:**
- Hub's innovation R&D pipeline prototypes AMP carousels, in-email forms, and kinetic CSS techniques
- Rendering intelligence report shows exactly which innovations work for the client's audience: "72% of your subscribers use email clients that support CSS animations. 34% support AMP. 100% will see the static fallback."
- Test persona engine demonstrates the experience across subscriber segments — iPhone dark mode, Gmail web, Outlook desktop
- QA gate enforces fallback-first: every interactive element has a verified static alternative
- Client sees a live demo in the review portal, not a slide deck

**Result:** Client approves interactive campaign with confidence. Engagement rates increase. Client presents the rendering intelligence report to their own leadership as evidence of innovation. The agency positioned as strategic innovation partner, not just an email vendor.

#### Scenario 4: Multi-Market FMCG Client — Global Consistency at Scale

A consumer goods client runs email campaigns across 25 markets with local marketing teams providing content in different languages. Currently, each market's emails look subtly different and quality varies.

**With the Hub:**
- Single component library used across all 25 markets — brand consistency enforced
- Localisation engine translates content while preserving brand voice and formatting
- Local marketing teams submit content via review portal — Hub developers assemble using shared components
- QA gate runs on every variant, ensuring the same quality bar in São Paulo and Stockholm
- Rendering intelligence dashboard shows support matrices per market (different audiences use different email clients)

**Result:** Consistent brand experience globally. Local teams get faster turnaround. Quality doesn't vary by market. Client's global marketing director sees one dashboard showing quality scores across all 25 markets.

### How the Hub Changes the Client Relationship

The Hub shifts the agency's positioning from **email production vendor** to **email innovation partner**.

| Before the Hub | After the Hub |
|---------------|--------------|
| Client asks "can you build this email?" | Client asks "what should we build next?" |
| The agency delivers templates | The agency delivers capability reports, rendering intelligence, and innovation roadmaps |
| Relationship measured by volume (emails produced) | Relationship measured by outcomes (engagement uplift, innovation adoption, campaign velocity) |
| Client could replace the agency with any capable competitor | Client benefits from the agency's compound knowledge, component library, and AI skills — accumulated across hundreds of engagements, not just their own |
| Innovation is a risk ("will it work?") | Innovation is data-backed ("here's exactly where it works and where the fallback covers") |
| Budget conversation: "how many emails can we get?" | Value conversation: "how much more engagement can we drive?" |

## 15.4 Competitive Landscape

The email creation tool market includes several established platforms, most of which have added AI features in 2024–2025. These tools are primarily designed for in-house brand teams managing a single email programme on a single CMS. The Hub operates in a different context — a multi-client agency that needs to compound knowledge across engagements and deploy to any platform. Its value lies not in matching these tools feature-for-feature but in combining capabilities that none of them integrate into a single developer-first platform built for the agency workflow.

| Competitor | What They Do | What They Do Well | What They Don't Do |
|-----------|-------------|-------------------|-------------------|
| **Stensul** | Enterprise email creation platform. Drag-and-drop editor, brand governance, approval workflows. AI email generator (brief-to-email), content refinement tools, subject line/CTA generators. Figma plugin (2025). Integrates with SFMC, Pardot, Eloqua, Adobe Campaign, Braze, Iterable. | Strong governance, enterprise SSO, broad CMS integrations (7+), AI content generation, Figma plugin for brand compliance | Primarily visual builder — no code-first developer workflow or Maizzle-level build pipeline. AI focuses on content generation (copy, subject lines) rather than specialised email development tasks (dark mode fixes, Outlook rendering). Per-seat SaaS pricing model. |
| **Dyspatch** | Email production platform. Modular builder, AMP for Email support, 300+ locale localisation. Scribe AI converts Figma files, HTML, or images into reusable modular components and generates campaigns from briefs. Integrates with SendGrid, Mailgun, Mailjet. | AMP support, strong module system, AI-powered component extraction from existing assets, 300+ locale translations | AI focuses on design-to-component conversion rather than specialised email development assistance. Smaller CMS/ESP connector range (3 integrations vs. Stensul's 7+). SaaS-hosted model. |
| **Knak** | No-code email builder for enterprise marketers. SFMC and Marketo native integration. AI-powered translations and brand voice features. | Marketer-focused simplicity, strong SFMC/Marketo integration, fast production for non-technical users | Explicitly no-code — designed for marketers, not developers. AI focused on translations and brand voice rather than email development tasks. |
| **Stripo** | Email template builder with drag-and-drop and HTML editor. Extensive AI: AI Hub for full email generation, text refinement, image generation (DALL-E, Gemini, GPT-Image-1), AI alt text. Cross-client testing across 98 clients via Email on Acid integration. Freemium model. | Broad AI content and image generation, large template library, 98-client rendering tests, HTML editing alongside drag-and-drop, email design system features | AI is broad content generation rather than specialised email development agents. Cross-client testing is screenshot-based (Email on Acid pass-through) — useful but different from structured rendering intelligence with support matrices. Components not cascading/versioned with cross-project inheritance. |
| **Parcel** | Browser-based email code editor (acquired by Customer.io). Live preview, collaboration, component system. AI for email generation and localisation (160+ languages). Code tools: CSS inlining, code shrinking, unused code removal. Tests in 80+ real inbox previews. Integrates with many ESPs (bidirectional import/export). | Excellent code editor, strong collaboration, good testing coverage, component system, AI email generation, broad ESP integrations | Code tools are post-processing (inlining, minifying) rather than a compile-time build pipeline with Tailwind. Components exist but lack cascading inheritance across clients/projects. SaaS-hosted model. |

### Where the Hub Is Genuinely Different

Every competitor listed above now offers some form of AI content generation — this is table stakes in 2025. The Hub's differentiation is not "we have AI and they don't" but rather the specific combination of capabilities below, which no single competitor provides:

- **Specialised AI agents, not generic AI** — The Hub's AI agents are purpose-built for email development tasks: the Scaffolder understands Maizzle templates and email client constraints, the Dark Mode Agent applies tested CSS patterns per client, the Outlook Fixer knows the specific rendering quirks of Word-engine Outlook. This is different from generic "generate copy from a prompt" AI that every competitor now offers.
- **Code-first with Maizzle** — Full HTML control with a compile-on-save build pipeline, Tailwind CSS inlining, responsive transforms, and unused class purging. Developers can solve rendering edge cases that visual builders fundamentally cannot handle. Maizzle delivers a developer-grade build system purpose-built for email.
- **Compound knowledge system (RAG)** — Every rendering fix, client quirk, and development pattern is captured in a RAG-indexed knowledge base that feeds into AI agents. The knowledge compounds over time — six months of fixes to the same component make the AI smarter about that component. This compounding effect is a structural advantage of the Hub's architecture.
- **Rendering intelligence as a deliverable** — Not just "test your email in 80 clients" (Stripo and Parcel offer that) but structured client support matrices showing which email innovations (AMP, interactive CSS, dark mode techniques, kinetic elements) work in which email clients, presented as capability reports for client stakeholders. The data answers "what can we do?" not just "does this email render?"
- **100% self-hosted, open-source stack** — No per-seat SaaS pricing. No vendor lock-in. The entire platform runs on self-hosted infrastructure with zero software licence costs. The knowledge base, component library, and AI skills are fully owned IP that appreciates over time.
- **Local-first AI with hybrid routing** — 70–90% of AI tasks handled by local LLMs at zero API cost, with frontier cloud models reserved for complex reasoning. Local-first processing keeps costs predictable and data on internal infrastructure.
- **Innovation R&D platform** — The Hub is not just a production tool. It is the engine for prototyping, benchmarking, and proving email innovations (AMP, interactive CSS, kinetic techniques) before pitching them to clients — with rendering intelligence data to back up every capability claim.

The distinction is straightforward: existing tools help in-house teams produce emails faster on their chosen platform. The Hub is built for an agency that works across platforms — it allows the agency to develop, test, and prove email innovations once and deploy them to any client's CMS from a single codebase that the organisation owns entirely. That cross-client compound effect is something a single-brand tool simply isn't designed to provide.

### Competitive Feature Adoption Plan

Every valuable capability competitors offer either already exists in the Hub plan or can be added with minimal effort. The table below maps each competitor feature to its Hub equivalent, showing where it's covered and what needs to be built.

#### Already Covered in the Hub Plan

| Competitor Feature | Who Has It | Hub Equivalent | Where in Plan | When |
|---|---|---|---|---|
| AI brief-to-email generation | Stensul, Dyspatch | **Scaffolder Agent** — generates complete Maizzle templates from natural language campaign briefs | Section 5.1 (AI Agents) | V1 Sprint 2 |
| Drag-and-drop email builder | Stensul, Knak, Stripo | **Monaco Editor + Component Library** — code-first approach with pre-built, tested components that developers drag into templates | Sections 9.2, V1 #2 + #4 | V1 Sprint 1–2 |
| Cross-client rendering tests | Stripo (98 clients), Parcel (80+) | **QA Pipeline** — Playwright-based screenshot testing for core clients (Apple Mail, Gmail, Outlook), Litmus/EoA API for full sweeps | Section 7.2, V1 #7 | V1 (core) ✅, V2 (expanded) |
| Component/module system | Dyspatch, Parcel | **Component Library v1** — 5–10 cascading components with Global → Client → Project inheritance, versioning, dark mode variants | Section 5.1, V1 #4 | V1 Sprint 2 |
| CMS/ESP integrations | Stensul (7+), Parcel (many), Dyspatch (3) | **CMS Connector Pipeline** — Braze (V1), then SFMC, Adobe Campaign, Taxi for Email. Architecture supports ~2–3 days per connector. | Section 3, V1 #6 | V1 (Braze) ✅, V2 (others) |
| Figma integration | Stensul (plugin), Dyspatch (Scribe AI) | **Design Sync** — Figma API integration with design token sync, component mapping | Section 4 | V2 Phase 1 |
| Brand governance / compliance | Stensul (Governed Creation) | **QA Gate point 10: Brand Compliance** — colour, font, spacing, logo rules enforced before export. Per-client brand profiles in V2. | Section 7.2, V1 #7 | V1 (basic) ✅, V2 (per-client) |
| Localisation / translation | Dyspatch (300+ locales), Parcel (160+) | **Localisation Engine** — AI-powered translation using local LLMs (zero API cost), preserving brand voice across locales | Section 12, V2 | V2 Phase 2 |
| Real-time collaboration | Parcel | **Collaborative Editing** — CRDT/OT-based multi-user editing | Section 12, V2 | V2 Phase 2 |
| Template import & extraction | Dyspatch (Scribe AI) | **Data Bootstrapping: Template Import** — drag-and-drop import of existing HTML, AI agents analyse and extract reusable patterns into component library | Section 13.3 | V1 Sprint 3 |

#### New Capabilities to Add

The following three capabilities are offered by competitors but not yet explicitly covered in the Hub plan. Each builds on existing Hub infrastructure with minimal additional effort.

| # | New Capability | Competitor Reference | How the Hub Builds It | Effort | When |
|---|---|---|---|---|---|
| 1 | **Content Agent** — AI-generated subject lines, preheaders, CTA copy, body copy refinement (rewrite, shorten, expand, change tone) | Stensul (content refinement, subject line/CTA generators), Stripo (AI text refinement), Dyspatch (campaign copy from brief) | Add as 8th AI agent using same LLM infrastructure. System prompt specialised for email marketing copy with brand voice constraints. Integrates into the editor as inline suggestions — select text, right-click, "Refine with AI." Local LLMs handle 70–90% of requests (basic rewrites, grammar fixes). Cloud models for creative generation. | Low — 2–3 days. System prompt + UI integration into Monaco editor context menu. | V1 Sprint 2 (alongside Scaffolder) |
| 2 | **AI Image Generation** — generate placeholder heroes, product imagery, background graphics directly in the editor | Stripo (DALL-E, Gemini, GPT-Image-1 built into editor) | Self-hosted Stable Diffusion XL via ComfyUI on existing GPU infrastructure — zero API cost, fits local-first strategy. "Generate image" button in the editor's asset panel. Useful for prototyping and mockups during client pitches. Cloud APIs (DALL-E, Midjourney) available as optional upgrade for production-quality assets. | Medium — 3–5 days. ComfyUI deployment + API wrapper + editor integration. | V2 Phase 1 |
| 3 | **AI Alt Text Generation** — automatically generate descriptive alt text for all images in a template | Stensul, Stripo (AI-generated alt text) | Extend the Accessibility Agent to analyse images via vision model (local or cloud) and generate contextual alt text. Runs as part of the Accessibility Audit in the QA pipeline. Developers review and approve suggestions. | Low — 1–2 days. Vision model API call + UI for review/approval. | V1 Sprint 2 (extend Accessibility Agent) |

#### What This Means

After implementing the three new capabilities above, every feature that competitors offer individually is available in the Hub — plus the differentiators that come from building for the agency model rather than for a single brand: cross-client knowledge compounding, multi-CMS deployment, cascading component inheritance, and a self-hosted stack where the organisation owns the IP. These aren't bolt-on features — they're structural advantages of a platform designed around how agencies actually work.

## 15.5 Cost Optimisation Strategy

The Hub is designed to minimise operational costs at every layer. Where external services can be replaced by building tools in-house without significant effort, the Hub builds internally.

### Zero-Licence Stack

| Component | SaaS Alternative (Annual Cost) | Hub Approach (Cost) |
|-----------|-------------------------------|-------------------|
| Email editor | Stensul / Knak ($30K–100K+/yr) | Monaco editor — open-source, self-hosted (**£0**) |
| Component library | Dyspatch ($20K–50K/yr) | Built in-house with PostgreSQL versioning (**£0**) |
| AI coding assistant | GitHub Copilot ($19/user/mo) | Self-hosted local LLMs + cloud API for complex tasks (**GPU cost only**) |
| Vector search (RAG) | Pinecone ($70+/mo) | pgvector extension in existing PostgreSQL (**£0**) |
| Auth / RBAC | Auth0 ($240+/mo) | Built in-house with JWT + Redis (**£0**) |
| Design tokens | Specify / Tokens Studio ($200+/mo) | Figma API direct integration (**£0**) |

### Build vs. Buy — Internal Tool Alternatives

Where an external API is not difficult to replicate for the Hub's specific needs, the Hub builds internally to avoid recurring costs:

| External Service | Annual Cost | Build-Internally Alternative | Effort |
|-----------------|-------------|------------------------------|--------|
| **Litmus / Email on Acid** | £5K–15K/yr | Built-in HTML validator + CSS support checker (Can I Email database is open-source). Playwright-based screenshot testing against local email client renderers for core clients (Apple Mail, Gmail web, Outlook). Use Litmus API only for edge cases or full 20+ client sweeps. | Medium — 2–3 weeks |
| **SpamAssassin API** | £1K–3K/yr | SpamAssassin is open-source — deploy locally as part of the Docker stack. Run spam scoring directly on internal infrastructure. | Low — 2–3 days |
| **Link checker** | SaaS link checkers $50+/mo | Built-in HTTP HEAD request validator with async batch checking. | Low — 1 day |
| **Image optimisation** | Cloudinary / imgix ($99+/mo) | Sharp (Node.js, open-source) for image compression, WebP conversion, and CDN-ready asset pipeline. | Low — 1–2 days |
| **File size analyser** | N/A | Built-in — trivial to implement. Gmail clipping threshold (102KB) check is a few lines of code. | Trivial |

### AI Cost Reduction — Real API Pricing

The local-first AI model strategy is the single biggest cost lever. Based on current Claude API pricing (March 2026):

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Hub Role |
|-------|----------------------|----------------------|----------|
| Claude Sonnet 4.6 | $3 | $15 | Primary workhorse — dark mode, accessibility, code review, content generation |
| Claude Haiku 4.5 | $1 | $5 | Knowledge lookups, validation checks, template classification |
| Claude Opus 4.6 | $15 | $75 | Complex scaffolding, architecture decisions (used sparingly) |

**Subscription alternative:** Anthropic offers monthly subscription tiers — $20 (Pro), $100 (Max 5×), and $200 (Max 20×) — which may be more cost-effective for individual developer seats than API pricing depending on usage patterns.

**Note:** All cost estimates are based on publicly available pricing as of March 2026. If pricing differs from published rates, figures should be amended accordingly.

**Typical Hub usage pattern (per day, cloud-routed tasks only — 30% of total):**
- ~100 Sonnet requests (avg 2K input + 1K output tokens each): ~$0.90 + $1.50 = ~$2.40/day
- ~40 Haiku requests (avg 1K input + 500 output tokens each): ~$0.04 + $0.10 = ~$0.14/day
- ~10 Opus requests (avg 3K input + 2K output tokens each): ~$0.45 + $1.50 = ~$1.95/day
- **Daily cloud AI cost: ~$4.50 → ~£110/month**

With prompt caching (90% discount on cached prompts) and batch API (50% discount for non-urgent tasks), realistic monthly spend is **£60–150/month** for cloud AI.

- **Without local models:** If all AI tasks used cloud APIs (~500+ requests/day), estimated monthly cost: £400–1,000/mo.
- **With local models (70–90% routing):** Local handles routine tasks at zero marginal cost. Cloud usage drops to ~50–150 requests/day. Estimated monthly cost: **£60–150/mo.**
- **Estimated annual AI savings:** £4,000–10,000/yr by running local models for the majority of tasks.

### Total Cost of Ownership

The table below covers **ongoing operational costs only** — the recurring expense of running the Hub after the initial build.

| Cost Category | Monthly | Annual | Notes |
|--------------|---------|--------|-------|
| **Server infrastructure** | £100–300 | £1,200–3,600 | Single server or small VM cluster for backend + frontend + DB |
| **GPU for local LLMs** | £150–400 | £1,800–4,800 | Single GPU instance (A100/A10G) for Ollama/vLLM, or existing company GPU if available |
| **Cloud AI API (30% of tasks)** | £60–150 | £720–1,800 | Claude Sonnet/Haiku for complex tasks only; prompt caching + batch API reduce costs further |
| **Litmus/EoA (optional)** | £0–400 | £0–5,000 | Only if full 20+ client rendering needed; built-in tools cover core clients |
| **Software licences** | £0 | **£0** | Entire stack is open-source |
| **Total estimated range** | **£310–1,250** | **£3,720–15,200** | Vs. £50K–150K+/yr for comparable SaaS platform |

**Note on people costs:** Developer time is not included in this comparison because it is constant in both scenarios. The email developers build email campaigns regardless of whether the Hub exists — the Hub redirects their effort into a more efficient workflow, it does not add headcount. SaaS platforms also require developer time to configure, manage, and produce work within them. The fair comparison is infrastructure and licence costs, where the Hub's open-source stack eliminates per-seat pricing entirely.

**Initial build investment:** The V1 build was completed in 5–7 weeks with a collaborative team of 2–3 developers (see Section 16). This was a one-time investment that produced a permanent, fully-owned platform — after which the ongoing costs above apply.

---

# 16. V1 Build — Timeline & Delivery

V1 — a fully functional platform demonstrating value with the team using it daily — was built by a small collaborative team of 2–3 developers working from a private GitHub repository. AI-assisted coding tools accelerated development significantly, and the collaborative approach distributed knowledge from the start, reducing key-person risk while building shared ownership of the platform.

## 16.1 V1 Scope Definition

V1 includes everything needed to be useful and demonstrable. Each feature was selected because it directly solves a problem the team faces today. **All V1 features have been delivered.**

### Included in V1 — What It Is and Why It Matters

| # | Feature | What It Does | How It Benefits the Team |
|---|---------|-------------|----------------------|
| 1 | **Auth + Project Workspace** | JWT-based auth with RBAC. Client-scoped project workspaces with team assignments. | **Client data isolation from day one.** Developers only see the clients they're assigned to. No accidental cross-client exposure. Demonstrates enterprise governance to stakeholders. |
| 2 | **Monaco Editor + Live Preview** | VS Code-quality code editor with split-pane live preview, Can I Email autocomplete, and inline CSS support warnings. | **Developers stay in the Hub instead of switching between tools.** Real-time feedback on which CSS properties break in which clients — catches Outlook issues while typing, not after a 3-hour QA cycle. |
| 3 | **Maizzle Build Pipeline** | Compile-on-save, Tailwind CSS inlining, responsive transforms, unused class purging, plaintext generation. | **Production-ready email HTML in seconds, not hours.** Eliminates the manual CSS inlining, minification, and responsive testing that currently eats 30–60 minutes per template. Every email leaves the Hub optimised. |
| 4 | **Component Library v1** | 5–10 pre-tested, versioned email components (headers, CTAs, product cards, footers, hero blocks) with dark mode variants. | **Build once, reuse everywhere.** A CTA button tested in 20+ clients is never manually reassembled again. Fixes propagate — update a component once and every email using it inherits the fix. This is where compound value starts. |
| 5 | **3 AI Agents (Scaffolder + Dark Mode + Content)** | Scaffolder generates email HTML from campaign briefs. Dark Mode Agent injects tested CSS patterns. Content Agent refines subject lines, CTAs, and body copy with brand voice constraints per client. | **Turns a multi-hour build into a 30-minute refinement.** The Scaffolder produces a working first draft, Dark Mode becomes automatic, and the Content Agent handles copywriting — matching every AI content capability competitors offer, but specialised for email. |
| 6 | **Raw HTML Export + Braze Connector** | One-click export as production-ready HTML or direct push to Braze as Content Blocks with Liquid template packaging. | **Eliminates the copy-paste-reformat cycle.** Currently, getting HTML from development into Braze involves manual formatting, Content Block creation, and Liquid tag insertion. The connector automates this entirely. |
| 7 | **10-Point QA Gate System** | HTML validation, CSS support matrix check, file size (Gmail clipping), link validation, spam score, dark mode audit, accessibility basics, fallback verification, image optimisation check, brand compliance. | **No email leaves the Hub without passing every check.** This is the safety net that makes innovation possible — the team can experiment with AMP, interactive CSS, and kinetic elements knowing the gate system will catch any rendering failure before it reaches a client inbox. |
| 8 | **RAG Knowledge Base v1** ✅ | Searchable knowledge base seeded with Can I Email support data (8 CSS compatibility docs), email development best practices (6 guides), and email client rendering quirks (6 client-specific docs). 20 curated markdown documents processed through full RAG pipeline (extract → chunk → embed → store) via `make seed-knowledge`. Manifest-driven with per-document tags and domain classification. 109 unit tests. | **Tribal knowledge becomes permanent.** The Outlook 2016 fix that one developer discovered 6 months ago is now searchable, indexed, and available to every AI agent. New team members access the entire team's accumulated expertise from day one. |
| 9 | **Client Approval Portal** | Client stakeholders log in with a viewer role (scoped to their projects only), see the live email render exactly as production, leave section-level feedback, and formally approve or request changes. Includes version comparison (what changed since last review), email/Slack notifications when a review is ready, and a time-stamped audit trail of all approvals. | **Replaces the screenshot-email approval cycle.** Clients currently receive static images, respond with ambiguous feedback, and iterate over days. The portal shows the live render, captures specific feedback, provides formal approve/reject workflow, and creates a documented audit trail — approval cycles drop from days to hours. |
| 10 | **Test Persona Engine** | Pre-configured subscriber profiles (device, email client, dark mode, locale, loyalty tier) for one-click preview of how specific audience segments experience the email. | **"Show me this email as a Gold-tier member on iPhone dark mode"** — one click. Currently this requires manually toggling preview settings, remembering which clients the audience uses, and guessing at rendering. The persona engine makes QA targeted and fast. |
| 11 | **Rendering Intelligence Dashboard** | QA results displayed as client support matrices, template quality scores, and visual regression tracking. | **Proves the Hub's value with data.** When a stakeholder asks "what can we actually do with email?", the dashboard shows exactly which innovations work in which clients — not opinions, but tested compatibility data. This is the output the team presents to clients to sell innovation. |

### V2 Iterations

| Feature | Status |
|---------|--------|
| Figma integration with brand guardrails | **Frontend demo delivered** (V2 Phase 4.3). Connection management, design token extraction UI. Real Figma API integration deferred. |
| Litmus / Email on Acid API | **Backend delivered** (V2 Phase 4.4). `app/rendering/` VSA module with `RenderingProvider` Protocol, Litmus + EoA providers (placeholder APIs), visual regression comparison, circuit breaker resilience. 4 REST endpoints, 12 unit tests. Frontend rendering UI deferred. |
| SFMC, Adobe, Taxi connectors | **Delivered** (V2 Phase 4.2). `ConnectorProvider` Protocol with 4 ESP implementations (Braze, SFMC, Adobe Campaign, Taxi). Placeholder APIs ready for production credentials. |
| Advanced agents (remaining 5) | **Outlook Fixer delivered** (2026-03-09) — first eval-first + skills workflow agent. SKILL.md + 4 L3 skill files, 12 synthetic test cases, 5-criteria judge, blueprint recovery router integration. **Accessibility Auditor next.** Then: Personalisation, Code Reviewer, Knowledge, Innovation. Each follows the eval-first + skills pattern from `TODO.md` Section 4.1. |
| Real-time collaborative editing | **Delivered** (V2 Phase 4.5). Yjs CRDT + y-codemirror.next with demo mode simulated collaborator. |
| Localisation engine (100+ locales) | **Delivered** (V2 Phase 4.5). 6 locale stubs (en/ar/de/es/fr/ja), cookie-based switching, RTL support, translation management. |
| Per-client brand guardrails | **Delivered** (V2 Phase 4.5). Brand settings page, CodeMirror linter extension, toolbar violations badge. |
| Visual conditional logic builder | **Delivered** (V2 Phase 4.5). @dnd-kit drag-and-drop Visual Liquid Builder with regex parser/serializer. |
| Client brief system integration | **Delivered** (V2 Phase 4.5). Jira/Asana/Monday.com connection cards, brief items, import-to-project flow. |

## 16.2 Build Timeline

| Phase | Deliverable | Time | Notes |
|-------|------------|------|-------|
| **Scaffolding** | FastAPI + Next.js + Docker + auth + DB | 2–3 days | AI-assisted coding handles boilerplate rapidly |
| **Email Engine** | Maizzle integration, build pipeline, file watcher | 3–4 days | Maizzle config is well-documented; pipeline plumbing takes iteration |
| **Editor UI** | Monaco + split preview + dark mode toggle | 3–4 days | shadcn/ui + Monaco is fast; preview iframe and hot reload need tuning |
| **AI Agents** | LLM API integration, Scaffolder + Dark Mode + Content agents, streaming responses | 3–4 days | System prompts are the real work. Content Agent adds ~1 day (same LLM infrastructure, different system prompt + editor context menu integration). |
| **AI Alt Text** | Vision model integration for automated image alt text generation as part of Accessibility Audit | 1–2 days | Extends QA pipeline. Vision API call + review/approve UI. |
| **Component Library** | 5–10 Maizzle components + browser UI + versioning | 3–4 days | Building the components themselves is the slow part — each needs manual cross-client testing |
| **Braze Connector** | API integration, Content Block export, Liquid template packaging | 2–3 days | Requires a Braze sandbox to test against |
| **QA Gate System** | Full 10-point check: HTML validation, CSS support, file size, links, spam score, dark mode, accessibility basics, fallback, images, brand | 2–3 days | Extends basic QA incrementally; SpamAssassin + Can I Email data are open-source |
| **RAG Knowledge Base** ✅ | pgvector setup, Can I Email ingestion, email dev best practices, team quirks import | 2–3 days | pgvector is already in the stack; initial data seeding is the main work. **Done:** 20 documents seeded across 3 domains. |
| **Client Approval Portal** | Client viewer login, live preview, section-level feedback, approve/request changes workflow, version comparison, notifications, audit trail | 3–4 days | Extends auth system with viewer role + approval workflow UI + notification hooks |
| **Test Persona Engine** | Pre-configured subscriber profiles for preview (device, client, dark mode, locale) | 1–2 days | Mock data profiles + preview toggle integration |
| **Rendering Dashboard** | QA results displayed as client support matrices, template quality scores | 2–3 days | Frontend dashboard over data already collected by QA pipeline |
| **Polish + Glue** | Routing, error handling, loading states, deployment | 2–3 days | The unglamorous 20% that takes 80% of patience |

**Total: 5–7 weeks with a collaborative team of 2–3 developers.** Workstreams were parallelised — one developer on the email engine and editor while another focused on AI agents and the knowledge base. Private GitHub repository with branch-based workflow ensured code review and quality from the start. **V1 delivered on schedule.**

## 16.3 Where AI-Assisted Coding Helps (And Where It Doesn't)

AI-assisted development tools have matured considerably. A small team equipped with these tools can deliver production-quality platforms in timeframes that would have seemed ambitious a year ago. A domain-specific email development platform, built on well-documented open-source technologies with a clear architectural blueprint, is well within reach for a collaborative team of 2–3 experienced developers working over a few focused weeks.

AI coding tools handle 70–80% of the boilerplate: API routes, React components, database models, Docker configs, auth middleware. This frees the team to focus on the parts that matter most — the email-specific integration work and the quality of the developer experience.

The bottlenecks AI won't shortcut:

- **Maizzle pipeline debugging** when builds don't behave as expected. This is integration plumbing that requires running, breaking, and fixing.
- **Email HTML rendering quirks** that only reveal themselves in actual email clients. No AI tool can replace sending a test email to Outlook 2016.
- **Editor + preview + build pipeline feel.** Getting Monaco, the live preview iframe, and the Maizzle build to feel responsive and connected is an integration problem, not a code-generation problem.

## 16.4 Recommended Sprint Structure

**Sprint 1 (2 weeks):** ✅ FastAPI + Next.js shell, auth, Monaco editor, Maizzle build pipeline, live preview, test persona engine. Write email HTML in a browser, see it compile live, and preview as different subscriber profiles.

**Sprint 2 (2–3 weeks):** ✅ AI agents (Scaffolder + Dark Mode + Content), component library, Braze connector, full 10-point QA gate system, RAG knowledge base v1, AI alt text generation. Full embedded intelligence and content generation matching every competitor's AI capability.

**Sprint 3 (1–2 weeks):** ✅ Client approval portal (viewer login, approve/reject workflow, version comparison, notifications, audit trail), rendering intelligence dashboard, polish and deployment. Complete V1 — clients can log in for approvals, QA data is visible, and the team has a tool they want to use daily.

With V1 delivered and V2 features substantially complete — Figma sync, additional ESP connectors, AI image generation, Litmus/EoA rendering integration, collaborative editing, localisation, brand guardrails, visual Liquid builder, client brief integration, OWASP security hardening (Phase 6), agent evaluation pipeline (Phase 5, live baseline established), and agent capability infrastructure (Phase 7: structured handoffs, confidence scoring, component context, agent memory system) — the remaining work is:

- **5 remaining AI agents** (task 4.1, eval-first + skills workflow: Accessibility Auditor next, then Personalisation, Code Reviewer, Knowledge, Innovation)
- **Eval-informed prompts** (7.2, unblocked by real failure data)
- **Knowledge graph integration** (Phase 8: Cognee-powered structured knowledge, per-agent SKILL.md files, email development ontology)
- **Graph-driven intelligence layer** (Phase 9: persona-graph profiles, Can I Email live sync, component-graph linking, adaptive blueprints, competitive intelligence, SKILL.md A/B testing)

The Outlook Fixer agent (delivered 2026-03-09) established the eval-first + skills pattern for all subsequent agents. The foundation is in place and the platform grows organically with each new capability.

---

*This plan is designed to turn innovation bench time into a production-grade platform that compounds the agency's email development capability across every client engagement. The result is a tool shaped specifically by how the agency works — multi-client, multi-platform, knowledge compounding — that grows more valuable with every project delivered through it.*
