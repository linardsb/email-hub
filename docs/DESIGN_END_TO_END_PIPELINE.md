# Design-to-Email Conversion Pipeline

Complete end-to-end architecture of the Email Hub — from Figma design file to production-ready, QA-validated, multi-client HTML email.

---

## System Overview

The Email Hub converts design files (Figma, Penpot, MJML, raw HTML) into production-ready email HTML through a **multi-stage pipeline** combining deterministic processing, AI agents, and comprehensive quality assurance.

### Core Components

| Component | Description | Location |
|-----------|-------------|----------|
| **Design Sync Module** | Provider-agnostic ingestion from Figma, Penpot, Sketch, Canva. Handles connections, token extraction, asset download, layout analysis, and conversion orchestration. | `app/design_sync/` |
| **Blueprint Engine** | State-machine orchestrator coordinating 9 AI agents through a DAG. Bounded self-correction (max 2 retries per agent, 25 total steps). Progressive context hydration. | `app/ai/blueprints/engine.py` |
| **Template Registry** | 16 golden templates with YAML metadata, slot definitions, default design tokens. Pre-compiled CSS. Section composition for custom layouts. | `app/ai/templates/registry.py` |
| **Component System** | 88 reusable email building blocks (hero, CTA, columns, accordions). Versioned with slot definitions, QA compatibility badges, and section adapter bridge. | `app/components/` + `email-templates/components/` |
| **Repair Pipeline** | 8-stage deterministic auto-repair: structure, MSO conditionals, dark mode meta, accessibility, personalisation, size optimization, links, brand compliance. | `app/qa_engine/repair/` |
| **QA Engine** | 14-check quality gate: HTML validation, CSS support, dark mode, accessibility, Outlook fallback, spam score, brand compliance, deliverability, and more. | `app/qa_engine/checks/` |
| **Maizzle Sidecar** | Node.js service for CSS optimization (PostCSS + Lightning CSS), MJML compilation, style inlining (Juice), and ontology-driven property elimination. | `services/maizzle-builder/` |
| **Rendering Gate** | Final pre-send validation. Per-client confidence scoring against 12+ email clients across 3 tiers. Configurable block/warn/skip modes. | `app/rendering/gate.py` |

---

## End-to-End Pipeline Flow

```
DESIGN INPUT
  Figma/Penpot File → Validate Connection → Fetch File Structure → Download Assets

ANALYSIS
  Layout Analysis → Section Detection → Token Extraction → Brief Generation → EmailDesignDocument (IR)

CONVERSION (3 paths)
  Route Decision →
    Path 1: Component Match + Render (recommended)
    Path 2: Recursive Node-to-HTML (legacy)
    Path 3: MJML → Maizzle Compile

AI AGENT PIPELINE
  Scaffolder → Repair (8 stages) → QA Gate (14 checks) → Recovery Router → Fixer Agent(s) ↻

ASSEMBLY
  Template Assembler → Design System Overlay → Sanitize (nh3) → Section Markers

BUILD & OPTIMIZE
  Maizzle Build → PostCSS Optimize → Lightning CSS Minify → Juice Inline

FINAL VALIDATION
  Quality Contracts → Rendering Gate → Per-Client Confidence → PASS / WARN / BLOCK

OUTPUT
  Template + Version (DB) → Export / ESP Push → Production Email
```

---

## Phase A: Design File Entry & Connection

```
User connects Figma/Penpot file (PAT + URL)
  → Validate Connection (FigmaService.validate_connection())
  → Encrypt & Store Token (DesignConnection model → DB)
  → Fetch File Structure (get_file_structure() → DesignNode tree)
  → Export & Download Assets (export_images() → local storage)
```

### Supported Providers

| Provider | Status | Implementation | Features |
|----------|--------|----------------|----------|
| **Figma** | Production | `app/design_sync/figma/` | Full: validate, structure, tokens, images, webhooks |
| **Penpot** | Production | `app/design_sync/penpot/` | Full: same as Figma (self-hosted) |
| **Sketch** | Limited | `app/design_sync/sketch/` | Stub implementation |
| **Canva** | Limited | `app/design_sync/canva/` | Stub implementation |
| **MJML Import** | Production | `POST /import/mjml` | Direct MJML markup ingestion |
| **HTML Import** | Production | `POST /import/html` | Reverse-engineer HTML → EmailDesignDocument |

### DesignNode Protocol (Provider-Agnostic)

All providers normalize output to a common `DesignNode` tree (`app/design_sync/protocol.py`). Each node carries: `id`, `name`, `type` (FRAME/TEXT/IMAGE/GROUP/COMPONENT/VECTOR), `children[]`, layout properties (x/y/width/height/padding), styling (fill_color, text_color, fonts), and rich text (`style_runs` for bold/italic/links per character range).

---

## Phase B: Layout Analysis & Section Detection

```
Detect Naming Convention (MJML tags / descriptive / generic)
  → Classify Sections by Name + Content (HEADER, HERO, CONTENT, CTA, FOOTER, NAV, SOCIAL)
  → Detect Column Layouts (Y-position grouping, 10px tolerance)
  → Extract Content Elements (TextBlocks, ImagePlaceholders, ButtonElements)
  → Output: EmailSection[] + DesignLayoutDescription
```

### Section Classification

| Section Type | Detection Method | Key Signals |
|-------------|-----------------|-------------|
| HEADER | Name + position | Contains logo, first frame in page |
| HERO | Name + content | Large image, headline text, near top |
| CONTENT | Content heuristic | Body text, may have columns |
| CTA | Name + button detection | Contains button elements, short text |
| FOOTER | Name + position | Last frame, small text, links |
| NAV | Name pattern | Horizontal link list |
| SOCIAL | Name + icons | Social media icon images |

### Token Extraction

Design tokens (colors, typography, spacing) extracted via `FigmaService.sync_tokens()` and validated/transformed through `token_transforms.py` with email client compatibility checks.

### Brief Generation

`brief_generator.py` converts layout analysis + tokens into a Markdown brief (max 4000 chars) for the Scaffolder AI agent: section summaries, image references, text content, color palette, typography specs.

---

## Phase C: EmailDesignDocument (Canonical IR)

Single contract between all input sources and the converter. All sources (Figma, Penpot, MJML, HTML reverse-engineering) convert to this format.

- **DocumentSource** — `provider` (figma/penpot/mjml/html), `file_ref`, `synced_at`
- **DocumentLayout** — `container_width` (default 600px), `sections[]` with type, content elements, column layout, metadata
- **DocumentTokens** — `colors` (palette roles), `typography` (heading/body fonts), `spacing`, `variables`
- **DocumentSection** — type (header/hero/content/cta/footer), `content[]` (textblocks, images, buttons), `metadata`

Files: `app/design_sync/email_design_document.py`, JSON Schema at `app/data/schemas/email-design-document-v1.json`

---

## Phase D: Three Conversion Paths

### Path 1: Component-Based (Recommended)

```
EmailDesignDocument
  → Component Matcher (section → component slug mapping)
  → Component Renderer (slot filling + token overrides)
  → Assemble into EMAIL_SKELETON (MSO conditionals included)
  → Sanitize: sanitize_web_tags_for_email()
  → ConversionResult
```

### Path 2: Recursive (Legacy)

```
DesignNode tree
  → Walk tree depth-first
  → node_to_email_html() per node (FRAME→table, TEXT→p, IMAGE→img)
  → Group children into rows (Y-position → tr/td)
  → Sanitize
  → ConversionResult
```

### Path 3: MJML

```
EmailDesignDocument
  → Generate MJML markup (mj-section, mj-column, mj-text)
  → Maizzle Sidecar Compile (POST /compile-mjml)
  → Inject Section Markers (round-trip editing)
  → ConversionResult
```

### Component Matching

| Section Type | Component Slug | Slot Fills |
|-------------|---------------|------------|
| HEADER | `header-v1`, `logo-header` | logo_image, company_name |
| HERO | `hero-block` | heading, hero_image, subheading |
| CONTENT (1-col) | `text-block` | heading, body |
| CONTENT (2-col) | `column-layout-2` | col1_*, col2_* |
| CONTENT (3-col) | `column-layout-3` | col1_*, col2_*, col3_* |
| CTA | `cta-block` | button_text, button_url |
| FOOTER | `footer` | company, address, links |
| SOCIAL | `social-links` | icon_urls |
| PRODUCT GRID | `product-grid` | items[] |
| CATEGORY NAV | `category-nav` | nav_items[] |
| IMAGE GALLERY | `image-gallery` | gallery_images[] |

---

## Phase E: AI Agent Blueprint Pipeline

The Blueprint Engine (`app/ai/blueprints/engine.py`) orchestrates 9 agents as a state machine with max 2 retries per agent and 25 total steps.

### Pipeline Flow

```
Scaffolder (Opus — "complex" tier)
  Brief → Template Selection → Slot Filling → Design Tokens
  3-pass pipeline: decide template, fill slots, apply tokens (pass 3 = no LLM)
    ↓
Repair Node (Deterministic) — 8-stage cascading auto-repair
    ↓
Visual Precheck (Deterministic) — Pre-QA screenshot analysis
    ↓
QA Gate (Deterministic) — 14 checks in parallel → StructuredFailure[]
    ↓
QA Passed?
  YES → Maizzle Build (PostCSS → Lightning CSS → Juice inline) → Export
  NO  → Recovery Router (adaptive fixer selection + cycle detection)
        → Routes to one of:
          Dark Mode | Outlook Fixer | Accessibility | Personalisation | Code Reviewer
        → Loop back to Repair → QA Gate
```

### The 9 AI Agents

| # | Agent | Model Tier | Role | Scope Constraint (Retry) |
|---|-------|-----------|------|--------------------------|
| 1 | **Scaffolder** | Complex (Opus) | Generate initial email HTML from brief | Full HTML rewrite |
| 2 | **Dark Mode** | Standard (Sonnet) | Add dark mode CSS + color overrides | Styles only |
| 3 | **Outlook Fixer** | Standard | Add VML/MSO conditionals for Outlook | MSO conditionals + VML only |
| 4 | **Accessibility** | Standard | WCAG AA fixes (alt, ARIA, semantics) | Attributes + semantic elements only |
| 5 | **Personalisation** | Standard | ESP merge tags (Liquid, AMPscript, etc.) | Text content + template tags only |
| 6 | **Code Reviewer** | Standard | Code quality analysis (read-only first pass) | Styles + redundant code only |
| 7 | **Content** | Standard | Copywriting refinement | Text content only |
| 8 | **Knowledge** | Advisory | Email dev knowledge base | Not in QA loop |
| 9 | **Innovation** | Advisory | Experimental features (CSS carousel, AMP) | Not in QA loop |

### QA Failure → Agent Routing

| QA Check Failure | Priority | Routed To |
|-----------------|----------|-----------|
| fallback (Outlook) | 1 (highest) | Outlook Fixer |
| accessibility | 2 | Accessibility |
| dark_mode | 3 | Dark Mode |
| personalisation_syntax | 4 | Personalisation |
| spam_score | 5 | Scaffolder |
| css_support | 6 | Code Reviewer |
| file_size | 7 | Code Reviewer |
| brand_compliance | 8 | Scaffolder |
| link_validation | 9 | Scaffolder |
| html_validation | 10 | Scaffolder |

### Structured Output Mode (Plan Merger + Template Assembler)

In structured mode, 7 downstream agents return **decision schemas** instead of raw HTML. These are merged into an `EmailBuildPlan` via `plan_merger.py`:

- `merge_dark_mode(plan, decisions)` — color overrides into design tokens
- `merge_accessibility(plan, decisions)` — alt text + heading fixes into slots
- `merge_personalisation(plan, decisions)` — ESP merge tags around slot content

The `TemplateAssembler` then deterministically generates final HTML from the plan in 16 steps: resolve template → fill slots → palette replacement → font replacement → spacing → responsive CSS → dark mode CSS → brand sweep → preheader → annotations. **Zero LLM calls in assembly** — fully deterministic, 100% reproducible.

### Agent Execution Flow (Single Agent)

1. **System Prompt Construction** — Base prompt + relevant skills (progressive disclosure)
2. **User Message Construction** — Brief + QA failures (on retry) + scope constraint + upstream handoff
3. **LLM Call** — `provider.complete(messages, model_override)`
4. **Output Extraction** — Extract HTML from `` ```html `` block + confidence from `<!-- CONFIDENCE: X.XX -->`
5. **XSS Sanitization** — `sanitize_html_xss(html, profile=agent_name)` via nh3 allowlists
6. **Post-Processing** — Agent-specific: Outlook Fixer validates MSO, Code Reviewer extracts JSON
7. **Emit AgentHandoff** — Frozen dataclass with decisions, warnings, confidence, typed payload

### Advanced Features

- **Confidence Calibration:** Per-agent thresholds from historical outcomes. Below threshold → human review instead of retry.
- **Recovery Outcome Tracking:** Which fixer succeeds for which check type. Enables adaptive routing based on project history.
- **Correction Examples:** Store successful fix pairs (original → fixed). Inject as context on retries.
- **Economy Mode:** Triggered when token budget < 20%. Compact handoff history, trajectory summary. Saves ~60% context.
- **Inline Judges:** On recovery retries, lightweight LLM judges evaluate output quality.
- **Insight Propagation:** Cross-agent learning within a run via insight bus.

---

## Phase F: 8-Stage Repair Pipeline

Runs **before** the QA gate. Each stage is deterministic (no LLM), pure-function, and incremental.

| Stage | Name | What It Does |
|-------|------|-------------|
| 1 | **Structure Repair** | Add DOCTYPE, html, head, body if missing |
| 2 | **MSO Conditional Repair** | Fix unbalanced Outlook conditionals, nesting |
| 3 | **Dark Mode Meta Injection** | Inject color-scheme meta + prefers-color-scheme media query |
| 4 | **Accessibility Fixes** | Add lang="en", role="presentation", scope="col", empty alt |
| 5 | **Personalisation Delimiter Check** | Warn on imbalanced {{ }} and %%[ ]%% (no auto-fix) |
| 6 | **Size Optimization** | Strip HTML comments (preserve MSO), remove empty styles |
| 7 | **Link Validation** | Fix empty href="" → "#", warn on javascript: hrefs |
| 8 | **Brand Repair** | Off-palette color correction, footer injection, logo injection |

File: `app/qa_engine/repair/pipeline.py`. Stage 8 requires `DesignSystem` from project; skips if none configured.

---

## Phase G: 14-Point QA Gate

All 14 checks run via the YAML-driven rule engine. Per-project `qa_profile` JSON column allows fine-grained threshold/param overrides.

| # | Check | Rules | Key Metrics | Pass Threshold |
|---|-------|-------|------------|----------------|
| 1 | **HTML Validation** | 20 | DOM structure, tags, nesting, semantics | score >= 0.5 |
| 2 | **CSS Support** | Ontology + syntax | 365-property support matrix, syntax errors | score >= 0.5 |
| 3 | **CSS Audit** | Compiler matrix | Per-client coverage scores | no errors |
| 4 | **File Size** | 8 | Gmail 102KB clip, Outlook 100KB, Yahoo 75KB | all thresholds met |
| 5 | **Link Validation** | 11 | HTTPS, URL format, phishing, VML links | score >= 0.5 |
| 6 | **Spam Score** | 50+ triggers | Trigger phrases, ALL-CAPS, punctuation | score >= 0.5 |
| 7 | **Dark Mode** | 16 | Meta tags, media queries, color coherence | score >= 0.5 |
| 8 | **Accessibility** | 24 | WCAG AA: lang, alt, ARIA, headings, links | score >= 0.5 |
| 9 | **Fallback (MSO)** | 8 | Conditional balance, VML, ghost tables, namespaces | score >= 0.5 |
| 10 | **Image Optimization** | 10 | width/height, alt, format, data URI, dimensions | score >= 0.5 |
| 11 | **Brand Compliance** | 7 | Colors, fonts, required elements, forbidden text | no violations (if rules exist) |
| 12 | **Personalisation Syntax** | 12 | 7 ESP platforms: Liquid, AMPscript, HubL, etc. | score >= 0.5 |
| 13 | **Deliverability** | 4 dimensions | Content quality, HTML hygiene, auth readiness, engagement | score >= 70/100 |
| 14 | **Liquid Syntax** | 3 passes | Structural, python-liquid parse, filter validation | score >= 0.5 |

### QA Override Mechanism

Developers can override failed QA checks with justification (10-2000 chars). Requires developer+ role. Override recorded in `qa_overrides` table. This is a soft gate — the email can proceed despite QA failure.

---

## Phase H: CSS Optimization & Build

```
QA-Passed HTML
  → Maizzle Build Sidecar (POST http://localhost:3001/build)
  → Extract <style> blocks
  → Expand CSS Shorthands (padding: 1px 2px → padding-top/right/bottom/left)
  → PostCSS Email Optimizer (ontology-driven: 365 properties × 12+ clients)
  → Per-Property Decision:
      Full Support    → Keep as-is
      Fallback Avail  → Convert (e.g. grid → table-cell)
      Zero Support    → Remove property
  → Lightning CSS Minification
  → Juice: CSS → Inline Styles (move <style> to style="" attributes)
  → Output: Optimized HTML + Metadata (original_size, optimized_size, removed_properties[], conversions[])
```

### Ontology Structure

The CSS ontology (`data/ontology.json`, synced via `make sync-ontology`) maps 365 CSS properties to support levels across 12+ email clients. Each property has per-client entries (full/partial/none) and optional fallback conversions.

**Target clients:** Gmail (web/mobile), Outlook (desktop/web/365), Apple Mail, Yahoo (web/mobile), Samsung Mail, Thunderbird, iOS Mail, Android Gmail.

### Template Precompilation

Golden templates are pre-optimized at registration time (`TemplatePrecompiler`), reducing CSS size 30-50%. Marked with `<!-- css-preoptimized -->` to skip redundant optimization at build time.

---

## Phase I: Rendering Gate (Final Validation)

```
Built HTML (post-Maizzle)
  → Quality Contracts (contrast WCAG, completeness, placeholder leak detection)
  → Rendering Confidence Scorer (per-client: CSS compat + emulator + calibration + layout)
  → Verdict: PASS | WARN | BLOCK
```

### Client Tier Thresholds

| Tier | Clients | Default Threshold |
|------|---------|-------------------|
| **Tier 1** (Strictest) | Gmail Web, Outlook Desktop, Apple Mail, Outlook 2019 | 80% |
| **Tier 2** | Yahoo Web/Mobile, Samsung Mail, Thunderbird | 70% |
| **Tier 3** | Android Gmail, Outlook Web, Outlook Dark, iOS Mobile | 60% |

Gate mode is configurable per project: `skip` (always pass), `warn` (non-blocking), `block` (prevents export/ESP push).

---

## Templates & Components System

### Golden Templates (16)

Pre-built email layouts in `app/ai/templates/library/`. YAML metadata defines: layout type, column count, slot definitions, default design tokens, ideal use cases.

**Types:** promotional, transactional, newsletter, welcome, event, receipt, etc.

**Slots:** `[data-slot="heading"]`, `[data-slot="hero_image"]`, `[data-slot="cta_text"]`, etc. Filled by Scaffolder or deterministic assembly.

### Component Seeds (88)

Reusable email building blocks in `email-templates/components/`. Hero blocks, CTA buttons, column layouts, accordions, carousels, animations. All use MSO conditionals, inline styles, and Mustache-style slot markers.

### Section Blocks (15)

Composable sections in `app/ai/templates/sections/`. Combined via `TemplateComposer` when no golden template matches the brief. Hero, content (1/2/3-col), CTA, footer, nav, social links, spacer, divider.

### Design System

Per-project brand identity (`app/projects/design_system.py`): BrandPalette, Typography, LogoConfig, FooterConfig, SocialLinks + dynamic token maps. Applied during assembly: palette replacement (find default hex → replace with client hex), font swaps, logo enforcement, dark mode color replacement.

### Template Selection & Composition Flow

```
Scaffolder selects best-match template
  (from TemplateRegistry.list_for_selection_scoped())
    ↓
Match found?
  YES → Load template HTML + slots → Fill slots with content
  NO  → Select section blocks → TemplateComposer.compose() (skeleton + sections + dark mode CSS)
    ↓
Apply Design System (palette replacement, font swaps, logo/footer injection)
    ↓
Assembled HTML
```

### Section Adapter Bridge

`app/components/section_adapter.py` converts `ComponentVersion` → `SectionBlock` via 5-stage pipeline: Sanitize HTML → Repair → Inject slot markers → Extract metadata → Build SectionBlock. LRU cached (max 256 entries).

---

## Key File Reference

### Design Sync Module

| File | Purpose | Key Exports |
|------|---------|-------------|
| `protocol.py` | Provider interface contracts | DesignSyncProvider, DesignNode, ExtractedTokens |
| `email_design_document.py` | Canonical intermediate representation | EmailDesignDocument |
| `service.py` | Connection/token orchestration | DesignSyncService |
| `import_service.py` | Conversion pipeline orchestrator | DesignImportService |
| `converter_service.py` | Design tree → HTML conversion | DesignConverterService |
| `converter.py` | Low-level element conversion | node_to_email_html(), sanitize_web_tags_for_email() |
| `component_matcher.py` | Section → component mapping | match_all(), ComponentMatch |
| `component_renderer.py` | Slot filling + template rendering | ComponentRenderer, render_section() |
| `brief_generator.py` | Markdown brief for Scaffolder | generate_brief() |
| `mjml_generator.py` | Layout → MJML markup | generate_mjml() |
| `quality_contracts.py` | Post-conversion QA | run_quality_contracts() |
| `figma/layout_analyzer.py` | Section detection algorithm | analyze_layout(), EmailSection |
| `figma/service.py` | Figma API client | FigmaService |
| `section_cache.py` | 2-level async cache (memory + Redis) | SectionCache |
| `routes.py` | 30+ REST endpoints | FastAPI router |

### Blueprint Engine & AI Agents

| File | Purpose |
|------|---------|
| `blueprints/engine.py` | State machine executor (800+ lines) |
| `blueprints/definitions/campaign.py` | Campaign graph definition |
| `blueprints/protocols.py` | BlueprintNode, NodeContext, NodeResult, AgentHandoff |
| `blueprints/nodes/scaffolder_node.py` | Brief → HTML generation |
| `blueprints/nodes/dark_mode_node.py` | Dark mode CSS injection |
| `blueprints/nodes/outlook_fixer_node.py` | MSO conditional generation |
| `blueprints/nodes/accessibility_node.py` | WCAG AA fixes |
| `blueprints/nodes/personalisation_node.py` | ESP merge tag injection |
| `blueprints/nodes/code_reviewer_node.py` | Code quality analysis |
| `blueprints/nodes/qa_gate_node.py` | 14-point QA checks |
| `blueprints/nodes/recovery_router_node.py` | Adaptive fixer selection |
| `blueprints/nodes/repair_node.py` | 8-stage repair |
| `blueprints/nodes/maizzle_build_node.py` | CSS optimization + inlining |
| `agents/scaffolder/pipeline.py` | 3-pass scaffolder pipeline |
| `agents/scaffolder/assembler.py` | Deterministic 16-step HTML assembly |
| `agents/scaffolder/plan_merger.py` | Merge agent decisions into EmailBuildPlan |
| `shared.py` | extract_html(), sanitize_html_xss(), 10 nh3 profiles |
| `handoff.py` | Typed handoff payloads + formatting |

### Templates, Components & Build

| File | Purpose |
|------|---------|
| `ai/templates/registry.py` | TemplateRegistry singleton, fill_slots() |
| `ai/templates/composer.py` | Section block composition |
| `ai/templates/precompiler.py` | CSS precompilation for golden templates |
| `ai/templates/library/*.html` | 16 golden template HTML files |
| `ai/templates/library/_metadata/*.yaml` | Template metadata (slots, tokens, layout) |
| `ai/templates/sections/*.html` | 15 composable section blocks |
| `components/section_adapter.py` | ComponentVersion → SectionBlock bridge |
| `projects/design_system.py` | Per-project brand identity |
| `projects/template_config.py` | Per-project template preferences |
| `email_engine/service.py` | Email build orchestration |
| `email_engine/css_compiler/` | CSS analysis + optimization |
| `services/maizzle-builder/index.js` | Node.js sidecar service |
| `services/maizzle-builder/postcss-email-optimize.js` | PostCSS ontology-driven optimizer |
| `services/maizzle-builder/mjml-compile.js` | MJML compilation |

### QA Engine & Repair

| File | Purpose |
|------|---------|
| `qa_engine/service.py` | QA orchestrator |
| `qa_engine/rule_engine.py` | YAML-driven rule evaluation backbone |
| `qa_engine/custom_checks.py` | 100+ registered custom check functions |
| `qa_engine/checks/*.py` | 14 check implementations |
| `qa_engine/rules/*.yaml` | YAML rule definitions per check |
| `qa_engine/repair/pipeline.py` | 8-stage repair orchestrator |
| `qa_engine/repair/structure.py` | HTML skeleton repair |
| `qa_engine/repair/mso.py` | MSO conditional repair |
| `qa_engine/repair/dark_mode.py` | Dark mode meta injection |
| `qa_engine/repair/accessibility.py` | Accessibility attribute fixes |
| `qa_engine/repair/brand.py` | Brand compliance repair |
| `rendering/gate.py` | Per-client confidence gate |

---

## All Directories Involved

### Design Sync — `app/design_sync/`

| Directory | Purpose |
|-----------|---------|
| `app/design_sync/` | Core: service, converter, models, schemas, routes |
| `app/design_sync/figma/` | Figma API client, layout analyzer, tree normalizer |
| `app/design_sync/figma/tests/` | Figma-specific tests |
| `app/design_sync/penpot/` | Penpot API client + converter |
| `app/design_sync/penpot/tests/` | Penpot-specific tests |
| `app/design_sync/sketch/` | Sketch provider (stub) |
| `app/design_sync/canva/` | Canva provider (stub) |
| `app/design_sync/mock/` | Mock provider for development |
| `app/design_sync/diagnose/` | Conversion diagnostic reports |
| `app/design_sync/html_import/` | HTML reverse-engineering to EmailDesignDocument |
| `app/design_sync/html_import/tests/` | HTML import tests |
| `app/design_sync/mjml_import/` | MJML parsing + import |
| `app/design_sync/mjml_templates/` | MJML component templates for generation |
| `app/design_sync/tests/` | Design sync unit + integration tests |

### AI & Blueprint Engine — `app/ai/`

| Directory | Purpose |
|-----------|---------|
| `app/ai/` | Core: shared.py, handoff.py, sanitize.py, voice/ |
| `app/ai/adapters/` | LLM provider adapters (Claude, OpenAI, etc.) |
| `app/ai/blueprints/` | Engine core: state machine, service, protocols |
| `app/ai/blueprints/definitions/` | Graph definitions (campaign.py) |
| `app/ai/blueprints/nodes/` | All 11 nodes (6 agentic + 5 deterministic) |
| `app/ai/blueprints/tests/` | Blueprint engine tests |
| `app/ai/skills/` | Skill extraction + progressive disclosure |
| `app/ai/skills/tests/` | Skill system tests |
| `app/ai/voice/` | Brand voice adaptation |
| `app/ai/tests/` | AI module general tests |

### AI Agents — `app/ai/agents/`

| Directory | Purpose |
|-----------|---------|
| `app/ai/agents/scaffolder/` | Scaffolder: pipeline, assembler, plan_merger, prompt |
| `app/ai/agents/dark_mode/` | Dark mode CSS agent |
| `app/ai/agents/outlook_fixer/` | Outlook MSO/VML fixer + mso_repair |
| `app/ai/agents/accessibility/` | WCAG AA accessibility auditor |
| `app/ai/agents/personalisation/` | ESP merge tag agent (7 platforms) |
| `app/ai/agents/code_reviewer/` | Code quality analysis agent |
| `app/ai/agents/content/` | Copywriting refinement agent |
| `app/ai/agents/knowledge/` | Email dev knowledge base agent |
| `app/ai/agents/innovation/` | Experimental features agent (AMP, CSS hacks) |
| `app/ai/agents/visual_qa/` | Visual QA / screenshot analysis agent |
| `app/ai/agents/import_annotator/` | Import annotation agent |
| `app/ai/agents/schemas/` | Structured decision schemas (all agents) |
| `app/ai/agents/skills/` | Per-agent SKILL.md files |
| `app/ai/agents/tools/` | Agent tool definitions |
| `app/ai/agents/evals/` | Eval system: judges, runner, calibration, golden cases |
| `app/ai/agents/tests/` | Agent-level tests |

### Templates — `app/ai/templates/` + `app/templates/`

| Directory | Purpose |
|-----------|---------|
| `app/ai/templates/` | Registry, composer, precompiler, models |
| `app/ai/templates/library/` | 16 golden template HTML files |
| `app/ai/templates/library/_metadata/` | YAML metadata (slots, tokens, layout type) |
| `app/ai/templates/sections/` | 15 composable section blocks + _skeleton.html |
| `app/ai/templates/maizzle_src/` | Maizzle source markup for golden templates |
| `app/ai/templates/tests/` | Template system tests |
| `app/templates/` | Template CRUD: models, service, repository, routes |
| `app/templates/upload/` | Self-serve HTML upload pipeline |
| `app/templates/upload/tests/` | Upload pipeline tests |

### Components — `app/components/` + `email-templates/`

| Directory | Purpose |
|-----------|---------|
| `app/components/` | Component CRUD: models, service, section_adapter |
| `app/components/data/` | Component manifest, file loader |
| `app/components/tests/` | Component tests |
| `email-templates/` | Root: config.js, Maizzle entry |
| `email-templates/components/` | 88 component seed HTML files |
| `email-templates/components/golden-references/` | 14 golden reference templates for eval calibration |
| `email-templates/components/interactive/` | Interactive components (accordion, carousel) |
| `email-templates/components/snippets-sublime/` | Sublime Text snippet exports |
| `email-templates/src/layouts/` | Maizzle layout files |
| `email-templates/src/templates/` | Maizzle template source files |

### QA Engine — `app/qa_engine/`

| Directory | Purpose |
|-----------|---------|
| `app/qa_engine/` | Core: service, rule_engine, custom_checks, models |
| `app/qa_engine/checks/` | 14 check implementations |
| `app/qa_engine/rules/` | YAML rule definitions per check |
| `app/qa_engine/repair/` | 8-stage repair pipeline |
| `app/qa_engine/repair/tests/` | Repair pipeline tests |
| `app/qa_engine/data/` | QA data files (spam triggers, ISP profiles) |
| `app/qa_engine/bimi/` | BIMI (Brand Indicators) validation |
| `app/qa_engine/chaos/` | Chaos testing for QA resilience |
| `app/qa_engine/gmail_intelligence/` | Gmail-specific rendering intelligence |
| `app/qa_engine/outlook_analyzer/` | Outlook-specific analysis |
| `app/qa_engine/property_testing/` | Property-based testing for QA checks |
| `app/qa_engine/property_testing/tests/` | Property testing tests |
| `app/qa_engine/tests/` | QA engine tests |

### Rendering Gate — `app/rendering/`

| Directory | Purpose |
|-----------|---------|
| `app/rendering/` | Core: gate.py, service, confidence scorer |
| `app/rendering/calibration/` | Confidence calibration against real renders |
| `app/rendering/calibration/tests/` | Calibration tests |
| `app/rendering/eoa/` | Email on Acid integration |
| `app/rendering/litmus/` | Litmus integration |
| `app/rendering/local/` | Local rendering (Playwright-based) |
| `app/rendering/local/tests/` | Local rendering tests |
| `app/rendering/sandbox/` | Sandboxed rendering environment |
| `app/rendering/sandbox/tests/` | Sandbox tests |
| `app/rendering/tests/` | Rendering module tests |
| `app/rendering/tests/visual_regression/` | Visual regression baseline tests |

### Email Engine & Build — `app/email_engine/`

| Directory | Purpose |
|-----------|---------|
| `app/email_engine/` | Core: service, build models, routes |
| `app/email_engine/css_compiler/` | CSS analysis + ontology-driven optimization |
| `app/email_engine/schema_markup/` | JSON-LD schema markup for emails |
| `app/email_engine/tests/` | Email engine tests |

### Maizzle Sidecar — `services/maizzle-builder/`

| Directory | Purpose |
|-----------|---------|
| `services/maizzle-builder/` | Express.js service: index.js, postcss-email-optimize.js, mjml-compile.js |
| `services/maizzle-builder/data/` | Ontology JSON (365 CSS properties x 12+ clients) |
| `services/maizzle-builder/scripts/` | Ontology sync scripts |

### Projects & Config — `app/projects/`

| Directory | Purpose |
|-----------|---------|
| `app/projects/` | Project CRUD, design_system.py, template_config.py |
| `app/projects/tests/` | Project tests |

### Supporting Modules

| Directory | Purpose |
|-----------|---------|
| `app/core/` | Config, database, logging, exceptions, middleware |
| `app/shared/` | Shared utils (escape_like, etc.), models (TimestampMixin) |
| `app/auth/` | Authentication (JWT, bcrypt, roles) |
| `app/approval/` | Approval workflow (gates export/push) |
| `app/connectors/` | ESP connectors (Braze, SFMC, etc.) |
| `app/personas/` | Audience personas for agent context |
| `app/knowledge/` | Knowledge graph for agent context |
| `app/memory/` | Episodic memory for cross-run learning |
| `app/briefs/` | Campaign brief management |
| `app/workflows/` | Kestra workflow orchestration |
| `app/reporting/` | Typst PDF report generation |
| `app/plugins/` | Plugin system |
| `app/streaming/` | WebSocket streaming |
| `app/mcp/` | MCP server integration |
| `alembic/` | Database migrations |
| `data/` | Data files (ISP profiles, ontology, email client fonts) |

### Frontend (CMS) — `cms/`

| Directory | Purpose |
|-----------|---------|
| `cms/apps/web/src/components/builder/` | Visual email builder (DnD, canvas, preview) |
| `cms/apps/web/src/components/builder/panels/` | Property panel (Content/Style/Responsive/Advanced) |
| `cms/apps/web/src/lib/builder-sync/` | Bidirectional code-builder sync engine |
| `cms/apps/web/src/components/rendering/` | Pre-send rendering gate UI + dashboard |
| `cms/apps/web/src/components/approvals/` | Approval workflow UI |
| `cms/apps/web/src/components/collaboration/` | Real-time collaboration (presence, conflicts) |
| `cms/apps/web/src/components/ecosystem/` | Ecosystem dashboard (plugins, workflows, reports) |
| `cms/apps/web/src/components/tolgee/` | Translation management integration |
| `cms/apps/web/src/hooks/` | SWR hooks for all subsystems |
| `cms/apps/web/src/types/` | TypeScript type definitions (design-system-config, etc.) |
