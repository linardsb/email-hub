# TODO-completed — Archive (Phases 0–39, completed before 2026-04-01)

> Quarterly rotation of `docs/TODO-completed.md`. Phases 0–39 covered
> foundation work through Phase 39 (Pipeline Hardening). Active phases
> (40+) live in `docs/TODO-completed.md`.
>
> For per-subtask history, search this file via jDocMunch
> `search_sections` — same section-id pattern as the live file.
>
> Rotation cadence: per quarter. Next rotation: when the live file's
> Phase-40+ section count exceeds ~12 phases or its size exceeds ~250KB.

---

## Phase 0 — Foundation Blockers

### ~~0.1 Database Migration for Email-Hub Models~~ DONE
**Plan ref:** Section 2.3, 16.2 (Scaffolding)
**What:** Generate Alembic migration for all 7 new module models (ClientOrg, Project, ProjectMember, EmailBuild, Component, ComponentVersion, QAReport, QACheckResult, ExportRecord, ApprovalRequest, Feedback, AuditEntry, Persona). Add PostgreSQL Row-Level Security policies on `client_org_id` columns.
**Security:**
- RLS policies: `CREATE POLICY project_isolation ON projects USING (client_org_id = current_setting('app.current_client_id')::uuid)`
- All new tables inherit TimestampMixin (created_at, updated_at for audit)
- Soft delete on sensitive tables (projects, approval requests)
**Verify:** `make db-migrate` succeeds. All tables created. RLS policies active. CRUD operations on new endpoints persist data.

### ~~0.2 Initialize shadcn/ui Component Library~~ DONE
**Plan ref:** Section 9.1, 1.2 (Frontend Tech Stack)
**What:** Run shadcn/ui init in `cms/apps/web/`. Install foundational components (button, card, input, dialog, tabs, dropdown-menu, sheet, skeleton, table, badge, separator, scroll-area, command, popover, select, textarea). Wire into existing 3-tier design token system in `cms/packages/ui/src/tokens.css`.
**Security:**
- Ensure all form components have proper ARIA attributes
- Input components must sanitise rendered content (XSS prevention)
- Dialog/sheet components must trap focus (accessibility + security)
**Verify:** Components render with correct [REDACTED] brand tokens. Dark mode toggle works. All components pass accessibility audit.

### ~~0.3 Generate OpenAPI TypeScript SDK~~ DONE
**Plan ref:** Section 9.1 (Frontend Architecture)
**What:** Run SDK generation from `cms/packages/sdk/` against running backend (`http://localhost:8891/openapi.json`). Produces typed client for all 43 endpoints.
**Security:**
- SDK must automatically inject Authorization Bearer header from session
- SDK must handle 401 responses with automatic redirect to login
- SDK must never log request bodies containing credentials
**Verify:** Import SDK in a page component. Make typed API call. TypeScript compilation passes. Auth header injected.

### ~~0.4 Authenticated API Client Layer~~ DONE
**Plan ref:** Section 9.1 (Real-time, API Integration)
**What:** Build `cms/apps/web/src/lib/api-client.ts` — wrapper around generated SDK with auth token injection, automatic refresh, error handling, rate limit backoff. Custom React hooks: `useProjects()`, `useTemplate()`, `useQAResults()`, etc.
**Security:**
- Token refresh interceptor: on 401, attempt refresh before redirecting to login
- Never store access tokens in localStorage (use httpOnly cookies or memory-only)
- Request timeout: 30s default, 120s for build/AI endpoints
- Retry logic: max 3 retries with exponential backoff, no retry on 4xx
**Verify:** Login flow works end-to-end. Protected pages redirect to login when unauthenticated. Token refresh works silently.

---

## Phase 1 — Sprint 1: Editor + Build Pipeline (Plan: 2 weeks)

> **Sprint 1 Deliverable (Plan Section 16.4):** "Write email HTML in a browser, see it compile live, and preview as different subscriber profiles."

### ~~1.1 Project Dashboard Page~~ DONE
**Plan ref:** Section 9.2 (Dashboard), V1 #1
**What:** Dashboard page at `/(dashboard)/page.tsx`. Project overview grid, recent activity feed, QA status summary, quick-start template selection. Data from `GET /api/v1/projects` and `GET /api/v1/orgs`.
**Security:**
- Only show projects the authenticated user has access to (RBAC-filtered on backend)
- No client org data leakage across user sessions
**Verify:** Dashboard loads. Shows only user's assigned projects. Empty state for new users.

### ~~1.2 Project Workspace Layout~~ DONE
**Plan ref:** Section 9.2 (Project Workspace), V1 #2
**What:** Split-pane workspace at `/projects/[id]/workspace`. Three resizable panels: editor (left), preview (center/right), AI chat (bottom, collapsible). Use a resizable pane library compatible with React 19.
**Security:**
- Route guard: verify user has access to project before rendering
- Project ID validated server-side (no client-side trust)
**Verify:** Three-pane layout renders. Panels resize. Collapses gracefully on mobile.

### ~~1.3 Monaco Editor Integration~~ DONE
**Plan ref:** Section 9.2 (Monaco Editor), V1 #2
**What:** Embed Monaco Editor with HTML/CSS/Liquid syntax highlighting. Add Can I Email CSS autocomplete (flag unsupported properties inline). Bracket matching, code folding, minimap, search/replace. Editor state persists per template.
**Security:**
- Editor content sanitised before sending to backend (strip script injections)
- Content-Security-Policy headers prevent execution of editor content in host page
- Editor runs in sandboxed context (no access to parent window APIs)
**Verify:** Editor loads with syntax highlighting. Can I Email warnings appear for unsupported CSS. Content persists on save.

### ~~1.4 Maizzle Live Preview~~ DONE
**Plan ref:** Section 6.3 (Build Pipeline), 9.2 (Live Preview), V1 #3
**What:** Compile-on-save via `POST /api/v1/email/preview`. Render compiled HTML in sandboxed iframe. Desktop/tablet/mobile viewport toggles. Dark mode preview toggle. Zoom controls.
**Security:**
- Preview iframe uses `sandbox=""` — fully sandboxed (no scripts, no same-origin access)
- Preview iframe loaded via blob URL or srcdoc, never from external URL
- PostMessage communication between editor and preview must validate origin
- No user-generated content executes JavaScript in preview context
**Verify:** Type HTML in editor → compiled preview updates within 2 seconds. Viewport toggles resize iframe. Dark mode toggle works.

### ~~1.5 Test Persona Engine UI~~ DONE
**Plan ref:** Section V1 #10, 16.4
**What:** Persona selector dropdown in preview panel. Load personas from `GET /api/v1/personas`. One-click preview as: "Gmail Desktop", "iPhone Dark Mode", "Outlook 2016", etc. Visual context switching (device frame, email client chrome).
**Security:**
- Personas scoped to project (no cross-project persona leakage)
- Persona data is non-PII (device config, not subscriber data)
**Verify:** Persona selector loads presets. Preview updates to show selected device/client context.

### ~~1.6 Template CRUD + Persistence~~ DONE
**Plan ref:** Section 2.3 (Projects module), V1 #1
**What:** Save/load templates within projects. Template versioning (each save creates a version). Version history sidebar. Restore previous version capability.
**Security:**
- Template content stored encrypted at rest (PostgreSQL column encryption or transparent data encryption)
- Version history includes author + timestamp for audit
- Template access scoped to project members only
**Verify:** Create template → edit → save → reload shows saved content. Version history shows all saves. Restore works.

---

## Phase 2 — Sprint 2: Intelligence + Export (Plan: 2-3 weeks)

> **Sprint 2 Deliverable (Plan Section 16.4):** "Functional AI-assisted email development with automated QA and CMS export."

### ~~2.1 Wire AI Provider to LLM~~ DONE
**Plan ref:** Section 5.5 (AI Model Selection), 5.1 (Agent Architecture)
**What:** Register Claude (via Anthropic SDK) or OpenAI-compatible provider in `app/ai/registry.py`. Add `AI__PROVIDER`, `AI__MODEL`, `AI__API_KEY` to config. Implement model routing logic: Opus for complex, Sonnet for standard, Haiku for lightweight tasks. Verify streaming works via WebSocket.
**Security:**
- API keys stored as environment variables, NEVER in code or database
- AI request/response bodies logged WITHOUT the actual content (log token counts + model + latency only)
- Rate limit AI endpoints separately: 20 req/min per user for chat, 5 req/min for generation
- Input sanitisation: strip any PII patterns from prompts before sending to external API
- AI responses go through output validation before returning to client
**Verify:** `POST /v1/chat/completions` returns streamed response. Model routing selects correct tier. API key is not exposed in logs or errors.

### ~~2.2 Scaffolder Agent~~ DONE
**Plan ref:** Section 5.1 (Scaffolder), V1 #5
**What:** First AI agent — generates Maizzle email HTML from natural language campaign briefs. System prompt defines email constraints (table layouts, inline CSS, MSO conditionals, responsive stacking). Outputs complete Maizzle template source.
**Security:**
- Agent output goes through QA validation before being offered to user
- System prompt includes instruction to never include external URLs or script tags
- Generated HTML sanitised for XSS before rendering in preview
**Verify:** Provide brief "Create a 2-column product showcase email with dark mode support" → get valid Maizzle HTML. Preview renders correctly.

### ~~2.3 Dark Mode Agent~~ DONE
**Plan ref:** Section 5.1 (Dark Mode Agent), V1 #5
**What:** Analyses existing HTML and injects `@media (prefers-color-scheme: dark)` rules, `[data-ogsc]`/`[data-ogsb]` selectors for Outlook, transparent PNG suggestions, colour token remapping. Uses Knowledge Base for client-specific dark mode quirks.
**Security:**
- Agent only modifies CSS/style blocks, never injects script content
- Output diff shown to developer before applying (human-in-the-loop)
**Verify:** Provide email HTML without dark mode → agent returns enhanced version with dark mode CSS. Preview confirms dark mode toggle works.

### ~~2.4 Content Agent~~ DONE
**Plan ref:** Section 5.1 (Content Agent), 15.4 (Competitive Feature — new capability #1)
**What:** Generates and refines email marketing copy: subject lines, preheaders, CTA text, body copy. Supports rewrite, shorten, expand, and tone adjustment. Brand voice constraints applied per client. Integrates into Monaco editor as context menu: select text → right-click → "Refine with AI."
**Security:**
- Brand voice constraints loaded from project settings, not hardcoded
- Content suggestions never include personal data patterns
- Generated copy flagged if it matches spam trigger patterns
**Verify:** Select text in editor → right-click → "Refine with AI" → get alternatives. Subject line generation produces 5 options.

### ~~2.5 AI Chat Sidebar UI~~ DONE
**Plan ref:** Section 9.2 (AI Orchestrator panel), V1 #5
**What:** Collapsible bottom panel in workspace. Agent selection toggles (Scaffolder, Dark Mode, Content). Natural language input with streaming response display. Code block rendering in responses. Accept/reject/merge controls to apply AI output to editor. Conversation history per session.
**Security:**
- WebSocket connection authenticated via JWT (validated on connect)
- Conversation history stored per-user, per-project (no cross-user visibility)
- AI conversation logs retained 90 days maximum (Plan Section 8.3)
- Merge operation creates a new template version (audit trail)
**Verify:** Open chat → select Scaffolder → provide brief → streamed response appears → click "Apply" → code merged into editor.

### ~~2.6 Component Library v1 — Backend~~ DONE
**Plan ref:** Section V1 #4, 2.3 (Component Library module)
**What:** Seed 5-10 pre-tested Maizzle email components: header, footer, CTA button, hero block, product card, spacer, social icons, image block, text block, divider. Each with dark mode variant, Outlook fallback, version metadata, and compatibility matrix stub.
**Security:**
- Component content validated on upload (no script injection in HTML components)
- Version immutability: published versions cannot be modified, only new versions created
- Component ownership tracked (author, last modifier)
**Verify:** `GET /api/v1/components` returns 5-10 components. Each has at least one version. Dark mode variant accessible.

### ~~2.7 Component Library Browser UI~~ DONE
**Plan ref:** Section 9.2 (Component Library), V1 #4
**What:** Page at `/components`. Grid view with component preview thumbnails. Search by name, type, client scope. Component detail view: rendered preview (light + dark mode), HTML source, version history, compatibility matrix table, usage documentation.
**Security:**
- Component previews rendered in sandboxed iframes (same as live preview)
- Components scoped: Global visible to all, Client-scoped visible to project members only
**Verify:** Browse components. Search filters work. Click component → see detail view with preview + source + versions.

### ~~2.8 10-Point QA Gate System~~ DONE
**Plan ref:** Section 7.2 (QA Pipeline), V1 #7
**What:** QA trigger button in workspace toolbar. Runs `POST /api/v1/qa/run` with current template HTML. Results displayed as pass/fail checklist with details per check. Gate enforcement: warn/block on export if checks fail. Senior override with documented justification.
**Backend:** Repository layer (`QARepository`), `QAOverride` model with audit trail, 4 new API endpoints (`GET /results`, `GET /results/latest`, `GET /results/{id}`, `POST /results/{id}/override`), Alembic migration `d8a3f2b91c47`, 55 unit tests (37 checks + 16 service + conftest fixtures).
**Frontend:** "Run QA" button in workspace toolbar with loading state; `QAResultsPanel` right sidebar (320px) with overall score, status badge, failed/passed checks (collapsible), override info; `QACheckItem` rows with pass/fail icons, score bars, i18n labels with fallback; `QAOverrideDialog` (28rem) with check selection, justification textarea (min 10 chars), developer+ RBAC; 5 SWR hooks (`useQARun`, `useQAResult`, `useQALatest`, `useQAResults`, `useQAOverride`); local TypeScript types in `types/qa.ts`; 38 i18n keys; code-reviewed (5 fixes: stale dialog state, unhandled promise, memoization, i18n crash guard).
**Security:**
- QA results stored with template version (audit: which version was tested)
- Override requires admin/developer role + written justification (logged)
- Override audit entry includes who, when, why, which checks bypassed
**Verify:** Click "Run QA" → 10 checks execute → results display inline. Failing checks show detail. Override flow works with audit logging.

### ~~2.9 Raw HTML Export + Braze Connector UI~~ DONE
**Plan ref:** Section 3.1 (Connector Architecture), V1 #6
**What:** Export console at `/export` or inline in workspace. Platform selector: Raw HTML download, Braze Content Blocks push. Export preview shows what will be sent. Braze connector: configure API key (encrypted), push as Content Block with Liquid packaging.
**Frontend:** `ExportDialog` (32rem) with two tabs — Raw HTML (client-side Blob download via `URL.createObjectURL`) and Braze (two-phase: production build → `POST /api/v1/connectors/export` with `content_block_name`); state machine (idle→building→exporting→success|error) with retry; `ExportStatusBadge` + `ExportCard` for history grid; `useExportHistory()` hook via `useSyncExternalStore` + `sessionStorage` (max 100 records, cross-component sync without context provider); `/connectors` dashboard page with platform filter tabs (All/Braze/Raw HTML); Export button in workspace toolbar; Plug sidebar nav icon; middleware RBAC (all roles); ~25 i18n keys across `connectors` + `export` namespaces; all semantic Tailwind tokens.
**Security:**
- Braze API key encrypted with AES-256 before storage. Never returned in API responses. Never logged.
- Credential scope validation: verify API key has minimum required permissions before storing
- Export creates audit entry (who exported, when, where, which template version)
- Export blocked if QA gate has failures (unless overridden with justification)
**Verify:** Configure Braze credentials → export template → Content Block appears in Braze sandbox. Raw HTML download produces valid file.

### ~~2.10 RAG Knowledge Base Seeding~~ DONE
**Plan ref:** Section V1 #8, 13.3 (Data Bootstrapping)
**What:** Seed knowledge base with: Can I Email CSS support data (automated crawl), email dev best practices (curated entries), email client rendering quirks (team knowledge capture). Verify hybrid search (vector + fulltext) returns relevant results for email development queries.
**Implementation:** 20 curated markdown documents across 3 domains: `css_support` (8 files — layout, box model, typography, colors, borders, media queries, selectors, dark mode), `best_practices` (6 files — table layout, responsive, images, CTA buttons, accessibility, file size), `client_quirks` (6 files — Outlook Windows, Gmail, Apple Mail/iOS, Yahoo, Samsung, Outlook.com). Async seed command (`app/knowledge/seed.py`) processes documents through full RAG pipeline (extract → chunk → embed → store) with idempotency (skips existing by filename). Manifest-driven (`app/knowledge/data/seed_manifest.py`) with per-document metadata, tags, and domain classification. 109 unit tests validate manifest structure, file integrity, and content format.
**Security:**
- Knowledge entries classified: public (Can I Email), internal (best practices), confidential (client quirks)
- Client-specific quirks tagged with client_org_id (access-controlled)
- Embedding model runs on infrastructure [REDACTED] controls (no PII sent to external embedding APIs)
**Verify:** `make seed-knowledge` ingests all 20 documents. Search "Outlook dark mode background image" → get relevant Can I Email data + rendering quirk entries. Knowledge Agent uses RAG context in responses.

---

## Phase 3 — Sprint 3: Client Handoff + Polish (Plan: 1-2 weeks)

> **Sprint 3 Deliverable (Plan Section 16.4):** "Complete V1 that clients can log into for approvals, QA data is visible, and the team has a tool they want to use daily."

### ~~3.1 Client Approval Portal~~ DONE
**Plan ref:** Section V1 #9, 9.2 (QA Dashboard approval workflow)
**What:** Approval routes at `/approvals`. Viewer role login (scoped to assigned projects only). Live email preview (read-only, sandboxed iframe). Section-level feedback annotations (click to highlight, leave comment). Global feedback textarea. Approve/request changes buttons. Version comparison (diff between current and last-reviewed version). Email/Slack notification when review is ready. Time-stamped audit trail of all approvals, changes, feedback.
**Backend:** Added `GET /api/v1/approvals/?project_id=X` list endpoint and `GET /api/v1/email/builds/{build_id}` for preview HTML. 7 API endpoints total (list, create, get, decide, add feedback, list feedback, audit trail).
**Frontend:** `/approvals` list page with status filter tabs (All/Pending/Approved/Rejected/Revision); `/approvals/[id]` detail page with 2-column layout (60% sandboxed preview with viewport/dark mode toggles, 40% side panel with Feedback/Audit tabs); 6 components (`ApprovalStatusBadge`, `ApprovalCard`, `ApprovalPreview`, `ApprovalFeedbackPanel`, `ApprovalAuditTimeline`, `ApprovalDecisionBar`); 8 SWR hooks (`useApprovals`, `useApproval`, `useCreateApproval`, `useApprovalDecide`, `useApprovalFeedback`, `useAddFeedback`, `useApprovalAudit`, `useBuild`); decision bar with approve/reject/request-revision buttons (admin/developer RBAC via `useSession()`); "Submit for Approval" button in workspace toolbar; ClipboardCheck sidebar nav icon; middleware RBAC for all roles; ~40 i18n keys; all semantic Tailwind tokens.
**Security:**
- Viewer role: READ ONLY. Cannot edit templates, run builds, export, or access other modules
- Approval URLs use signed tokens (not guessable IDs) — expire after 30 days
- Feedback content sanitised (no script injection via comments)
- Notification emails contain no template content (link back to portal only)
- Audit trail immutable: entries can be created, never modified or deleted
- Session timeout: 30 minutes inactivity for viewer role
**Verify:** Client logs in with viewer credentials → sees only their project's emails → leaves section feedback → approves → audit trail shows complete history.

### ~~3.2 Rendering Intelligence Dashboard~~ DONE
**Plan ref:** Section V1 #11, 12.6 (Compound Innovation Effect)
**What:** Dashboard at `/intelligence` with QA quality trends, per-check analytics, and recent results. Client-side aggregation from `GET /api/v1/qa/results` (no backend aggregation endpoint needed).
**Frontend:** `/intelligence` page with 4 sections: `ScoreOverviewCards` (4-column grid: total runs, avg score, pass rate, overrides); `CheckPerformanceChart` (CSS horizontal bars showing avg score per QA check, sorted worst-first, colored by threshold — green >=80%, yellow >=50%, red <50%); `ScoreTrendBars` (CSS vertical bars of last 20 results' overall scores with pass/fail coloring); `RecentResultsTable` (paginated table with status badges, score, checks passed, date); "Email Client Rendering" placeholder card with "Coming Soon" badge (deferred to task 4.4 Litmus integration). `useQADashboard` hook fetches 50 results and computes all metrics via `useMemo`. `QADashboardMetrics` type in `types/qa.ts`. BarChart3 sidebar nav icon. Middleware RBAC (all roles). ~30 i18n keys in `intelligence` namespace. All semantic Tailwind tokens.
**Security:**
- Dashboard data aggregated — no individual subscriber data ever displayed
- Export dashboard as PDF requires developer+ role
- Analytics data retention: 12 months, then aggregated
**Verify:** Dashboard shows QA trends. Support matrix populates from accumulated QA results. Template quality scores calculate correctly.

### ~~3.3 Dashboard Homepage Enhancement~~ DONE
**Plan ref:** Section 9.2 (Dashboard)
**What:** Enhance Phase 1.1 dashboard with real data: project overview grid with status indicators, recent activity feed (builds, QA runs, exports, approvals), team workload summary, QA status at a glance (pass rate), quick-start template selection (from component library).
**Frontend:** Dashboard page rewritten with 4 stat cards (Total Projects, Components, QA Pass Rate with threshold coloring, Pending Approvals with warning state); Quality Overview card (2/3 width) with avg score, total runs, overrides count, mini trend dots (last 10 QA results pass/fail); Recent Activity feed (1/3 width) showing latest 5 QA runs with score and date; Project grid (top 3 with "View All" link); Quick Start card with "Open Workspace" + "Browse Components" action links. 6 existing SWR hooks used (`useProjects`, `useOrgs`, `useComponents`, `useQADashboard`, `useQAResults`, `useApprovals`); no new backend endpoints. ~20 new i18n keys in `dashboard` namespace. All semantic Tailwind tokens.
**Security:**
- Activity feed shows only actions on user's accessible projects
- No sensitive data in activity summaries (e.g., "Template exported to Braze" not "Template exported to Braze API key ending in ...xyz")
**Verify:** Dashboard shows real project data. Activity feed updates in near-realtime. Quick-start creates new template from component.

### ~~3.4 Error Handling, Loading States, UI Polish~~ DONE
**Plan ref:** Section 16.2 (Polish + Glue)
**What:** Skeleton loaders on all data-fetching pages. Toast notifications for async operations (build started, export completed, QA passed). Proper 404/403/500 error pages. Form validation with inline errors. Optimistic updates where safe. Offline detection.
**Frontend:** Shared `EmptyState` component (`components/ui/empty-state.tsx`) replacing 6 ad-hoc inline empty states across approvals, connectors, intelligence, components, knowledge pages; `ErrorState` integration on intelligence page and approval detail page; route-level `loading.tsx` skeletons for intelligence and connectors; improved approval detail skeleton matching 2-pane layout; `Loader2` spinner on login, persona create, and QA override submit buttons; non-semantic shadcn alias tokens fixed in `create-persona-dialog.tsx` and `qa-override-dialog.tsx` (`border-input`→`border-input-border`, `bg-background`→`bg-input-bg`, `placeholder:text-muted-foreground`→`placeholder:text-input-placeholder`, `focus:border-ring/ring-ring`→`focus:border-input-focus/ring-input-focus`, `accent-primary`→`accent-interactive`, `hover:bg-accent`→`hover:bg-surface-hover`, `bg-primary text-primary-foreground`→`bg-interactive text-foreground-inverse`); `fade-in` CSS animation (`@keyframes` + `--animate-fade-in` token) added to `tokens.css` and applied to content wrappers on 5 major pages; 403 unauthorized page already existed at `(dashboard)/unauthorized/page.tsx`.
**Security:**
- Error pages never expose stack traces, internal paths, or configuration
- 403 page: "You don't have access to this resource" — no detail about what the resource is
- API errors: structured error responses with error codes, not raw exception messages
- Client-side error boundary catches React crashes gracefully
**Verify:** Navigate to invalid URL → 404 page. Access forbidden resource → 403 page. Kill backend → graceful offline state. All forms validate before submit.

### ~~3.5 CMS + Nginx Docker Stack~~ DONE
**Plan ref:** Section 16.2 (Deployment), 10 (Infrastructure)
**What:** Get `cms` container building and healthy (pnpm install + next build + standalone output). Wire nginx reverse proxy: `/` → cms (port 3000), `/api/` → app (port 8891), `/ws` → app WebSocket. SSL termination ready (cert volume mount). Full `docker compose up` with all 7 services healthy.
**Implementation:** 3 `.dockerignore` files (root, cms/, maizzle-builder/) reducing build context from 392MB to 66MB; configurable `maizzle_builder_url` in `app/core/config.py`; `INTERNAL_API_URL` and `MAIZZLE_BUILDER_URL` env vars in docker-compose; nginx security hardening (blocked `.env`/`.git`/`alembic`/`__pycache__` paths returning 403, `include mime.types`); commented SSL server block + cert volume mount; CSP `connect-src 'self'` for nginx-proxied deployment; `NEXT_PUBLIC_DEMO_MODE=true` baked into CMS Docker build; Dockerfile shebang fix for UV_LINK_MODE=copy; `.env.example` documenting all deployment vars; Alembic seed migration fixes (timestamps, system user FK). All 7 services healthy: db, redis, migrate (exited 0), app, cms, maizzle-builder, nginx.
**Security:**
- Nginx: rate limiting (100 req/s per IP), request body size limit (10MB), header hardening (X-Frame-Options DENY, X-Content-Type-Options nosniff, Strict-Transport-Security, Referrer-Policy strict-origin-when-cross-origin)
- Nginx: block access to `.env`, `.git`, `alembic/`, `__pycache__/` paths
- All containers: non-root user, `no-new-privileges`, `cap_drop: ALL`, minimal `cap_add`
- Redis: password-protected, not exposed to host in production
- PostgreSQL: not exposed to host in production (only via Docker network)
- Health check endpoints public; all other endpoints require auth
**Verify:** `docker compose up` → all 7 services healthy. `curl localhost:80` → CMS frontend. `curl localhost:80/api/v1/health` → backend health. `curl localhost:80/.env` → 403.

---

## Phase 4 — V2 Roadmap (Plan Section 16.1: V2 Iterations)

### ~~4.8 Knowledge Base Search UI~~ DONE
**Plan ref:** Section 4.8 (RAG Knowledge Base — "Natural language search"), `.agents/plans/4.8-knowledge-base-search.md`
**What:** Frontend search page at `/knowledge`. Search-first UX with large search bar, domain filter pills (All/CSS Support/Best Practices/Client Quirks), tag filter pills, dual mode (search results with relevance scores vs document browse grid), pagination, document detail dialog (Content/Metadata tabs). Full demo mode data layer (20 documents, 15 tags, search with scoring). Completes PRD 4.8 acceptance criteria for "Natural language search" UI.
**Frontend:** `/knowledge` page with debounced search (400ms) triggering `POST /api/v1/knowledge/search`; browse mode with paginated `GET /api/v1/knowledge/documents` (domain/tag filtering); `KnowledgeSearchResultCard` (filename, domain badge, chunk preview, relevance score bar); `KnowledgeDocumentCard` (title, description, tags, domain, chunk count); `KnowledgeDocumentDialog` (max-w-3xl, Content/Metadata tabs with scrollable chunks); `use-knowledge.ts` with 6 SWR hooks (`useKnowledgeDocuments`, `useKnowledgeDocument`, `useKnowledgeDocumentContent`, `useKnowledgeDomains`, `useKnowledgeTags`, `useKnowledgeSearch`); `types/knowledge.ts` local types; demo data in `lib/demo/data/knowledge.ts` (20 docs, 3 domains, 15 tags, chunk content for 5 key docs); demo resolver routes for all 5 GET endpoints + 1 POST search; loading skeleton; BookOpen sidebar nav icon; middleware RBAC (all roles); ~30 i18n keys in `knowledge` namespace; all semantic Tailwind tokens.
**Security:**
- Knowledge document previews rendered as text only (no HTML execution)
- Search input debounced to prevent API flooding
- Domain/tag filters validated against known values in demo mode
**Verify:** `/knowledge` page loads with 20 document cards. Search "dark mode" returns relevant results with scores. Domain/tag filters narrow results. Document dialog shows chunks and metadata. `pnpm build` passes.

### ~~4.9 Smart Agent Memory~~ DONE
**Plan ref:** `.agents/plans/4.9-smart-agent-memory.md`
**What:** Conversation history tab in workspace chat panel with session persistence, search, and restore.
**Frontend:** `ChatSession` and `ChatMessage` types in `types/chat-history.ts`; `useChatHistory` hook with `sessionStorage` persistence; `SessionCard` component with timestamp, message count, preview; session list with search/filter; restore previous conversations; 3 components in `components/workspace/chat/`; ~15 i18n keys in `workspace` namespace.
**Verify:** Chat history tab shows previous sessions. Search filters sessions. Restoring a session loads messages. `pnpm build` passes.

### ~~4.10 Version Comparison Dialog~~ DONE
**Plan ref:** `.agents/plans/4.10-version-comparison.md`
**What:** Side-by-side template version diff in approval portal for visual comparison.
**Frontend:** `VersionCompareDialog` (max-w-7xl) with dual sandboxed iframe previews; version selector dropdowns; auto-selects latest two versions; changelog and date metadata; loading/empty states; `useTemplateVersions` hook; ~12 i18n keys in `approvals` namespace.
**Verify:** "Compare Versions" button appears on approval detail page. Dialog opens with two versions side by side. Dropdown changes versions. `pnpm build` passes.

### ~~4.11 Custom Persona Creation~~ DONE
**Plan ref:** `.agents/plans/4.11-custom-persona-creation.md`
**What:** Dialog form enabling users to create custom email client test profiles.
**Frontend:** `CreatePersonaDialog` (max-w-[28rem]) with 7 form fields matching `PersonaCreate` schema; two-column grid layout; slug auto-generation; viewport width validation (200-2000px); email client dropdown (8 options); demo mode mock via mutation-resolver; auto-selects new persona in `PersonaSelector`; ~16 i18n keys in `workspace` namespace.
**Verify:** "Create Persona" menu item in persona dropdown. Dialog submits and new persona appears. `pnpm build` passes.

### ~~4.12 Exportable Intelligence Reports~~ DONE
**Plan ref:** `.agents/plans/4.12-exportable-reports.md`
**What:** Export button on intelligence dashboard for client presentation reports.
**Frontend:** `ExportReportMenu` dropdown with Print/PDF (`window.print()`) and CSV export (client-side Blob download with overview metrics, check performance, quality trend); `@media print` styles in `tokens.css`; ~6 i18n keys in `intelligence` namespace.
**Verify:** Export dropdown renders on intelligence page. Print opens browser dialog. CSV downloads with correct data. `pnpm build` passes.

### 4.13 Agent Harness Engineering (Phase 1: Blueprint Engine ✅)
**Plan ref:** Section 5.1 (Agent Architecture), harnessing_agents.txt (Industry Research)
**What:** Implement the agent harness layer — the execution loop, progressive disclosure, and self-verification scaffolding that surrounds each AI agent. The harness is model-agnostic infrastructure that transforms agents from single-pass generators into iterative, self-correcting production workers. Based on patterns from Claude Code, Cursor, Manus, SWE-Agent, and the Four Disciplines Framework.
**Phase 1 Implementation (Blueprint State Machine):** `app/ai/blueprints/` — State machine engine interleaving deterministic nodes (QA gate, Maizzle build, Braze export) with agentic nodes (scaffolder, dark mode), implementing bounded self-correction (max 2 rounds), progressive context hydration, and recovery routing. Shared utilities extracted to `app/ai/shared.py`. `POST /api/v1/blueprints/run` endpoint (3/min rate limit, admin/developer RBAC). Campaign blueprint graph: scaffolder → qa_gate → (pass) maizzle_build → export / (fail) recovery_router → fixer → qa_gate loop. 22 files, 27 tests, all passing lint + types.

**Harness Components:**

1. **TAOR Execution Loop (Think-Act-Observe-Repeat)** — Replace single-pass agent execution with an iterative loop: agent thinks about the task, acts (generates output), observes results (runs validation), and repeats if validation fails. Each agent gets a configurable max iteration count (default: 3) and exit conditions.

2. **PreCompletionChecklist Middleware** — Intercepts agent "done" signals and forces a final verification pass against the original task specification. Prevents the "Ralph Wiggum Loop" where agents declare victory without testing. For example: Scaffolder generates HTML → harness runs QA checks automatically → if accessibility fails, error logs fed back to agent for self-correction.

3. **Progressive Disclosure (Context Economy)** — Lazy-load agent skills and knowledge instead of pre-loading everything into context. Agent receives only tool names as static context; full definitions fetched on-demand when the agent selects a tool. Knowledge base queries scoped to the current check/task, not the entire corpus. Target: 26x token efficiency improvement (based on industry benchmarks). Prevents "Context Rot" where agents lose track of goals in long sessions.

4. **Linter-Gated Guardrails** — Deterministic safety nets that don't rely on LLM reasoning:
   - HTML structure validation runs automatically on every agent file save (rejected if invalid)
   - Risk classification via lightweight model (Haiku) auditing commands before execution
   - Brand compliance rules enforced as hard constraints ("Must-Nots" like "never modify brand-reserved colours")
   - QA gate results fed back as harness-level rejections, not just suggestions

5. **Progress Log & Task Decomposition** — `agent-progress.json` per session where agents record features tested, bugs fixed, and decisions made. Long tasks decomposed into 2-hour independently verifiable sub-tasks. Prevents "lost in the middle" attention degradation on long trajectories.

6. **Model-Agnostic Escalation** — Harness-level routing: local LLM (Ollama/vLLM) handles 70-90% of routine tasks → harness monitors output confidence → auto-escalates to frontier model (Claude Opus) when confidence drops below threshold or when multi-step rendering conflicts detected. Swap models without code changes via the existing provider registry.

**Harness Benefits Table:**

| Harness Pattern | QA Agent Impact | Strategic Value |
|-----------------|----------------|-----------------|
| TAOR Loop | Agents iterate on bug fixes autonomously | Reduces manual developer rework |
| Progressive Disclosure | Agents only see tokens needed for current test | 26x token efficiency improvement |
| Constraint Architecture | Defines "Must-Nots" (e.g., brand-reserved colours) | 100% brand compliance |
| Task Decomposition | Full-campaign audits split into verifiable sub-tasks | Increases reliability and speed |
| Linter Gates | Invalid HTML rejected before QA stage | Catches errors deterministically |
| Model Escalation | Routine tasks local, complex tasks cloud | Reduces API cost by 70-90% |

**Security:**
- Harness-level audit trail for every agent iteration (who triggered, what changed, why it looped)
- Escalation decisions logged (which model, why escalated, confidence scores)
- Brand constraint violations blocked deterministically — never delegated to LLM judgement
- Progress logs scoped to project (no cross-project leakage)
**Verify:** Agent executes with TAOR loop (visible iteration count in UI). PreCompletionChecklist catches intentionally broken HTML. Progressive disclosure reduces token usage measurably. Local → cloud escalation triggers on complex tasks. Progress log persists across sessions.

### ~~4.1 Remaining 6 AI Agents~~ DONE
**Plan ref:** Section 5.1 (Agent Architecture), `.agents/plans/outlook-fixer-agent.md`
**Prerequisite:** Complete Phase 7 Step 1 (blueprint infrastructure: 7.1 + 7.3 + 7.4) and Step 2 (retrofit existing agents) BEFORE building new agents. This ensures every new agent inherits `AgentHandoff` schemas, confidence scoring, and component context from day one — no retrofitting needed.

**Build Order (prioritised):**
1. ~~**Outlook Fixer**~~ DONE — SKILL.md + 4 L3 skill files, service/prompt/schemas, blueprint node, recovery router integration, 12 synthetic test cases, 5-criteria judge, dry-run verified (535 tests pass)
2. ~~**Accessibility Auditor**~~ DONE — SKILL.md + 4 L3 skill files (wcag_email_mapping, alt_text_guidelines, color_contrast, screen_reader_behavior), service/prompt/schemas, blueprint node, recovery router integration, 10 synthetic test cases, 5-criteria judge (wcag_aa_compliance, alt_text_quality, contrast_ratio_accuracy, semantic_structure, screen_reader_compatibility), dry-run verified (540 tests pass)
3. ~~**Personalisation Agent**~~ DONE — SKILL.md + 4 L3 skill files (braze_liquid, sfmc_ampscript, adobe_campaign_js, fallback_patterns), service/prompt/schemas, blueprint node, recovery router integration, 12 synthetic test cases (4 Braze, 4 SFMC, 3 Adobe Campaign, 1 mixed), 5-criteria judge (syntax_correctness, fallback_completeness, html_preservation, platform_accuracy, logic_match), dry-run verified (540 tests pass)
4. ~~**Code Reviewer**~~ DONE — SKILL.md + 4 L3 skill files (redundant_code, css_client_support, nesting_validation, file_size_optimization), service/prompt/schemas, blueprint node, recovery router integration (css_support + file_size routed to code_reviewer), 12 synthetic test cases, 5-criteria judge (issue_genuineness, suggestion_actionability, severity_accuracy, coverage_completeness, output_format), dry-run verified (542 tests pass)
5. ~~**Knowledge Agent**~~ DONE — SKILL.md (pre-existing L1+L2) + 4 L3 skill files (rag_strategies, email_client_engines, can_i_email_reference, citation_rules), service/prompt/schemas, blueprint node (advisory — not in QA→recovery loop), 10 synthetic test cases (CSS property support, best practices, client quirks, comparisons, troubleshooting, edge cases), 5-criteria judge (answer_accuracy, citation_grounding, code_example_quality, source_relevance, completeness), dry-run verified (542 tests pass)
6. ~~**Innovation Agent**~~ DONE — SKILL.md (pre-existing L1+L2) + 4 L3 skill files (css_checkbox_hacks, amp_email, css_animations, feasibility_framework), service/prompt/schemas, blueprint node (advisory — not in QA→recovery loop), 10 synthetic test cases, 5-criteria judge (technique_correctness, fallback_quality, client_coverage_accuracy, feasibility_assessment, innovation_value), dry-run verified (191 AI tests pass)

#### Eval-First + Skills Build Pattern (applies to ALL agents)

Based on Anthropic's [Agent Skills](https://claude.com/blog/equipping-agents-for-the-real-world-with-agent-skills) pattern and real eval data from Phase 5.4-5.8 live execution. Each new agent follows this workflow:

```
1. SKILL.md first    → Write domain skill with progressive disclosure (L1 metadata, L2 instructions, L3+ reference files)
2. Synthetic data    → 10-12 dimension-based test cases in evals/synthetic_data_{agent}.py
3. Judge prompts     → 3-5 binary pass/fail criteria in evals/judges/{agent}.py
4. Generate traces   → make eval-run --agent {agent}
5. Error analysis    → make eval-analysis → identify skill gaps
6. Iterate skill     → Refine SKILL.md targeting failure clusters → re-eval → measure delta
7. Baseline          → make eval-baseline when pass rates stabilise
```

**Skill Structure (per agent):**
```
app/ai/agents/{agent}/
├── service.py          # Agent code — loads SKILL.md at runtime
├── prompt.py           # System prompt (thin — references SKILL.md)
├── schemas.py          # Input/output schemas
├── SKILL.md            # L1: YAML frontmatter (name, description) + core instructions
├── skills/             # L3+: Progressive disclosure reference files
│   ├── {topic}.md      # Loaded on-demand when agent detects relevance
│   └── ...
└── evals/              # Agent-specific eval data (shared runner/judges)
```

**Key principle:** Skills are testable via the eval system. Each skill file's impact is measurable: add skill → re-eval → check if target criteria improve. No guessing.

**Existing skill asset:** `app/ai/agents/html-email-innovation.skill` — 668-line production skill covering Outlook bug fixes (15 patterns), VML, dark mode, Braze/Liquid, accessibility, responsive layouts. To be decomposed into per-agent SKILL.md files.

**Real eval failure data informing agent priorities:**
| Eval Failure (Phase 5.4-5.8) | Target Agent | SKILL.md Source |
|---|---|---|
| scaffolder:mso_conditional_correctness 0% | Outlook Fixer | html-email-innovation.skill Parts 1-2 |
| scaffolder:accessibility_baseline 8% | Accessibility Auditor | html-email-innovation.skill Part 4 |
| scaffolder:dark_mode_readiness 25% | (Dark Mode agent skill refinement) | html-email-innovation.skill Section 5 |
| dark_mode:html_preservation 10% | (Dark Mode agent skill refinement) | html-email-innovation.skill Section 5 |
| content:operation_compliance 57% | (Content agent skill refinement) | — |

### ~~4.2 Additional CMS Connectors~~ DONE
**Plan ref:** Section 3.1 (~2-3 days each), `.agents/plans/4.2-additional-cms-connectors.md`
**What:** Add SFMC, Adobe Campaign, and Taxi for Email backend connectors following the Braze pattern. All three are placeholder implementations (mock API calls) matching the Braze style.
**Backend:** `ConnectorProvider` Protocol in `app/connectors/protocol.py` for type-safe dispatch; `SUPPORTED_CONNECTORS` registry mapping connector type strings to provider classes with lazy instantiation and caching; 3 new connector packages: `app/connectors/sfmc/` (SFMCConnectorService — Content Builder Content Area with AMPscript packaging), `app/connectors/adobe/` (AdobeConnectorService — delivery content fragments with Adobe IMS packaging), `app/connectors/taxi/` (TaxiConnectorService — Taxi Syntax-wrapped templates); each with schemas + service following Braze pattern; 16 unit tests (4 protocol conformance + 12 provider tests); demo mutation resolver updated for per-connector mock IDs.
**Security:**
- All connector services satisfy `ConnectorProvider` Protocol (runtime-checkable)
- No credential storage yet (placeholder implementations) — AES-256 encryption deferred to real API integration
- Export audit trail via existing `ExportRecord` model (unchanged)
**Verify:** `make test` passes (304 tests). All 4 connectors dispatch correctly via `POST /api/v1/connectors/export`. Frontend export dialog works with sfmc/adobe_campaign/taxi in demo mode. `connector_type` validation returns 422 for unsupported types.

### ~~4.3 Design Sync — Multi-Provider Backend + Frontend Rename~~ DONE
**Plan ref:** Section 4 (Design Tool Integration), `.agents/plans/figma-design-sync.md`
**What:** Full `app/design_sync/` VSA module with multi-provider architecture. `DesignSyncProvider` Protocol with 3 implementations: `FigmaDesignSyncService` (real Figma REST API — `httpx` calls to `/v1/files/{key}` and `/v1/files/{key}/styles`, parses colors/typography/spacing), `SketchDesignSyncService` (stub), `CanvaDesignSyncService` (stub). Fernet-encrypted PAT storage (PBKDF2-derived from `DESIGN_SYNC__ENCRYPTION_KEY` or `AUTH__JWT_SECRET_KEY`). `DesignConnection` + `DesignTokenSnapshot` SQLAlchemy models with cascade delete. BOLA enforcement via `verify_project_access()` on single-resource ops + user-scoped list queries (admin sees all projects, others see owned + member projects). 6 REST endpoints at `/api/v1/design-sync/` with auth + rate limiting. Frontend renamed from `/figma` → `/design-sync` with provider filter tabs (All/Figma/Sketch/Canva), generic connect dialog with provider dropdown, provider icons. All hooks/types/components/demo data/i18n updated. 19 backend tests, Alembic migration.
**Backend:** `app/design_sync/` — `protocol.py` (Protocol + dataclasses), `crypto.py` (Fernet encrypt/decrypt), `models.py`, `schemas.py` (field mapping for frontend compat), `repository.py`, `service.py` (provider registry, BOLA), `routes.py`, `exceptions.py`; `figma/service.py` (real API), `sketch/service.py` (stub), `canva/service.py` (stub); `tests/test_service.py` (19 tests); `DesignSyncConfig` in `app/core/config.py`; `cryptography>=44.0.0` in `pyproject.toml`.
**Frontend:** `/design-sync` page with `DesignConnectionCard`, `DesignStatusBadge`, `DesignTokensView`, `ConnectDesignDialog`, `ProviderIcon` components; 6 SWR hooks in `use-design-sync.ts`; `types/design-sync.ts`; demo data with `provider` field; i18n `designSync` namespace; nav link updated.
**Remaining:** Change webhook handling, plugin ecosystem (Emailify, Email Love, MigmaAI), pagination on list endpoint.
**Verify:** `/design-sync` page loads. Connect dialog creates connection with provider selection. Sync triggers real Figma API (with valid PAT). Design tokens extracted. `make check` passes (lint, types, 19 tests).

### ~~4.4 Litmus / Email on Acid API Integration~~ DONE
**Plan ref:** Section 7.2 (Cross-Client Render), `.agents/plans/4.4-litmus-eoa-integration.md`
**What:** New `app/rendering/` VSA module for cross-client rendering tests via Litmus and Email on Acid APIs. `RenderingProvider` Protocol (same pattern as `ConnectorProvider`) with `submit_test`, `poll_status`, `get_results` methods. Two provider implementations: `litmus/` and `eoa/` (placeholder APIs). `RenderingTest` + `RenderingScreenshot` DB models. Repository with eager-loaded screenshots, filtered list/count, pending poller query. `RenderingService` with circuit breaker (`CircuitBreaker` from `app/core/resilience`), visual regression comparison (per-client diff percentage with 2% threshold). `RenderingConfig` in `app/core/config.py` (`RENDERING__PROVIDER`, `RENDERING__LITMUS_API_KEY`, `RENDERING__EOA_API_KEY`, polling settings). 4 REST endpoints under `/api/v1/rendering/` (submit, list, get, compare) with auth + rate limiting. 12 unit tests (316 total).
- ~~API integration for 20+ client rendering screenshots~~ DONE
- ~~Visual regression detection~~ DONE
- ~~Rendering report generation~~ DONE
- ~~Frontend UI alignment with backend schemas~~ DONE — Types, hooks, demo data aligned to backend `RenderingTestResponse`/`ScreenshotResult`; 6 components updated + 1 new (`VisualRegressionDialog`); API paths fixed (`/rendering/` not `/renderings/`); async polling, pagination, HTML input, visual regression comparison UI

### ~~4.5 Advanced Features~~ DONE
- ~~Real-time collaborative editing (CRDT/OT — Yjs + y-codemirror.next, demo mode with simulated collaborator)~~ DONE
- ~~Localisation engine (6 locale stubs, cookie-based switching, RTL support, translation management table)~~ DONE
- ~~Per-client brand guardrails (brand settings page, CodeMirror linter extension, toolbar violations badge)~~ DONE
- ~~AI image generation (workspace dialog, style presets, gallery, insert-into-template)~~ DONE
- ~~Visual Liquid builder UI (@dnd-kit drag-and-drop, regex parser/serializer, Code/Visual tab switching)~~ DONE
- ~~Client brief system integration (Jira/Asana/Monday.com connection cards, brief items, import-to-project)~~ DONE

---

## Phase 5 — Agent Evaluation System (Specification Engineering Layer)

> **Objective:** Build the "Evaluation Design" primitive from the Four Disciplines framework (Section 06 of pitch). **This eval framework applies to ALL 9 agents** — the 3 currently implemented and the 6 planned. Every agent that enters the Hub must pass through the same eval pipeline before it touches production work. No agent ships without: synthetic test data, an LLM judge, human-calibrated baselines, and a regression gate. This is not optional infrastructure — it is the mechanism that makes Specification Engineering real.

> **Applies to ALL agents:**
> | # | Agent | Status | Eval Status |
> |---|-------|--------|-------------|
> | 1 | **Scaffolder** | Implemented | Synthetic data created (12 cases) |
> | 2 | **Dark Mode** | Implemented | Synthetic data created (10 cases) |
> | 3 | **Content** | Implemented | Synthetic data created (14 cases) |
> | 4 | **Outlook Fixer** | Implemented (4.1) | 12 synthetic cases, 5-criteria judge |
> | 5 | **Accessibility Auditor** | Implemented (4.1) | 10 synthetic cases, 5-criteria judge |
> | 6 | **Personalisation Agent** | Implemented (4.1) | 12 synthetic cases, 5-criteria judge |
> | 7 | **Code Reviewer** | Implemented (4.1) | 12 synthetic cases, 5-criteria judge |
> | 8 | **Knowledge Agent** | Implemented (4.1) | 10 synthetic cases, 5-criteria judge |
> | 9 | **Innovation Agent** | Implemented (4.1) | 10 synthetic cases, 5-criteria judge |
>
> **Rule: No agent goes to production without completing steps 5.1-5.5 for that agent.** Steps 5.6-5.8 apply system-wide.

> **Progress:**
> - [x] Eval framework scaffolded (`app/ai/agents/evals/`)
> - [x] Dimensions defined for Scaffolder, Dark Mode, Content
> - [x] Synthetic data created for 3 implemented agents (36 test cases total)
> - [x] Real-world email patterns sourced (Litmus, MailChimp, Parcel.io, email-darkmode repo, Mailmeteor)
> - [x] Eval runner CLI created (`runner.py`)
> - [ ] 5.1 — Review & harden test data (security audit)
> - [x] 5.2 — Write LLM judge prompts (3 of 9 agents)
> - [ ] 5.3 — Run first eval batch & collect traces
> - [x] 5.4 — Error analysis tooling built (`error_analysis.py` CLI, failure clustering, pass rate computation; 11 unit tests)
> - [x] 5.5 — Judge calibration tooling built (`calibration.py` TPR/TNR + `scaffold_labels.py` prefilled label templates; 11 unit tests)
> - [x] 5.6 — QA gate calibration tooling built (`qa_calibration.py` check-vs-human agreement; 9 unit tests)
> - [x] 5.7 — Blueprint pipeline eval runner built (`blueprint_eval.py` with 5 test briefs; 8 unit tests)
> - [x] 5.8 — Regression detection built (`regression.py` baseline comparison + `make eval-check` CI gate; 10 unit tests)
> - [x] 5.4-5.8 — **Dry-run pipeline**: `--dry-run` flag on runner/judge/blueprint CLIs; `mock_traces.py` deterministic generators; `make eval-dry-run` exercises full pipeline without LLM; `make eval-full`/`eval-calibrate`/`eval-qa-calibrate` targets; 9 integration tests (58 eval tests total)
> - [x] 5.4-5.8 — **Live execution hardening**: `verify_provider.py` pre-flight check (`make eval-verify`); incremental JSONL writing (crash-safe); `--skip-existing` resume flag on runner + judge_runner; `eval-run` auto-verifies provider before running
> - [x] 5.4-5.8 — **Live execution** (2026-03-09): 36 traces + 36 verdicts via `anthropic:claude-sonnet-4`. Baseline established (16.7% overall pass rate). Blueprint evals 5/5 passed (100% QA with self-correction). Human labeling pending (540 rows in `traces/*_human_labels.jsonl`)
> - [x] Eval data for Outlook Fixer — 12 synthetic cases, 5-criteria judge (`OutlookFixerJudge`), blueprint node + recovery router integration
> - [x] Eval data for Accessibility Auditor — 10 synthetic cases, 5-criteria judge (`AccessibilityJudge`), blueprint node + recovery router integration
> - [x] Eval data for Personalisation Agent — 12 synthetic cases, 5-criteria judge (`PersonalisationJudge`), blueprint node + recovery router integration
> - [x] Eval data for Code Reviewer — 12 synthetic cases, 5-criteria judge (`CodeReviewerJudge`), blueprint node + recovery router integration
> - [x] Eval data for Knowledge Agent — 10 synthetic cases, 5-criteria judge (`KnowledgeJudge`), advisory blueprint node (no recovery router — Q&A agent)
> - [x] Eval data for Innovation Agent — 10 synthetic cases, 5-criteria judge (`InnovationJudge`), advisory blueprint node (no recovery router — generator agent)

### Per-Agent Eval Requirements (Mandatory for ALL 9 Agents)

Every agent — whether built now or in task 4.1 — must have:
1. **Synthetic test data** (`synthetic_data_<agent>.py`) — 10-12 dimension-based test cases with real-world inputs
2. **LLM judge prompt** (`judge_<agent>.py`) — binary pass/fail on 3-5 subjective criteria the QA gate can't catch
3. **Human calibration** — 20 expert-labeled outputs, TPR > 0.85, TNR > 0.80
4. **Adversarial test cases** — 1-2 prompt injection / edge case inputs per agent
5. **Regression baseline** — known-good scores stored in version control

### Current State (3 of 9 Agents)
- Synthetic test data created for 3 implemented agents: `app/ai/agents/evals/`
  - `synthetic_data_scaffolder.py` — 12 test cases (MSO ghost tables, VML, Gmail clipping, vague/contradictory briefs)
  - `synthetic_data_dark_mode.py` — 10 test cases with 5 real-world HTML templates (Outlook data-ogsc/ogsb, VML preservation, already-dark, brand-heavy)
  - `synthetic_data_content.py` — 14 test cases across all 8 operations (spam triggers from real blocklists, PII detection, healthcare/finance compliance)
  - `dimensions.py` — failure-prone dimension definitions per agent
  - `runner.py` — CLI runner that outputs JSONL traces
- Real-world email patterns sourced from: Litmus, MailChimp Design Reference, Parcel.io, email-darkmode repo, StackOverflow Design, Mailmeteor spam lists
- Binary LLM judges implemented for 4 agents: `app/ai/agents/evals/judges/` package with `ScaffolderJudge` (5 criteria), `DarkModeJudge` (5 criteria), `ContentJudge` (5 criteria), `OutlookFixerJudge` (5 criteria: mso_conditional_correctness, vml_wellformedness, html_preservation, fix_completeness, outlook_version_targeting); shared `Judge` Protocol, `parse_judge_response()` with markdown fence handling; `JUDGE_REGISTRY` for dispatch; `judge_runner.py` CLI with batched execution and rate limiting
- **All 9 agents have eval data** — synthetic test cases + LLM judges for every agent

### 5.1 Review & Harden Synthetic Test Data (Scaffolder, Dark Mode, Content)
**What:** Review the 36 synthetic test cases for completeness, realism, and security. Verify no real client data or credentials leaked into test fixtures. Add 2-3 missing edge cases per agent identified during review. Ensure all HTML fixtures are self-contained (no external resource dependencies).
**Applies to:** Scaffolder, Dark Mode, Content (current 3). **Repeat this step for each new agent built in task 4.1.**
**Security:**
- Audit all test HTML for embedded URLs (must be placehold.co or example.com only)
- Verify no real brand names, client data, or API keys in any fixture
- Test inputs must not contain prompt injection attempts (add 1-2 adversarial test cases per agent)
**Verify:** All 36+ test cases load without errors. `python -m app.ai.agents.evals.runner --agent all --output traces/` executes (even if agents return errors due to no LLM configured). No real client data in any fixture.

### 5.2 Write LLM Judge Prompts — Binary Pass/Fail (ALL Agents)
**What:** Following the evals-skills `write-judge-prompt` methodology, create binary pass/fail LLM judges for subjective quality criteria that the 10-point QA gate cannot catch. **One judge per agent (9 total when complete)**, each evaluating 3-5 subjective criteria.
**Judges for currently implemented agents:**
- **Scaffolder Judge:** Does the HTML faithfully implement the brief? Is the layout email-client appropriate (not web-only patterns)? Are MSO conditionals correctly structured?
- **Dark Mode Judge:** Are dark mode colors visually coherent (not just technically present)? Is the original HTML preserved without structural changes? Are Outlook selectors complete?
- **Content Judge:** Is the copy compelling and on-brand? Does the tone match the request? Are spam triggers absent while maintaining persuasiveness?
**Judges for planned agents (create when each agent is built):**
- **Outlook Fixer Judge:** Are MSO conditionals correctly targeted? Is VML well-formed? Are existing styles preserved?
- **Accessibility Judge:** Is generated alt text meaningful (not just "image")? Are WCAG AA violations correctly identified and prioritised?
- **Personalisation Judge:** Is Liquid/AMPscript syntactically correct? Does the logic match the natural language intent? Are edge cases (null data, empty arrays) handled?
- **Code Reviewer Judge:** Are flagged issues genuine (not false positives)? Are suggestions actionable? Is severity appropriate?
- **Knowledge Agent Judge:** Is the answer grounded in retrieved context (faithful)? Is it relevant to the query? Are source citations accurate?
- **Innovation Agent Judge:** Is the feasibility assessment accurate? Is the fallback strategy robust? Does audience coverage estimate match reality?
**Security:**
- Judge prompts must NOT include the agent's system prompt (information leakage)
- Judge prompts must NOT make external API calls
- Judge outputs must be structured JSON (pass/fail + reasoning), never freeform
**Verify:** Each judge prompt produces consistent binary pass/fail on 5 hand-labeled examples. Inter-run agreement > 90% on the same inputs.

### 5.3 Run First Eval Batch & Collect Traces (Scaffolder, Dark Mode, Content)
**What:** Configure a working LLM provider (can be local Ollama or cloud API). Run all 36 test cases through the 3 implemented agents. Collect full JSONL traces: input, output, timing, model, QA results. Store in `traces/` directory (gitignored). **Repeat for each new agent as it's built.**
**Security:**
- `traces/` directory added to `.gitignore` (may contain LLM outputs)
- Trace files must not be committed to version control
- LLM API keys used for eval only — separate from production keys if possible
- Rate limit eval runs (not all 36 at once — batch of 5 with delays)
**Verify:** 36 JSONL trace files generated. Each trace has: id, agent, input, output, timing, error status. No API key or credential in trace data.

### 5.4 Error Analysis on Collected Traces (ALL Agents)
**What:** Following the evals-skills `error-analysis` methodology, manually read through all traces. Categorise failures into a taxonomy per agent (e.g., "layout wrong", "MSO missing", "color contrast failed", "brief misinterpreted"). Compute failure rates per category. Prioritise the top 3 failure modes for each agent. **This step runs for every agent — it is how we discover what each agent gets wrong.**
**Tooling built:** `app/ai/agents/evals/error_analysis.py` — CLI that reads verdict JSONL, clusters failures by (agent, criterion), computes per-criterion pass rates, identifies top 3 failure modes. Run via `make eval-analysis`. 11 unit tests.
**Security:**
- Error analysis results stored as structured data (not freeform text that could leak into prompts)
- Failure taxonomy scoped to technical categories (no client-identifying information)
**Verify:** Failure taxonomy document with categories, counts, and examples. Top 3 failure modes per agent identified with severity rating.

### 5.5 Calibrate Judges Against Human Labels (ALL Agents)
**What:** Following the evals-skills `validate-evaluator` methodology, have a domain expert (email developer) manually label 20 agent outputs per agent as pass/fail. Run the LLM judges on the same outputs. Compute TPR (true positive rate) and TNR (true negative rate). Target: TPR > 0.85, TNR > 0.80. **Every agent needs this — no agent's judge is trusted without human calibration.**
**Tooling built:** `app/ai/agents/evals/scaffold_labels.py` — generates prefilled JSONL label templates from traces+verdicts (user fills `human_pass` true/false). `app/ai/agents/evals/calibration.py` — CLI that computes TPR/TNR per criterion against human labels. Run via `make eval-labels` then manual labeling. One file per agent containing both judge + QA criteria. 11 unit tests.
**Security:**
- Human labels stored separately from traces (no contamination)
- Labeling interface does not expose system prompts or agent internals
- Label data is project-scoped and access-controlled
**Verify:** Confusion matrix per judge. TPR and TNR meet targets. If not, iterate on judge prompts and re-calibrate.

### 5.6 Calibrate the 10-Point QA Gate (System-Wide)
**What:** Using the human-labeled outputs from 5.5, measure the QA gate's agreement with human judgment across all agents. Identify which of the 10 checks have low precision or recall. Adjust thresholds or add new checks where the gate misses failures that humans catch.
**QA checks to calibrate:** html_validation, brand_compliance, css_support, image_optimization, accessibility, dark_mode, spam_score, fallback, file_size, link_validation
**Tooling built:** `app/ai/agents/evals/qa_calibration.py` — CLI that runs all 10 QA checks on trace HTML, compares pass/fail against human labels, reports per-check agreement rate and flags checks <75% for tuning. 9 unit tests.
**Security:**
- QA gate threshold changes tracked in version control with justification
- No QA check bypassed without the existing override + audit trail mechanism
**Verify:** Per-check precision and recall against human labels. At least 8/10 checks have precision > 0.80. Any underperforming checks documented with improvement plan.

### 5.7 Blueprint Pipeline Eval Runner (System-Wide)
**What:** Extend the eval runner to test the full Blueprint Engine end-to-end. Feed briefs through `BlueprintEngine.run()` and capture the entire graph execution: which nodes ran, iteration counts, QA retries, recovery routing decisions, final convergence. Test the self-correction loop: inject briefs that will fail QA on first pass and verify the pipeline recovers within 2 rounds. **As new agents join the blueprint graph, their nodes are covered by this runner.**
**Tooling built:** `app/ai/agents/evals/blueprint_eval.py` — CLI with 5 test briefs (happy_path_simple, dark_mode_recovery, complex_layout_retry, vague_brief, accessibility_heavy). Captures per-node traces with step/retry counts, token usage, elapsed time. 8 unit tests.
**Security:**
- Blueprint traces include token usage (cost tracking)
- Escalation events logged (when pipeline gives up and escalates to human)
- No infinite loop possible (MAX_TOTAL_STEPS=20 already enforced)
**Verify:** 5 end-to-end blueprint traces collected. At least 2 show successful self-correction (QA fail → recovery → pass). Escalation triggers correctly on intentionally unfixable inputs.

### 5.8 Automated Regression Suite (ALL Agents, System-Wide)
**What:** Wire eval runner into CI/CD. On model update or prompt change: run 10 representative test cases per agent, evaluate with judges, compare scores to baseline. Block deployment if pass rate drops > 10% from baseline. **This gate covers every agent in the system — when a new agent is added, its test cases and judge are added to the regression suite.** This is the "Evaluation Design" primitive in action.
**Tooling built:** `app/ai/agents/evals/regression.py` — CLI that compares current pass rates against stored baseline with configurable tolerance (default 10%). `--update-baseline` flag. Exits code 1 on regression (CI gate). `make eval-check` combines analysis + regression. 10 unit tests. **Note:** CI integration deferred — Makefile targets only for now.
**Security:**
- CI/CD eval runs use dedicated API keys with eval-only permissions
- Baseline scores stored in version control (not in database)
- Regression alerts go to team channel, not to clients
- Eval results never exposed in production API responses
**Verify:** Change a prompt → CI runs eval suite → regression detected → deployment blocked with report. Restore prompt → eval passes → deployment proceeds.

### Per-Agent Eval Specifications (Reference for Task 4.1)

**When building each of the remaining 6 agents, complete steps 5.1-5.5 for that agent before merging to main.**

| Agent | Eval Type | Key Dimensions | Judge Criteria |
|-------|-----------|----------------|----------------|
| **Outlook Fixer** | Code-based (MSO structure) + judge | Input complexity, Outlook version targeting, VML usage | MSO targeting correct? VML well-formed? Existing styles preserved? |
| **Accessibility Auditor** | Code-based (WCAG rules) + judge (alt text) | Violation severity, image context, heading structure | Alt text meaningful? Violations correctly identified? Severity appropriate? |
| **Personalisation Agent** | Code-based (syntax) + judge (logic) | ESP platform, conditional complexity, data source types | Syntax valid? Logic matches intent? Edge cases handled? |
| **Code Reviewer** | Mostly code-based (linting) | Code smell types, file size, CSS support matrix | Issues genuine? Suggestions actionable? Severity appropriate? |
| **Knowledge Agent** | RAG evals (Recall@k, faithfulness) | Query type, knowledge domain, answer specificity | Answer grounded in context? Relevant? Citations accurate? |
| **Innovation Agent** | Judge-based (feasibility, fallbacks) | Technique novelty, client coverage, fallback robustness | Feasibility accurate? Fallback robust? Coverage estimate real? |

---

## Phase 6 — OWASP API Top 10 Security Hardening

Audit conducted 2026-03-06 using CodeQL + Semgrep + manual route review. Root cause: `current_user` is authenticated at route level but NOT passed to service layer for authorization. The `templates` module does this correctly with `verify_project_access()` — replicate across all affected modules.

### 6.1 BOLA Fixes — Add `verify_project_access()` to All Resource Endpoints
**Affects:** `approval/`, `connectors/`, `qa_engine/`, `rendering/`, `knowledge/`, `projects/`
**Pattern:** Pass `current_user` to service → call `verify_project_access(resource.project_id, user)` before read/write

- [x] 6.1.1 `PATCH /projects/{id}` — ~~any developer can update ANY project~~ DONE — `verify_project_access()` added (CRITICAL)
- [x] 6.1.2 `POST /approvals/{id}/decide` — ~~any user can approve/reject ANY approval~~ DONE — all 7 approval endpoints protected (CRITICAL)
- [x] 6.1.3 `POST /connectors/export` — ~~any developer can export ANY build by ID~~ DONE — build→project FK chain verified (CRITICAL)
- [x] 6.1.4 `POST /qa/results/{id}/override` — ~~any developer can override ANY QA result~~ DONE — QA→build→project FK chain verified (CRITICAL)
- [x] 6.1.5 `GET/POST /approvals/{id}/*` — ~~all approval endpoints lack project access checks~~ DONE — `_verify_approval_access()` helper (HIGH)
- [x] 6.1.6 `POST /rendering/compare` — ~~can compare any two test IDs without ownership~~ DONE — both test project IDs verified (HIGH)
- [x] 6.1.7 `GET /knowledge/documents/{id}/download` — already role-gated (admin/developer), no project-scoped changes needed (HIGH)
- [x] 6.1.8 WebSocket `/ws/stream` — ~~no multi-tenant isolation~~ DONE — project_id filter validated against membership (HIGH)
- [x] 6.1.9 AI agent endpoints — ~~agents accept briefs without project scoping~~ DONE — optional project_id with access check (HIGH)
- [x] 6.1.10 `GET /email/builds/{build_id}` — ~~any authenticated user can fetch any build by ID~~ DONE — `verify_project_access(build.project_id, user)` added to `EmailEngineService.get_build()` (CRITICAL)

### ~~6.2 Response & Error Hardening~~ DONE
- [x] 6.2.1 `POST /email/build` — ~~raw exception messages leaked to client~~ DONE — `error_sanitizer.py` central safe message registry; `email_engine` + `connectors` store generic messages in DB, log real errors server-side (HIGH)
- [x] 6.2.2 LLM provider calls — ~~no circuit breaker~~ DONE — `_ResilientLLMProvider` wraps all LLM `complete()` calls with `CircuitBreaker` (5 failures → 60s open); all adapter/agent/service error messages genericized (no provider names, status codes, or raw exceptions) (HIGH)
- [x] 6.2.3 Error handler leaks exception class names to client — DONE — `get_safe_error_type()` returns generic categories (`not_found`, `forbidden`, `ai_error`, etc.); `get_safe_error_message()` with MRO-walking safe message lookup; passthrough for validation errors only; 21 unit tests (MEDIUM)
- [x] 6.2.4 Auth exception handlers (`invalid_credentials_handler`, `account_locked_handler`) leaked `"InvalidCredentialsError"` / `"AccountLockedError"` type strings — DONE — now use `get_safe_error_message/type()`, returning `"authentication_error"` / `"account_locked"` generic types; 2 new tests (HIGH)

### ~~6.3 Rate Limiting & Resource Controls~~ DONE
- [x] 6.3.1 AI quota per-IP (in-memory) → per-user (Redis) — DONE — `UserQuotaTracker` in `app/core/quota.py` (Redis-backed with in-memory fallback); `app/ai/routes.py` keyed by `current_user.id`; 7 unit tests (MEDIUM)
- [x] 6.3.2 Per-user WebSocket connection limit — DONE — `ConnectionManager` tracks `_user_connections` dict; `max_connections_per_user=5` config; broadcast cleanup syncs user tracking; 7 unit tests (MEDIUM)
- [x] 6.3.3 Timeout on LLM streaming responses — DONE — `asyncio.timeout(stream_timeout_seconds)` in `ChatService.stream_chat()`; sends `finish_reason: "timeout"` chunk; `stream_timeout_seconds=120` config; 2 unit tests (MEDIUM)
- [x] 6.3.4 Blueprint daily cost cap — DONE — `BlueprintCostTracker` in `app/core/quota.py` (Redis-backed); checks budget after each node, breaks with `cost_cap_exceeded`; `daily_token_cap=500k` config; `user_id` threaded route→service→engine; 4 unit tests (MEDIUM)

### ~~6.4 Business Logic Hardening~~ DONE
- [x] 6.4.1 Approval state machine — prevent invalid transitions (MEDIUM)
- [x] 6.4.2 JWT algorithm — pin HS256 constant, remove config override, align docs (MEDIUM)
- [x] 6.4.3 LLM output sanitization — replace regex with nh3 allowlist sanitizer (MEDIUM)

### ~~6.5 Security Development Cycle (SDC) Improvements~~ DONE
- [x] 6.5.1 `make check` now includes `security-check` — developers cannot skip Bandit security lint (SDC)
- [x] 6.5.2 CI workflow (`.github/workflows/ci.yml`) — backend (lint + types + security + test) and frontend (types + test) on push/PR to main (SDC)
- [x] 6.5.3 PR template (`.github/PULL_REQUEST_TEMPLATE.md`) — security checklist (auth, authz, input validation, error sanitization, rate limiting) (SDC)
- [x] 6.5.4 Memory routes missing rate limiting — DONE — all 5 `/memory/` endpoints now have `@limiter.limit()` (10/min writes, 30/min reads) (MEDIUM)
- [x] 6.5.5 Frontend token expiry mismatch — DONE — `auth.ts` now reads JWT `exp` claim via `getExpFromToken()` instead of hardcoded 14-min offset; removed `(user as any)` type casts (MEDIUM)
- [x] 6.5.6 Export history sessionStorage validation — DONE — `isValidRecord()` type guard validates parsed JSON shape before use (MEDIUM)

---

## Phase 7 — Agent Capability Improvements

**Plan ref:** Section 5.1 (Agent Architecture), Section 5.6 (Smart Agent Memory), Section 5.7 (Agent Harness Architecture)
**What:** Enhancements to agent quality, coordination, and self-improvement that go beyond what the current plan covers. These build on the existing blueprint engine, eval system, and RAG pipeline — wiring things together rather than building new systems.

### Execution Strategy

Run evals first to establish a baseline, build Phase 7 infrastructure before the remaining 6 agents, then integrate Cognee so every new agent inherits all patterns from day one.

~~**Step 0 — Eval Baseline (Phase 5.4-5.8 execution)**~~ DONE (2026-03-09)
Live eval executed: 36 traces + 36 verdicts via `anthropic:claude-sonnet-4`. Baseline: 16.7% overall (scaffolder 46.7%, dark_mode 82%, content 85.7%). Blueprint evals 5/5 passed. Top failures: mso_conditionals (0%), accessibility (8%), html_preservation (10%). Data unblocks 7.2 (eval-informed prompts) and 4.1 (skill-first agent builds).

~~**Step 1 — Blueprint Infrastructure (7.1 + 7.3 + 7.4)**~~ DONE
Built `AgentHandoff` frozen dataclass, `ComponentMeta`, `ComponentResolver` Protocol in `protocols.py`. Engine stores/propagates handoff, checks confidence < 0.5 → `needs_review` status. Async `_build_node_context` with component context injection. `extract_confidence()`/`strip_confidence_comment()` in `shared.py`. `DbComponentResolver` in `resolvers.py`. `HandoffSummary` in API response schema. 21 new tests.

~~**Step 2 — Retrofit Existing Agents (Scaffolder, Dark Mode)**~~ DONE
Updated ScaffolderNode + DarkModeNode to emit `AgentHandoff` with confidence scores and component refs. DarkModeNode reads upstream handoff warnings. RecoveryRouterNode reads handoff warnings for dark mode routing hints. System prompts updated with confidence assessment instructions. Content agent retrofit deferred (no blueprint node yet).

~~**Step 2.5 — Full Handoff History + Memory Persistence Bridge**~~ DONE (2026-03-09)
Extended `BlueprintRun._handoff_history` to accumulate ALL handoffs (not just latest). Downstream nodes receive `context.metadata["handoff_history"]` with full chain. API response includes `handoff_history: list[HandoffSummary]`. Created `handoff_memory.py` bridge that auto-persists each handoff as episodic memory via `on_handoff` callback. Wired into `BlueprintService.run()`. Failure-safe (callback errors logged, never crash pipeline). 4 new tests (8 total handoff tests).

~~**Step 2.6 — SKILL.md Files for Existing Agents (Scaffolder, Dark Mode)**~~ DONE (2026-03-09)
Created progressive disclosure SKILL.md files for Scaffolder (L1+L2 + 4 L3 files: client_compatibility, maizzle_syntax, mso_vml_quick_ref, table_layouts) and Dark Mode (L1+L2 + 3 L3 files: client_behavior, color_remapping, outlook_dark_mode). Services updated with `detect_relevant_skills()` + `build_system_prompt()` for on-demand skill loading based on brief analysis.

~~**Step 3 — Cognee Integration + Ontology + Seeding (8.1 + 8.6 + 8.2)**~~ DONE (2026-03-10)
~~8.1 Cognee integration layer~~ DONE: `app/knowledge/graph/` module with `GraphKnowledgeProvider` Protocol + `CogneeGraphProvider` implementation; `CogneeConfig` in settings (disabled by default, inherits AI config); `POST /api/v1/knowledge/graph/search` endpoint (auth + 20/min rate limit, chunks + completion modes); `GraphError` → `AppError` hierarchy; cognee as optional dependency (`pip install -e ".[graph]"`); 8 unit tests (568 total). ~~8.6 Email development ontology~~ DONE: `app/knowledge/ontology/` Python-native module — 25 email clients, 365 CSS properties, 1011 support entries, 70 fallback relationships in YAML data files; `OntologyRegistry` singleton with indexed lookups; `unsupported_css_in_html()` query powering data-driven QA; `export_ontology_documents()` for Cognee graph ingestion; `css_support.py` QA check replaced with ontology-powered scan; 51 tests (661 total). ~~8.2 Knowledge graph seeding~~ DONE: `_seed_ontology_graph()` added to `seed.py` feeding ontology-derived documents into Cognee ECL pipeline alongside existing RAG document seeding.

~~**Step 4 — Graph Context Provider + SKILL.md Files (8.3 + 8.5)**~~ DONE (2026-03-10)
~~8.3 Graph context provider~~ DONE: `app/ai/blueprints/graph_context.py` wired into blueprint engine `_build_node_context()`. ~~8.5 SKILL.md files~~ DONE: All 9 agents have progressive disclosure SKILL.md (L1+L2) + L3 skill files with on-demand loading via `detect_relevant_skills()` + `build_system_prompt()`.

~~**Step 5 — Build Remaining 6 Agents WITH Phase 7+8 Patterns (Task 4.1)**~~ DONE (Outlook Fixer, Accessibility Auditor, Personalisation, Code Reviewer, Knowledge, Innovation — all complete)
Each new agent inherits handoff/confidence/context/graph/SKILL.md infrastructure from day one. No retrofitting needed.

~~**Step 5.5 — Agent Architecture Improvements (`.agents/plans/agent-improvements.md`)**~~ DONE (2026-03-09)
All 6 phases complete. `BaseAgentService` shared pipeline extracted (`app/ai/agents/base.py`) — 7 agents refactored, ~500 lines removed. Thread-safe `_get_model_tier` + `_should_run_qa` hooks replace singleton state mutation. Prompt gap fixes (scaffolder MSO/a11y/dark mode MANDATORY, content num_alternatives). Recovery router: "fallback" keyword collision fixed + cycle detection via `handoff_history`. Eval trace fix (dark mode input HTML stored, judge graceful degradation). Response schemas standardised: `confidence` + `skills_loaded` on all 9 agents; `to_handoff()` on BaseAgentService. Memory recall wired into blueprint engine `_build_node_context()`. 544 tests pass.

~~**Step 6 — Eval-Informed Prompts (7.2)**~~ DONE (2026-03-09)
Created `app/ai/agents/evals/failure_warnings.py` — reads `traces/analysis.json` (from `make eval-analysis`), filters per-agent criteria below 85% pass rate, generates formatted warning fragments injected into all 9 agent `build_system_prompt()` between L2 SKILL.md and L3 reference files. Mtime-cached, max 5 warnings per agent (worst-first), mock reasoning cleanup, graceful degradation when no analysis file exists. 16 new tests, 560 total passing. Plan: `.agents/plans/eval-informed-prompts.md`.

~~**Step 7 — Outcome Logging (8.4)**~~ DONE (2026-03-10)
`outcome_logger.py` formats blueprint run outcomes as narrative summaries + queues to Redis + stores in pgvector Memory. `OutcomeGraphPoller` background task drains Redis queue into Cognee graph with batch processing and leader election. Fire-and-forget pattern ensures graph/memory errors never impact blueprint API. 19 tests.

### ~~7.1 Structured Inter-Agent Handoff Schemas~~ DONE (extended 2026-03-09)
**What:** Define typed handoff contracts between agents in blueprint pipelines. Currently agents chain via raw HTML output. Instead, each agent should emit a structured handoff object containing: the output artifact, metadata about decisions made (e.g., "used 2-column layout", "applied VML fallback for hero"), warnings/caveats, and context the next agent needs.
**Why:** Dark Mode agent receiving raw HTML from Scaffolder doesn't know which design patterns were used, which components were pulled in, or what trade-offs were made. Structured handoffs eliminate "undoing each other's work."
**Implementation:** `AgentHandoff` frozen dataclass in `app/ai/blueprints/protocols.py` with `artifact`, `decisions`, `warnings`, `component_refs`, `confidence` fields. Blueprint engine passes handoff objects between nodes. **Extended:** Full handoff history accumulates in `BlueprintRun._handoff_history` — all nodes see every prior node's decisions via `context.metadata["handoff_history"]`. Auto-persisted to episodic memory via `handoff_memory.py` bridge (`on_handoff` callback). API response includes `handoff_history: list[HandoffSummary]`.
**Retrofit:** Updated Scaffolder, Dark Mode to emit `AgentHandoff`. RecoveryRouterNode reads upstream warnings.
**Security:** Handoff objects scoped to blueprint session. No cross-project leakage. Decisions logged to audit trail. Memory persistence failure-safe (callback errors logged, never crash pipeline).
**Verify:** Blueprint pipeline passes structured handoff between scaffolder → dark_mode nodes. Full history available to all downstream nodes. Handoffs auto-persisted to memory. 8 unit tests (4 original + 4 history/callback tests).

### ~~7.2 Eval-Informed Agent Prompts~~ DONE (2026-03-09)
**What:** Feed common failure patterns from eval error analysis (`make eval-analysis`) back into agent system prompts automatically. When eval clusters show recurring failures (e.g., "Scaffolder consistently misses MSO conditionals for 3-column layouts"), inject those as explicit warnings in the agent's prompt.
**Why:** Eval system already captures failure clusters in `error_analysis.py`. Currently this data sits in JSONL files — it should actively improve agent performance in a feedback loop.
**Prerequisite:** ~~Requires real eval traces from Phase 5.4-5.8 live execution.~~ DONE — baseline established 2026-03-09 with real failure patterns available in `traces/analysis.json`.
**Implementation:** `app/ai/agents/evals/failure_warnings.py` — reads `traces/analysis.json`, filters per-agent criteria <85% pass rate, formats `## KNOWN FAILURE PATTERNS` prompt section (max 5 warnings, worst-first, mock reasoning cleanup). All 9 agent `prompt.py` files call `get_failure_warnings("agent_name")` in `build_system_prompt()`, injecting between L2 SKILL.md and L3 reference files. Mtime-based caching avoids re-reading JSON per call. Graceful degradation (returns `None` if no analysis file). Plan: `.agents/plans/eval-informed-prompts.md`.
**Security:** Failure patterns contain no user data (only aggregated error categories). No new routes or API surface. Analysis path hardcoded, not user-controllable.
**Verify:** 16 unit tests in `app/ai/agents/evals/tests/test_failure_warnings.py`. 560 total tests pass. With `traces/analysis.json` present, agents get failure warnings. Without it, prompts unchanged.

### ~~7.3 Agent Confidence Scoring~~ DONE
**What:** Agents emit a confidence score (0-1) alongside their output, based on self-assessment of task complexity, knowledge gaps, and output quality. Blueprint engine uses confidence to decide: high confidence → proceed to QA, low confidence → route to human review instead of burning retry loops.
**Why:** Prevents wasting 2-3 self-correction rounds on tasks the agent knows it can't solve. Surfaces genuinely hard problems to developers faster.
**Implementation:** `confidence` field on agent response schema. Configurable threshold per agent (default: 0.6). Blueprint engine checks confidence before routing to QA vs human review node. Confidence calibrated against eval pass rates over time.
**Retrofit:** Add confidence self-assessment step to Scaffolder, Dark Mode, Content agents. Initial thresholds set conservatively (0.5) and tuned after eval data available.
**Security:** Confidence scores logged in audit trail. Never exposed to end-users (internal routing metric only).
**Verify:** Agent returns confidence score. Blueprint routes low-confidence outputs to human review node. Confidence correlates with actual QA pass rate (validated via eval data).

### ~~7.4 Template-Aware Component Context~~ DONE
**What:** When an agent works on a template that uses components from the component library, automatically load that component's metadata (version, dark mode variant, known quirks, compatibility notes) into the agent's context.
**Why:** Scaffolder pulls in a `hero` component but doesn't know it has a known Outlook 2016 rendering issue. Dark Mode agent doesn't know the component already has a dark mode variant. This context prevents redundant work and avoids breaking working components.
**Implementation:** Template parser identifies component references → queries `app/components/` for metadata → injects as structured context in agent prompt. Leverages existing component versioning and the progressive disclosure pattern (only loads components actually used).
**Retrofit:** Existing agents automatically benefit once the component context loader is wired into the blueprint engine — no per-agent changes needed.
**Security:** Component metadata is project-scoped (existing RLS). No additional access surface.
**Verify:** Agent working on template with `hero` component receives component metadata in context. Agent output references component-specific constraints. Token usage stays within progressive disclosure budget.

### ~~7.5 Hub Agent Memory System (PRD 4.9.3-4.9.6)~~ DONE
**Plan ref:** PRD Section 4.9.3-4.9.6 (Agent Memory Entries, Temporal Decay, Cross-Agent Sharing), `.agents/plans/dcg-agent-memory.md`
**What:** Full `app/memory/` VSA module with pgvector-backed semantic memory for AI agents. Persistent, project-scoped memory entries with vector embeddings for similarity search, temporal decay, and a DCG note promotion bridge (4.9.7).
**Implementation:** `MemoryEntry` model with `Vector(1024)` embedding, HNSW index, 3 memory types (procedural/episodic/semantic), temporal decay via `POWER(2, -age/half_life)`, 5 REST endpoints (`POST /memory`, `POST /memory/search`, `GET /memory/{id}`, `DELETE /memory/{id}`, `POST /memory/promote`), `MemoryCompactionPoller` background task, `MemoryConfig` in settings. Alembic migration `f1a2b3c4d5e6`. 19 unit tests (repository: 6, service: 6, routes: 7).
**Verify:** Store, recall, promote all tested. Auth on all endpoints (admin/developer). Viewer role blocked (403). 404 on missing entries. Lint, mypy, pyright all clean.

### ~~7.6 DCG-Based Lightweight Cross-Agent Memory~~ DONE
**Plan ref:** PRD Section 4.9.7 (DCG Agent Memory), `destructive_command_guard/docs/prd-agent-memory-sharing.md`
**What:** Add 2 MCP tools (`store_note`, `recall_notes`) to the existing dcg MCP server, enabling agents to share project-scoped observations via append-only JSONL files. Zero new dependencies, ~150 lines of Rust.
**Why:** dcg already sits in the critical path of every agent's command execution and auto-detects which agent is calling. The history DB already stores per-agent evaluation data. Exposing a lightweight key/value note layer via MCP gives agents cross-agent memory with no infrastructure cost — complementing the Hub's full pgvector memory system (7.5) at the shell/tool layer.
**Dependencies:** None. Uses existing dcg MCP server, agent detection, and JSONL I/O.
**Implementation:**

#### Phase 1 — Core (MVP) DONE
- [x] Add `AgentNote` struct to `destructive_command_guard/src/notes.rs` (timestamp, agent, key, value, project)
- [x] Implement `store_note()` — append to `.dcg/{project}_notes.jsonl` with auto-detected agent identity
- [x] Implement `recall_notes()` — read + filter from JSONL (by key, agent, project; limit 50)
- [x] Register both tools in `handle_list_tools_request` and `handle_call_tool_request`
- [x] Enforce size limits (1024 char value, 500 notes max per project, 128 char key)
- [x] Key namespace convention: `project.*`, `safety.*`, `workflow.*`, `config.*`
- [x] 13 unit tests for store/recall round-trip, isolation, limits, sanitization
- [x] 1 MCP integration test (store from "agent A", recall from "agent B")

**Security:** Notes are project-local (no cross-project leakage). Agent identity auto-detected (not self-reported). `.dcg/` gitignored.
**Verify:** Agent A stores a note. Agent B recalls it via MCP. Store/recall latency < 5ms.

---

## Phase 8 — Knowledge Graph Integration (Cognee)

**Plan ref:** Section 5.6 (Smart Agent Memory), new Section 5.8 (Knowledge Graph Integration)
**What:** Replace flat RAG chunk retrieval with graph-structured knowledge using [Cognee](https://github.com/topoteretes/cognee) — an open-source AI memory platform that builds persistent knowledge graphs from raw data. This transforms the Hub's agent memory from "similar text chunks" to "structured entity relationships," making agents more precise and less error-prone.
**Why:** The current RAG pipeline (`app/knowledge/`) retrieves similar text, not related concepts. Agents asked about "Outlook dark mode" get 5 similar paragraphs — but not the structured chain: *Outlook 2019 -> does_not_support -> CSS variables -> fallback -> MSO conditional VML*. Knowledge graphs capture these relationships explicitly.
**Dependencies:** Phase 7 infrastructure (handoff schemas, confidence scoring, component context) should be in place first. Phase 5.4-5.8 eval execution provides baseline metrics to measure improvement.

### Execution Order

**Step 1 — Cognee Integration Layer (8.1)**
Add Cognee as a dependency. Create `app/knowledge/graph/` adapter that wraps Cognee's `add()` + `cognify()` + `search()` behind the existing knowledge service interface. This runs alongside existing RAG — additive, not replacement.

**Step 2 — Seed Knowledge Graph (8.2)**
Feed existing knowledge base documents (Can I Email data, email dev guides, client quirks) through Cognee's ECL pipeline. Extracts entities (email clients, CSS properties, rendering engines, components) and relationships automatically.

**Step 3 — Graph Context Provider for Agents (8.3)**
Add a graph search context provider that blueprint nodes query before generation. Agents receive structured relationships alongside existing RAG chunks. Highest impact for Scaffolder and Dark Mode agents where compatibility chains matter most.

**Step 4 — Outcome Logging (8.4)**
Feed completed blueprint run outcomes (QA verdicts, recovery paths, what worked/failed) back into Cognee. Over time, builds institutional memory of which patterns succeed.

**Step 5 — Agent SKILL.md Domain Files (8.5)**
Create per-agent SKILL.md files with domain-specific knowledge, grounded by the knowledge graph. Each agent gets a skill file covering its Four Discipline sections (Prompt Craft, Context Engineering, Intent Engineering, Specification Engineering) with domain-specific rules pulled from graph entities.

**Step 6 — Ontology Definition (8.6)**
Define an email development OWL ontology (email clients, CSS properties, rendering engines, component types, ESP platforms). Cognee uses this to ground entity extraction against known domain concepts rather than relying on LLM training data.

### 8.1 Cognee Integration Layer
**What:** Add `cognee` as a Python dependency. Create `app/knowledge/graph/` module with `GraphKnowledgeProvider` that wraps Cognee's async API (`add`, `cognify`, `search`) behind a Protocol interface consistent with existing knowledge architecture.
**Why:** Keeps Cognee isolated behind an interface — can swap graph backends later without touching agent code. Runs alongside existing vector+fulltext search, not replacing it.
**Deployment model (DECIDED):** Background worker pattern — graph search queries run in-process (Kuzu is sub-millisecond for traversals), heavy operations (`cognify()`, outcome logging from 8.4) run via existing `DataPoller` background task system with Redis queue. This matches the existing pattern for memory compaction (Section 5.6 Layer 5). Migration path to sidecar container available if needed later.
**Graph DB (DECIDED):** Kuzu (file-based). Zero extra infrastructure. Sub-millisecond traversals for read-heavy agent queries. Stored in `DATA_ROOT_DIRECTORY` alongside other file-based data. Migration path to PostgreSQL available via Cognee's adapter layer if cross-database joins are needed later.
**Implementation:**
- `app/knowledge/graph/__init__.py`
- `app/knowledge/graph/provider.py` — `GraphKnowledgeProvider` Protocol + Cognee implementation
- `app/knowledge/graph/config.py` — Cognee config (graph DB: Kuzu file-based, data in `DATA_ROOT_DIRECTORY`)
- `app/knowledge/graph/tasks.py` — Background task wrappers for `cognify()` and outcome ingestion via `DataPoller`
- Wire into `KnowledgeService` as an optional search mode alongside existing hybrid search
**Security:** Cognee databases stored in project-scoped directories. No cross-tenant access. Graph queries logged to audit trail. Background tasks inherit existing Redis leader election for single-writer safety.
**Verify:** `KnowledgeService.search()` can return graph-structured results alongside existing chunk results. Background `cognify()` completes without blocking API server. Unit tests for provider interface.

### ~~8.2 Knowledge Graph Seeding~~ DONE (2026-03-10)
**What:** Run existing knowledge base documents through Cognee's ECL pipeline (`add()` -> `cognify()`) to extract entities and relationships into a knowledge graph.
**Why:** Transforms static document chunks into interconnected knowledge. "Gmail clips at 102KB" becomes a queryable entity linked to "file_size_check" and "Gmail" with relationship "clips_above_threshold."
**Implementation:**
- Extend `make seed-knowledge` to also run Cognee pipeline after existing chunking/embedding
- Seed manifest (`app/knowledge/data/seed_manifest.py`) unchanged — same source documents, additional processing path
- Initial entity types: EmailClient, CSSProperty, RenderingEngine, Component, Workaround, Limitation
**Security:** Same documents, additional index. No new data surface.
**Verify:** After seeding, graph contains extracted entities from Can I Email data. Query "What does Outlook 2019 not support?" returns structured graph traversal results.

### ~~8.3 Graph Context Provider for Blueprint Nodes~~ DONE (2026-03-10)
**What:** Add graph-aware context retrieval to the blueprint engine's `_build_node_context()`. Before an agent generates output, query Cognee for structured relationships relevant to the task.
**Why:** This is the highest-impact integration. Instead of "here are 5 similar chunks about dark mode," agents get: *"Apple Mail supports prefers-color-scheme -> use media query. Outlook ignores it -> use MSO conditional fallback. Gmail Android partially supports -> test with persona."*
**Implementation:**
- New context source in `app/ai/blueprints/engine.py::_build_node_context()`
- Uses Cognee's `GRAPH_COMPLETION` or `TRIPLET_COMPLETION` search types
- Progressive disclosure: only fetch graph context when the task involves email client compatibility, CSS support, or component interactions
- Results formatted as structured triplets injected into agent system prompt
**Security:** Graph queries scoped to project. Query content logged. No PII in graph (email dev knowledge only).
**Verify:** Scaffolder agent generating a 3-column layout receives structured compatibility data for target email clients. Dark Mode agent receives known workarounds for components in the template.

### ~~8.4 Blueprint Outcome Logging~~ DONE (2026-03-10)
**What:** After a blueprint run completes, feed the outcome (which agents ran, what they produced, QA results, recovery actions taken) back into Cognee via `cognee.add()`.
**Why:** Builds institutional memory. After 50 blueprint runs, agents can query: "What fixes have worked when QA fails for VML backgrounds in Outlook?" — answered from real outcomes, not LLM guessing.
**Implementation:**
- Post-run hook in `BlueprintEngine` that serialises `BlueprintRun` outcome to text
- Feeds through Cognee pipeline to extract patterns (successful fixes, common failure modes, recovery paths)
- Tagged with project scope and agent types involved
**Security:** Outcomes contain generated HTML patterns, not client content. Project-scoped. Temporal decay applies (Section 5.6 Layer 5).
**Verify:** After 10+ blueprint runs, querying "common Scaffolder failures" returns aggregated patterns from actual runs.

### ~~8.5 Per-Agent Domain SKILL.md Files~~ DONE (2026-03-10)
**What:** Create a SKILL.md file for each of the 9 agents following the Four Discipline structure (Section 5.4). Each skill file contains domain-specific rules, examples, anti-patterns, and context requirements grounded by the knowledge graph. Skills start as manually authored baselines and grow over time as agents accumulate knowledge.
**Why:** Currently agent prompts are static strings in `prompt.py` constants. SKILL.md files make agent expertise versionable, updatable without code changes, and benchmarkable via the eval system. Combined with the knowledge graph, skills reference verified entities rather than relying on LLM memory.
**Implementation:**
- `app/ai/agents/{agent_name}/SKILL.md` for each agent
- **Prompt Craft**: Best system prompts with success metrics, failure examples, output format specs
- **Context Engineering**: Required data sources, graph queries that improve output, progressive disclosure rules
- **Intent Engineering**: Trade-off hierarchies, escalation boundaries, decision frameworks
- **Specification Engineering**: Output schemas, acceptance criteria, eval test cases
- Skill loader reads SKILL.md at runtime and injects into agent context (existing pattern from Section 5.4)
- Graph-grounded: skill files reference entity types from the ontology (8.6) for precise constraints

**Skill Growth Lifecycle:**
1. **Manual baseline** — Devs author initial SKILL.md with proven patterns, known anti-patterns, output specs
2. **Passive accumulation** — Knowledge graph captures agent run outcomes (8.4). After 50+ runs, patterns emerge
3. **Growth proposals** — Periodic `DataPoller` job analyses graph for patterns not yet in SKILL.md. Generates diff suggestions (new procedural knowledge, updated success metrics, new anti-patterns). Proposed as review items — never auto-applied
4. **Dev review + merge** — Dev reviews proposed skill additions, approves or rejects. Versioned in git like any code change
5. **Size management** — SKILL.md files have a token budget (progressive disclosure). When skill grows beyond budget, entries ranked by impact (graph outcome data), low-impact entries archived to knowledge graph (still retrievable via graph search, just not in default agent context)

**Security:** SKILL.md files contain no client data. Versioned in git. Growth proposals logged with source data references. Changes auditable.
**Verify:** Agent loaded with SKILL.md produces measurably better output on eval suite vs static prompt. Skill updates don't require code deployment. Growth proposals reference specific graph entities and outcome data.

### ~~8.6 Email Development Ontology (Full Granularity)~~ DONE (2026-03-10)
**What:** Define a comprehensive OWL ontology for the email development domain. Full coverage of every email client version, every CSS property from Can I Email, all rendering engines, HTML elements relevant to email, ESP platforms, and template patterns.
**Why:** Without an ontology, Cognee's LLM-based entity extraction invents entity types inconsistently ("Outlook" vs "Microsoft Outlook" vs "Outlook 2019"). The ontology grounds extraction against canonical domain concepts, ensuring the knowledge graph is consistent and queryable. Full granularity means agents can reason at the version level ("Outlook 2016 on Windows" vs "Outlook 365 on Mac" have different rendering engines).
**Implementation:**
- `app/knowledge/graph/ontology/email_development.owl`
- Configure Cognee's `ONTOLOGY_RESOLVER=rdflib` + `MATCHING_STRATEGY=fuzzy` (80% similarity threshold)
- **Entity types and scope:**
  - `EmailClient` — Every client+version from Can I Email database (Apple Mail 10-18, Gmail Web/Android/iOS, Outlook 2007-365/Windows/Mac, Yahoo, AOL, Samsung Mail, Thunderbird, etc.) with version ranges
  - `CSSProperty` — Full Can I Email CSS property database (300+ properties with support status per client)
  - `RenderingEngine` — WebKit, Blink, Gecko, Word (MSO), Presto, with client→engine mappings
  - `HTMLElement` — Email-relevant elements with support status (semantic elements, `<picture>`, `<video>`, AMP elements)
  - `Component` — Maps to `app/components/` taxonomy (header, CTA, hero, product card, footer, etc.) with dark mode variant relationships
  - `Workaround` — Named patterns (MSO conditional comments, VML backgrounds, `mso-` properties, `<!--[if mso]>` blocks)
  - `Limitation` — Named constraints (Gmail 102KB clip, Outlook DPI scaling, Yahoo `!important` stripping)
  - `ESPPlatform` — Braze, SFMC, Adobe Campaign, Taxi, with template language relationships (Liquid, AMPscript, Handlebars)
  - `TemplatePattern` — Layout archetypes (single column, 2-col, 3-col, hybrid, fluid) with client compatibility profiles
  - `InteractiveFeature` — AMP components, CSS animations, kinetic techniques, with feasibility per client
- **Relationships:** `supports`, `does_not_support`, `partially_supports`, `fallback_for`, `renders_with`, `requires`, `conflicts_with`, `variant_of`, `degrades_to`
- **Data source:** Primary data scraped/imported from Can I Email API + database. Supplemented by Good Email Code patterns and team's tribal knowledge
- Updated as new email clients or CSS properties emerge. Can I Email data refresh on `make seed-knowledge`
**Security:** Ontology is public domain knowledge (email client names, CSS specs, Can I Email data). No sensitive data.
**Verify:** After seeding with ontology, entity extraction produces canonical names. "Outlook 2019" and "Microsoft Outlook 2019" resolve to the same entity. Graph contains 300+ CSS property nodes with per-client support status. Query "what does Gmail Android not support?" returns comprehensive, version-specific results.

## Phase 9 — Graph-Driven Intelligence Layer

**Plan ref:** Section 5.8 (Knowledge Graph Integration), Section 5.6 (Smart Agent Memory), Section 12.6 (Compound Innovation Effect)
**What:** Extensions that leverage the knowledge graph (Phase 8) across the entire Hub — connecting personas, components, blueprints, competitive intelligence, and skill evolution into a self-improving system.
**Dependencies:** Phase 8 core (8.1-8.6) must be operational. Phase 5 evals providing baseline data.

### ~~9.1 Graph-Powered Client Audience Profiles~~ DONE
**What:** Connect the Test Persona Engine (`app/personas/`) to the knowledge graph. When a persona specifies "iPhone 15 + Apple Mail 18 + Dark Mode," the graph surfaces: which CSS properties are safe, which components have tested dark mode variants, which workarounds are needed — all pre-filtered for that specific audience profile.
**Why:** Currently agents generate first, then discover breakage during QA. With graph-powered personas, agents receive pre-filtered compatibility context before generation. Eliminates the "generate → QA fail → retry" loop for known compatibility issues.
**Implementation:**
- Extend `app/personas/service.py` to query graph when a persona is selected
- Persona selection triggers graph traversal: persona.email_client → `supports`/`does_not_support` → CSS properties + components + workarounds
- Results cached per persona (compatibility data changes infrequently)
- Blueprint engine injects persona graph context into `NodeContext` alongside existing persona data
- Progressive disclosure: only load graph context for the persona's email client chain, not the entire graph
**Security:** Persona data is project-scoped (existing RLS). Graph queries read-only. Cached results invalidated on graph update.
**Verify:** Selecting "Outlook 2019 + Windows + Dark Mode" persona injects structured compatibility constraints into agent context. Agent output avoids known unsupported CSS properties without needing QA to catch them. Measurable reduction in QA retry loops vs Phase 8 baseline.

### ~~9.2 Can I Email Live Sync~~ DONE
**What:** Periodic sync job that pulls fresh data from the Can I Email API/database, diffs against existing graph entities, and updates the knowledge graph and ontology automatically.
**Why:** Knowledge base is currently seeded once via `make seed-knowledge`. Can I Email updates regularly (new client versions, updated support data). Stale compatibility data means agents give wrong advice. Live sync ensures agents always work with current data.
**Implementation:**
- `app/knowledge/graph/sync/caniemail.py` — sync job that fetches Can I Email data
- Diff engine compares fetched data against existing graph entities
- New/changed entities fed through Cognee's `add()` + `cognify()` pipeline (background worker, 8.1 pattern)
- Ontology auto-extended when new email clients or CSS properties appear (new entity nodes, not OWL schema changes)
- Configurable sync interval (weekly default, daily optional)
- Runs via existing `DataPoller` background task system
- Sync report logged: N new entities, N updated relationships, N deprecated
**Security:** Can I Email is public data. Sync job runs with read-only external access. Graph writes scoped to knowledge domain (no user data).
**Verify:** After sync, new email client version appears in graph. Agents querying that client get updated compatibility data. Sync report shows meaningful diffs.

### ~~9.3 Component-to-Graph Bidirectional Linking~~ DONE
**What:** When a component is created, updated, or tested in `app/components/`, automatically create/update its entity in the knowledge graph with: supported email clients (from QA test results), known quirks (from QA failures), dark mode variant status, and rendering engine compatibility. Reverse direction: graph insights surface as component metadata in the component browser UI.
**Why:** Component metadata is currently static (version, description). The graph can enrich this with real test data — "this CTA component passed QA in 18/20 clients, fails in Outlook 2016 VML and Samsung Mail 14." Agents using components get real compatibility data, not just static descriptions.
**Implementation:**
- `app/components/qa_bridge.py` — `extract_compatibility()` maps HTML CSS issues to per-client levels (full/partial/none) via ontology; `run_component_qa()` runs full QA gate + stores `ComponentQAResult` join model
- `app/components/graph_export.py` — `export_component_documents()` generates Cognee ECL-friendly docs with compatibility profiles and CSS issue details
- `ComponentQAResult` join model links `ComponentVersion` → `QAResult` with denormalised compatibility JSON; cascade delete on both FKs
- `POST /api/v1/components/{id}/versions/{v}/qa` (developer, 10/min) triggers QA + compatibility extraction
- `GET /api/v1/components/{id}/compatibility` (authenticated, 30/min) returns per-client support breakdown
- `ComponentResponse.compatibility_badge` (full/partial/issues) populated from latest QA data
- `CanIEmailSyncPoller._refresh_graph()` re-exports component documents after ontology sync
- Alembic migration `a1b2c3d4e5f6` for `component_qa_results` table
- 20 new tests (qa_bridge: 5, graph_export: 5, compatibility: 10); 747 total backend tests
**Security:** Both new endpoints have auth + rate limiting. Error responses use `AppError` hierarchy (auto-sanitized). Component data is project-scoped. Graph entities inherit project scope.
**Verify:** Creating a component and running QA creates a graph entity with test results. Component browser shows compatibility badge. Agent using the component receives graph-derived quirk warnings.

### ~~9.4 Failure Pattern Propagation Across Agents~~ DONE
**What:** When any agent discovers a failure pattern (e.g., Dark Mode agent finds "Samsung Mail strips `color-scheme` meta tag"), this is stored as a graph relationship — not just an agent memory entry. Every agent that subsequently touches Samsung Mail compatibility automatically gets this knowledge through graph context.
**Why:** Section 5.6 Layer 6 describes cross-agent memory sharing via project-scoped memory pools. Graph relationships are more powerful — they're structured, queryable, and don't require explicit sharing logic. The graph's structure means propagation is inherent in the data model.
**Implementation:**
- Extend outcome logging (8.4) to extract failure patterns as typed graph relationships
- Pattern format: `Entity → failure_type → Description` (e.g., `Samsung_Mail_14 → strips → color-scheme_meta`)
- Failure patterns tagged with: discovery date, agent type that discovered it, number of times observed, confidence level
- All agents' graph context queries automatically include relevant failure patterns (no per-agent wiring needed)
- High-frequency patterns automatically promoted to SKILL.md growth proposals (8.5 lifecycle)
**Security:** Failure patterns contain technical details only (CSS properties, email clients). No user/client data. Project-scoped when client-specific, org-scoped when universal.
**Verify:** Dark Mode agent discovers Samsung Mail failure. Scaffolder agent working on a Samsung Mail-targeting template receives the failure pattern in context without explicit configuration. Pattern appears in SKILL.md growth proposals after threshold observations.

### ~~9.5 Client-Specific Subgraphs for Project Onboarding~~ DONE
**What:** When a new project is created for a client, auto-generate a project-specific subgraph: the client's target email clients (from persona data) → their supported CSS properties → known workarounds → recommended components → historical failure patterns. This becomes the project's "compatibility brief."
**Why:** New developers on a project currently have no structured context about which email clients matter for that client, what works, and what doesn't. The subgraph gives instant onboarding context. Agents working on the project start with pre-loaded domain knowledge instead of discovering constraints through trial and error.
**Implementation:**
- Post-create hook on `Project` model → generates subgraph from persona selections
- Subgraph query: project personas → email clients → CSS support matrix → compatible components → known workarounds → historical outcomes from similar projects
- Subgraph materialised as a cached view (regenerated when personas change or graph updates)
- Accessible via: API endpoint (`GET /api/v1/projects/{id}/compatibility-brief`), agent context (injected into all blueprint runs for the project), UI page (project settings → compatibility overview)
- Knowledge Agent can answer questions scoped to the project subgraph: "What CSS properties should I avoid for this project?"
**Security:** Subgraph inherits project scope (RLS). Contains only email dev knowledge filtered for the project's target audience. No cross-project data.
**Verify:** Creating a project with Outlook 2019 + Apple Mail personas generates a subgraph with compatibility constraints for those clients. Agent working on the project receives subgraph context. New developer querying the Knowledge Agent gets project-specific answers.

### ~~9.6 Graph-Informed Blueprint Route Selection~~ DONE
**What:** Blueprint engine dynamically adjusts node sequence based on graph data about the target audience and template content. Skip unnecessary nodes, add required ones, reorder for efficiency.
**Why:** Currently blueprints follow a fixed sequence (scaffolder → dark_mode → QA → export). But if the target audience is 100% Apple Mail (internal corporate comms), the Outlook Fixer node is wasted work. If the template uses AMP components, an AMP validation node should be added. Graph-informed routing makes blueprints adaptive.
**Implementation:**
- `app/ai/blueprints/route_advisor.py` — `RoutingPlan` with `build_routing_plan()` analysing audience profile + content keywords to recommend skip/add/reorder
- `app/ai/blueprints/engine.py` — pre-execution routing plan, `skip_nodes` set consulted before each node, `routing_decisions` logged on run, `_skip_summary()` helper
- `app/ai/blueprints/schemas.py` — `RoutingDecisionResponse` in `BlueprintRunResponse`
- Rules: skip Outlook Fixer for non-Microsoft audiences, skip Dark Mode for non-dark-mode clients, add AMP validation for AMP content, audience-based prioritisation
- Developer can force full pipeline (overrides routing plan)
- 563 lines test coverage (`test_route_advisor.py`) + 161 lines engine integration tests (`test_engine_routing.py`)
**Security:** Route decisions based on project-scoped graph data. No new access surface. Audit trail captures routing rationale.
**Verify:** Blueprint for Apple Mail-only project skips Outlook nodes. Blueprint for template with AMP adds AMP validation. Routing decisions visible in blueprint run log with graph-backed reasoning.

### ~~9.7 Competitive Intelligence Graph~~ DONE
**What:** Extend the ontology to include competitor capabilities (Stripo, Parcel, Chamaileon, Dyspatch, Knak — from Plan Section 15.4). When the Innovation Agent evaluates new techniques, it checks the graph for feasibility and competitive landscape.
**Why:** Section 15.4 maps competitor features. This data in the graph lets the Innovation Agent answer: "Is this technique feasible for the client's audience AND do competitors support it?" Powers the capability reports mentioned in Section 12.2 with structured data instead of manual research.
**Implementation:**
- `app/knowledge/ontology/competitive_feasibility.py` — `compute_audience_coverage()` cross-references capability CSS deps with ontology support matrix, `build_competitive_report()` generates full audience-scoped report, `format_feasibility_context()` for agent prompt injection
- `app/knowledge/ontology/schemas.py` + `routes.py` — `GET /api/v1/ontology/competitive-report` (JSON) + `/text` (formatted), auth + rate limited
- Engine LAYER 10 enhanced: uses audience-aware feasibility when `audience_client_ids` available (from LAYER 7), falls back to standard competitive context
- `app/ai/blueprints/competitor_context.py` — added `build_audience_competitive_context()` convenience wrapper
- 5 competitors (Stripo, Parcel, Chamaileon, Dyspatch, Knak), 24 capabilities, 55+ Hub capabilities with agent mappings
- 17 feasibility tests + 5 route tests + 3 audience-aware context tests (35 total new)
**Security:** Competitor data is public knowledge (pricing pages, feature lists). No proprietary intelligence. All endpoints auth + rate limited.
**Verify:** Innovation Agent asked "what techniques can we offer that Stripo can't?" returns graph-backed answer with audience feasibility. Capability report includes competitive positioning data.

### ~~9.8 SKILL.md A/B Testing via Eval System~~ DONE
**What:** When the skill growth system (8.5) proposes a SKILL.md update, automatically A/B test it against the current version using the eval suite. Only merge if the updated skill performs equal or better.
**Why:** Skill growth proposals are currently review-only (dev reads the diff and decides). A/B testing adds empirical evidence: run the eval suite with current SKILL.md, then with proposed update, compare pass rates. This closes the loop: knowledge graph → skill proposal → eval validation → merge.
**Implementation:**
- `app/ai/agents/skill_override.py` — Runtime SKILL.md override registry (in-process, no disk writes)
- `app/ai/agents/evals/skill_ab.py` — A/B test runner CLI (`compare_variants`, `build_ab_report`, `run_ab_test`)
- `app/ai/agents/evals/schemas.py` — `SkillABCriterionDelta`, `SkillABResult`, `SkillABReport` dataclasses
- All 9 agent `prompt.py` files refactored to check `get_override()` before file-loaded SKILL.md
- Runs eval suite twice (current vs proposed) on same synthetic test data
- Computes per-criterion pass rate delta, overall improvement, minimum 10 cases per dimension
- Output: JSON comparison report with recommendation (merge / reject / needs_more_data)
- `make eval-skill-test AGENT=scaffolder PROPOSED=path/to/SKILL.md` CLI command
- Proposed updates that degrade any criterion by >5% auto-rejected with explanation
- 17 unit tests (override registry, comparison logic, report builder, edge cases)
**Security:** A/B tests run on synthetic test data (no client data). Results logged for audit. Rejected proposals archived with reasoning.
**Verify:** Proposed SKILL.md update runs through A/B test. Report shows per-criterion comparison. Update that improves 3 criteria and degrades none is recommended for merge. Update that degrades 1 criterion by >5% is auto-rejected.

---

## Phase 10 — Full-Stack Agent Workflow (Frontend Integration)

**What:** Wire all Phase 8-9 backend intelligence into the frontend so email developers can run the full AI-powered workflow from the UI — from project setup with priority clients, through blueprint-orchestrated multi-agent pipelines, to graph-informed QA and export. Currently ~50% of backend capabilities are invisible from the frontend.
**Design principle:** QA always checks against ALL 25 email clients. "Priority clients" mark which clients get prominent display in QA results, drive failure pattern urgency, and influence agent retry priority — but never exclude non-priority clients from validation. No campaign-level client selector needed; campaigns inherit project priorities.
**Dependencies:** Phase 8 (knowledge graph) + Phase 9 (graph intelligence) backend complete. Phase 0-3 frontend foundation in place.

### ~~10.1 Project Priority Clients Selector~~ DONE
**What:** Add a multi-select "Priority Email Clients" field to project creation and project settings forms. Populated from the ontology's 25 email clients. Persists to the existing `target_clients` JSON column on `Project`. Shows client icons, engine type (WebKit/Blink/Word), and market share from ontology data. QA always validates against ALL 25 clients; priority clients get prominent display, higher urgency in failure patterns, and influence agent retry priority.
**Why:** `target_clients` (priority clients) drives audience profiles (9.1), onboarding subgraphs (9.5), failure pattern urgency (9.4), and blueprint route selection (9.6). Empty = all clients treated equally. Non-priority clients are still fully checked — priority only affects display emphasis and agent attention.
**Implementation:**
- New component: `target-clients-selector.tsx` — searchable multi-select with client metadata (icon, engine, share %)
- Add to `create-project-dialog.tsx` as optional step (defaults to empty = all clients equal priority)
- Add to project settings page for editing after creation
- New API hook: `useEmailClients()` fetching from ontology endpoint (or static list from SDK)
- `ProjectCreateRequest` / `ProjectUpdateRequest` schemas already support `target_clients`
- SDK regeneration to include `target_clients` in `ProjectResponse`
- No campaign-level client selector — campaigns inherit project priorities
**Security:** Client list is public ontology data. Project-scoped via existing RLS. Input validated against known client IDs.
**Verify:** Create project with "Outlook 2019 + Gmail" as priority. Project detail shows priority clients. QA results show ALL 25 clients but priority clients are visually emphasised. Empty priority = all clients shown equally. Blueprint runs receive audience context for priority clients.

### ~~10.2 Onboarding Compatibility Brief UI~~ DONE
**What:** Add a "Compatibility Brief" tab/section to the project workspace that displays the auto-generated onboarding subgraph (9.5). Shows: executive summary, per-client CSS constraint profiles, cross-client risk matrix, and a "Regenerate" button that calls `POST /projects/{id}/onboarding-brief`.
**Why:** The backend generates rich compatibility briefs per project but there's no way to see them. Email developers need this as a reference while building — "what CSS is safe across all clients, and where do my priority clients have constraints?"
**Implementation:**
- New page/tab: `project-compatibility-brief.tsx` in workspace or project settings
- Sections: Summary card (client count, total risky properties, dark mode warning), per-client accordion (unsupported CSS list, fallbacks, engine info), risk matrix table (properties × clients heat map)
- "Regenerate Brief" button → `POST /api/v1/projects/{id}/onboarding-brief`
- Auto-generate on first visit if brief doesn't exist
- New API hook: `useOnboardingBrief(projectId)` with SWR caching
- SDK types: `OnboardingBriefResponse` (message, dataset_name, document_count, client_count)
**Security:** Brief data is project-scoped. Read-only for viewer role. Regenerate requires developer+ role.
**Verify:** Navigate to project compatibility tab. Brief displays with per-client profiles (all 25 clients, priority clients highlighted). "Regenerate" updates the content. Brief reflects project's priority clients with emphasis.

### ~~10.3 Blueprint Run Trigger & Pipeline Visualisation~~ DONE
**What:** Add a "Generate with Blueprint" button in the workspace that triggers a full multi-agent blueprint run (not just a single agent call). Show real-time pipeline progress: which agent is running, QA gate status, self-correction loops, handoff chain, and final result with confidence score.
**Why:** The chat sidebar currently calls individual agent endpoints, bypassing the blueprint engine entirely. The engine is where all the intelligence layers (audience context, failure patterns, component injection, handoff memory, self-correction) converge. Without a UI trigger, the most powerful feature in the hub is CLI-only.
**Implementation:**
- New component: `blueprint-run-dialog.tsx` — select blueprint template (campaign, dark-mode-fix, accessibility-audit, etc.), input brief text, optional HTML input, shows project's priority clients
- Pipeline visualisation: `blueprint-pipeline-view.tsx` — vertical node list showing: agent name + status (pending/running/complete/failed), QA gate results per node, self-correction attempt count, handoff decisions and warnings, confidence score per agent
- WebSocket or SSE streaming for real-time updates (blueprint engine already emits events)
- New API hooks: `useBlueprintRun(runId)` for status polling, `useBlueprintTemplates()` for available blueprints
- "Apply Result" button to insert generated HTML into Monaco editor
- "View Handoff History" expandable panel showing cross-agent decisions
- SDK types: `BlueprintRunResponse`, `BlueprintNodeStatus`, `HandoffSummary`
**Security:** Blueprint runs consume AI quota (existing rate limits apply). Run status scoped to project. Only project members can trigger runs.
**Verify:** Click "Generate with Blueprint" → select campaign → enter brief → pipeline shows agents executing in sequence → QA gate results appear → final HTML available with "Apply" button. Self-correction visible when QA fails.

### ~~10.4 Blueprint Run History & Outcomes~~ DONE
**What:** Add a "Runs" tab in the workspace showing all blueprint runs for the project — status, agents involved, QA pass/fail, duration, token usage. Click into a run to see full handoff history, agent decisions, failure patterns discovered, and the generated output.
**Why:** Blueprint outcome logging (8.4) captures rich data but it's only in the database/graph. Developers need to review past runs to understand what agents did, why QA failed, and what patterns were discovered. Essential for debugging and iterating on email quality.
**Implementation:**
- New page: `blueprint-runs-list.tsx` — table with columns: run ID, blueprint name, status (badge), agents involved, QA result, duration, created_at
- Run detail view: `blueprint-run-detail.tsx` — timeline of node executions, expandable handoff cards, QA check breakdown, failure patterns extracted, generated HTML diff
- Filter/sort: by status, date range, blueprint type
- New API hooks: `useBlueprintRuns(projectId)` with pagination, `useBlueprintRun(runId)` for detail
- Link from pipeline visualisation (10.3) to run detail after completion
- New backend endpoints needed: `GET /api/v1/blueprints/runs?project_id=X` (list), `GET /api/v1/blueprints/runs/{id}` (detail)
**Security:** Run history scoped to project (RLS). Viewer role can read but not trigger new runs. Token usage visible to developer+ only.
**Verify:** Run a blueprint → appears in runs list with correct status → click into detail → see full handoff history and QA breakdown. Filter by "failed" shows only failed runs.

### ~~10.5 Component Compatibility Badges & Matrix~~ DONE
**What:** Display per-client compatibility badges on component cards in the component browser. Add a compatibility matrix view showing which components work in which clients. Add a "Run QA" button on component detail to trigger `POST /components/{id}/versions/{v}/qa`.
**Why:** Component-to-graph linking (9.3) generates compatibility data but the frontend never shows it. Email developers choosing components need to know "will this CTA button work in Outlook?" before inserting it into their template.
**Implementation:**
- Update `ComponentResponse` SDK type to include `compatibility_badge` (full/partial/issues/untested)
- Badge component: coloured dot/icon on component cards (green=full, yellow=partial, red=issues, grey=untested)
- Component detail: compatibility section showing per-client support status (full/partial/none per client)
- "Run QA" button on component version detail → `POST /api/v1/components/{id}/versions/{v}/qa`
- Compatibility matrix page: `components-compatibility-matrix.tsx` — grid of components × clients with support indicators
- Filter component browser by "compatible with [client]" using project's priority clients as default filter (all clients still visible)
- New API hook: `useComponentCompatibility(componentId)`
**Security:** QA trigger rate-limited (10/min). Compatibility data is read-only for viewers. Component data project-scoped.
**Verify:** Component card shows green badge (all clients pass). Click component → see per-client breakdown. "Run QA" updates badge. Filter by "Outlook compatible" hides incompatible components.

### ~~10.6 Graph-Powered Knowledge Search~~ DONE
**What:** Upgrade the `/knowledge` page to support graph search mode alongside existing RAG search. Add a toggle: "Text Search" (current) vs "Graph Search" (Cognee). Graph search returns entities and relationships with visual presentation — entity cards with relationship links between them.
**Why:** The flat RAG search on `/knowledge` returns text chunks. The graph search (Phase 8.1) returns structured entities (email clients, CSS properties) with relationships (supports, fallback_for, incompatible_with). This is far more useful for understanding compatibility.
**Implementation:**
- Search mode toggle: "Text" | "Graph" (graph disabled with tooltip if `COGNEE__ENABLED=false`)
- Graph results component: `graph-search-results.tsx` — entity cards showing name, type, properties, related entities
- Relationship visualisation: simple list view with "→ supports →", "→ fallback_for →" relationship labels (not full graph viz)
- Search modes map to: Text → `POST /api/v1/knowledge/search`, Graph → `POST /api/v1/knowledge/graph/search`
- Graph search supports `dataset_name` filter (email_ontology, email_components, project_onboarding_X)
- Optional: "Ask" mode using graph completion (`mode: "completion"`) for natural language Q&A
- New API hook: `useGraphSearch()` calling `/api/v1/knowledge/graph/search`
- SDK types: `GraphSearchRequest`, `GraphSearchResponse`, `GraphEntity`, `GraphRelationship`
**Security:** Graph search has same auth + rate limits as text search. Dataset names validated server-side. No graph write access from frontend.
**Verify:** Toggle to Graph Search → search "Outlook dark mode" → see entity cards for Outlook + dark mode CSS properties with support relationships. Toggle back to Text → same query returns text chunks.

### ~~10.7 Failure Pattern Dashboard~~ DONE
**What:** Add a "Failure Patterns" section to the intelligence dashboard showing extracted patterns across blueprint runs — which agents fail on which checks for which clients, how patterns trend over time, and which patterns have been resolved.
**Why:** Failure pattern propagation (9.4) collects rich data about cross-agent failures but there's no visibility. Email developers and leads need to see: "Outlook dark mode fails 40% of the time" → "we need to update the SKILL.md" or "this client needs a workaround documented."
**Implementation:**
- "Failure Patterns" tab on `/renderings` page (merged from standalone `/failure-patterns` route)
- Pattern list: agent name, QA check, affected clients, frequency, first/last seen, status (active/resolved)
- Trend chart: failure frequency over time per agent/check (simple line chart)
- Filter by: agent, QA check, email client, date range
- Pattern detail: shows the description, workaround hint, associated blueprint runs
- New backend endpoint needed: `GET /api/v1/blueprints/failure-patterns?project_id=X` (paginated list with filters)
- Link from QA results panel → "View related failure patterns"
**Security:** Pattern data project-scoped. Contains only technical details (CSS properties, email clients), no user data. Read-only for all roles.
**Verify:** After several blueprint runs with QA failures, dashboard shows patterns. Filter by "Outlook" shows Outlook-specific failures. Trend chart shows pattern frequency. Click pattern → see detail with workaround.

### ~~10.8 Agent Confidence & Handoff Visibility~~ DONE
**What:** Display agent confidence scores in the chat sidebar and blueprint pipeline view. Show a "needs review" badge when confidence < 0.5. Display handoff decisions (what the agent decided and warned about) in an expandable panel below agent responses.
**Why:** Agents already emit confidence scores (7.3) and structured handoffs (7.1) but the frontend doesn't show them. Developers need to know when an agent is unsure and what decisions were made during generation.
**Implementation:**
- Confidence indicator: coloured bar/badge on agent responses (green ≥0.7, yellow 0.5-0.7, red <0.5)
- "Needs Review" badge on responses with confidence < 0.5
- Handoff panel: expandable section below response showing: decisions made (list), warnings (list), component references (links), skills loaded (list)
- Blueprint pipeline view (10.3): confidence score per node, handoff arrows between nodes showing decisions
- Update chat API response parsing to extract `confidence` and handoff metadata from agent responses
- SDK types: agent response schemas already include `confidence` + `skills_loaded`
**Security:** Confidence scores and handoff data are informational. No new access surface.
**Verify:** Agent responds with 0.45 confidence → "Needs Review" badge appears. Expand handoff → see decisions and warnings. Blueprint pipeline shows confidence per step.

### ~~10.9 Workspace Agent Context Panel~~ DONE
**What:** Add a collapsible "Agent Context" panel in the workspace that shows what intelligence layers are active for the current project — audience profile summary, active failure patterns, loaded SKILL.md version, component context, and onboarding brief status.
**Why:** All intelligence layers inject silently into agent prompts. Developers have no visibility into what context agents are working with. This panel makes the invisible visible — "the scaffolder knows about 3 failure patterns for Outlook and has 12 component references loaded."
**Implementation:**
- New component: `agent-context-panel.tsx` — collapsible sidebar section or drawer
- Sections: Audience Profile (target clients, constraints summary), Active Failure Patterns (count + top patterns), SKILL.md Status (loaded version, last A/B test result), Component Context (detected components in current template), Onboarding Brief (generated/not generated, last refresh)
- Data sources: project target_clients, memory recall for failure patterns, agent response metadata for skills_loaded
- Refresh button to re-fetch context state
- Link each section to its detail view (compatibility brief, failure dashboard, etc.)
- New backend endpoint: `GET /api/v1/projects/{id}/agent-context-summary` (aggregates all context layers)
**Security:** Context summary is read-only, project-scoped. No sensitive data — only agent configuration state.
**Verify:** Open workspace for project with target clients set → context panel shows audience profile, failure pattern count, SKILL.md status. Change template to include a component → component context section updates.

### ~~10.10 SDK Regeneration & Type Coverage~~ DONE
**What:** Regenerate the TypeScript SDK to include all Phase 8-10 response types and endpoints. Add missing types: `BlueprintRunResponse`, `BlueprintNodeStatus`, `HandoffSummary`, `GraphSearchRequest/Response`, `GraphEntity`, `GraphRelationship`, `FailurePatternResponse`, `OnboardingBriefResponse`, `ComponentCompatibilityResponse`, `AgentContextSummary`.
**Why:** The SDK is the contract between backend and frontend. Missing types mean frontend components use `any` or manual type definitions, which defeats the type-safety principle. All new endpoints from Phase 8-10 need SDK coverage.
**Implementation:**
- Run `make sdk` (or equivalent generation command) against updated backend OpenAPI spec
- Verify all new endpoints appear in generated types
- Add new React hooks in `cms/apps/web/src/hooks/`: `useBlueprintRun()`, `useBlueprintRuns()`, `useBlueprintTemplates()`, `useGraphSearch()`, `useOnboardingBrief()`, `useComponentCompatibility()`, `useFailurePatterns()`, `useAgentContextSummary()`, `useEmailClients()`
- Update existing hooks where response types changed (e.g., `useComponents()` now includes `compatibility_badge`)
- Ensure all hooks use `authFetch` with proper error handling and SWR caching
**Security:** SDK generation is automated from OpenAPI spec — no manual type definitions that could diverge. All hooks use authenticated fetch.
**Verify:** `make check-fe` passes. All new components use typed SDK hooks — zero `any` types. New endpoints callable from frontend with full type safety.

### ~~10.11 Blueprint-Aware Chat Mode~~ DONE
**What:** Add a "Blueprint Mode" toggle to the AI chat sidebar. When enabled, chat messages trigger blueprint runs instead of single-agent calls. The user selects agents to include, and the chat orchestrates a full pipeline with QA gating and self-correction, streaming progress updates into the chat panel.
**Why:** Some developers prefer the chat interface over a separate blueprint dialog. Blueprint mode in chat means they can type "create a responsive email for Outlook and Gmail with dark mode" and get a full pipeline run inline — with the same audience context, failure patterns, and self-correction as the standalone blueprint trigger (10.3).
**Implementation:**
- Toggle button in chat header: "Single Agent" | "Blueprint Mode"
- Blueprint mode: chat input triggers `POST /api/v1/blueprints/run` instead of individual agent endpoints
- Progress messages streamed into chat: "Scaffolder generating... → QA gate running... → Dark Mode agent fixing... → Complete (confidence: 0.82)"
- Blueprint selects agents automatically based on brief content (or user can pin specific agents)
- Final result appears as a chat message with "Apply to Editor" button
- Handoff history shown as collapsible thread under the result
- Falls back to single agent mode if blueprint service is unavailable
**Security:** Same rate limits and quota as standalone blueprint runs. Chat history project-scoped.
**Verify:** Toggle Blueprint Mode → type brief → see pipeline progress in chat → result appears with confidence score and "Apply" button → handoff history expandable. Switch back to Single Agent → normal agent behaviour.

### ~~10.12 Intelligence Dashboard Enhancements~~ DONE
**What:** Extend the existing intelligence dashboard (`/intelligence`) with Phase 8-9 data: graph entity counts, knowledge freshness (last Can I Email sync), blueprint success rates over time, top failure patterns, agent performance by confidence distribution, and component compatibility coverage.
**Why:** The intelligence dashboard currently shows QA trends and support matrices. Phase 8-9 generates much richer data that should surface here — graph health, sync status, agent quality trends, and failure pattern analysis.
**Implementation:**
- New dashboard cards: Graph Health (entity count, last sync, dataset sizes), Blueprint Success Rate (chart: pass/fail/self-corrected over time), Agent Performance (confidence distribution per agent, mean/median), Failure Patterns (top 5 most frequent, trend arrows), Component Coverage (% of components with QA data, average compatibility score)
- Can I Email sync status: last sync timestamp, changes applied, next scheduled sync
- Data from existing backend endpoints + new aggregation endpoint: `GET /api/v1/intelligence/summary`
- Export enhanced: PDF/CSV now includes graph metrics and blueprint stats
**Security:** Dashboard read-only. Aggregated data only — no individual run details without clicking through. Developer+ role required.
**Verify:** Dashboard shows graph entity count, last sync date, blueprint success rate chart, top failure patterns. Data updates after running blueprints and syncing knowledge.

---

## Phase 11 — QA Engine Hardening & Agent Quality Improvements

**What:** Upgrade QA checks from shallow string matching to production-grade DOM-parsed validation, expand coverage with new checks, and fix the highest-failure agent skills. Current QA checks detect ~60% of real email issues; target is 95%+. Then migrate all 10 agents to deterministic architecture (structured JSON output + template assembly + cascading auto-repair) lifting eval pass rate from 16.7% → 99%+.
**Dependencies:** Phase 5 (eval framework operational), Phase 8-9 (ontology + graph available for enriched checks). All 10 QA checks exist and run end-to-end.
**Design principle:** Every check upgrade must be backward-compatible (same `QACheckResult` schema). New checks added to `ALL_CHECKS` list. Agent fixes validated via `make eval-run` before/after comparison. Deterministic architecture (11.22) uses PIV loop pattern: LLM decides (structured JSON) → code assembles (deterministic) → QA validates (deterministic) → LLM fixes (structured retry).


### ~~11.1 QA Check Configuration System~~ DONE
**What:** Replace hardcoded thresholds and trigger lists with a per-check configuration model. Currently values like `MAX_SIZE_KB=102`, spam triggers (10 words), and pass thresholds are baked into check implementations. Add `QACheckConfig` that supports per-project overrides and per-client tuning.
**Why:** Every check below needs configurable thresholds. Without this, improvements require code changes instead of config. Client-specific QA rules (e.g., stricter accessibility for healthcare) are impossible.
**Implementation:**
- ~~Create `app/qa_engine/check_config.py` — `QACheckConfig` Pydantic model with `enabled: bool`, `severity: str`, `threshold: float`, `params: dict[str, Any]`~~
- ~~Add `QAProfileConfig` model mapping check names → `QACheckConfig` instances~~
- ~~Default profile loaded from `app/qa_engine/defaults.yaml` (new file)~~
- ~~Per-project override via `qa_profile` JSON column on `Project` model~~
- ~~Service layer merges default + project overrides at runtime~~
- ~~Each check's `run()` method receives optional config parameter~~
**Security:** Config is project-scoped, validated by Pydantic. No raw user input reaches check logic.
**Verify:** ~~Create two projects with different QA profiles. Same HTML produces different scores based on project config. `make test` passes.~~ 72/72 tests pass, mypy + pyright clean.

### ~~11.2 HTML Validation — DOM Parser Upgrade~~ DONE
**What:** Replace string matching (`"<!DOCTYPE" in html`) with proper DOM parsing using `html.parser` or `lxml`. Current check only verifies DOCTYPE and `<html>` tag presence — misses malformed structure, missing `<head>`/`<body>`, invalid nesting, missing charset meta.
**Why:** Real emails with syntax errors pass the current check. Malformed HTML causes unpredictable rendering across clients. This is the foundation check — if HTML structure is broken, all other checks are unreliable.
**Implementation:**
- Replace string checks in `app/qa_engine/checks/html_validation.py` with `lxml.html` parser
- Validate: DOCTYPE is HTML5 (`<!DOCTYPE html>`), `<html>` contains `<head>` + `<body>`, `<head>` has `<meta charset="utf-8">`, no unclosed block-level tags, proper nesting order
- Return specific failure details: "Missing `<body>` tag", "Unclosed `<div>` at approximate position"
- Scoring: 1.0 = all structural checks pass, deduct 0.15 per structural issue, minimum 0.0
- Add `lxml` to dependencies (if not already present)
**Security:** Parser input is the HTML string already validated by Pydantic schema (1-500K chars). No external fetches.
**Verify:** Test with: valid HTML (1.0), missing DOCTYPE (0.85), missing body (0.85), multiple issues (cumulative deductions), malformed nesting (caught). Existing tests still pass.

### ~~11.2a Shared QA Rule Engine — YAML-Driven Check Definitions~~ DONE
**What:** Build a shared rule engine that loads check definitions from YAML files and evaluates them against lxml DOM trees. Replaces hardcoded Python check logic with data-driven rules. Both `html_validation.py` (11.2) and `accessibility.py` (11.3) are refactored to use this engine, and all subsequent check upgrades (11.4–11.12) will load their own YAML rule files.
**Why:** Currently each check hardcodes its validation logic in Python. Adding/tuning rules requires code changes. A rule engine lets us: (a) add rules by editing YAML, no Python needed, (b) share check types across all 10+ QA checks, (c) expose rules to agents via RAG knowledge base (`make seed-knowledge`), (d) let per-project config enable/disable individual rules by ID. The two research docs (`docs/email-accessibility-wcag-aa.md` — 250+ WCAG rules, `docs/html-email-components.md` — 280+ component rules) become machine-parseable YAML that powers both QA validation and agent knowledge.
**Implementation:**
- ~~Create `app/qa_engine/rule_engine.py` — `Rule` dataclass (id, group, check_type, selector, message, deduction_key, etc.), `RuleEngine` class, `load_rules(path)` YAML loader~~
- ~~Implement ~15 check type evaluators: `attr_present`, `attr_value`, `attr_empty`, `attr_pattern`, `attr_absent`, `element_present`, `element_absent`, `element_count`, `parent_has`, `children_match`, `text_content`, `sibling_check`, `style_contains`, `raw_html_pattern`, `custom` (delegates to named Python functions for complex logic)~~
- ~~Create `app/qa_engine/rules/` directory~~
- ~~Create `app/qa_engine/rules/email_structure.yaml` — convert 11.2's 20 hardcoded checks + new rules from `docs/html-email-components.md` (document structure, layout, images, buttons, footer, dark mode, MSO, etc.)~~
- Create `app/qa_engine/rules/accessibility.yaml` — all WCAG AA rules from `docs/email-accessibility-wcag-aa.md` (language, table semantics, images, headings, links, content semantics, dark mode contrast, AMP forms) *(deferred to 11.3)*
- ~~Refactor `html_validation.py` — replace 20 hardcoded methods with thin wrapper: parse DOM → `RuleEngine(load_rules("email_structure.yaml")).evaluate(doc)` → return `QACheckResult`. Move complex logic (unclosed tag counting, block-in-inline nesting) to `custom` check functions~~
- ~~Register custom check functions for logic too complex for declarative rules: `heading_hierarchy`, `tracking_pixel_alt`, `layout_table_heuristic`, `mso_balanced_conditionals`, `unclosed_tags`, `block_in_inline`, `preview_padding_aria`, `dark_unsafe_colors`, `unsubscribe_link_present`~~
- ~~Add both YAML files to RAG knowledge base sources in `make seed-knowledge`~~
- ~~Future checks (11.4–11.12) only need: write a YAML rule file + optionally register custom functions~~
**Security:** YAML files loaded from local filesystem only (hardcoded paths, no user-controlled input). `yaml.safe_load()` used (no arbitrary code execution). Rule evaluation is read-only DOM traversal.
**Verify:** ~~All existing `html_validation` tests pass identically (behavioral regression guard). Rule engine unit tests: `load_rules()` parses valid YAML, handles malformed YAML gracefully, each of 15 check types tested with minimal fixtures.~~ `python -c "import yaml; yaml.safe_load(open('rules/accessibility.yaml'))"` pending (11.3). `email_structure.yaml` validated. 1002/1002 tests pass.

### ~~11.3 Accessibility Check — WCAG AA Coverage~~ DONE
**What:** Expand from 3 checks (lang, alt, role) to comprehensive WCAG AA validation. Current eval data shows 70% alt text pass rate and 70% screen reader compatibility — the check is too lenient. Add: heading hierarchy, link text quality, color contrast estimation, alt text quality scoring, table semantics.
**Why:** Accessibility is the highest eval failure category across agents. The check should catch issues before agents attempt fixes, reducing retry loops. Healthcare/finance clients require strict WCAG compliance.
**Implementation:**
- Rewrite `app/qa_engine/checks/accessibility.py` using HTML parser (not regex)
- **Alt text quality**: Check ALL images (not just first). Validate: present, 5-125 chars for content images, `alt=""` for decorative images, not generic ("image", "photo", "picture", "logo")
- **Heading hierarchy**: Validate h1-h6 in order, no skipped levels, at most one `<h1>`
- **Link text quality**: Flag "click here", "read more", "learn more" — require descriptive text
- **Color contrast**: Extract foreground/background color pairs from inline styles, estimate contrast ratio (4.5:1 normal text, 3:1 large text per WCAG AA)
- **Table semantics**: Layout tables need `role="presentation"`, data tables need `<caption>`, `scope` attributes on `<th>`
- **Screen reader**: Check for `aria-label` on interactive elements, `aria-describedby` where appropriate
- Scoring: weight by severity (missing alt = -0.2, heading skip = -0.1, contrast fail = -0.15, etc.)
**Security:** Read-only HTML analysis. No DOM manipulation.
**Verify:** Test matrix: fully accessible HTML (1.0), missing alts (deducted), broken heading hierarchy (deducted), poor link text (deducted), low contrast (deducted). Test that decorative images with `alt=""` are not penalised.

### ~~11.4 Fallback Check — MSO Conditional Parser~~ DONE
**What:** Replace presence-only detection (`"<!--[if mso" in html`) with a proper MSO conditional parser that validates syntax correctness, balanced pairs, VML nesting, and namespace declarations. Eval data shows **50% MSO conditional correctness failure** — the single worst failure cluster.
**Why:** Outlook rendering breaks silently when MSO conditionals are malformed. Current check passes HTML that will render incorrectly in Outlook (the largest email client by enterprise adoption). This is the highest-impact single check fix.
**Implementation:**
- ~~Rewrite `app/qa_engine/checks/fallback.py` with MSO-specific parser~~ DONE
- ~~**Balanced pair validation**: Count `<!--[if` openers == `<![endif]-->` closers. Report unbalanced pairs with approximate position~~ DONE
- ~~**VML nesting**: Verify all `<v:*>` and `<o:*>` elements are inside `<!--[if mso]>` blocks. Flag VML orphans~~ DONE
- ~~**Namespace validation**: If VML present, verify `xmlns:v="urn:schemas-microsoft-com:vml"` and `xmlns:o="urn:schemas-microsoft-com:office:office"` on `<html>` tag~~ DONE
- ~~**Ghost table structure**: Detect multi-column layouts and verify MSO ghost tables have proper `width` attributes~~ DONE
- ~~**Conditional targeting**: Validate version targeting syntax (`<!--[if gte mso 12]>`, `<!--[if !mso]><!--> ... <!--<![endif]-->`)~~ DONE
- ~~Extract reusable `validate_mso_conditionals(html) -> list[MSOIssue]` function for agents to call~~ DONE
- ~~Scoring: -0.25 per unbalanced pair, -0.2 per VML orphan, -0.15 per missing namespace, -0.1 per ghost table issue~~ DONE
**Security:** Read-only parsing. No code execution.
**Verify:** ~~Test: valid MSO HTML (1.0), unbalanced conditional (0.75), VML outside conditional (0.8), missing namespaces (0.85), complex nested conditionals (validates correctly). Eval re-run shows fallback check now catches issues that agents fail on.~~ DONE — 28 tests (18 parser unit + 10 integration), 195/195 QA tests pass.

### ~~11.5 Dark Mode Check — Semantic Validation~~ DONE
**What:** Upgrade from presence-only checks to semantic validation of dark mode implementation. Current check accepts empty `@media (prefers-color-scheme: dark)` blocks and HTML with `color-scheme` meta but no actual color remapping. Eval shows **50% meta tag failure rate**.
**Why:** Dark mode is the #1 rendering complaint from email clients. Passing the check with a broken dark mode implementation gives false confidence. The check should validate that dark mode actually works, not just that the syntax exists.
**Implementation:**
- ~~Rewrite `app/qa_engine/checks/dark_mode.py` with CSS parser~~
- ~~**Meta tag validation**: Both `<meta name="color-scheme" content="light dark">` AND `<meta name="supported-color-schemes" content="light dark">` must be in `<head>` (not body, not malformed)~~
- ~~**Media query validation**: `@media (prefers-color-scheme: dark)` block must contain at least one CSS rule with a color property (`color`, `background-color`, `background`, `border-color`)~~
- ~~**Outlook selector validation**: `[data-ogsc]` and `[data-ogsb]` selectors must contain actual color declarations (not empty)~~
- ~~**Color coherence**: Extract light mode colors and dark mode remapped colors. Flag obvious issues: white-on-white, black-on-black, text disappearing~~
- ~~**Apple Mail**: Check for `[data-apple-mail-background]` pattern (common Apple Mail dark mode fix)~~
- ~~Scoring: meta tags present (0.3), media query with rules (0.3), Outlook selectors with rules (0.2), color coherence (0.2)~~
**Security:** CSS parsing is read-only. Color extraction uses regex on style attributes.
**Verify:** ~~Test: complete dark mode (1.0), meta tags only (0.3), empty media query (0.3), Outlook selectors without rules (0.5), color coherence failure (flagged). Regression: existing passing HTML still passes.~~ 207/207 QA tests pass (47 parser unit + 16 integration + 144 other). Standalone `dark_mode_parser.py` with 6 sub-validators, `rules/dark_mode.yaml` (16 rules, 6 groups), 16 custom check functions, Dark Mode agent L3 skill file.

### ~~11.6 Spam Score Check — Production Trigger Database~~ DONE
**What:** Expand from 10 hardcoded trigger phrases to 50+ weighted triggers with case-insensitive word-boundary matching. Add formatting heuristics (excessive punctuation, all-caps words, obfuscation patterns). Current implementation misses most real spam patterns.
**Why:** Emails that pass current check may hit spam filters in Gmail, Outlook, Yahoo. SpamAssassin uses 100+ content rules. A flagged email wastes the entire campaign investment.
**Implementation:**
- ~~Rewrite `app/qa_engine/checks/spam_score.py`~~
- ~~**Trigger database**: Move triggers to `app/qa_engine/data/spam_triggers.yaml` — 50+ phrases with weights (0.05-0.30) and categories (urgency, money, action, clickbait)~~
- ~~**Case-insensitive word boundary matching**: Use `re.compile(rf"\b{trigger}\b", re.IGNORECASE)` — no more false positives from substrings~~
- ~~**Formatting heuristics**: Detect excessive punctuation (3+ `!` or `?`), all-caps words (>3 consecutive), mixed case obfuscation ("fR33", "d1scount")~~
- ~~**Subject line awareness**: If HTML contains `<title>` or known subject line meta, score it separately (subject is 3x more spam-prone)~~
- ~~**Weighted scoring**: `score = 1.0 - sum(trigger_weights)`, pass if score ≥ configurable threshold (default 0.5)~~
- ~~**Detail reporting**: List every matched trigger with weight and category for user transparency~~
**Security:** Trigger database is static YAML, not user-modifiable. Regex patterns are pre-compiled at module load.
**Verify:** ~~Test: clean copy (1.0), "Buy Now" (deducted), "FREE SHIPPING!!!" (multiple deductions), obfuscated "FR33" (caught), edge case "guarantee" in legitimate context (low weight).~~ 353/353 QA tests pass (11 spam tests). `data/spam_triggers.yaml` (59 triggers, 7 categories), `rules/spam_score.yaml` (6 rules, 4 groups), 6 custom check functions, rule engine integration.

### ~~11.7 Link Validation — HTML Parser + URL Format Check~~ DONE
**What:** Replace fragile regex extraction with proper HTML parser link extraction. Add URL format validation, ESP template variable syntax checking, and empty href detection.
**Why:** Current regex breaks on complex href syntax (mixed quotes, newlines, encoded characters). Malformed links cause broken emails that look unprofessional. ESP template variables like `{{ url }}` need syntax validation.
**Implementation:**
- Rewrite `app/qa_engine/checks/link_validation.py` using HTML parser
- **Proper extraction**: Parse all `<a>` tags, extract `href` attribute value properly (handles quotes, encoding)
- **URL format validation**: Use `urllib.parse.urlparse()` — verify scheme, netloc, path are well-formed
- **ESP template validation**: Detect `{{ }}` (Liquid), `%%[ ]%%` (AMPscript), `<%= %>` (JSSP). Validate balanced delimiters
- **Empty href detection**: Flag `href=""`, `href="#"` (except intentional anchors), `href="javascript:"`
- **URL encoding**: Flag unencoded spaces, special characters that will break in email clients
- **Tracking pixel whitelist**: Don't flag known tracking pixel patterns (1x1 images, `open.gif` etc.)
- Scoring: -0.15 per broken link, -0.10 per HTTP link, -0.05 per empty/suspicious href
**Security:** No HTTP requests to validate links (avoid SSRF). Validation is syntax-only.
**Verify:** Test: all valid HTTPS links (1.0), HTTP link (deducted), malformed URL (deducted), empty href (deducted), valid Liquid template var (not flagged), unbalanced `{{ url }` (flagged).

### ~~11.8 File Size Check — Multi-Client Thresholds~~ DONE
**What:** Extend beyond Gmail-only 102KB threshold to include client-specific limits from the ontology. Add content breakdown analysis (markup vs styles vs images).
**Why:** Emails may pass Gmail's threshold but clip in Yahoo (75KB) or hit issues in other clients. Without breakdown analysis, developers don't know what to trim.
**Implementation:**
- Update `app/qa_engine/checks/file_size.py`
- **Client-specific thresholds**: Load from ontology or config: Gmail (102KB), Yahoo (~75KB), Outlook.com (~100KB). Report per-client pass/fail
- **Content breakdown**: Calculate size of: inline styles, HTML markup (minus styles), embedded images (base64), total. Report as percentages
- **Gzip estimate**: Calculate gzip compressed size as secondary metric (actual transfer size)
- **Actionable guidance**: If over threshold, identify largest contributors: "Inline styles: 45KB (44%) — consider external stylesheet or removing unused rules"
- Scoring: 1.0 if under all client thresholds, deduct based on most impacted client's overage
**Security:** Read-only size calculation. No file system access.
**Verify:** Test: small HTML (1.0), 80KB HTML (passes Gmail, flags Yahoo), 110KB HTML (fails multiple), breakdown percentages are accurate.

### ~~11.9 Image Optimization — Comprehensive Validation~~ DONE
**What:** Upgrade from first-image-only dimension check to all-image validation with format analysis, dimension value validation, and tracking pixel detection.
**Why:** Current check only catches the first missing dimension and only flags BMP format. WebP has limited email client support. Invalid dimension values (`width="auto"`, `width="0"`) cause layout breaks.
**Implementation:**
- Rewrite `app/qa_engine/checks/image_optimization.py` using HTML parser
- **All images**: Check every `<img>` tag, not just the first. Report per-image results
- **Dimension validation**: Verify `width` and `height` are positive integers, < 5000px, realistic aspect ratios. Flag `auto`, `100%`, negative values
- **Format support**: Flag formats with limited email support — WebP (poor), SVG (partial), BMP (never), AVIF (none). Recommend JPEG/PNG/GIF
- **Tracking pixels**: Detect 1x1 images — don't flag for missing dimensions (legitimate pattern)
- **Retina detection**: If `width` attribute differs significantly from intrinsic width hint, note potential retina image
- Scoring: -0.15 per image missing dimensions, -0.10 per unsupported format, cap at 0.0
**Security:** No image fetching (avoid SSRF). Attribute analysis only.
**Verify:** Test: all images with dimensions (1.0), missing dimensions on 3 images (deducted), WebP format (flagged), 1x1 tracking pixel without dimensions (not flagged), `width="auto"` (flagged).

### ~~11.10 CSS Support Check — Syntax Validation & Vendor Prefixes~~ DONE
**What:** Add CSS syntax validation and vendor prefix detection to the existing ontology-powered check. Current check scans for unsupported properties but doesn't catch malformed CSS or vendor prefixes that may not work.
**Why:** Malformed CSS rules silently fail in email clients. Vendor prefixes (`-webkit-`, `-moz-`) have inconsistent email client support but aren't in the ontology. Full issue list truncation at 10 hides real problems.
**Implementation:**
- Extend `app/qa_engine/checks/css_support.py`
- **CSS syntax validation**: Parse CSS blocks with `cssutils` or regex-based validator. Flag malformed rules (unclosed braces, missing semicolons, invalid property names)
- **Vendor prefix detection**: Flag `-webkit-`, `-moz-`, `-ms-`, `-o-` prefixes. Cross-reference with ontology for actual support data
- **Full issue reporting**: Remove 10-issue truncation. Return all issues in `details` field. Frontend can paginate
- **External stylesheet detection**: If `<link rel="stylesheet">` found, flag it (most email clients strip external CSS)
- Scoring: existing ontology scoring + deductions for syntax errors (-0.1 each) and unsupported vendor prefixes (-0.05 each)
**Security:** CSS parsing is read-only. No external fetches for linked stylesheets.
**Verify:** Test: valid CSS with supported properties (1.0), unsupported `display: flex` (deducted per ontology), malformed CSS `color: ` with no value (flagged), vendor prefix `-webkit-transform` (flagged), external stylesheet (flagged).

### ~~11.11 Brand Compliance Check — Per-Project Rules Engine~~ DONE
**What:** Replace the always-pass placeholder with a configurable brand rules engine. Validate colors, typography, logo presence, and footer requirements against per-project brand guidelines.
**Why:** Brand compliance is currently zero-enforced. Off-brand emails reaching clients damages credibility. This is the only check that's completely non-functional.
**Implementation:**
- Rewrite `app/qa_engine/checks/brand_compliance.py`
- Create `BrandRules` Pydantic model: `allowed_colors: list[str]`, `required_fonts: list[str]`, `required_elements: list[str]` (e.g., "footer", "logo"), `forbidden_patterns: list[str]`
- Load brand rules from project config (new `brand_rules` JSON column on `Project` model, or separate `BrandProfile` model)
- **Color validation**: Extract all CSS colors (hex, rgb, rgba, named), validate against brand palette. Flag off-brand colors with severity
- **Typography validation**: Extract font-family declarations, validate against brand-approved fonts
- **Required elements**: Check for required sections (footer with legal text, logo image, unsubscribe link)
- **If no brand rules configured**: Return `passed=True` with "No brand rules configured — set up brand profile for enforcement" (backward-compatible)
- Scoring: -0.2 per off-brand color, -0.15 per wrong font, -0.25 per missing required element
**Security:** Brand rules are project-scoped, validated by Pydantic. No code execution.
**Verify:** Test: HTML matching brand rules (1.0), off-brand color (deducted), wrong font (deducted), missing footer (deducted), no brand rules configured (1.0 with info message). Existing tests unchanged.
**Delivered:** `brand_analyzer.py` (CSS color/font extraction, required element detection, cached analysis); `rules/brand_compliance.yaml` (7 rules, 5 groups); rewritten `checks/brand_compliance.py` as rule engine wrapper; 7 custom check functions in `custom_checks.py`; backward-compatible (empty rules → pass); 27 new tests (12 analyzer + 15 integration).

### ~~11.12 New Check — Personalisation Syntax Validation (Check #11)~~ DONE
**What:** Add an 11th QA check that validates ESP-specific template syntax: Liquid (Braze), AMPscript (SFMC), JSSP (Adobe Campaign). No existing check covers personalisation correctness. Agent eval shows **58% logic match failure** for Personalisation agent.
**Why:** Broken template syntax causes runtime errors in ESPs — variables don't render, conditionals break, fallbacks fail. This is invisible until the email is sent to real subscribers. Catching syntax errors in QA prevents broken personalisation in production.
**Implementation:**
- ~~Create `app/qa_engine/checks/personalisation_syntax.py`~~
- ~~Add to `ALL_CHECKS` list in service~~
- ~~**Auto-detect platform**: Scan for `{{ }}` (Liquid), `%%[ ]%%` (AMPscript), `<%= %>` (JSSP). If none found, return `passed=True` ("No personalisation detected")~~
- ~~**Liquid validation**: Balanced `{% if %}...{% endif %}`, `{% for %}...{% endfor %}`, valid `{{ var | filter }}` syntax, `{% unless %}...{% endunless %}`~~
- ~~**AMPscript validation**: Balanced `%%[...]%%` blocks, valid function syntax (`Lookup()`, `Set @var`), `IF...ENDIF` balance~~
- ~~**JSSP validation**: Balanced `<%= %>` blocks, proper escaping~~
- ~~**Fallback detection**: For each dynamic variable, check if a default/fallback is provided (e.g., `{{ name | default: "there" }}`)~~
- ~~**Cross-platform conflict**: Flag if multiple ESP syntaxes detected in same HTML (likely error)~~
- ~~Scoring: -0.2 per unbalanced tag pair, -0.15 per missing fallback, -0.1 per syntax error~~
**Security:** Pure syntax parsing, no template execution. No variable interpolation.
**Verify:** ~~Test: valid Liquid with fallbacks (1.0), unbalanced `{% if %}` (deducted), missing fallback on `{{ first_name }}` (deducted), valid AMPscript (1.0), mixed Liquid+AMPscript (flagged). `make test` passes.~~

### ~~11.13 Outlook Fixer Agent — MSO Diagnostic Validator~~ DONE
**What:** Add deterministic MSO validation to the Outlook Fixer agent service. Before returning HTML, programmatically verify MSO conditional balance and VML nesting. Reuse the `validate_mso_conditionals()` function from 11.4. Current eval: **50% MSO conditional correctness failure**.
**Why:** LLMs consistently struggle with MSO conditional syntax — they see `<!--[if mso]>` as incomplete comments and "fix" them. A post-generation validator catches these errors before the agent returns output, converting a 50% failure to near-zero.
**Implementation:**
- Import `validate_mso_conditionals()` from `app/qa_engine/checks/fallback.py` into `app/ai/agents/outlook_fixer/service.py`
- After LLM generates HTML, call validator. If issues found:
  - Attempt programmatic fix: re-balance conditionals, inject missing namespaces
  - If programmatic fix insufficient, retry LLM with explicit error context: "Your output has 2 unbalanced MSO conditionals at positions X, Y. Fix these specific issues."
  - Max 1 programmatic retry to avoid infinite loops
- Update Outlook Fixer SKILL.md `mso_conditionals.md` with explicit pair-balance rules and common LLM mistakes
- Emit validator results in `AgentHandoff.warnings` for downstream agents
**Security:** Validator is read-only analysis. Programmatic fixes are limited to injecting closing tags and namespace attributes.
**Verify:** `make eval-run --agent outlook_fixer` shows MSO conditional pass rate improvement from 50% to 85%+. Manual test: intentionally unbalanced MSO HTML → agent fixes it. Existing tests pass.

### ~~11.14 Dark Mode Agent — Deterministic Meta Tag Injector~~ DONE
**What:** Add deterministic meta tag injection to the Dark Mode agent service. Before returning HTML, check `<head>` for both required meta tags and inject if missing. Current eval: **50% meta tag failure**.
**Why:** The agent forgets one of the two required meta tags ~50% of the time. A simple programmatic check + inject eliminates this failure mode entirely without relying on the LLM.
**Implementation:**
- In `app/ai/agents/dark_mode/service.py`, after LLM generation:
  - Parse HTML, find `<head>` section
  - Check for `<meta name="color-scheme" content="light dark">` — inject if missing
  - Check for `<meta name="supported-color-schemes" content="light dark">` — inject if missing
  - Inject at end of `<head>` (before `</head>`) to avoid disrupting existing content
- Update Dark Mode SKILL.md with explicit meta tag checklist
- Add color coherence validation: extract light/dark color pairs, flag white-on-white or black-on-black combinations
**Security:** Meta tag injection is adding standard HTML tags to `<head>`. No script injection possible.
**Verify:** `make eval-run --agent dark_mode` shows meta tag pass rate improvement from 50% to 95%+. Test: HTML without meta tags → agent adds them. HTML with both tags → no change.

### ~~11.15 Scaffolder Agent — MSO-First Generation~~ DONE
**What:** Update Scaffolder SKILL.md and service to generate MSO-correct HTML from the first attempt. Load Outlook Fixer's MSO patterns as reference context. Current eval: **58% MSO conditional failure** — the scaffolder should never generate broken MSO.
**Why:** If the scaffolder generates correct MSO from the start, the entire blueprint pipeline avoids one retry loop. MSO fixes are the most common recovery router destination. Prevention > correction.
**Implementation:**
- Update `app/ai/agents/scaffolder/SKILL.md` with mandatory MSO section:
  - Every template MUST include MSO centering table wrapper
  - MUST include `xmlns:v` and `xmlns:o` on `<html>` when VML used
  - MUST balance all conditional comments
  - Reference Outlook Fixer's `mso_conditionals.md` patterns
- In `app/ai/agents/scaffolder/service.py`, load Outlook Fixer's L3 SKILL files into system prompt context (top 15 MSO patterns)
- Add same `validate_mso_conditionals()` post-generation check as 11.13
- Emit MSO validation status in `AgentHandoff.decisions` so downstream agents know MSO is verified
**Security:** Cross-agent SKILL file loading is read-only from local filesystem.
**Verify:** `make eval-run --agent scaffolder` shows MSO conditional pass rate improvement from 58% to 85%+. Blueprint pipeline test: scaffolder output passes fallback QA check on first attempt.

### ~~11.16 Personalisation Agent — Per-Platform Syntax Validator~~ DONE
**What:** Add deterministic per-platform template syntax validation to the Personalisation agent service. Before returning HTML, validate balanced tags and fallback presence. Current eval: **58% logic match failure**.
**Why:** LLMs generate plausible-looking but syntactically broken template code. Liquid `{% if %}` without `{% endif %}`, AMPscript `%%[` without `]%%`. A programmatic validator catches these mechanical errors.
**Implementation:**
- `ESPPlatform` expanded from 3 → 7 platforms (added klaviyo, mailchimp, hubspot, iterable)
- `SKILL_FILES` expanded from 4 → 8 L3 skill files (all 7 ESP skills + fallback_patterns)
- `platform_map` expanded to 7 entries; cross-platform references for all 7 ESPs with specific keywords
- `format_syntax_warnings(html)` shared helper in `service.py` — calls `analyze_personalisation()` from `personalisation_validator.py`, formats warnings with `[error]`/`[warning]` prefixes
- `PersonalisationService._post_process()` override with `contextvars.ContextVar` thread-safe warning storage
- `PersonalisationResponse.syntax_warnings` field exposes validator findings via API
- `PersonalisationNode` in blueprint emits `warnings=tuple(syntax_warnings)` in `AgentHandoff` for Recovery Router
- SKILL.md updated with post-generation validation annotations and balanced-tag emphasis
- 28 unit tests (formatter, service post-process, contextvar, all 7 platforms, all 8 skills, cross-platform refs)
**Security:** Syntax validation only. No template rendering or variable interpolation.
**Verify:** `make check` passes. All 28 tests pass. mypy + pyright clean (0 errors).

### ~~11.17 Code Reviewer Agent — Actionability Framework~~ DONE
**What:** Update Code Reviewer SKILL.md to require "change X to Y" format for every suggestion. Current eval: **67% suggestion actionability** — suggestions are too vague.
**Why:** Vague suggestions like "simplify CSS" don't help agents or developers. Actionable suggestions like "Replace `display: flex` with `<table>` layout (unsupported in Outlook 2019)" can be auto-applied.
**Implementation:**
- Update `app/ai/agents/code_reviewer/SKILL.md`:
  - Every suggestion MUST include: property/element name, current value, recommended replacement, affected clients
  - Format: `ISSUE: {property} on line {N} | CURRENT: {value} | FIX: {replacement} | CLIENTS: {list}`
  - Reference ontology data in suggestions (link CSS property to client support matrix)
- Expand "email allowlist" in SKILL.md: add `mso-` prefixes, `[data-ogsc]` selectors, MSO conditionals, VML elements as known-good patterns
- In service, validate output format: if suggestions don't match actionable format, retry with format correction prompt
- Add 75%+ coverage completeness target: reviewer should flag issues in at least 75% of categories (CSS, HTML structure, accessibility, performance)
**Security:** Output format validation is string matching. No code execution.
**Verify:** `make eval-run --agent code_reviewer` shows suggestion actionability improvement from 67% to 85%+. Manual review: every suggestion has concrete before/after values.

### ~~11.18 Accessibility Agent — Alt Text Quality Framework~~ DONE
**What:** Update Accessibility Auditor SKILL.md with structured alt text generation rules. Current eval: **70% alt text quality, 70% screen reader compatibility**.
**Why:** Generic alt text ("image", "photo") is worse than no alt text — it clutters screen readers without conveying information. The agent needs clear rules for decorative vs informative images and quality criteria.
**Implementation:**
- Update `app/ai/agents/accessibility/SKILL.md` with alt text framework:
  - **Decorative images** (borders, spacers, backgrounds): `alt=""`
  - **Content images** (product shots, photos): 5-15 words, describe what's shown, not the file name
  - **Functional images** (buttons, icons, CTAs): describe the action ("Submit form", "Download PDF"), not appearance
  - **Logo images**: company name only ("Acme Corp"), not "Acme Corp logo image"
  - **Complex images** (charts, infographics): `aria-describedby` pointing to text description
- Add WCAG AA contrast ratio rules to SKILL.md: 4.5:1 for normal text, 3:1 for large text (≥18pt or ≥14pt bold)
- Update service to validate alt text quality before returning: reject single-word alts, reject generic terms, verify length bounds
- Add screen reader landmark recommendations: `role="banner"`, `role="main"`, `role="contentinfo"` for email structure
**Security:** Alt text generation from image context. No image fetching or processing.
**Verify:** `make eval-run --agent accessibility` shows alt text quality improvement from 70% to 85%+. Test: image with no context → descriptive alt generated. Decorative spacer → `alt=""`.

### ~~11.19 Content Agent — Length Guardrails~~ DONE
**What:** Add token/character limits per operation type to the Content agent. Current eval: **71% length appropriate** — expand operations overshoot, shorten operations remove critical info.
**Why:** Email copy has strict length constraints. Subject lines (50 chars ideal), preheaders (85-100 chars), CTAs (2-5 words). Without guardrails, the LLM generates copy that doesn't fit.
**Implementation:**
- Update `app/ai/agents/content/SKILL.md` with length rules per operation:
  - Subject line: 30-60 chars (50 ideal), no truncation in mobile preview
  - Preheader: 85-100 chars (fills preview pane, prevents body text leak)
  - CTA text: 2-5 words, action verb first ("Get Started", "Download Now")
  - Body copy: respect original length ±20% for tone/rewrite operations
  - Expand: max 150% of original length
  - Shorten: min 50% of original, preserve all key information points
- In service, post-generation length validation:
  - If subject > 60 chars, retry with explicit "shorten to under 60 characters" instruction
  - If CTA > 5 words, retry with word count constraint
  - Max 1 retry per length violation
- Add excessive punctuation detection: strip `!!!`, `???`, `...` patterns from generated copy
**Security:** Length validation is character counting. No content injection.
**Verify:** `make eval-run --agent content` shows length appropriate improvement from 71% to 85%+. Test: "expand this paragraph" → output ≤ 150% original length. Subject line generation → ≤ 60 chars.

### ~~11.20 Recovery Router — Enriched Failure Context~~ DONE
**What:** Upgrade recovery router to pass detailed, structured failure information to fixer agents instead of generic check names. Currently sends `"fallback: failed"` — should send `"fallback: 2 unbalanced MSO conditionals at lines 45, 89; VML orphan at line 112"`.
**Why:** Agents with specific error context fix issues 3x faster than agents with generic "this check failed" messages. Reduces retry loops from 2-3 to 1. This amplifies every individual check improvement.
**Implementation:**
- Update `app/ai/blueprints/nodes/recovery_router_node.py`
- QA check results already contain `details: str` — pass the full details string (not just check name) to recovery context
- Structure failure context as: `{check_name: str, score: float, details: str, suggested_agent: str, priority: int}`
- Order failures by priority (MSO > accessibility > dark mode > spam > links > images > size)
- Inject into `NodeContext.metadata["qa_failure_details"]` — list of structured failure objects
- Recovery router selects agent based on highest-priority failure, but passes ALL failure details so agent can fix multiple issues in one pass
- Add cycle detection enhancement: if same check failed with same details twice, escalate to scaffolder (full regeneration) instead of same fixer
- **Scoped retry constraints:** On retry, constrain what each agent can modify to prevent cascading failures. Scaffolder: HTML structure only (no new CSS frameworks). Dark mode: CSS only (`<style>` + inline styles, no HTML restructuring). Content: text nodes + attributes only (`alt`, `title`, `aria-label`). Outlook fixer: add MSO/VML only (no HTML removal). Enforce via prompt constraints on retry + output diff validation (reject changes outside allowed scope).
**Security:** Failure details are derived from QA check output (already sanitised). No user input injection.
**Verify:** Blueprint test: intentionally broken HTML with 3 QA failures → recovery router passes all 3 with details → fixer agent receives structured context. Fewer retry loops than current generic routing. Retry output diff stays within allowed scope per agent.

### ~~11.21 Deterministic Micro-Judges — Codify Judge Criteria into QA Checks~~ DONE
**What:** Extract the subset of eval judge criteria that can be validated deterministically and add them as enhanced QA checks. ~60% of judge criteria across all 9 agents map to codifiable rules (e.g., "uses nested tables with 600px max-width" from ScaffolderJudge, "balanced MSO conditionals" from OutlookFixerJudge). This gives judge-quality detection at QA-gate speed (0 tokens, <50ms per check).
**Why:** Items 11.2–11.12 already upgrade individual QA checks. This task explicitly maps each judge criterion to its deterministic equivalent, ensuring QA checks cover what judges catch. After this, the QA gate catches ~90% of what LLM judges would flag, making inline judges (11.23) only necessary for the remaining ~10% that requires LLM reasoning (brief fidelity, tone accuracy, copy quality).
**Implementation:**
- Create `app/qa_engine/judge_criteria_map.py` — mapping of `{agent: {criterion: qa_check_name | None}}`:
  - ScaffolderJudge: `email_layout_patterns` → html_validation (11.2), `mso_conditionals` → fallback (11.4), `dark_mode_readiness` → dark_mode (11.5), `accessibility_baseline` → accessibility (11.3), `brief_fidelity` → None (requires LLM)
  - DarkModeJudge: `html_preservation` → html_validation, `outlook_selector_completeness` → fallback, `meta_and_media_query` → dark_mode, `contrast_preservation` → accessibility, `color_coherence` → None (requires LLM)
  - ContentJudge: `spam_avoidance` → spam_score (11.6), `operation_compliance` → None, `copy_quality` → None, `tone_accuracy` → None, `security_and_pii` → brand_compliance (11.11)
  - (Map remaining 6 agents similarly)
- For each mapped criterion, verify the upgraded QA check (11.2–11.12) covers the judge's specific validation logic. Add sub-checks where gaps exist.
- Add `make eval-qa-coverage` command: runs all judges + QA checks on same test set, reports criterion-vs-check agreement rate. Target: >85% agreement on mapped criteria.
- Update recovery router (11.20) — use criteria map to route QA failures to the correct fixer agent with judge-criterion-level specificity
**Security:** No new attack surface — extends existing deterministic checks only.
**Verify:** Run `make eval-qa-coverage` on all 9 agents' synthetic data. For each mapped criterion, QA check agrees with judge verdict >85% of the time. Unmapped criteria (brief_fidelity, tone_accuracy, etc.) documented as "LLM-only" — these are what 11.23 inline judges cover.

### ~~11.22 Template-First Hybrid Architecture — From 16.7% to 99%+ Overall Pass Rate~~ DONE

**What:** Replace LLM-generates-everything architecture with a hybrid model where deterministic code generates all structural HTML and the LLM makes content/design decisions only. The LLM never writes a `<table>` tag, `<!--[if mso]>` conditional, or `<meta>` tag — it selects templates, fills content slots, and chooses design tokens. Deterministic Python assembles the final HTML from tested, pre-validated building blocks.

**Why:** Current 16.7% pass rate (36 traces via claude-sonnet-4) fails because the LLM is asked to generate the hardest HTML that exists — table layouts, MSO conditionals, VML, 25-client compatibility. Even frontier models struggle (Sonnet: 0% on MSO conditionals, 8% on accessibility, 10% on html_preservation). The insight: **if deterministic code generates every structural element, QA checks are validating code we wrote and tested, not LLM output.** This eliminates entire failure categories by construction rather than correction. No model changes needed — this extracts maximum value from Claude Sonnet/Opus by giving the LLM the job it's actually good at (creative content decisions) and taking away the job it's bad at (syntax-precise structural HTML). Local/weaker models are not viable — email HTML generation is one of the hardest LLM tasks; substituting models would degrade quality further.

**Target ceiling:** 99%+ overall pass rate. Structural checks: deterministic guarantees via golden templates + cascading repair. Semantic quality (tone, copy): structured output schemas with per-field retry.

**Dependencies:** 11.1–11.21 (upgraded QA checks + deterministic micro-judges provide better feedback signals). Phase 8-9 (ontology for client compatibility data). Phase 7 (SKILL.md, BaseAgentService). Phase 2 (component library for golden template building blocks).

**Detailed implementation plan:** `.agents/plans/11.22-deterministic-agent-architecture.md`

**Key decisions:**
- **Golden templates:** Maizzle source (`app/ai/templates/maizzle_src/`) + pre-compiled HTML (`app/ai/templates/library/`). Templates extend existing `main.html` layout.
- **Slot markers:** `data-slot="{id}"` attributes on HTML elements (survives lxml parsing, easy to target).
- **Template metadata:** YAML companion files in `_metadata/*.yaml` (decoupled from HTML).
- **Structured output:** Provider-agnostic — Anthropic adapter uses tool_use, OpenAI adapter uses response_format, fallback to JSON-in-prompt + Pydantic validation. `CompletionResponse.parsed` field.
- **Repair pipeline:** Lives in `app/qa_engine/repair/` (paired with QA checks). 7 deterministic stages, reuses existing `mso_repair.py` and `meta_injector.py`.
- **Section blocks:** Reuse existing Maizzle components (`email-templates/components/`) as starting material, harden with MSO/a11y/dark mode for QA compliance.
- **Backward compatibility:** `output_mode: Literal["html", "structured"] = "html"` on all agent requests. `_process_structured()` hook in `BaseAgentService`.

**Execution order (4 weeks):**
| Week | Subtasks (parallel where possible) | Milestone |
|------|-------------------------------------|-----------|
| W1 | 11.22.1 + 11.22.2 (parallel — no deps) | Foundation: templates + schemas |
| W2 | 11.22.3 + 11.22.4 (depend on W1) | **M1: 70%** — pipeline + auto-repair |
| W3 | 11.22.5 + 11.22.6 (depend on W1-W2) | **M2: 85%** — architect prompts + context budget |
| W4 | 11.22.7 + 11.22.8 (depend on W1-W3) | **M3: 95%** — 5 HTML agents migrated |
| Ongoing | 11.22.9 (continuous) | **M4: 99%+** — iteration on failure modes |

**Architecture pattern (PIV loop):** Inspired by Stripe Minions + deterministic agentic coding workshop. LLM makes decisions (structured JSON) → deterministic code assembles HTML → deterministic QA validates → LLM retries with exact errors. Each agent gets per-agent decision schema (`DarkModePlan`, `OutlookFixPlan`, `AccessibilityPlan`, `PersonalisationPlan`, `CodeReviewPlan`, `ContentPlan`). Backward compatible via `output_mode: Literal["html", "structured"]` flag on each agent's request schema.

**Files (~62 new, ~30 modified):** Templates (~20 HTML + 4 Python), schemas (8 Python), pipeline (3 Python), repair stages (9 Python), SKILL.md rewrites (7 + 5 prompt.py), composer (15 HTML + 2 Python), agent migrations (14 service.py + nodes), tests (5 Python).

#### ~~11.22.1 Golden Template Library — Pre-Validated Email Skeletons~~ DONE
**What:** Build 15 battle-tested email templates (Maizzle source + pre-compiled HTML) covering ~95% of real campaign briefs. Each template passes all 11 QA checks with score >= 0.9. Templates use `data-slot="{id}"` attribute markers on HTML elements — the LLM fills slots, never generates structural HTML.
**Why:** Highest-impact change. MSO conditionals go from 0% to ~99% (pre-written, pre-tested). Dark mode ~50% to ~99% (meta tags, media queries, Outlook selectors pre-wired). The LLM's job shrinks from "generate a complete email" to "pick a template and fill in the blanks."
**Implementation:**
- Create `app/ai/templates/` directory with dual-format template library:
  - `app/ai/templates/models.py` — `GoldenTemplate`, `TemplateSlot`, `TemplateMetadata` frozen dataclasses. `SlotType` Literal (headline/body/cta/image/etc), `LayoutType` Literal (newsletter/promotional/transactional/event/retention/announcement/minimal)
  - `app/ai/templates/registry.py` — `TemplateRegistry` class: `get(name)`, `search(layout_type, column_count, has_hero)`, `fill_slots(template, fills)`, `list_for_selection() -> list[TemplateMetadata]`. Module-level `get_template_registry()` singleton
  - `app/ai/templates/compiler.py` — `compile_template(name)` / `compile_all()` via maizzle-builder sidecar HTTP call. Caches compiled HTML in `library/`
  - `app/ai/templates/maizzle_src/` — 15 Maizzle source templates extending `src/layouts/main.html`, using `<component>` includes
  - `app/ai/templates/library/` — Pre-compiled HTML (committed, works without sidecar)
  - `app/ai/templates/library/_metadata/` — YAML companion files per template (name, display_name, layout_type, column_count, sections, ideal_for, description, slot definitions with slot_id/slot_type/selector/required/max_chars/placeholder)
- Build 15 initial templates:
  - **Newsletter** (2): single-column, two-column
  - **Promotional** (3): hero image, product grid, 50/50 split
  - **Transactional** (3): receipt, shipping, welcome/onboarding
  - **Event** (2): invitation, reminder
  - **Retention** (2): win-back, survey
  - **Announcement** (2): product launch, company news
  - **Minimal** (1): text-heavy minimal design
- Each template must:
  - Extend `src/layouts/main.html` (inherits MSO skeleton, dark mode meta, VML/Office namespaces)
  - Use `data-slot="{id}"` attributes on all content elements
  - Have `role="presentation"` on all layout tables, `alt` on all images, `scope` on `<th>`
  - Pass all 11 QA checks with score >= 0.9 (verified by parametrized pytest)
  - Use fluid hybrid layout (600px max-width, responsive to 320px)
- QA regression test: `app/ai/templates/tests/test_templates.py` — parametrized over all templates × all 11 checks
**Security:** Templates are static files in the repo. No user input in template structure. Slot fills validated by `TemplateSlot.max_chars` before assembly. HTML slot content sanitised by `sanitize_html_xss()`.
**Verify:** `make test -k test_templates` — all 15 templates pass all 11 QA checks >= 0.9. `make types` — zero errors.

#### ~~11.22.2 Structured Output Schemas — LLM Returns JSON, Not HTML~~ DONE
**What:** Define typed dataclass schemas for each agent's decisions (not HTML output). Extend LLM provider protocol for provider-agnostic structured output. Add `output_mode` flag to all agent requests and `_process_structured()` hook to `BaseAgentService`.
**Why:** Structured output is dramatically more reliable than freeform generation. JSON is parseable, validatable, and retryable at the field level — a malformed subject line doesn't require regenerating the entire email. Provider-agnostic approach lets each adapter use its best mechanism (Anthropic→tool_use, OpenAI→response_format).
**Implementation:**
- Create `app/ai/agents/schemas/` — 7 decision dataclass files:
  - `build_plan.py` — `EmailBuildPlan` (master scaffolder output): `TemplateSelection` (template_name, reasoning, section_order for compose, fallback), `SlotFill` (slot_id, content, is_personalisable), `DesignTokens` (primary/secondary/background/text colors, font families, border_radius, button_style), `SectionDecision` (section_name, background_color, hidden)
  - `dark_mode_plan.py` — `DarkModePlan`: `ColorMapping` (light/dark color, selector, property), meta_tag_strategy, outlook_override_strategy, preserve_brand_colors
  - `outlook_plan.py` — `OutlookFixPlan`: `MSOFix` (issue_type, location_hint, fix_description, fix_html), add_namespaces, add_ghost_tables
  - `accessibility_plan.py` — `AccessibilityPlan`: `AltTextDecision` (img_selector, category, alt_text, is_decorative), `A11yFix` (issue_type, selector, fix_value)
  - `personalisation_plan.py` — `PersonalisationPlan`: `PersonalisationTag` (slot_id, tag_syntax, fallback, is_conditional), `ConditionalBlock` (condition, true/false content, platform_syntax)
  - `code_review_plan.py` — `CodeReviewPlan`: formalises existing `CodeReviewIssue` as `CodeReviewFinding` (rule_name, severity, responsible_agent, current/fix values, selector, is_actionable)
  - `content_plan.py` — `ContentPlan`: `ContentAlternative` (text, tone, char/word count, reasoning), selected_index
- Extend `app/ai/protocols.py` — add `parsed: dict[str, object] | None = None` field to `CompletionResponse`
- Extend adapters (provider-agnostic):
  - `app/ai/adapters/anthropic.py` — detect `output_schema` in kwargs → define tool with schema, set `tool_choice`, parse tool_use response → `CompletionResponse.parsed`
  - `app/ai/adapters/openai_compat.py` — detect `output_schema` in kwargs → set `response_format` with json_schema → parse response → `CompletionResponse.parsed`
  - Both pass through gracefully when `output_schema` not provided (no behavioral change)
- Extend `app/ai/agents/base.py`:
  - Add `output_mode_default`, `_output_mode_supported` class attrs
  - Split `process()` into `_process_html()` (current) + `_process_structured()` (new hook, raises `NotImplementedError` by default)
  - Add `_get_output_mode(request)` helper
- Add `output_mode: Literal["html", "structured"] = "html"` to all 5 HTML agent request schemas
- Add `plan: dict[str, object] | None = None` to all 5 HTML agent response schemas
**Security:** JSON schema enforced by frozen dataclasses. Slot fill content sanitised by `sanitize_html_xss()` during assembly. Design token hex values validated. No raw dict access.
**Verify:** `make types` — zero errors. `make test` — existing tests pass (backward compatible, output_mode defaults to "html").

#### ~~11.22.3 Multi-Pass Generation Pipeline — Decompose for Reliability~~ DONE
**What:** Replace the single LLM call with 3 focused passes, each with a narrow scope and independent validation. Errors in one pass don't cascade — a bad CTA doesn't require regenerating the layout decision.
**Why:** Compound reliability: if each pass has 95% accuracy, a single pass = 95% overall, but the current single-call approach asks for 10+ correct decisions simultaneously (95%^10 = 60%). Three focused passes with 3-4 decisions each: (95%^4)^3 = 70% worst case, but with per-field retry the effective rate approaches 99%.
**Implementation:**
- Create `app/ai/agents/pipeline.py` — `MultiPassPipeline` orchestrator:
  - **Pass 1 — Layout Analysis** (cheap, Haiku-tier model via `_get_model_tier("lightweight")`):
    - Input: campaign brief
    - Output: `TemplateSelection` — which golden template, reasoning
    - Validation: template_id exists in library, layout matches brief intent
    - Retry: if invalid template_id, retry with available template list
    - Cost: ~500-1,000 tokens
  - **Pass 2 — Content Generation** (quality, Sonnet-tier model via `_get_model_tier("standard")`):
    - Input: brief + selected template's `SlotDef` list (tells LLM exactly what content is needed)
    - Output: `list[SlotFill]` + `subject_line` + `preheader`
    - Validation: all required slots filled, content within `SlotDef.constraints` (char limits, required fields)
    - Retry: per-slot — only regenerate slots that failed validation
    - Cost: ~2,000-4,000 tokens
    - **Parallelisable**: if template has independent slots, generate them in parallel
  - **Pass 3 — Design & Personalisation** (cheap, Haiku-tier):
    - Input: brief + template + filled slots summary
    - Output: `DesignTokens` + `PersonalisationConfig`
    - Validation: hex colors valid, contrast ratio ≥ 4.5:1 (computed deterministically), font stacks valid, ESP variables syntactically correct
    - Retry: if contrast fails, retry with "ensure dark_text on dark_background has ≥4.5:1 contrast ratio"
    - Cost: ~500-1,000 tokens
  - **Assembly** (deterministic, 0 tokens):
    - `assemble_from_plan()` combines all three pass outputs into final HTML
    - Run all 10 QA checks
    - If QA fails: identify which pass produced the failing element, retry ONLY that pass with QA feedback
- Wire into `BaseAgentService` — `MultiPassPipeline` replaces single `_call_llm()` for generation agents
- Existing single-call path preserved behind feature flag `AGENT__USE_MULTI_PASS` (default `True`, set `False` for A/B comparison)
**Security:** Each pass receives only the context it needs (principle of least privilege for LLM context). Pass outputs validated by Pydantic before assembly. No pass has access to credentials or system internals.
**Verify:** Run all 36 eval synthetic cases through multi-pass pipeline. Measure per-pass success rate (target: ≥95% per pass). Measure overall first-attempt QA pass rate (target: ≥85%). Measure token usage (target: ≤ 5,000 tokens total vs ~8,000-15,000 for current single-call). Measure latency (target: ≤ 8s wall time with parallel slots).

#### ~~11.22.4 Cascading Auto-Repair Pipeline — Belt-and-Suspenders Post-Processing~~ DONE
**What:** 7-stage deterministic repair pipeline in `app/qa_engine/repair/` (paired with QA checks). Runs between assembly and QA gate. Each stage is a pure function — no LLM. Wraps existing `mso_repair.py` and `meta_injector.py`. Replaces per-agent post-processing with a unified repair chain.
**Why:** Defense in depth. Golden templates + structured output should yield ~95% QA pass rate. Repair catches remaining structural issues (malformed slot content, edge cases in personalisation injection). The difference between 95% and 99%+.
**Implementation:**
- Create `app/qa_engine/repair/` directory with `RepairStage` Protocol and `RepairPipeline` orchestrator:
  - `pipeline.py` — `RepairPipeline.run(html) -> RepairResult(html, repairs_applied, warnings)`. Sequential stages, failure-safe (stage errors logged, not crashed).
  - `structure.py` — Stage 1: ensure DOCTYPE/html/head/body via lxml parse+serialize. Preserve MSO comments and `data-slot` attrs.
  - `mso.py` — Stage 2: wrap existing `app/ai/agents/outlook_fixer/mso_repair.repair_mso_issues()`. Add namespace injection (`xmlns:v`, `xmlns:o`).
  - `dark_mode.py` — Stage 3: wrap existing `app/ai/agents/dark_mode/meta_injector.inject_missing_meta_tags()`. Ensure `@media (prefers-color-scheme: dark)` block exists.
  - `accessibility.py` — Stage 4: add `lang="en"` if missing, `role="presentation"` on layout tables, `scope="col"` on `<th>`, `alt=""` on images missing alt.
  - `personalisation.py` — Stage 5: count ESP delimiter balance (Liquid `{{`/`}}`, AMPscript `%%`/`%%`). Warn on imbalance (don't auto-close).
  - `size.py` — Stage 6: strip HTML comments (except MSO `<!--[if`), collapse whitespace, remove empty `style=""`.
  - `links.py` — Stage 7: replace empty `href=""` with `href="#"`, warn on `javascript:` hrefs.
- Integrate into `app/ai/blueprints/engine.py` — run after agentic node returns HTML, before QA gate. Store `repair_log` and `repair_warnings` in `run.metadata`.
- Test idempotency: running pipeline twice = same output.
**Security:** All deterministic HTML manipulation via lxml/regex. No external fetches. No LLM calls. No `eval()`.
**Verify:** `make test -k test_repair_pipeline` — each stage independently tested + end-to-end. Pipeline is idempotent. Golden templates unchanged after repair (no-op). `make test` — no regressions.

#### ~~11.22.5 SKILL.md Rewrite — Architect Prompts, Not Generator Prompts~~ DONE
**What:** Add dual-mode structure to all 7 HTML agent SKILL.md files: a `## Output Mode: Structured (JSON)` section with schema examples and a `## Output Mode: HTML (Legacy)` section preserving current instructions. Update `prompt.py` files to detect `output_mode` and load the appropriate section.
**Why:** The prompt must match the architecture — "return JSON decisions" produces fundamentally different (better) output than "generate HTML."
**Implementation:**
- Each SKILL.md gets structured mode section: JSON schema, example input→output pairs, "Do NOT return HTML" instruction
- **Scaffolder**: "Select template + fill slots" with `EmailBuildPlan` schema example
- **Dark Mode**: "Return color mappings" with `DarkModePlan` schema example
- **Outlook Fixer**: "Return MSO fix plan" with `OutlookFixPlan` schema example
- **Accessibility**: "Return a11y fix plan" with `AccessibilityPlan` schema example (alt text decisions + structural fixes)
- **Personalisation**: "Return tag injection plan" with `PersonalisationPlan` schema example
- **Code Reviewer**: Tighten schema compliance (already structured, formalise `CodeReviewPlan`)
- **Content**: Add explicit JSON format spec (already text-based, formalise `ContentPlan`)
- Update `prompt.py` per agent: `build_system_prompt(skills, output_mode)` loads appropriate SKILL.md section
- Use `make eval-skill-test` for each rewrite to A/B compare pass rates
**Security:** SKILL.md files are prompt content only.
**Verify:** `make eval-skill-test AGENT={agent} PROPOSED=...` for each agent. Structured output compliance ≥95%.

#### ~~11.22.6 Context Assembly Optimisation — Token Budget Enforcement~~ DONE
**What:** Optimise what context each agent receives per pass. Multi-pass architecture enables pass-specific context — Pass 1 (layout) needs only the brief, Pass 2 (content) needs brief + slot definitions, Pass 3 (design) needs brief + template palette. No pass needs full SKILL.md + handoff history + failure warnings.
**Implementation:**
- Create `app/ai/agents/context_budget.py`:
  - `ContextBudget` dataclass: `max_tokens: int`, `sections: dict[str, int]` (per-section budgets)
  - `measure_context(prompt: str) -> ContextMetrics` — token counts per section
  - `enforce_budget(context: dict, budget: ContextBudget) -> dict` — trim lowest-priority sections to fit budget
- Per-pass budgets:
  - Pass 1 (layout): 2,000 tokens max (brief + template list summaries)
  - Pass 2 (content): 4,000 tokens max (brief + slot definitions + 2 few-shot examples)
  - Pass 3 (design): 1,500 tokens max (brief + brand guidelines + current template palette)
- **Selective SKILL.md loading**: Load only the L1 section for the current pass. L2/L3 loaded only if Pass fails and retries.
- **Handoff summarisation**: For multi-node blueprint chains, summarise handoffs >2 nodes back to a single paragraph.
- **Failure warning pruning**: Only inject warnings relevant to the current pass (e.g., MSO warnings only in Pass 1 layout selection, not in Pass 2 content generation).
**Security:** No new attack surface. Context trimming is deterministic.
**Verify:** Measure prompt token counts per pass. Target: total across 3 passes ≤ 8,000 tokens (vs current single-call ~10,000-15,000). Per-pass accuracy should not decrease from trimming (same or better signal-to-noise).

#### ~~11.22.7 Novel Layout Fallback — Graceful Degradation for Edge Cases~~ DONE
**What:** Handle the ~5% of briefs that don't match any golden template. Instead of falling back to unreliable full-HTML generation, compose new layouts by combining tested building blocks (sections from golden templates). This is the difference between 95% and 97-99%.
**Why:** Golden templates cover common layouts, but clients occasionally request unusual combinations (e.g., 3-column on mobile, accordion sections, gamification elements). Without a fallback, these briefs either fail or revert to the old unreliable pipeline.
**Implementation:**
- Create `app/ai/templates/composer.py` — `TemplateComposer`:
  - `decompose_templates() -> list[SectionBlock]` — break golden templates into reusable section blocks (hero, text_block, two_col, card_grid, cta, footer, spacer, divider)
  - `SectionBlock` dataclass: `block_type`, `html_skeleton`, `slot_definitions`, `mso_wrapper: bool`, `dark_mode_vars: list[str]`
  - `compose(blocks: list[str], order: list[str]) -> GoldenTemplate` — assemble a new template from section blocks, auto-generate MSO wrappers between adjacent blocks, merge dark mode variables
  - `validate_composition(template: GoldenTemplate) -> list[QACheckResult]` — run QA checks on composed template before use
- Update Scaffolder Pass 1 to support composition:
  - If no golden template matches brief (confidence < 0.7), return `CompositionPlan` instead of `TemplateSelection`
  - `CompositionPlan`: ordered list of `SectionBlock` IDs + per-block slot overrides
  - Assembler builds from `CompositionPlan` using `TemplateComposer.compose()`
- Composed templates validated by QA before slot filling — if composition fails QA, fall back to closest matching golden template with a warning
- Track composition frequency in `traces/` — if >10% of briefs require composition, build new golden templates for the common compositions
**Security:** Section blocks are derived from golden templates (pre-validated). Composition is deterministic concatenation + MSO wrapper generation. No LLM involvement in structural composition.
**Verify:** Create 5 "unusual" briefs that don't match any golden template. Verify: composer produces valid compositions, assembled HTML passes QA, fallback to closest template works when composition fails. Measure: composition QA pass rate ≥90%.

#### ~~11.22.8 Agent Role Redefinition — Tighten Specialisation~~ DONE
**What:** Redefine agent responsibilities to eliminate overlap and match the template-first architecture. Several agents become simpler or unnecessary when templates handle structure.
**Why:** Current agent overlap causes conflicting fixes — Scaffolder generates dark mode, then Dark Mode agent overwrites it. Template-first architecture means each agent owns a specific slice of the `EmailBuildPlan`, with no structural HTML generation.
**Implementation:**
- **Scaffolder**: Template selection + content slot filling only. No HTML generation. Owns Pass 1 + Pass 2.
- **Dark Mode**: Color remapping decisions only. Returns `DesignTokens.dark_*` values. Deterministic code handles all CSS/meta/Outlook injection. Owns Pass 3 color subset.
- **Content**: Subject line, preheader, CTA text, body copy editing. Operates on `SlotFill.body_text` fields only. Separate from Scaffolder (can run independently for copy-only tasks).
- **Outlook Fixer**: Reduced scope — only activated when repair pipeline detects MSO issues that golden templates shouldn't have (indicates template bug or unusual composition). Primarily a diagnostic agent that reports issues rather than generating HTML fixes.
- **Accessibility**: Alt text generation + heading hierarchy validation. Returns structured `{image_id: alt_text}` decisions. Code applies them. Does NOT generate or modify HTML.
- **Personalisation**: ESP variable placement decisions. Returns `PersonalisationConfig`. Code injects syntax-correct variables. Does NOT write Liquid/AMPscript directly.
- **Code Reviewer**: Reviews `EmailBuildPlan` for appropriateness (template choice, slot content quality, design token contrast, personalisation completeness). Does NOT review raw HTML.
- **Knowledge**: Unchanged — RAG Q&A.
- **Innovation**: Prototypes new `SectionBlock` types and `GoldenTemplate` compositions. Tests via `TemplateComposer.validate_composition()`. Does NOT generate freeform HTML.
- Update `app/ai/blueprints/definitions/` — blueprint node sequences reflect new agent scopes. Scaffolder node produces `EmailBuildPlan`, downstream agents modify specific plan fields, final assembly node is deterministic.
**Security:** No change — agents produce structured data, code handles HTML. Attack surface reduced (less raw HTML in LLM output).
**Verify:** Blueprint end-to-end test: brief → Scaffolder (plan) → Content (refine slots) → Dark Mode (dark tokens) → Personalisation (variables) → Assembly (deterministic) → QA → Export. Each agent's output is valid JSON matching its schema. No agent produces raw HTML.

#### ~~11.22.9 Eval-Driven Iteration Loop — Milestone Tracking to 99%~~ DONE
**What:** Establish the measurement framework for tracking progress from 16.7% to 99%+. Every change in 11.22.1–11.22.8 must be validated by the eval system before merging. Regression detection prevents backsliding.
**Implementation:**
- Define baseline: current `traces/baseline.json` (16.7% overall, per-agent and per-criterion breakpoints)
- After each 11.24.x subtask, run `make eval-run` + `make eval-analysis` + `make eval-regression`
- Use `make eval-skill-test` for every SKILL.md rewrite (A/B comparison)
- Track progress in `traces/improvement_log.jsonl` — append `{date, change_description, agent, criterion, before_rate, after_rate}`
- **Milestone targets:**
  - M1 (after 11.22.1 golden templates + 11.22.2 structured output): 70% overall — structural failures eliminated for template-covered briefs
  - M2 (after 11.22.3 multi-pass): 85% overall — per-field retry catches content generation errors
  - M3 (after 11.22.4 repair pipeline): 95% overall — cascading repair catches remaining structural edge cases
  - M4 (after 11.22.5 SKILL.md rewrites): 97% overall — LLM produces better structured decisions
  - M5 (after 11.22.6 context optimisation + 11.22.7 novel layout fallback): 99%+ structural, ~98% semantic, **99%+ overall**
  - M6 (after 11.22.8 agent redefinition): sustained 99%+ with reduced token cost and latency
- If a change decreases any agent's pass rate by >3 percentage points, revert and investigate
- **Autonomous eval loop:** Implement modify→run→measure→keep/revert cycle for prompt optimization. After each prompt/SKILL.md change: run agents against the same briefs, score via QA gate (deterministic) + LLM judge (subjective), record in `traces/improvement_log.jsonl`. Keep changes that improve pass rate, auto-revert those that don't. Can run overnight as unattended sweeps.
- **CI golden test cases:** Small set of email templates with known-correct QA outcomes that must pass in CI (`make eval-golden`). Catches regressions on model/prompt/check changes without running full eval suite. Golden cases derived from highest-confidence eval traces.
- **New eval dimensions for template-first**: add eval criteria for template selection accuracy (did LLM pick the right template?), slot fill quality (content appropriate for slot constraints?), design token coherence (colors accessible, on-brand?)
- Update synthetic test data: add 10 cases specifically testing template selection edge cases (ambiguous briefs, multi-intent briefs, novel layout requests)
**Verify:** After completing all 11.24.x subtasks:
- `make eval-analysis` shows ≥97% overall pass rate
- Per-agent minimums: no agent below 90%
- `mso_conditionals` ≥99% (from 0% — guaranteed by golden templates)
- `accessibility` ≥95% (from 8% — alt text + heading decisions are structured)
- `html_preservation` ≥99% (from 10% — assembler preserves template structure)
- Token usage per blueprint run: ≤ 8,000 tokens (from ~15,000-30,000 with self-correction loops)
- Latency per blueprint run: ≤ 10s (from ~30-60s with retry loops)

---

## Phase 17 — Visual Regression Agent & VLM-Powered QA

**What:** Add a 10th AI agent that uses vision-language models to screenshot rendered emails across simulated clients, detect rendering discrepancies by comparing screenshots, and generate targeted CSS fixes. Integrates Playwright for headless rendering, ODiff for perceptual image diffing, and a VLM (Claude vision / GPT-4o vision) for semantic analysis of visual defects. Includes a component baseline screenshot system for regression detection across builds.
**Why:** Every email platform (Litmus, Email on Acid, Parcel) relies on server-side rendering farms or manual screenshot review. No platform uses AI to _understand_ what went wrong visually and auto-fix it. The hub already has 9 agents, a blueprint engine, and a self-correcting CRAG loop — a Visual QA agent is the natural 10th agent that closes the "render → detect → fix" loop entirely within the platform. The ScreenCoder (2025) multi-agent decomposition pattern (grounding → planning → generation) maps directly to the blueprint engine's node architecture. This single feature makes the hub irreplaceable because it eliminates the $500+/month Litmus dependency and delivers faster, smarter results.
**Dependencies:** Phase 11 (QA engine + agent architecture), Phase 14 (checkpoint for long-running visual pipelines), Phase 16 (CRAG mixin pattern for auto-correction).
**Design principle:** Each sub-task is independently shippable behind feature flags. Visual regression can run as QA check #12 without the VLM fix agent. VLM agent can run standalone without ODiff baselines. Screenshots stored alongside `ComponentVersion` baselines — no new storage infrastructure required.

### 17.1 Playwright Email Rendering Service `[Backend]`
**What:** A rendering service that takes compiled email HTML and produces screenshots across simulated email client viewports. Uses Playwright with pre-configured viewport sizes and CSS injection to simulate client-specific rendering behaviors (Gmail style stripping, Outlook word-engine quirks, Apple Mail full CSS support). Outputs PNG screenshots with metadata (viewport, simulated client, timestamp).
**Why:** The hub currently has no way to see what an email looks like in different clients without external services. Playwright is already a dev dependency (used in e2e tests). Reusing it for email rendering avoids new infrastructure. Client simulation via CSS injection and style stripping is 90% accurate for layout validation without needing actual email client access.
**Implementation:**
- Create `app/rendering/screenshot.py` — `EmailScreenshotService` class:
  - `async render_screenshots(html: str, clients: list[str] | None = None) -> list[ScreenshotResult]` — renders HTML in Playwright, returns list of `ScreenshotResult(client_name: str, viewport: tuple[int, int], image_bytes: bytes, css_modifications: list[str])`
  - Pre-configured client profiles in `RENDERING_PROFILES: dict[str, RenderingProfile]`: `gmail_web` (strip `<style>` blocks, max-width 680px), `outlook_2019` (inject Word engine CSS constraints: no flexbox, no grid, table-only layout enforcement), `apple_mail` (full CSS, 600px), `outlook_dark` (dark mode color inversion), `mobile_ios` (375px viewport)
  - Each profile: `RenderingProfile(name: str, viewport_width: int, viewport_height: int, css_injections: list[str], style_strip_patterns: list[re.Pattern], dark_mode: bool)`
  - Uses `async with async_playwright() as p: browser = await p.chromium.launch(headless=True)` — single browser instance, new context per render
  - Screenshot via `page.screenshot(type="png", full_page=True, clip={"x": 0, "y": 0, "width": viewport_width, "height": min(page_height, 4096)})` — cap at 4096px to prevent memory issues
  - Images stored as bytes in memory (not disk) — caller decides storage
- Create `app/rendering/schemas.py` — `ScreenshotResult`, `RenderingProfile`, `ScreenshotRequest`, `ScreenshotResponse` (base64 encoded images for API transport)
- Modify `app/rendering/routes.py` — add `POST /api/v1/rendering/screenshots` with auth + rate limiting (`5/minute` — rendering is expensive). Accepts `{html: str, clients: list[str]}`, returns `{screenshots: list[{client: str, image_base64: str}]}`
- Config (`app/core/config.py` → `RenderingConfig`): `screenshots_enabled: bool = False`, `screenshot_max_clients: int = 5`, `screenshot_timeout_ms: int = 15000`
**Security:** HTML rendered in Playwright's sandboxed Chromium — no network access (`context.route("**/*", lambda route: route.abort())` blocks all external requests). Screenshot output is a PNG image — no executable content. Rate limited to prevent abuse. HTML input validated via existing `validate_output()` before rendering.
**Verify:** Render a known email HTML with `gmail_web` profile → `<style>` blocks stripped from rendered output, width constrained to 680px. Render same HTML with `apple_mail` → styles preserved. Render with `outlook_2019` → flexbox/grid properties have no visual effect (simulated). Screenshot dimensions match configured viewport. `screenshots_enabled=False` returns 501. `make test` passes. Rendering completes within timeout.
- [x] ~~17.1 Playwright email rendering service~~ DONE

### 17.2 ODiff Visual Regression Baseline System `[Backend]`
**What:** Perceptual image diffing system using ODiff (Zig/SIMD, handles anti-aliasing noise) that compares rendered screenshots against stored baselines. Creates and manages baseline screenshots per `ComponentVersion` and per `GoldenTemplate`. Outputs diff images highlighting pixel regions that changed, with a configurable similarity threshold. Diff images attachable to the approval portal.
**Why:** Manual "does this look right?" screenshot review is the #1 bottleneck in email QA. ODiff (from game QA / visual regression domain) distinguishes real layout changes from anti-aliasing noise — something pixel-exact diff tools can't do. Storing baselines per `ComponentVersion` means every component update automatically gets regression-tested against its last known-good state. This is proven technology repurposed for email.
**Implementation:**
- Install `odiff` as a binary dependency (Zig-compiled, ~2MB, available via npm or direct binary). Python wrapper via subprocess call
- Create `app/rendering/visual_diff.py` — `VisualDiffService` class:
  - `async compare(baseline: bytes, current: bytes, threshold: float = 0.01) -> DiffResult` — returns `DiffResult(identical: bool, diff_percentage: float, diff_image: bytes | None, pixel_count: int, changed_regions: list[Region])`
  - `async update_baseline(entity_type: str, entity_id: int, client: str, image: bytes) -> None` — stores baseline screenshot. Entity types: `component_version`, `golden_template`
  - `async get_baseline(entity_type: str, entity_id: int, client: str) -> bytes | None` — retrieves stored baseline
  - Region detection: parse ODiff output regions into `Region(x: int, y: int, width: int, height: int)` for highlighting in UI
- Create `app/rendering/models.py` — `ScreenshotBaseline` SQLAlchemy model: `id`, `entity_type` (varchar), `entity_id` (int), `client_name` (varchar), `image_data` (LargeBinary), `image_hash` (varchar, SHA-256), `created_at`, `updated_at`. Unique constraint on `(entity_type, entity_id, client_name)`
- Alembic migration for `screenshot_baselines` table
- Create `app/rendering/repository.py` — `ScreenshotBaselineRepository` with CRUD + `get_by_entity(entity_type, entity_id, client_name)` + `list_by_entity(entity_type, entity_id)`
- Modify `app/rendering/routes.py` — add `POST /api/v1/rendering/visual-diff` (accepts two base64 images, returns diff), `GET /api/v1/rendering/baselines/{entity_type}/{entity_id}` (list baselines), `POST /api/v1/rendering/baselines/{entity_type}/{entity_id}/update` (update baseline from current screenshot)
- Config: `visual_diff_enabled: bool = False`, `visual_diff_threshold: float = 0.01` (1% pixel difference triggers alert)
**Security:** Baseline images stored in DB (not filesystem) — BOLA-safe via entity ownership validation. ODiff subprocess called with fixed arguments only — no user input in command. Diff images are PNG output only. All endpoints require auth + developer/admin role.
**Verify:** Upload baseline for a golden template → modify template CSS → re-render → diff detects changes with diff_percentage > threshold. Identical screenshots → `identical=True`, `diff_percentage=0.0`. Anti-aliasing-only changes (sub-pixel rendering differences) → below threshold. Baseline CRUD works. `make test` passes.
- [x] ~~17.2 ODiff visual regression baseline system~~ DONE

### 17.3 VLM Visual Analysis Agent `[Backend]`
**What:** A new AI agent (`VisualQAAgent`) that consumes rendered screenshots and uses a vision-language model to identify rendering defects with semantic understanding — not just pixel diffs but "the CTA button is cut off in Outlook", "the two-column layout collapsed to single column in Gmail", "dark mode inverted the logo but not the background". Produces structured `VisualDefect` reports with suggested CSS fixes.
**Why:** ODiff tells you _where_ pixels changed. A VLM tells you _what went wrong_ and _how to fix it_. This is the ScreenCoder pattern applied to email: grounding (identify the defect region), planning (determine the CSS cause), generation (produce the fix). No email platform does this — it's the single most differentiated capability the hub can offer.
**Implementation:**
- Create `app/ai/agents/visual_qa/` package:
  - `schemas.py` — `VisualDefect(region: Region, description: str, severity: str, affected_clients: list[str], suggested_fix: str, css_property: str | None)`, `VisualQAResult(defects: list[VisualDefect], summary: str, auto_fixable: bool)`
  - `service.py` — `VisualQAAgentService(BaseAgentService)`:
    - Override `process()` to accept multimodal input: rendered screenshots + original HTML
    - Build VLM prompt: "Compare these email screenshots rendered in {clients}. Identify rendering defects — layout breaks, missing elements, color inversions, text overflow, image sizing issues. For each defect, specify the CSS property causing it and suggest a fix."
    - Parse VLM response into structured `VisualDefect` objects via `response_format` (structured output)
    - Cross-reference detected CSS properties against ontology (`load_ontology()`) for known compatibility issues
    - Generate fix suggestions that reference specific ontology fallbacks when available
  - `SKILL.md` — agent skill file following existing pattern (5 evaluation criteria: defect_detection_accuracy, fix_correctness, false_positive_rate, client_coverage, severity_calibration)
- Create `app/ai/agents/visual_qa/decisions.py` — `VisualQADecisions` structured output schema (following 11.22.8 pattern): `defects: tuple[VisualDefect, ...]`, `overall_rendering_score: float`, `critical_clients: list[str]`
- Modify `app/ai/blueprints/nodes/` — add `visual_qa_node.py` following existing node pattern (`VisualQANode(BlueprintNode)`). Runs after export node as optional validation step. Integrates with checkpoint system (Phase 14)
- Modify `app/ai/blueprints/handoff.py` — add `VisualQAHandoff(AgentHandoff)` with `screenshots: dict[str, str]` (client → base64), `baseline_diffs: list[DiffSummary]`
- Config: `AI__VISUAL_QA_ENABLED: bool = False`, `AI__VISUAL_QA_MODEL: str = "claude-sonnet-4-5-20250514"` (vision-capable model required), `AI__VISUAL_QA_CLIENTS: list[str] = ["gmail_web", "outlook_2019", "apple_mail"]`
**Security:** Screenshots are generated internally (17.1) — no user-uploaded images in VLM prompts. VLM prompt contains only screenshot images + HTML structure — no PII. Response parsed via structured output (no raw HTML injection). Model selection restricted to vision-capable models via capability check. Output CSS fixes validated via `sanitize_html_xss()` before application.
**Verify:** Generate email with known Outlook incompatibility (flexbox layout) → VLM detects "layout collapsed in Outlook", suggests table-based alternative. Generate fully compatible email → VLM reports zero defects. Cross-reference: VLM-detected CSS issue matches ontology known incompatibility. False positive rate < 10% on golden template test suite. `visual_qa_enabled=False` skips entirely. `make test` passes.
- [x] ~~17.3 VLM visual analysis agent~~ DONE

### 17.4 Auto-Fix Pipeline Integration `[Backend]`
**What:** Connect the VLM Visual QA agent's defect reports back into the CRAG correction loop to automatically fix detected visual issues. When `VisualQAAgent` identifies fixable defects, feed the defect descriptions + suggested fixes back to the Scaffolder/OutlookFixer agent as correction instructions. Creates a render → detect → fix → re-render verification cycle.
**Why:** Detection without correction is just a report. The hub's CRAG mixin (16.5) already handles the "detect CSS issue → retrieve fallback → regenerate" pattern. This extends it to visual defects detected by the VLM, creating a fully autonomous visual QA loop that no human needs to review for common rendering issues.
**Implementation:**
- Create `app/ai/agents/visual_qa/correction.py` — `VisualCorrectionService`:
  - `async correct_visual_defects(html: str, defects: list[VisualDefect], model: str) -> tuple[str, list[str]]` — takes original HTML + detected defects, generates corrected HTML
  - For each defect with `css_property` set: look up ontology fallback via `load_ontology().fallbacks_for()` (reusing CRAG pattern)
  - For defects without known CSS property: include VLM's `suggested_fix` in the correction prompt
  - Correction prompt: "Fix the following rendering issues in this HTML email: {defect_descriptions}. Use these known fallbacks: {ontology_fallbacks}. Preserve all existing functionality."
  - Output validated via `validate_output()` → `extract_html()` → `sanitize_html_xss()`
  - Capped at 1 correction round (same as CRAG) — avoids infinite loops
- Modify `app/ai/blueprints/nodes/visual_qa_node.py` — after VLM analysis, if `auto_fixable=True` and `defects` exist: call `VisualCorrectionService.correct_visual_defects()`, then re-render screenshots for verification. If re-render shows improvement (lower diff percentage), accept the fix. If regression, keep original
- Modify `app/ai/agents/validation_loop.py` — add `VisualCRAGMixin` extending `CRAGMixin` with visual correction capability. `_visual_crag_validate(html, screenshots, model)` chains: screenshot → VLM analysis → correction → re-screenshot → verify
- Config: `AI__VISUAL_QA_AUTO_FIX: bool = False` (separate from detection — detection can run without auto-fix), `AI__VISUAL_QA_MAX_CORRECTION_ROUNDS: int = 1`
**Security:** Correction prompt contains only defect descriptions (generated by VLM, not user input) + ontology fallback code (trusted data). Output sanitised via `sanitize_html_xss()`. Re-render verification prevents regression — if fix makes things worse, original HTML preserved. Cost capped at 1 round.
**Verify:** Email with flexbox layout → VLM detects Outlook break → auto-fix replaces with table layout → re-render confirms fix. Email with no defects → no correction attempted (zero LLM cost). Auto-fix that causes regression → original preserved. `auto_fix=False` runs detection only. `make test` passes.
- [x] ~~17.4 Auto-fix pipeline integration~~ DONE

### 17.5 Frontend Visual QA Dashboard `[Frontend]`
**What:** Frontend UI for visual regression results: side-by-side screenshot comparison across clients, diff overlay toggle, defect annotations with severity badges, baseline management, and "Accept Fix" / "Reject Fix" actions for VLM-suggested corrections. Integrated into the workspace as a new tab alongside the existing QA results panel.
**Why:** The visual QA data is only useful if developers can see and act on it. Side-by-side client comparison replaces the Litmus screenshot review workflow entirely within the hub. Baseline management lets teams track visual regressions across template versions.
**Implementation:**
- Create `cms/apps/web/src/components/visual-qa/` — `VisualQAPanel.tsx` (main container), `ClientComparisonGrid.tsx` (side-by-side screenshots), `DiffOverlay.tsx` (toggle diff image over screenshot), `DefectAnnotation.tsx` (clickable defect regions with description tooltip), `BaselineManager.tsx` (view/update baselines)
- Create `cms/apps/web/src/hooks/use-visual-qa.ts` — SWR hooks: `useScreenshots(templateId)`, `useVisualDiff(templateId)`, `useBaselines(entityType, entityId)`, `useUpdateBaseline()`
- Modify workspace layout — add "Visual QA" tab in the QA results section (alongside existing HTML validation, CSS support, etc.)
- Add i18n keys across 6 locales (en, de, fr, es, it, nl) — ~30 keys for labels, tooltips, status messages
- SDK regeneration for new rendering endpoints
**Security:** Screenshots displayed via `<img src="data:image/png;base64,...">` — no external URLs. Diff overlay uses canvas API — no innerHTML. Baseline update requires developer/admin role.
**Verify:** Render screenshots → display in grid → toggle diff overlay → annotations appear at correct regions. Baseline update flow works end-to-end. Responsive layout at all viewport sizes. `make check-fe` passes. i18n keys present in all 6 locales.
- [x] ~~17.5 Frontend visual QA dashboard~~ DONE

### 17.6 Tests & SDK Integration `[Full-Stack]`
**What:** Comprehensive test suite for visual regression pipeline: screenshot rendering tests, ODiff integration tests, VLM agent unit tests (with mocked vision responses), correction pipeline tests, baseline CRUD tests, route tests with auth/rate limiting. SDK regeneration covering all new rendering endpoints.
**Why:** Visual QA involves multiple async services (Playwright, ODiff, VLM) that must be tested in isolation and integration. The rendering service especially needs reliability testing — browser crashes, timeouts, and memory limits must be handled gracefully.
**Implementation:**
- Create `app/rendering/tests/` — `test_screenshot.py` (rendering profiles, viewport simulation, timeout handling), `test_visual_diff.py` (ODiff integration, threshold logic, baseline CRUD), `test_routes.py` (auth, rate limiting, error handling for all new endpoints)
- Create `app/ai/agents/visual_qa/tests/` — `test_visual_qa_agent.py` (VLM response parsing, defect detection, structured output), `test_correction.py` (auto-fix pipeline, regression prevention, ontology integration)
- SDK regeneration via `@hey-api/openapi-ts`
- Target: 40+ tests covering all paths
**Security:** Tests verify auth requirements on all endpoints. Rate limiting verified. Baseline BOLA protection tested.
**Verify:** `make test` passes with all new tests. `make check` all green. SDK types match API responses. No regression in existing test suite.
- [x] ~~17.6 Tests & SDK integration~~ DONE

---

## Phase 18 — Rendering Resilience & Property-Based Testing

**What:** Build a chaos testing engine that deliberately degrades email HTML to simulate real-world email client behaviors, and a property-based testing framework that generates hundreds of random email configurations to verify invariants hold. Adds "resilience score" to the QA pipeline alongside the existing 11 checks.
**Why:** Current QA tests emails in ideal conditions — clean HTML, all styles applied, images loaded. Real inboxes are hostile: Gmail strips `<style>` blocks, Outlook ignores modern CSS, corporate firewalls block images, dark mode inverts colors unexpectedly. Chaos engineering (borrowed from distributed systems / Google's 2025 framework) applied to email rendering reveals fragility that golden template tests miss. Property-based testing (borrowed from formal verification / QuickCheck) covers the combinatorial space — the hub currently tests 7 golden templates, but there are thousands of possible section/client/dark-mode/locale combinations.
**Dependencies:** Phase 11 (QA engine checks), Phase 16 (CRAG for auto-correction of discovered issues), Phase 17 (screenshot rendering for visual verification).
**Design principle:** Chaos profiles are composable — test one degradation at a time or stack multiples. Property generators are seeded for reproducibility. Both integrate as optional QA checks — existing pipeline unchanged when disabled. Results feed back into knowledge base as RAG documents.

### 18.1 Email Chaos Engine `[Backend]`
**What:** A testing engine that applies controlled degradations to email HTML, simulating real-world email client behaviors. Each degradation is a composable `ChaosProfile` — strip all `<style>` blocks (Gmail), remove media queries (many mobile clients), block all images (corporate firewalls / image-off settings), inject dark mode color inversion (Outlook/Apple Mail), remove MSO conditional comments, convert all `<div>` to `<span>` (some webmail), limit HTML to 102KB (Gmail clipping), strip `class` attributes. Runs the degraded HTML through the existing QA engine to measure resilience.
**Why:** An email that passes QA with all styles intact but breaks when Gmail strips styles is a false positive. Chaos testing reveals these fragilities before they reach real inboxes. Google's chaos engineering framework (2025) showed systems with ongoing resilience validation recovered 32% faster — the same principle applies to email templates. No email platform offers this; competitors test "does it render correctly?" while this tests "does it survive the real world?"
**Implementation:**
- Create `app/qa_engine/chaos/` package:
  - `profiles.py` — `ChaosProfile(name: str, description: str, transformations: list[Callable[[str], str]])` and pre-built profiles:
    - `GMAIL_STYLE_STRIP`: remove all `<style>` and `<link rel="stylesheet">` elements via BeautifulSoup
    - `IMAGE_BLOCKED`: replace all `<img>` `src` with transparent 1x1 GIF, verify alt text visibility
    - `DARK_MODE_INVERSION`: inject `filter: invert(1) hue-rotate(180deg)` on `<body>`, simulate `[data-ogsc]` and `[data-ogsb]` attribute addition
    - `OUTLOOK_WORD_ENGINE`: strip flexbox/grid properties, convert `<div>` containers to `<table>` wrappers, remove CSS custom properties
    - `GMAIL_CLIPPING`: truncate HTML at 102,400 bytes, verify "View entire message" doesn't cut mid-tag
    - `MOBILE_NARROW`: inject `max-width: 375px` on body, verify no horizontal scroll (content overflow)
    - `CLASS_STRIP`: remove all `class` attributes (some security-focused email clients)
    - `MEDIA_QUERY_STRIP`: remove all `@media` rules from inline and block styles
  - `engine.py` — `ChaosEngine` class:
    - `async run_chaos_test(html: str, profiles: list[str] | None = None) -> ChaosTestResult` — applies each profile, runs QA checks on degraded HTML, returns per-profile results
    - `ChaosTestResult(original_score: float, degraded_scores: dict[str, float], resilience_score: float, critical_failures: list[ChaosFailure])` — `resilience_score` = weighted average of degraded scores / original score
    - `ChaosFailure(profile: str, check_name: str, severity: str, description: str)` — specific QA check failures introduced by degradation
  - `composable.py` — `compose_profiles(*profiles) -> ChaosProfile` — stack multiple degradations for worst-case testing
- Modify `app/qa_engine/service.py` — add `async run_chaos_test(template_id: int, html: str) -> ChaosTestResult` calling `ChaosEngine`. Optional — only runs when `chaos_testing_enabled=True`
- Modify `app/qa_engine/routes.py` — add `POST /api/v1/qa/chaos-test` with auth + rate limiting (`3/minute`)
- Modify `app/qa_engine/schemas.py` — add `ChaosTestResult`, `ChaosFailure`, `ChaosTestRequest` response schemas. Add optional `resilience_score: float | None` to existing `QARunResponse`
- Config: `QA__CHAOS_TESTING_ENABLED: bool = False`, `QA__CHAOS_DEFAULT_PROFILES: list[str] = ["gmail_style_strip", "image_blocked", "dark_mode_inversion", "gmail_clipping"]`
**Security:** Chaos transformations are deterministic pure functions — no LLM calls, no external network. HTML mutations use BeautifulSoup (parser, not eval). Degraded HTML is temporary (never persisted). Rate limited to prevent CPU abuse from expensive transformations.
**Verify:** Apply `GMAIL_STYLE_STRIP` to email with inline styles → QA score unchanged. Apply to email relying on `<style>` block → QA score drops, specific CSS failures reported. Stack `GMAIL_STYLE_STRIP` + `IMAGE_BLOCKED` → compound failures detected. `resilience_score` correctly reflects degradation impact. 102KB Gmail clipping correctly truncates. `chaos_testing_enabled=False` skips entirely. `make test` passes.
- [x] ~~18.1 Email chaos engine~~ DONE

### 18.2 Property-Based Email Testing Framework `[Backend]`
**What:** Define email invariants (properties that must always hold regardless of content) and a generator that produces hundreds of random email configurations to verify these invariants. Borrows from QuickCheck/Hypothesis — generates random section combinations, content lengths, image counts, nesting depths, and client targets, then asserts invariants hold across all generated cases. Failing cases are automatically minimised to find the simplest reproduction.
**Why:** The hub tests 7 golden templates — a tiny fraction of the possible configuration space. Property-based testing covers combinations that no human would think to test: a 12-section email with RTL text, 3 nested tables, and Outlook dark mode. This catches edge cases that manifest in production but never appear in curated test suites. Agentic property-based testing (2025) found genuine bugs in NumPy and other mature libraries.
**Implementation:**
- Create `app/qa_engine/property_testing/` package:
  - `invariants.py` — `EmailInvariant` Protocol with `check(html: str) -> InvariantResult`, pre-built invariants:
    - `ContrastRatio`: all text has WCAG AA contrast ratio >= 4.5:1 against background
    - `ImageWidth`: no `<img>` wider than 600px (email max width standard)
    - `LinkIntegrity`: every `<a>` has non-empty `href`, no `javascript:` URIs
    - `SizeLimit`: total HTML < 102KB (Gmail clipping threshold)
    - `AltTextPresence`: every `<img>` has non-empty `alt` attribute
    - `TableNestingDepth`: table nesting depth <= 8 (Outlook rendering limit)
    - `ViewportFit`: content renders within 600px width without horizontal scroll
    - `EncodingValid`: all characters are valid UTF-8, no null bytes
    - `MSOBalance`: every `<!--[if mso]>` has matching `<![endif]-->`
    - `DarkModeReady`: if `prefers-color-scheme` used, both light and dark values specified
  - `generators.py` — `EmailGenerator` class using `hypothesis` library:
    - `generate_section_config() -> SectionConfig` — random section count (1-15), types from `SectionBlock` categories, content lengths (10-2000 chars)
    - `generate_style_config() -> StyleConfig` — random font stacks, color palettes (including near-threshold contrast), spacing values
    - `generate_client_target() -> str` — weighted random client selection matching real-world market share distribution
    - `generate_email(config: EmailConfig) -> str` — uses `TemplateAssembler` to build valid HTML from random config
  - `runner.py` — `PropertyTestRunner`:
    - `async run(invariants: list[str], num_cases: int = 100, seed: int | None = None) -> PropertyTestReport` — generates N random emails, checks all invariants, returns failures with minimal reproduction
    - `PropertyTestReport(total_cases: int, passed: int, failed: int, failures: list[PropertyFailure], seed: int)` — `PropertyFailure` includes the minimised config that triggers the invariant violation
    - Hypothesis `@given` integration for automatic shrinking of failing cases
- Modify `app/qa_engine/routes.py` — add `POST /api/v1/qa/property-test` with auth + rate limiting (`1/minute` — computationally expensive)
- Config: `QA__PROPERTY_TESTING_ENABLED: bool = False`, `QA__PROPERTY_TEST_CASES: int = 100`, `QA__PROPERTY_TEST_SEED: int | None = None` (fixed seed for CI reproducibility)
- Add `make test-properties` command — runs property tests with fixed seed for CI
**Security:** Generators produce synthetic HTML only — no user data. Hypothesis library is well-established (no security concerns). Rate limited aggressively due to CPU cost. Generated emails never persisted — temporary in-memory only.
**Verify:** Run 100 property tests → at least some invariant violations found (proves the generator covers edge cases). Fix a known invariant violation → re-run with same seed → violation no longer appears. `SizeLimit` invariant catches oversized emails. `ContrastRatio` catches near-threshold color combinations. `make test-properties` completes within 60 seconds. `make test` passes.
- [x] ~~18.2 Property-based email testing framework~~ DONE

### 18.3 Resilience Score Integration & Knowledge Feedback `[Backend]`
**What:** Integrate chaos test results and property test findings into the existing QA pipeline as optional check #12 ("rendering resilience"). Auto-generate knowledge base documents from discovered failures — each new chaos failure becomes a RAG-retrievable document describing the failure pattern, affected clients, and recommended fix. This creates a self-improving knowledge base that grows from every test run.
**Why:** Chaos and property testing produce insights that should compound across projects. A Gmail clipping issue found on Project A should inform email generation on Project B. The hub's knowledge base (Phase 8-9) + RAG pipeline (Phase 16) can surface these learnings at generation time — "this section pattern caused Gmail clipping for 3 previous projects."
**Implementation:**
- Create `app/qa_engine/checks/rendering_resilience.py` — `RenderingResilienceCheck(QACheck)`:
  - `async run(html: str, config: QAConfig) -> QACheckResult` — runs chaos engine with default profiles, returns pass/fail based on `resilience_score >= threshold`
  - Threshold: `QA__RESILIENCE_THRESHOLD: float = 0.7` (email must retain 70% of its QA score under degradation)
- Modify `app/qa_engine/service.py` — register `RenderingResilienceCheck` as check #12 (optional, behind feature flag)
- Create `app/qa_engine/chaos/knowledge_writer.py` — `ChaosKnowledgeWriter`:
  - `async write_failure_documents(failures: list[ChaosFailure], project_id: int) -> list[int]` — creates `Document` entries in knowledge base for each unique failure pattern
  - Document format: title = "{profile} failure: {check_name}", content = markdown description with affected clients, failure details, recommended fix, HTML snippet showing the problematic pattern
  - Deduplication: check for existing document with same title + project before creating new one
  - Tags: `domain="chaos_findings"`, `section_type="failure_pattern"`
- Modify `app/knowledge/service.py` — `search()` considers chaos_findings domain when query matches rendering/resilience patterns
- Config: `QA__CHAOS_AUTO_DOCUMENT: bool = False` (auto-generate knowledge docs from failures), `QA__RESILIENCE_CHECK_ENABLED: bool = False`
**Security:** Knowledge documents contain only structural HTML patterns (no PII). Document creation uses existing `KnowledgeService.ingest_document()` with tenant isolation via project_id.
**Verify:** Run chaos test → failures found → knowledge documents auto-created → subsequent RAG search for same pattern returns the chaos finding. Resilience check passes for well-structured email (score > 0.7). Resilience check fails for fragile email (single-column layout breaks under style stripping). `make test` passes.
- [x] ~~18.3 Resilience score integration & knowledge feedback~~ DONE

### 18.4 Frontend Chaos & Property Testing UI `[Frontend]`
**What:** Frontend components for chaos test results (per-profile score breakdown, failure details, "Fix This" action dispatching to CRAG) and property test reports (pass/fail summary, failing case inspector with minimised config display). Integrated into the QA dashboard.
**Why:** Chaos and property test data must be actionable — developers need to see which degradations break their email and drill into specific failures. The "Fix This" action connecting to CRAG creates a one-click fix workflow.
**Implementation:**
- Create `cms/apps/web/src/components/qa/ChaosTestPanel.tsx` — profile score radar chart, failure list with severity, "Run Chaos Test" action button
- Create `cms/apps/web/src/components/qa/PropertyTestPanel.tsx` — pass/fail gauge, failing invariant list, expandable case detail with minimised config
- Create `cms/apps/web/src/hooks/use-chaos-test.ts`, `use-property-test.ts` — SWR hooks for new endpoints
- Add i18n keys across 6 locales — ~25 keys
- SDK regeneration for chaos/property endpoints
**Security:** No raw HTML displayed in UI — all results are structured data. "Fix This" action uses existing CRAG endpoint with auth.
**Verify:** Run chaos test → results display in panel → per-profile scores shown → failure details expandable. Property test → pass/fail summary → failing cases inspectable. `make check-fe` passes.
- [x] ~~18.4 Frontend chaos & property testing UI~~ DONE

### 18.5 Tests & Documentation `[Full-Stack]`
**What:** Full test suite for chaos engine (profile application correctness, composability, QA integration), property testing (invariant checks, generator coverage, seed reproducibility), resilience check (#12), knowledge feedback writer. ADR documenting the resilience testing architecture.
**Implementation:**
- Create `app/qa_engine/chaos/tests/` — `test_chaos_engine.py` (profile transformations, composability, resilience scoring), `test_knowledge_writer.py` (document creation, deduplication)
- Create `app/qa_engine/property_testing/tests/` — `test_invariants.py` (each invariant against known pass/fail HTML), `test_generators.py` (output validity, seed reproducibility), `test_runner.py` (end-to-end with shrinking)
- Route tests for new endpoints (auth, rate limiting)
- Target: 35+ tests
- ADR-007 in `docs/ARCHITECTURE.md` — Rendering Resilience Testing
**Verify:** `make test` passes. `make check` all green. No regression in existing tests.
- [x] ~~18.5 Tests & documentation~~ DONE — 37 new tests across 8 files (test_service_chaos.py, test_chaos_engine.py, test_chaos_profiles.py, test_knowledge_writer.py, test_resilience_check.py, test_generators.py, test_invariants.py, test_runner.py); ADR-007 Rendering Resilience Testing in docs/ARCHITECTURE.md; 2768 total backend tests

---

## Phase 19 — Outlook Transition Advisor & Email CSS Compiler

**What:** Two capabilities that address the most urgent industry event (Microsoft ending Word-based Outlook rendering, October 2026) and the most impactful technical optimization (an email-specific CSS compiler using Lightning CSS). The Outlook Transition Advisor analyzes templates for Word-engine dependencies and generates migration plans. The CSS compiler performs AST-level optimization targeting "email client VMs" — removing unsupported properties, auto-converting modern CSS to table equivalents, and inlining optimally.
**Why:** October 2026 is the biggest rendering engine change in email history. Every enterprise with Outlook-targeted templates needs a migration plan. No platform offers automated analysis of Word-engine dependencies or a clear modernization path. The CSS compiler goes beyond Juice (string-level inlining) to AST-level optimization using the hub's own ontology data — producing smaller, faster, more compatible output than any existing tool.
**Dependencies:** Phase 11 (QA engine + existing Outlook Fixer agent), Phase 16 (ontology data for CSS compatibility), Phase 8-9 (knowledge graph for workaround patterns).
**Design principle:** Advisor is non-destructive — analyzes and reports without modifying templates. Compiler optimizations are opt-in per property class. Both use the hub's ontology as the single source of truth for CSS compatibility.

### 19.1 Outlook Word-Engine Dependency Analyzer `[Backend]`
**What:** Static analyzer that scans email HTML for Word rendering engine dependencies: VML shapes (`v:*` elements), ghost tables (tables used purely for layout in MSO conditionals), MSO conditional comments (`<!--[if mso]>`), Word-specific CSS (`mso-*` properties), DPI-dependent image sizing, and `.ExternalClass` hacks. Produces a dependency report with severity ratings and modernization suggestions.
**Why:** Developers have accumulated years of Outlook workarounds — ghost tables, VML buttons, mso-line-height-rule hacks. After October 2026, these are dead code that bloats HTML and adds maintenance burden. The analyzer tells you exactly which workarounds can be safely removed based on your audience's Outlook version distribution.
**Implementation:**
- Create `app/qa_engine/outlook_analyzer/` package:
  - `detector.py` — `OutlookDependencyDetector`:
    - `analyze(html: str) -> OutlookAnalysis` — parses HTML via BeautifulSoup, returns structured dependency report
    - Detection rules (all regex/AST — no LLM):
      - `VML_SHAPES`: find `<v:roundrect>`, `<v:rect>`, `<v:oval>`, `<v:shape>` elements
      - `GHOST_TABLES`: `<table>` elements inside `<!--[if mso]>` conditionals with no visible content
      - `MSO_CONDITIONALS`: all `<!--[if mso]>` / `<!--[if !mso]>` blocks with content categorization
      - `MSO_CSS_PROPERTIES`: `mso-line-height-rule`, `mso-table-lspace`, `mso-padding-alt`, etc.
      - `DPI_IMAGES`: images with explicit `width`/`height` attributes that differ from CSS dimensions (DPI compensation)
      - `EXTERNAL_CLASS`: `.ExternalClass` CSS rules
      - `WORD_WRAP_HACKS`: `word-wrap`, `word-break` with mso-specific values
    - `OutlookAnalysis(dependencies: list[OutlookDependency], total_count: int, removable_count: int, byte_savings: int, modernization_plan: list[ModernizationStep])`
    - `OutlookDependency(type: str, location: str, line_number: int, code_snippet: str, severity: str, removable: bool, modern_replacement: str | None)`
  - `modernizer.py` — `OutlookModernizer`:
    - `modernize(html: str, analysis: OutlookAnalysis, target: str = "new_outlook") -> str` — applies safe modernizations:
      - Replace VML buttons with CSS `border-radius` + `background-color` (New Outlook = Chromium)
      - Remove ghost tables, unwrap content
      - Remove `mso-*` CSS properties (or keep inside `<!--[if mso]>` for dual-support period)
      - Replace `.ExternalClass` hacks with standard CSS
    - `target` parameter: `"new_outlook"` (aggressive — remove all Word hacks), `"dual_support"` (keep hacks inside conditionals for transition period), `"audit_only"` (report but don't modify)
- Modify `app/qa_engine/routes.py` — add `POST /api/v1/qa/outlook-analysis` (analyze), `POST /api/v1/qa/outlook-modernize` (apply modernizations) with auth + rate limiting
- Config: `QA__OUTLOOK_ANALYZER_ENABLED: bool = False`, `QA__OUTLOOK_DEFAULT_TARGET: str = "dual_support"`
**Security:** Analyzer is read-only — parses HTML via BeautifulSoup (no eval). Modernizer applies deterministic transformations only. No external calls. Output sanitized via `sanitize_html_xss()`.
**Verify:** Analyze email with VML buttons → all VML elements detected, modern CSS replacement suggested. Analyze clean modern email → zero dependencies. Modernize with `new_outlook` → VML replaced with CSS, ghost tables removed, byte size reduced. Modernize with `dual_support` → hacks wrapped in conditionals but functional in both engines. `make test` passes.
- [x] ~~19.1 Outlook Word-engine dependency analyzer~~ DONE

### 19.2 Audience-Aware Outlook Migration Planner `[Backend]`
**What:** A migration planning service that combines the dependency analysis (19.1) with audience data (Outlook version distribution from ESP analytics or manual input) to produce a phased migration plan. Shows which workarounds are safe to remove now (< 5% of audience on old Outlook), which need the dual-support period, and projects a timeline for full modernization.
**Why:** "Remove all Outlook hacks" is too aggressive for most enterprises — they need to know which hacks are safe to remove based on their actual audience. A financial services client with 40% Outlook 2016 users has a different migration timeline than a tech company with 90% Gmail. This audience-aware planning is what makes the tool consultancy-grade.
**Implementation:**
- Create `app/qa_engine/outlook_analyzer/planner.py` — `MigrationPlanner`:
  - `plan(analysis: OutlookAnalysis, audience: AudienceProfile) -> MigrationPlan` — produces phased plan
  - `AudienceProfile(client_distribution: dict[str, float])` — e.g., `{"outlook_2016": 0.15, "outlook_2019": 0.20, "new_outlook": 0.10, "gmail_web": 0.35, ...}`
  - `MigrationPlan(phases: list[MigrationPhase], total_savings_bytes: int, estimated_completion: str, risk_assessment: str)`
  - `MigrationPhase(name: str, dependencies_to_remove: list[OutlookDependency], audience_impact: float, safe_when: str)` — `safe_when` = "now" / "when old_outlook < 10%" / "after october 2026"
  - Phase ordering: safest removals first (audience_impact < 1%), riskier removals later
- Modify `app/qa_engine/routes.py` — add `POST /api/v1/qa/outlook-migration-plan` accepting analysis + audience profile
- Modify `app/connectors/service.py` — add `async get_audience_profile(connection_id: int) -> AudienceProfile | None` — pull client distribution from ESP analytics API (Braze/SFMC provide this). Returns `None` if ESP doesn't support analytics
**Security:** Audience data is aggregate statistics (percentages per client) — no PII. ESP analytics API calls use existing encrypted credentials from `ESPConnection`. Migration plan contains only code patterns and percentages.
**Verify:** Plan with 40% old Outlook → conservative phased approach, most hacks kept. Plan with 5% old Outlook → aggressive modernization recommended. Plan with no audience data → generic timeline based on industry averages. ESP audience pull works for Braze (mock server). `make test` passes.
- [x] ~~19.2 Audience-aware Outlook migration planner~~ DONE

### 19.3 Lightning CSS Email Compiler `[Backend]`
**What:** An email-specific CSS compiler built on Lightning CSS (Rust, 100x faster than JS parsers) that performs AST-level optimization for email clients. Unlike Juice (which does string-level CSS inlining), this compiler understands the email rendering landscape: removes CSS properties unsupported by target clients (driven by ontology data), auto-converts modern CSS to email-safe equivalents, merges redundant declarations, removes dead selectors, and produces optimal inlined output.
**Why:** Current CSS processing in the Maizzle pipeline uses Juice for inlining — a brute-force approach that doesn't understand email client constraints. The compiler produces smaller HTML (often 15-25% reduction) by eliminating properties that would be ignored anyway, and converts modern CSS to compatible equivalents (e.g., `gap` → `margin` on child elements for Outlook). Lightning CSS's Python bindings make this a drop-in enhancement.
**Implementation:**
- Install `lightningcss` Python bindings (via `pip install lightningcss`) or use Rust binary via subprocess
- Create `app/email_engine/css_compiler/` package:
  - `compiler.py` — `EmailCSSCompiler`:
    - `compile(html: str, target_clients: list[str] | None = None) -> CompilationResult` — full compilation pipeline
    - `CompilationResult(html: str, original_size: int, compiled_size: int, removed_properties: list[str], conversions: list[CSSConversion], warnings: list[str])`
    - Pipeline stages:
      1. **Parse**: extract all CSS (inline styles + `<style>` blocks) via Lightning CSS parser
      2. **Analyze**: cross-reference each property against ontology support matrix for target clients
      3. **Transform**: apply conversions for unsupported properties (ontology `Fallback` objects provide alternatives)
      4. **Eliminate**: remove properties with zero support across all target clients (dead CSS)
      5. **Optimize**: Lightning CSS minification — merge longhands into shorthands, reduce `calc()`, remove redundant declarations
      6. **Inline**: inject optimized styles as inline `style` attributes (replacing Juice)
      7. **Output**: final HTML with optimized CSS
  - `conversions.py` — `CSSConversion` rules driven by ontology fallbacks:
    - `flexbox_to_table`: convert `display:flex` containers to `<table>` equivalents
    - `grid_to_table`: convert `display:grid` layouts to table-based
    - `gap_to_margin`: convert `gap` property to `margin` on child elements
    - `custom_properties_to_values`: resolve `var(--x)` references to computed values
    - `modern_to_outlook`: generate MSO conditional blocks for properties that need dual-path
  - `integration.py` — `MaizzleCompilerPlugin` — hook into Maizzle sidecar build pipeline (replace Juice step)
- Modify `services/maizzle-builder/` — add optional CSS compiler step via POST /compile-css endpoint (alternative to Juice inlining)
- Modify `app/email_engine/routes.py` — add `POST /api/v1/email/compile-css` for standalone CSS compilation
- Config: `EMAIL_ENGINE__CSS_COMPILER_ENABLED: bool = False`, `EMAIL_ENGINE__CSS_COMPILER_TARGET_CLIENTS: list[str] = ["gmail_web", "outlook_2019", "apple_mail", "yahoo_mail"]`
**Security:** CSS parsing via Lightning CSS (Rust, memory-safe). No eval/exec of CSS content. Ontology data is read-only. Output validated via `sanitize_html_xss()`. No external network calls.
**Verify:** Compile email with `display:flex` targeting `[outlook_2019]` → flexbox converted to table layout. Compile targeting `[gmail_web, apple_mail]` only → flexbox preserved (both support it). Size reduction measured: compiled output < original for all golden templates. Juice-replaced output renders identically to Juice output in golden template screenshots. `make test` passes.
- [x] ~~19.3 Lightning CSS email compiler~~ DONE

### 19.4 Frontend Outlook Advisor & Compiler Dashboard `[Frontend]`
**What:** Frontend UI for Outlook migration analysis (dependency heatmap, migration timeline, "Modernize" action), audience profile input/ESP import, and CSS compilation results (size before/after, removed properties, conversion list). Integrated into workspace toolbar and QA panel.
**Implementation:**
- Create `cms/apps/web/src/components/outlook/` — `OutlookAdvisorPanel.tsx` (dependency list with severity), `MigrationTimeline.tsx` (phased plan visualization), `AudienceProfileInput.tsx` (manual entry or ESP import)
- Create `cms/apps/web/src/components/email-engine/CSSCompilerPanel.tsx` — before/after size comparison, property removal list, conversion details
- SWR hooks: `useOutlookAnalysis()`, `useMigrationPlan()`, `useCSSCompile()`
- i18n: ~30 keys across 6 locales
- SDK regeneration
**Verify:** Full Outlook analysis → migration plan displayed → "Modernize" applies changes → re-analysis shows reduction. CSS compiler → size reduction shown. `make check-fe` passes.
- [x] ~~19.4 Frontend Outlook advisor & compiler dashboard~~ DONE

### 19.5 Tests & Documentation `[Full-Stack]`
**What:** Tests for Outlook analyzer (detection of all 7 dependency types), modernizer (safe transformations, dual-support mode), migration planner (audience-weighted phasing), CSS compiler (all conversion rules, size reduction, ontology integration). 45+ tests. ADR-008.
**Implementation:**
- Create `app/qa_engine/outlook_analyzer/tests/` — `test_detector.py`, `test_modernizer.py`, `test_planner.py` — 25+ tests
- Create `app/email_engine/css_compiler/tests/` — `test_compiler.py`, `test_conversions.py` — 20+ tests
- Route tests for all new endpoints
- ADR-008 in `docs/ARCHITECTURE.md` — Outlook Transition & CSS Compilation
**Verify:** `make test` passes. `make check` all green.
- [x] ~~19.5 Tests & documentation~~ DONE

---

## Phase 20 — Gmail AI Intelligence & Deliverability

**What:** Three capabilities targeting the Gmail ecosystem: (1) predict how Gmail's Gemini AI will summarize an email, (2) auto-inject schema.org structured data based on email intent, (3) pre-send deliverability scoring. Plus BIMI readiness verification.
**Why:** Gmail's AI filtering (launched early 2026) creates a new layer between sender and recipient — emails are now summarized, categorized, and filtered by AI before users see them. No email platform addresses this. Schema.org markup directly impacts Gmail Promotions tab visibility (deal annotations, product carousels). BIMI is mandatory for enterprise trust signals in 2026. Deliverability scoring closes the "looks good but never reaches inbox" gap.
**Dependencies:** Phase 11 (QA engine for deliverability checks), Phase 16 (query router intent classification — reusable for email intent classification).
**Design principle:** Gmail AI prediction is best-effort (no one has access to Gemini's actual summarization model) — we use a local LLM to approximate. Schema.org injection is deterministic (rule-based, not LLM). Deliverability scoring is heuristic-based with optional LLM enhancement.

### 20.1 Gmail AI Summary Predictor `[Backend]`
**What:** A service that estimates how Gmail's Gemini-powered summarization will present an email to the recipient. Generates a predicted "summary card" — the 1-2 sentence preview that appears in Gmail's inbox view, the categorization (Primary/Promotions/Updates/Social), and the likely "key action" extraction. Uses an LLM to simulate Gemini's summarization behavior based on the email's subject line, preview text, and body content.
**Why:** Gmail's AI summarization means the email you send is not the email users see. If Gemini summarizes a promotional email as "Company wants you to buy X at Y% off", that summary IS the email for most users. Optimizing the email to produce favorable AI summaries is an entirely new discipline — and no one offers tooling for it. This is greenfield competitive advantage.
**Implementation:**
- Create `app/qa_engine/gmail_intelligence/` package:
  - `predictor.py` — `GmailSummaryPredictor`:
    - `async predict(html: str, subject: str, from_name: str) -> GmailPrediction` — extracts text content from HTML, feeds to LLM with Gmail-specific summarization prompt
    - `GmailPrediction(summary_text: str, predicted_category: str, key_actions: list[str], promotion_signals: list[str], improvement_suggestions: list[str])`
    - Summarization prompt engineered to mimic Gemini's known behaviors: focus on CTAs, pricing, urgency signals, sender reputation heuristics
    - Category prediction based on: sender domain, subject line patterns, CTA density, unsubscribe link presence, schema.org markup presence
    - `improvement_suggestions`: specific changes to subject/preview text/content that would improve the summary
  - `optimizer.py` — `PreviewTextOptimizer`:
    - `async optimize(html: str, subject: str, target_summary: str | None = None) -> OptimizedPreview` — suggests preview text and subject line variations that produce better AI summaries
    - `OptimizedPreview(original_subject: str, suggested_subjects: list[str], original_preview: str, suggested_previews: list[str], reasoning: str)`
- Modify `app/qa_engine/routes.py` — add `POST /api/v1/qa/gmail-predict` (prediction), `POST /api/v1/qa/gmail-optimize` (suggestions)
- Config: `QA__GMAIL_PREDICTOR_ENABLED: bool = False`, `QA__GMAIL_PREDICTOR_MODEL: str = "gpt-4o-mini"` (cost-efficient for summarization)
**Security:** Email content passed to LLM for summarization — same security model as existing agents (no PII expected in template HTML). Prompt sanitized via `sanitize_prompt()`. LLM response is text-only — no code execution. Rate limited.
**Verify:** Promotional email with pricing → predicted category = "Promotions", summary includes price/discount. Transactional email (order confirmation) → predicted category = "Updates", summary includes order details. Subject line optimization → suggestions differ from original and are coherent. `gmail_predictor_enabled=False` skips entirely. `make test` passes.
- [x] ~~20.1 Gmail AI summary predictor~~ DONE

### 20.2 Schema.org Auto-Markup Injection `[Backend]`
**What:** Automatically inject appropriate schema.org JSON-LD structured data into email HTML based on classified email intent. Supports Gmail Actions (ConfirmAction, ViewAction, TrackAction), Deal Annotations (promotions tab product cards with price/discount/expiry), Event markup (RSVP actions), and Order tracking (ViewOrderAction with status). Intent classification reuses the hub's QueryRouter pattern (16.1).
**Why:** Schema.org markup directly impacts Gmail inbox experience: Deal Annotations surface product images and prices in the Promotions tab, Action buttons appear in the inbox list view without opening the email, and Event markup enables RSVP from the inbox. Most email platforms ignore this entirely — markup is added manually by developers who happen to know about it. Auto-injection based on detected intent makes it effortless.
**Implementation:**
- Create `app/email_engine/schema_markup/` package:
  - `classifier.py` — `EmailIntentClassifier`:
    - `classify(html: str, subject: str) -> EmailIntent` — regex-first classification (reusing 16.1 pattern):
      - `promotional`: pricing patterns (`$`, `£`, `%`, "sale", "discount", "offer"), CTA patterns ("Shop now", "Buy", "Order")
      - `transactional`: order number patterns, shipping/tracking keywords, receipt indicators
      - `event`: date/time patterns with RSVP/register/attend keywords
      - `newsletter`: "unsubscribe" + regular content without commercial CTAs
      - `notification`: status update patterns, account activity keywords
    - `EmailIntent(type: str, confidence: float, extracted_entities: dict)` — entities include detected prices, dates, order numbers, product names
  - `injector.py` — `SchemaMarkupInjector`:
    - `inject(html: str, intent: EmailIntent) -> str` — injects JSON-LD `<script type="application/ld+json">` in `<head>`
    - Intent → markup mapping:
      - `promotional` → `Product` + `Offer` with `price`, `priceCurrency`, `availabilityEnds` (if detected), `DealAnnotation` for Gmail Promotions tab
      - `transactional` → `Order` + `OrderStatus` with `orderNumber`, `TrackAction` with tracking URL
      - `event` → `Event` with `startDate`, `location`, `RsvpAction` or `ViewAction`
      - `notification` → `ViewAction` linking to relevant dashboard/page
    - Validates generated JSON-LD against schema.org vocabulary before injection
  - `validator.py` — `SchemaValidator` — validates JSON-LD structure, required properties per type, Gmail-specific requirements (sender verification, HTTPS action URLs)
- Modify `app/email_engine/service.py` — add optional schema injection step in email build pipeline (after HTML compilation, before export)
- Modify `app/email_engine/routes.py` — add `POST /api/v1/email/inject-schema` for standalone schema injection
- Config: `EMAIL_ENGINE__SCHEMA_INJECTION_ENABLED: bool = False`, `EMAIL_ENGINE__SCHEMA_TYPES: list[str] = ["promotional", "transactional", "event"]`
**Security:** JSON-LD is structured data — no executable code. Action URLs validated as HTTPS only (Gmail requirement). No user-provided URLs in generated markup — only URLs extracted from the email HTML itself. Injection point is `<head>` only — no body modification.
**Verify:** Email with "$50 off, expires March 30" → `DealAnnotation` injected with price=$50, discount, expiry date. Order confirmation email → `Order` + `TrackAction` injected. Event invitation → `Event` + `RsvpAction` injected. Newsletter → no markup injected (intentional — newsletters don't benefit). JSON-LD validates against schema.org. `make test` passes.
- [x] ~~20.2 Schema.org auto-markup injection~~ DONE

### 20.3 Deliverability Prediction Score `[Backend]`
**What:** Pre-send deliverability scoring that analyzes email HTML for spam trigger patterns, image-to-text ratio, link density, authentication readiness (SPF/DKIM/DMARC/BIMI), and content quality signals. Produces a 0-100 deliverability score with specific improvement recommendations. Integrates as QA check #13.
**Why:** An email that renders perfectly but lands in spam is worse than one with rendering issues that reaches the inbox. The global average inbox placement rate is 83.1% — meaning ~17% of emails never reach the recipient. Current QA checks validate rendering and accessibility but ignore deliverability entirely. This closes the gap.
**Implementation:**
- Create `app/qa_engine/checks/deliverability.py` — `DeliverabilityCheck(QACheck)`:
  - `async run(html: str, config: QAConfig) -> QACheckResult` — scoring across dimensions:
    - **Content quality** (0-25): text-to-image ratio (>60% text = good), link density (<1 link per 50 words), no URL shorteners, no excessive capitalization, no spam trigger words ("FREE!!!", "Act now", "Limited time")
    - **HTML hygiene** (0-25): valid `DOCTYPE`, character encoding declared, reasonable HTML size (<102KB), no hidden text (same color as background), no single-image emails
    - **Authentication readiness** (0-25): checks for DKIM alignment hints in headers (if available), DMARC-friendly sender patterns, List-Unsubscribe header presence, unsubscribe link in body
    - **Engagement signals** (0-25): preview text present and distinct from subject, personalization tokens detected, clear primary CTA, reasonable content length
  - Each dimension produces sub-scores + specific `DeliverabilityIssue(dimension: str, severity: str, description: str, fix: str)`
  - Overall score = sum of dimension scores. Pass threshold: `QA__DELIVERABILITY_THRESHOLD: int = 70`
- Modify `app/qa_engine/service.py` — register as optional check #13
- Modify `app/qa_engine/routes.py` — add `POST /api/v1/qa/deliverability-score` for standalone scoring
- Config: `QA__DELIVERABILITY_CHECK_ENABLED: bool = False`, `QA__DELIVERABILITY_THRESHOLD: int = 70`
**Security:** All analysis is local — no external API calls. Spam trigger word list is static (no dynamic loading). No PII in scoring output.
**Verify:** Clean transactional email → score > 85. Spam-like promotional email (ALL CAPS subject, image-heavy, many links) → score < 50. Adding List-Unsubscribe → score increases. Adding preview text → score increases. Single-image email → HTML hygiene score penalized. `make test` passes.
- [x] ~~20.3 Deliverability prediction score~~ DONE

### 20.4 BIMI Readiness Check `[Backend]`
**What:** Verify BIMI (Brand Indicators for Message Identification) compliance: check sending domain's DMARC policy (must be quarantine or reject), validate BIMI DNS record format, verify SVG logo meets Gmail's Tiny PS format requirements, and check CMC (Common Mark Certificate) status. Generates the BIMI TXT record as part of deployment checklist.
**Why:** BIMI displays the sender's verified logo in the inbox — directly impacting open rates (up to 10% increase per industry data). Google dropped the trademark requirement in 2025 (CMC now sufficient), making BIMI accessible to all brands. But setup is complex (DMARC + DNS + SVG format + certificate) — automating the readiness check removes the barrier.
**Implementation:**
- Create `app/qa_engine/checks/bimi.py` — `BIMIReadinessCheck`:
  - `async check_domain(domain: str) -> BIMIStatus` — DNS lookups for DMARC record, BIMI record, SVG validation
  - `BIMIStatus(dmarc_ready: bool, dmarc_policy: str, bimi_record_exists: bool, bimi_record: str | None, svg_valid: bool | None, cmc_status: str, generated_record: str, issues: list[str])`
  - DMARC check: DNS TXT lookup for `_dmarc.{domain}`, parse `p=` policy (must be `quarantine` or `reject`)
  - BIMI check: DNS TXT lookup for `default._bimi.{domain}`, parse `v=BIMI1; l={svg_url}; a={pem_url}`
  - SVG validation: if BIMI record exists, fetch SVG URL, validate Tiny PS profile (square, no external references, specific element restrictions)
  - Record generator: produce the TXT record string for the domain based on provided SVG/certificate URLs
- Modify `app/qa_engine/routes.py` — add `POST /api/v1/qa/bimi-check` accepting `{domain: str}` with auth + rate limiting
- Config: `QA__BIMI_CHECK_ENABLED: bool = False`
**Security:** DNS lookups are read-only. SVG fetch uses `httpx` with timeout + size limit (max 32KB). No execution of SVG content. Domain input validated (must be valid domain format). Rate limited to prevent DNS abuse.
**Verify:** Domain with full BIMI setup → all checks pass, record validated. Domain with DMARC `p=none` → `dmarc_ready=False`, specific guidance to change policy. Domain without BIMI record → `bimi_record_exists=False`, generated record template provided. Invalid SVG (non-square, external references) → `svg_valid=False`. `make test` passes.
- [x] ~~20.4 BIMI readiness check~~ DONE

### 20.5 Frontend Gmail Intelligence Panel & Tests `[Frontend]`
**What:** Frontend UI for Gmail prediction (predicted summary card preview, category badge, optimization suggestions), deliverability score gauge, BIMI status indicator, and schema.org markup preview. Plus full test suite (30+ tests) and SDK regeneration.
**Implementation:**
- Create `cms/apps/web/src/components/gmail/` — `GmailPredictionPanel.tsx`, `SummaryCardPreview.tsx` (renders predicted summary card), `DeliverabilityGauge.tsx`, `BIMIStatusBadge.tsx`, `SchemaPreview.tsx` (shows injected JSON-LD)
- SWR hooks: `useGmailPrediction()`, `useDeliverabilityScore()`, `useBIMICheck()`, `useSchemaInject()`
- i18n: ~35 keys across 6 locales
- Tests: `test_gmail_predictor.py` (8 tests), `test_schema_markup.py` (10 tests), `test_deliverability.py` (8 tests), `test_bimi.py` (6 tests), route tests
- SDK regeneration
**Verify:** `make test` passes. `make check-fe` passes. `make check` all green.
- [x] ~~20.5 Frontend Gmail intelligence panel & tests~~ DONE

---

## Phase 21 — Real-Time Ontology Sync & Competitive Intelligence

**What:** Auto-sync the email compatibility ontology from the caniemail open-source dataset, track email client rendering changes over time, and build a competitive intelligence layer that monitors how email client updates affect existing templates.
**Why:** The ontology (335+ CSS properties × 25+ clients) is the hub's single source of truth for compatibility — but it's manually maintained. The caniemail dataset updates weekly with community-contributed data. Auto-syncing keeps the hub current without manual effort. Client rendering change detection creates a proprietary dataset that goes beyond what caniemail offers — real-time awareness of when a client changes behavior.
**Dependencies:** Phase 8-9 (ontology + knowledge graph), Phase 16 (structured queries use ontology data), Phase 17 (screenshot baselines for change detection).
**Design principle:** Ontology sync is additive-only by default — new data merges, existing data never deleted without manual approval. Change detection is non-blocking — findings are advisory, surfaced in UI, not gates.

### 21.1 caniemail Auto-Sync Pipeline `[Backend]`
**What:** A scheduled pipeline that fetches the latest caniemail dataset from GitHub, diffs against the current ontology, and merges new/updated support data. Runs daily via the existing `DataPoller` infrastructure. Produces a changelog of what changed for developer review.
**Why:** caniemail is the industry standard for CSS email support data — open source, community-maintained, updated weekly. Currently the hub's ontology was seeded once; keeping it current requires manual effort. Auto-sync ensures every CSS support query returns current data. The @jsx-email/doiuse-email npm package proves this data is machine-readable.
**Implementation:**
- Create `app/knowledge/ontology/caniemail_sync.py` — `CanIEmailSyncService`:
  - `async sync(dry_run: bool = False) -> SyncReport` — fetch, diff, merge pipeline
  - Fetch: `httpx.AsyncClient.get("https://raw.githubusercontent.com/hteumeuleu/caniemail/master/data/...")` — individual feature JSON files
  - Parse: convert caniemail format (feature name, stats per client, notes, links) to ontology `CSSProperty` + `SupportLevel` format
  - Diff: compare fetched data against current ontology — identify new properties, updated support levels, new client versions
  - Merge: apply updates to ontology (additive by default). New properties added. Support levels updated only if they improve precision (partial → supported/unsupported)
  - `SyncReport(new_properties: int, updated_levels: int, new_clients: int, changelog: list[ChangelogEntry], errors: list[str])`
  - `ChangelogEntry(property_id: str, client_id: str, old_level: str | None, new_level: str, source: str)`
- Create `app/knowledge/ontology/caniemail_poller.py` — `CanIEmailPoller(DataPoller)`:
  - Runs every 24 hours (configurable)
  - Calls `CanIEmailSyncService.sync(dry_run=False)`
  - Logs sync report via structured logging
  - Stores last sync timestamp + report in Redis for dashboard display
- Modify `app/main.py` — register `CanIEmailPoller` (same pattern as `CheckpointCleanupPoller`)
- Modify `app/knowledge/routes.py` — add `POST /api/v1/knowledge/ontology/sync` (manual trigger, admin only), `GET /api/v1/knowledge/ontology/sync-status` (last sync time + report)
- Config: `KNOWLEDGE__CANIEMAIL_SYNC_ENABLED: bool = False`, `KNOWLEDGE__CANIEMAIL_SYNC_INTERVAL_HOURS: int = 24`, `KNOWLEDGE__CANIEMAIL_DRY_RUN: bool = True` (dry run by default until manually verified)
**Security:** Fetches from a known GitHub URL only — no user-provided URLs. Data is CSS property support information — no executable content. Sync is additive-only by default. Admin-only manual trigger. GitHub rate limiting handled via conditional requests (If-Modified-Since).
**Verify:** Run sync → new properties added that weren't in original ontology seed. Run sync again immediately → no changes (idempotent). Run dry_run → report generated but no data modified. Invalid GitHub response → graceful failure, no data corruption. Ontology queries return updated data after sync. `make test` passes.
- [x] ~~21.1 caniemail auto-sync pipeline~~ DONE

### 21.2 Email Client Rendering Change Detector `[Backend]`
**What:** A scheduled service that renders a suite of CSS feature-detection email templates through the Playwright rendering service (17.1), compares screenshots against stored baselines, and flags when a client's rendering behavior changes. Creates a proprietary, real-time email client behavior changelog.
**Why:** caniemail tells you what CSS _should_ work in email clients. This tells you what CSS _actually_ works right now — and when it changes. Email clients update silently (Gmail's CSS support has expanded significantly over the years without announcement). Detecting these changes creates proprietary intelligence that goes beyond any public dataset.
**Implementation:**
- Create `app/knowledge/ontology/change_detector.py` — `RenderingChangeDetector`:
  - `async detect_changes() -> list[RenderingChange]` — renders feature detection templates, compares against baselines
  - Feature detection templates: one per critical CSS property, each tests a single property with visual indicator (e.g., `display:flex` with visible layout difference between flex and fallback)
  - `RenderingChange(property_id: str, client_id: str, previous_behavior: str, current_behavior: str, screenshot_diff: bytes, detected_at: datetime)`
  - Uses 17.1 `EmailScreenshotService` for rendering, 17.2 `VisualDiffService` for comparison
  - Stores detected changes in knowledge base as documents (domain="rendering_changes")
- Create feature detection templates in `app/knowledge/ontology/feature_templates/` — 20-30 HTML files testing critical CSS properties (flexbox, grid, custom properties, `gap`, `aspect-ratio`, `clamp()`, etc.)
- Create `app/knowledge/ontology/change_poller.py` — `RenderingChangePoller(DataPoller)` — runs weekly
- Config: `KNOWLEDGE__CHANGE_DETECTION_ENABLED: bool = False`, `KNOWLEDGE__CHANGE_DETECTION_INTERVAL_HOURS: int = 168` (weekly)
**Security:** Feature detection templates are static HTML (no dynamic content). Rendering uses sandboxed Playwright (17.1 security model). Changes stored as structured data + screenshot diffs — no executable content.
**Verify:** Modify a rendering profile to simulate a client change (e.g., enable flexbox in outlook_2019 profile) → change detector flags the difference. No profile changes → no changes detected. Detected change creates knowledge base document. `make test` passes.
- [x] ~~21.2 Email client rendering change detector~~ DONE

### 21.3 Competitive Intelligence Dashboard & Tests `[Frontend]`
**What:** Frontend dashboard showing ontology sync status, rendering change timeline, support matrix diff viewer (what changed since last sync), and email client trend analysis. Plus full test suite and SDK regeneration.
**Implementation:**
- Create `cms/apps/web/src/components/knowledge/OntologySyncPanel.tsx` — last sync status, changelog viewer, manual sync trigger (admin only)
- Create `cms/apps/web/src/components/knowledge/RenderingChangelog.tsx` — timeline of detected rendering changes with screenshot diffs
- SWR hooks: `useOntologySyncStatus()`, `useRenderingChanges()`
- i18n: ~20 keys across 6 locales
- Tests: `test_caniemail_sync.py` (10 tests — fetch, parse, diff, merge, idempotency), `test_change_detector.py` (8 tests), route tests
- SDK regeneration
- Target: 25+ tests
**Verify:** `make test` passes. `make check-fe` passes. `make check` all green.
- [x] ~~21.3 Competitive intelligence dashboard & tests~~ DONE

---

## Phase 22 — AI Evolution Infrastructure

**What:** Close the "identified gaps" from the pitch's AI Evolution section: model capability registry with capability-based routing, prompt template store with A/B testing, token budget manager, fallback chains for provider resilience, and cost governor with per-model budget caps and circuit breakers.
**Why:** The hub currently treats models as interchangeable text boxes (hardcoded model names per tier). When a new model launches, model deprecates, or provider has an outage, manual intervention is needed. These five capabilities make every AI improvement a zero-downtime, zero-code operation — the pitch's stated goal for V1 competitive advantage.
**Dependencies:** Phase 15 (adaptive routing foundation), all agent phases (consumers of the new infrastructure).
**Design principle:** Each capability is independently deployable. Existing `LLMProvider` protocol and `get_registry()` patterns preserved — new capabilities wrap the existing interface rather than replacing it.

### 22.1 Model Capability Registry `[Backend]`
**What:** Each model declares capabilities (vision, tool_use, structured_output, extended_thinking), constraints (context_window, max_output_tokens, cost_per_token), and metadata (provider, local_vs_cloud, deprecation_date). The router matches task requirements to model capabilities rather than just tier names.
**Implementation:**
- Create `app/ai/capability_registry.py` — `ModelCapability` enum, `ModelSpec` frozen dataclass, `CapabilityRegistry` singleton with `register(model_id, spec)`, `find_models(requirements: set[ModelCapability], min_context: int) -> list[ModelSpec]`
- Modify `app/ai/routing.py` — `resolve_model()` checks capability requirements when provided, falls back to tier-based routing
- Config: model specs in `AI__MODEL_SPECS` YAML/JSON config
- [x] 22.1 Model capability registry ~~DONE~~

### 22.2 Prompt Template Store `[Backend]`
**What:** Move agent system prompts from Python files to a versioned database store with A/B variant support. Agents load prompts at runtime via `PromptStore.get(agent_id, variant)`. Versions tracked with rollback.
**Implementation:**
- Create `app/ai/prompt_store.py` — `PromptTemplate` model (id, agent_id, version, variant, content, active), `PromptStore` with CRUD + `get_active(agent_id, variant)`, migration to seed from existing SKILL.md files
- Modify `app/ai/agents/base.py` — `_build_system_prompt()` checks `PromptStore` first, falls back to SKILL.md
- Config: `AI__PROMPT_STORE_ENABLED: bool = False`
- [x] 22.2 Prompt template store ~~DONE~~

### 22.3 Token Budget Manager `[Backend]`
**What:** Count tokens before sending to LLM. Truncate or summarize conversation history to stay within context window. Adaptive strategy: recent messages preserved, older messages summarized.
**Implementation:**
- Create `app/ai/token_budget.py` — `TokenBudgetManager` with `estimate_tokens(messages)` (tiktoken for OpenAI, approximation for others), `trim_to_budget(messages, max_tokens)` with summarization strategy
- Modify `app/ai/adapters/` — all adapters call `trim_to_budget()` before API call
- Config: `AI__TOKEN_BUDGET_ENABLED: bool = False`, `AI__TOKEN_BUDGET_RESERVE: int = 4096` (reserve for response)
- [x] 22.3 Token budget manager ~~DONE~~

### 22.4 Fallback Chains & Provider Resilience `[Backend]`
**What:** Ordered model fallbacks per tier. Primary model failure auto-cascades to next. Example: `complex: [claude-opus-4-6 → gpt-4o → local-qwen-72b]`. Every fallback event logged.
**Implementation:**
- Create `app/ai/fallback.py` — `FallbackChain` with `async call_with_fallback(messages, tier) -> Response` — tries each model in order, catches timeout/rate-limit/deprecation errors, logs fallback events
- Modify `app/ai/routing.py` — `resolve_model()` returns `FallbackChain` instead of single model when fallback config present
- Config: `AI__FALLBACK_CHAINS` YAML config per tier
- [x] ~~22.4 Fallback chains & provider resilience~~ DONE

### 22.5 Cost Governor `[Backend]`
**What:** Real-time token and cost tracking per model, per agent, per project. Configurable budget caps with circuit breakers — auto-route to cheaper models or local fallbacks when spend approaches threshold.
**Implementation:**
- Create `app/ai/cost_governor.py` — `CostGovernor` with `track(model, tokens_in, tokens_out, agent, project)` (Redis-backed counters), `check_budget(agent, project) -> BudgetStatus`, circuit breaker integration
- Modify `app/ai/adapters/` — all adapters report usage to `CostGovernor` after each call
- Dashboard endpoint: `GET /api/v1/ai/cost-report` (admin only)
- Config: `AI__COST_GOVERNOR_ENABLED: bool = False`, `AI__MONTHLY_BUDGET_GBP: float = 600.0`, `AI__BUDGET_WARNING_THRESHOLD: float = 0.8`
- [x] ~~22.5 Cost governor~~ DONE

### 22.6 Tests & Documentation `[Full-Stack]`
**What:** Tests for all 5 capabilities (30+ tests). ADR-009 AI Evolution Infrastructure.
- [x] ~~22.6 Tests & documentation~~ DONE

---

## Phase 23 — Multimodal Protocol & MCP Agent Interface (partial)

### 23.1 Multimodal Content Block Protocol `[Backend]`
**What:** Replace string-based `Message.content` with typed `ContentBlock` union supporting text, images, audio, structured output, and tool results. Core protocol types, validation, token estimation, adapter serialization, and backward compatibility.
**Implementation:**
- Create `app/ai/multimodal.py` — `ContentBlock` union: `TextBlock`, `ImageBlock`, `AudioBlock`, `StructuredOutputBlock` (with `name` regex validation), `ToolResultBlock`; frozen dataclasses; `validate_content_block()` with MIME magic bytes, size limits (image 20MB, audio 100MB), duration 300s, `$ref` whitelist (only `#`-prefixed internal refs), recursion depth guard; `normalize_content()` backward compat; `estimate_block_tokens()` (Anthropic image formula, PNG header parsing, duration-based audio)
- Create `app/ai/multimodal_schemas.py` — Pydantic schemas for API transport with base64 encoding/decoding, `schema_to_block()`/`block_to_schema()` converters
- Modify `app/ai/protocols.py` — `Message.content: str | list[ContentBlock]` with `TYPE_CHECKING` guard for circular import avoidance
- Modify `app/ai/adapters/anthropic.py` — `_serialize_content_blocks()` (Anthropic content block format), `_build_messages_payload()` with vision capability check, `_extract_structured_output()`
- Modify `app/ai/adapters/openai_compat.py` — `_serialize_content_blocks()` (OpenAI data URI format), `_build_messages_payload()` with vision capability check, `_extract_structured_output()`, structured output via `response_format`
- Modify `app/ai/token_budget.py` — `_count_message_tokens()` handles multimodal via `estimate_blocks_tokens()`, system message truncation skips multimodal
- Migrate `app/ai/agents/visual_qa/service.py` — raw dict content blocks → typed `ImageBlock`/`TextBlock` (removed `type: ignore` hack)
- Migrate `app/ai/blueprints/nodes/visual_qa_node.py` — same migration for both detection and verification VLM calls
- Config: `AI__MAX_IMAGE_SIZE_MB` 20, `AI__MAX_AUDIO_DURATION_S` 300, `AI__SUPPORTED_IMAGE_TYPES`
- 80 new tests (53 core + 27 adapter/compat), 3292 total backend
- [x] ~~23.1 Multimodal content block protocol~~ DONE

### 23.2 Adapter Multimodal Serialization `[Backend]`
**What:** Both LLM adapters serialize `ContentBlock` types into provider-specific API formats with structured output, vision capability checking, and input validation. Keeps agents provider-agnostic.
**Implementation:**
- Modify `app/ai/adapters/openai_compat.py` — `OpenAICompatProvider`:
  - `_serialize_content_blocks()` converts ContentBlock list to OpenAI format (TextBlock → text, ImageBlock → `image_url` with data URI, AudioBlock → text placeholder, ToolResultBlock → flattened text)
  - `_extract_structured_output()` finds `StructuredOutputBlock` in last message, sets `response_format` with `json_schema` on payload
  - `_check_vision_capability()` queries `CapabilityRegistry` for `ModelCapability.VISION`, failure-safe (assumes capable on error)
  - `_build_messages_payload()` orchestrates: normalize → validate → vision fallback (images → text descriptions for non-vision models) → serialize
  - `complete()` parses structured JSON response into `CompletionResponse.parsed`
  - `stream()` uses same payload builder
- Modify `app/ai/adapters/anthropic.py` — `AnthropicProvider`:
  - Same `_serialize_content_blocks()` in Anthropic format (ImageBlock → `{"type": "image", "source": {"type": "base64", ...}}`, URL images → `{"type": "url", ...}`)
  - `_extract_structured_output()` → `tools` + `tool_choice` with single-tool pattern for structured output
  - `_build_messages_payload()` returns `(system_parts, chat_messages, has_cache_control)` tuple, validates system message blocks
  - `complete()` extracts `tool_use` block input as parsed JSON
  - Vision capability check identical to OpenAI adapter
- Modify `app/ai/multimodal.py`:
  - Add `name: str = "response"` field to `StructuredOutputBlock` with `_VALID_SCHEMA_NAME` regex validation (`[a-zA-Z0-9_-]{1,64}`)
  - Add `_MAX_SCHEMA_DEPTH = 50` recursion guard to `_check_schema_refs()`
- Migrate `app/ai/agents/visual_qa/service.py` — raw dict content blocks → typed `ImageBlock`/`TextBlock`, add `base64.b64decode` error handling with graceful `VisualQAResponse` return
- Both serializers explicitly skip `StructuredOutputBlock` (handled via request-level params, not content blocks)
- Token budget: no changes needed (23.1 already handled multimodal estimation)
- Cost governor: no changes needed (API responses already include image tokens in usage counts)
- 4 new test files added, 84 total multimodal tests (43 core + 41 adapter), 3292 total backend
- [x] ~~23.2 Adapter multimodal serialization~~ DONE

### 23.3 Agent Multimodal Integration `[Backend]`
**What:** Wire multimodal `ContentBlock` types through the agent layer. `BaseAgentService` gains multimodal-aware message building, `VisualQAService` refactored to use typed helpers, `ScaffolderNode` accepts design reference images, and `BlueprintEngine` gets LAYER 14 for multimodal context injection.
**Implementation:**
- `app/ai/agents/base.py` — `_text_block()` and `_image_block()` static convenience constructors with validation; `_build_multimodal_messages()` builds `Message` list with interleaved `TextBlock` + context blocks, sanitizes text via `sanitize_prompt()`; `process()` and `stream_process()` gain `context_blocks: list[ContentBlock] | None = None` parameter
- `app/ai/blueprints/protocols.py` — `NodeContext.multimodal_context: list[ContentBlock] | None = None` field with `TYPE_CHECKING` guard import
- `app/ai/agents/visual_qa/service.py` — refactored with `_screenshots_to_blocks()` helper that validates size, decodes base64, returns typed `ImageBlock`/`TextBlock` list or `VisualQAResponse` on error; `process()` uses `_build_multimodal_messages()` from base class
- `app/ai/blueprints/nodes/scaffolder_node.py` — reads `context.multimodal_context` for design reference images; checks vision capability via `CapabilityRegistry.find_models(requirements={ModelCapability.VISION})`; builds multimodal messages with design instruction + `ImageBlock` when vision-capable model available; falls back to text-only otherwise
- `app/ai/blueprints/engine.py` — LAYER 14 multimodal context injection (after LAYER 13, before LAYER 11): scaffolder node gets `ImageBlock` from `design_import_assets` metadata, visual_qa node gets `ImageBlock` list from `screenshots` metadata with base64 decode + `TextBlock` labels; all blocks validated via `validate_content_blocks()` before assignment; failure-safe with structured warning logging
- Config: `AI__MULTIMODAL_CONTEXT_ENABLED: bool = False` on `AIConfig` (Phase 23.3)
- `.env.example` updated with `AI__MULTIMODAL_CONTEXT_ENABLED=false`
- No new endpoints — internal infrastructure only
- 22 new tests in `app/ai/tests/test_agent_multimodal.py`: `TestBaseAgentMultimodal` (6 tests — helpers + message building), `TestVisualQAMultimodal` (4 tests — screenshot conversion), `TestBlueprintMultimodalContext` (3 tests — NodeContext field), `TestScaffolderDesignReference` (1 test), `TestMultimodalFeatureFlag` (2 tests), `TestMultimodalEdgeCases` (1 test — empty blocks), `TestScaffolderVisionCapability` (2 tests — vision check with/without capability), `TestEngineLayer14` (3 tests — screenshot injection, design assets, invalid base64 handling)
- 3314 total backend tests
- [x] ~~23.3 Agent multimodal integration~~ DONE

### 23.4 MCP Tool Server `[Backend]`
**What:** Expose Hub services as Model Context Protocol tools. Any MCP-compatible client (Claude Desktop, Cursor, VS Code Copilot, custom agents) can discover and invoke Hub services directly. Workflow-oriented tools with email-domain-aware descriptions (50+ words each) and LLM-friendly markdown responses with token budget enforcement.
**Implementation:**
- Create `app/mcp/` package (18 files):
  - `__init__.py` — `MCPContext` type alias for `Context[Any, Any, Any]`
  - `server.py` — `create_mcp_server()` factory with `FastMCP(stateless_http=True, json_response=True)`, singleton `get_mcp_server()`, `_apply_tool_allowlist()` filters tools via operator fnmatch allowlist at registration time
  - `config.py` — `is_tool_allowed()` fnmatch-based tool allowlist filter
  - `formatting.py` — LLM-friendly response formatters: `truncate_html()` with size markers, `format_qa_result()` (verdict-first with fix guidance), `format_knowledge_result()` (relevance-scored), `format_css_compilation()` (size reduction stats), `format_simple_result()` (generic dict/list/str), `to_dict()` (Pydantic/dataclass converter), `_apply_token_budget()` (char-approximated truncation, ~4 chars/token)
  - `auth.py` — `verify_mcp_token()` via existing `decode_token()` JWT infrastructure, `_role_to_scopes()` mapping (admin→read/write/admin, developer→read/write, viewer→read)
  - `resources.py` — 2 MCP resources: `ontology://css/{property_name}` (CSS support data from caniemail), `hub://capabilities` (feature flag status for 15 capabilities)
  - `__main__.py` — `python -m app.mcp` stdio entry point for IDE integration
  - `tools/__init__.py` + 6 tool modules — 17 tools across 6 domains:
    - `tools/qa.py` — `qa_check` (11-gate validation), `email_production_readiness` (composite: QA + deliverability + Gmail prediction + Outlook scan with progress reporting), `chaos_test` (8-profile degradation), `outlook_analyze` (7 dependency types + modernization), `gmail_predict` (AI summary + category prediction)
    - `tools/knowledge.py` — `knowledge_search` (auto-routed with domain filter), `css_support_check` (ontology support matrix), `safe_css_alternatives` (fallback finder)
    - `tools/email.py` — `css_optimize` (7-stage Lightning CSS pipeline), `inject_schema_markup` (intent classification + JSON-LD injection)
    - `tools/rendering.py` — `email_visual_check` (multi-client Playwright screenshots, feature-gated), `visual_diff` (feature-gated placeholder)
    - `tools/templates.py` — `list_templates` (project-context gated), `search_components` (pgvector component search)
    - `tools/ai.py` — `ai_cost_status` (Redis-backed budget monitoring), `deliverability_score` (4-dimension heuristic scoring), `bimi_check` (DNS + SVG validation with domain regex)
  - `tests/__init__.py` + 3 test files
- All 17 tools have: try/except error handling returning sanitized messages (never stack traces), HTML size validation (500KB cap), structured logging (`mcp.tool_error`), token budget enforcement via `_apply_token_budget()`
- Tool descriptions are 50+ words each with email-specific context (teaching descriptions for LLMs)
- Modify `app/core/config.py` — `MCPConfig(enabled=False, max_response_tokens=4000, tool_timeout_s=120, audit_log_enabled=True, tool_allowlist=[])`
- Modify `app/main.py` — conditional mount at `/mcp` via `StarletteMount` + `streamable_http_app()` when `MCP__ENABLED=true`, pre-create singleton during lifespan startup
- Modify `pyproject.toml` — `mcp>=1.12.0` dependency (installed as 1.26.0), per-file-ignores for `app/mcp/tools/**/*.py` (ARG001 — ctx required by FastMCP convention), mypy overrides for `mcp.*` (ignore_missing_imports) and `app.mcp.tools.*` (disable type-arg)
- Create `mcp-config.json` — Claude Desktop / Cursor IDE manifest
- 19 tests: `test_tools.py` (6 — server creation, 17-tool registration, description quality ≥30 words, stateless mode, instructions, resources), `test_formatting.py` (7 — truncation, QA/knowledge/CSS formatters, token budget), `test_auth.py` (4 — role-to-scope mapping)
- [x] ~~23.4 MCP tool server~~ DONE

### 23.5 Voice Brief Input Pipeline `[Backend]`
**What:** Accept audio file uploads as email briefs. Transcribe via OpenAI Whisper API (default) or local Whisper model, extract structured email brief (topic, sections, tone, CTA, audience, constraints) from transcript via LLM, feed to Scaffolder agent as a standard `BlueprintRunRequest`.
**Implementation:**
- Create `app/ai/voice/` package (7 files):
  - `transcriber.py` — `VoiceTranscriber` Protocol + `WhisperAPITranscriber` (OpenAI Whisper API via `openai.AsyncOpenAI`) + `WhisperLocalTranscriber` (local `openai-whisper` via thread pool) + factory singleton
  - `brief_extractor.py` — `VoiceBriefExtractor` uses LLM to extract structured `EmailBrief` from transcript with JSON schema prompt, confidence scoring (< 0.7 = raw transcript fallback), markdown fence stripping
  - `service.py` — `VoiceBriefService` orchestrating: validate → transcribe → extract → blueprint run. Base64 pre-check before decode (memory abuse prevention), duration validation, project access verification on `/run`
  - `schemas.py` — Frozen dataclasses (`Transcript`, `TranscriptSegment`, `EmailBrief`, `SectionBrief`) + Pydantic API models (`VoiceTranscribeRequest`, `VoiceBriefRequest`, `VoiceRunRequest`, response models)
  - `routes.py` — 3 endpoints at `/api/v1/ai/voice/`: `POST /transcribe` (5/min), `POST /brief` (3/min), `POST /run` (2/min). All auth-gated, config-driven rate limits
  - `exceptions.py` — `VoiceError` hierarchy: `VoiceDisabledError` (501), `AudioValidationError` (422), `TranscriptionError` (502), `BriefExtractionError` (502)
  - `__init__.py` — package init
- Modify `app/core/config.py` — add `VoiceConfig` with 11 settings (enabled, transcriber, models, limits, thresholds, rate limits)
- Modify `app/ai/exceptions.py` — register voice exception handlers with status code mapping
- Modify `app/core/error_sanitizer.py` — add 5 voice exception safe messages
- Modify `app/main.py` — mount voice router at `/api`
- Modify `pyproject.toml` — add `pydub>=0.25.1` dependency
- 10 unit tests in `app/ai/tests/test_voice_pipeline.py`: validation (6), transcription (2), brief formatting (2)
- Config: `VOICE__ENABLED=false` by default, feature-toggled
- [x] ~~23.5 Voice brief input pipeline~~ DONE

---

### 23.6 Frontend Multimodal UI `[Frontend]`
- Voice brief review UI (VoiceBriefList, VoiceBriefCard, VoiceBriefDetail with audio player + transcript segment highlighting + extracted brief display + "Generate Email" CTA)
- DesignReferenceUpload (drag-and-drop with format/size validation)
- MCPConfigPanel (server status, tool allowlist, connection log, API key management — admin-gated)
- 2 SWR hook files (`use-voice-briefs`, `use-mcp`)
- Workspace toolbar voice briefs button with badge; settings page MCP section
- ~55 i18n keys across 6 locales (en, de, es, fr, ar, ja)
- `make check-fe` green
- [x] ~~23.6 Frontend multimodal UI~~ DONE

### 23.7 Tests & Documentation `[Full-Stack]`
- 67 new tests across 8 files:
  - `app/mcp/tests/test_tool_execution.py` (20 tests): Tool execution with mocked services across 6 categories + error handling
  - `app/mcp/tests/test_allowlist.py` (5 tests): Fnmatch-based tool allowlist filtering
  - `app/mcp/tests/test_resources.py` (4 tests): CSS ontology resource template + capabilities resource
  - `app/mcp/tests/test_auth.py` (+3 tests): Async token verification (valid, invalid, leak prevention)
  - `app/mcp/tests/test_formatting.py` (+3 tests): List formatting, Pydantic/dataclass to_dict, token budget truncation
  - `app/ai/tests/test_voice_transcriber.py` (8 tests): WhisperAPI + WhisperLocal transcribers
  - `app/ai/tests/test_voice_extractor.py` (10 tests): LLM brief extraction, JSON parsing, confidence thresholds
  - `app/ai/tests/test_voice_routes.py` (8 tests): Route auth, success paths, validation errors
- ADR-010 Multimodal Protocol & MCP Architecture appended to `docs/ARCHITECTURE.md`
- 197 total Phase 23 tests, 3405 total backend tests
- `make check` all green (format + lint + types + tests + security)
- [x] ~~23.7 Tests & documentation~~ DONE

---

## Phase 24B — Email Client Rendering Accuracy & Liquid Validation

**What:** Upgrade the email client rendering pipeline from static YAML-maintained CSS support data to an auto-synced industry data source, restructure targeting around rendering engines instead of individual clients, add Liquid template dry-run validation, replace crude Playwright simulation profiles with accurate client sanitizer emulation, and adopt progressive enhancement HTML generation (engine-tier assembly) instead of generate-then-fix.

### 24B.1 Can I Email Data Sync `[Backend]`
- CLI entrypoint: `app/knowledge/ontology/sync/cli.py` with `--dry-run` flag
- `make ontology-sync` / `make ontology-sync-dry` Makefile targets
- `check_freshness(max_age_days=90)` method on `CanIEmailSyncService` — reads Redis sync state
- Override file: `app/knowledge/ontology/data/overrides.yaml` — manual entries take priority over sync data
- `load_ontology()` merges overrides into support matrix with validation warnings for unknown IDs
- `apply_sync()` skips entries that have manual overrides
- 7 tests in `app/knowledge/ontology/sync/tests/test_completion.py`
- [x] ~~24B.1 Can I Email data sync~~ DONE

### 24B.2 Rendering Engine Taxonomy `[Backend]`
- 4 new methods on `OntologyRegistry`: `clients_by_engine()`, `engine_support()` (worst-case per engine), `engines_not_supporting()`, `engine_market_share()`
- `unsupported_engines_in_html()` query function — engine-grouped CSS issues with market share and severity
- `CssSupportCheck` now includes engine-level summary (e.g., "Engine: Word (23.8% share) — no support for display: flex")
- 8 tests in `app/knowledge/ontology/tests/test_engine_taxonomy.py`
- [x] ~~24B.2 Rendering engine taxonomy~~ DONE

### 24B.3 Progressive Enhancement Assembly `[Backend]`
- `tier_strategy: Literal["universal", "progressive"]` field on `EmailBuildPlan`
- `TemplateAssembler` Step 11: `_apply_tier_strategy()` — scans sections for modern CSS (flex/grid/border-radius), wraps in MSO conditionals
- `_generate_word_fallback()` — strips flex/grid → `display: block`, removes border-radius, converts background-image to background attribute
- `_wrap_mso_conditional()` — standard `<!--[if !mso]><!-->` / `<!--[if mso]>` wrapping
- `ScaffolderPipeline._detect_tier_strategy()` — auto-detects modern CSS in template HTML
- 7 tests in `app/ai/agents/scaffolder/tests/test_tier_strategy.py`
- [x] ~~24B.3 Progressive enhancement assembly~~ DONE

### 24B.4 Gmail & Outlook.com Sanitizer Emulation `[Backend]`
- `app/rendering/local/emulators.py` — `EmulatorRule` + `EmailClientEmulator` rule-chain framework
- Gmail emulator (6 rules): strip `<style>` blocks, strip `<link>` tags, rewrite class names with `m_` prefix, strip unsupported inline CSS (position/float/flex/grid), strip form elements, enforce body max-width 680px
- Outlook.com emulator (3 rules): strip unsupported CSS (background-image/box-shadow/text-shadow/border-radius), expand margin/padding shorthand to longhand, inject `data-ogsc`/`data-ogsb` dark mode attributes
- `RenderingProfile.emulator_id` field + `outlook_web` profile added to `CLIENT_PROFILES`
- `_prepare_html()` in runner.py applies emulator transforms when profile has an `emulator_id`
- 12 tests in `app/rendering/local/tests/test_emulators.py`
- [x] ~~24B.4 Gmail & Outlook.com sanitizer emulation~~ DONE

### 24B.5 Liquid Template Dry-Run Validation `[Backend]`
- `python-liquid>=1.12` dependency added
- `app/qa_engine/liquid_analyzer.py` — structural analysis: tag nesting, filter extraction, variable detection, Braze-specific pattern recognition (connected_content, content_blocks, abort_message)
- `app/qa_engine/checks/liquid_syntax.py` — QA check #13 with 3-pass validation:
  1. Structural analysis — detect unclosed blocks, mismatched end tags
  2. python-liquid parse — catch syntax errors (Braze templates skipped)
  3. Filter & variable validation — unknown filters, missing `| default` on deep property access
- Braze passthrough: `connected_content`, `content_blocks`, `abort_message` not flagged as errors
- Nesting depth limit (configurable, default 5)
- Registered as check #13 in `ALL_CHECKS`
- 10 tests in `app/qa_engine/tests/test_liquid_syntax.py`
- [x] ~~24B.5 Liquid template dry-run validation~~ DONE

### 24B.6 Per-Agent nh3 Allowlists `[Backend]`
- `SanitizationProfile` frozen dataclass + `PROFILES` dict with 9 profiles in `app/ai/shared.py`:
  - `default`/`scaffolder`/`dark_mode`/`personalisation` — full 46-tag set
  - `content` — 11 inline/text tags only (no tables, no structural)
  - `accessibility` — full + 18 extra ARIA attributes + `tabindex`
  - `outlook_fixer` — full + VML block extraction/restoration
  - `code_reviewer` — empty tags (catches any HTML leakage from JSON agent)
  - `innovation` — full + form/input/button/select/textarea/label tags
- `sanitize_html_xss(html, profile="default")` — profile-aware sanitization
- VML block extraction (`_extract_vml_blocks`/`_restore_vml_blocks`) for scaffolder, dark_mode, default, personalisation, and outlook_fixer profiles
- `BaseAgentService.sanitization_profile` class attribute wired into `_post_process()`
- All 7 agent services set their profile: scaffolder, dark_mode, content, accessibility, personalisation, outlook_fixer, code_reviewer
- 11 tests in `app/ai/tests/test_sanitization_profiles.py`
- [x] ~~24B.6 Per-agent nh3 allowlists~~ DONE

### 24B.7 Tests & Integration `[Full-Stack]`
- `app/tests/test_24b_integration.py` — 9 cross-cutting integration tests:
  - Engine-aware QA (flexbox reports Word engine risk)
  - Tiered assembly + Gmail emulator integration
  - Per-agent sanitization pipeline (content strips tables, scaffolder preserves, innovation allows forms, outlook preserves VML)
  - Liquid check fires on templates, clean HTML passes
- CLAUDE.md updated: 13 checks, engine taxonomy, per-agent sanitization, emulators, progressive enhancement
- 64 new tests total across all subtasks, 3511 total backend tests passing
- Golden cases 7/7 passing (no regression)
- `make check` all green
- [x] ~~24B.7 Tests & integration~~ DONE

---

## Phase 24.7 — Frontend Builder Integration & Workspace `[Frontend]`

### 24.7 Frontend Builder Integration & Workspace
- Workspace split-view with code editor ↔ visual builder bidirectional sync
- Builder toolbar with device preview, QA run, AI suggest, copy/download/push actions
- Synced sections from code editor render as draggable builder sections
- Component palette drag-and-drop with version HTML fetch and cache (50-entry LRU)
- Keyboard shortcuts: Ctrl+Z/Y undo/redo, Delete remove section, Ctrl+D duplicate, Ctrl+Arrow reorder, Escape deselect
- Property panel integration with design system token overrides
- Builder onboarding overlay for first-time users
- [x] ~~24.7 Frontend builder integration & workspace~~ DONE

---

## Phase 24.8 — Tests & Documentation `[Full-Stack]`

### 24.8 Tests & Documentation
- **Backend tests** (25 new, 76 total streaming tests):
  - `test_manager.py` +6 tests: disconnect nonexistent, broadcast empty room, send to unknown user, multi-room limit, active rooms count, color wrap
  - `test_routes.py` +5 tests: viewer ack, unknown JSON type, expired token, awareness relay, invalid JSON parse error
  - `test_document_store.py` +5 tests: concurrent updates, time-based compaction, corrupted state recovery, unloaded state vector, empty SV peer update
  - `test_sync_handler.py` +4 tests: step2 broadcast, step2 rejected, single byte ignored, unknown sync subtype
  - `test_websocket_integration.py` — 7 new cross-module tests (CRDT init, sync step1, viewer sync, viewer update rejected, room cleanup eviction, passthrough mode, pong handling)
  - `test_crdt_integration.py` — 8 new end-to-end tests (full sync flow, concurrent edits, compaction preservation, sync after compaction, document growth, evict/reload, init idempotent, cleanup idempotent)
- **Frontend tests** (78 new, 187 total frontend tests):
  - `builder-canvas.test.tsx` — 15 tests (empty state, section rendering, selection, deselection, toolbar actions, keyboard nav, aria attributes)
  - `property-panel.test.tsx` — 12 tests (header, tabs, close, Escape, custom props)
  - `collaboration.test.tsx` — 21 tests (PresencePanel: 8, CollaborationBanner: 7, ConflictResolver: 6)
  - `use-builder.test.ts` — 20 tests (all reducer actions, undo/redo, history, edge cases)
  - `use-presence.test.ts` — 10 tests (collaborators, follow/unfollow, cursor, activity, cleanup)
- **ADR-011** appended to `docs/ARCHITECTURE.md` — Real-Time Collaboration & Visual Builder architecture
- 3562 backend tests passing, 187 frontend tests passing
- `make check-fe` all green, `make lint` all green, `make types` no new errors
- [x] ~~24.8 Tests & documentation~~ DONE

---

## Phase 24.9 — AI-Powered HTML Import & Section Annotation `[Full-Stack]`

### 24.9 AI-Powered HTML Import & Section Annotation
- **Import Annotator Agent** (`app/ai/agents/import_annotator/`):
  - `schemas.py` — `AnnotationDecision` + `ImportAnnotationResult` frozen dataclasses
  - `exceptions.py` — `ImportAnnotationError(AppError)` with 422 status
  - `prompt.py` — System prompt builder with L3 skill detection (table layouts, div layouts, ESP tokens, column patterns)
  - `service.py` — `ImportAnnotatorService(BaseAgentService)` with `annotate()`, JSON structured output parsing, lxml CSS selector annotation with selector validation
  - `SKILL.md` — L1+L2 progressive disclosure skill file
  - `skills/` — 4 L3 skill files: `table_layouts.md`, `div_layouts.md`, `esp_tokens.md`, `column_patterns.md`
- **Eval suite** (`app/ai/agents/import_annotator/evals/`):
  - `synthetic_data_import.py` — 15 test cases (table, div, hybrid, 2/3/4-col, deeply nested SFMC, Liquid/AMPscript/Handlebars/MSO, minimal, complex 10+ section, already-annotated)
  - `judges/import_judge.py` — 5-criteria judge (section_boundary_accuracy, annotation_completeness, html_preservation, esp_token_integrity, column_detection)
  - Registered in `JUDGE_REGISTRY` (11 judges total)
- **API route** — `POST /api/v1/email/import-annotate` with `require_role("developer")` auth + `10/minute` rate limit
- **Schemas** — `ImportAnnotateRequest` (html + esp_platform), `ImportAnnotateResponse` (annotated_html + sections + warnings)
- **Sanitization profile** — `import_annotator` profile with `data-section-id/component-name/section-layout` allowed + VML extraction
- **Error sanitizer** — `ImportAnnotationError` registered in safe messages + passthrough types
- **Connector integration** — `ConnectorService.import_and_annotate()` method for ESP template import + annotation
- **Frontend**:
  - `annotation-utils.ts` — `mergeSections()`, `splitSection()`, `unwrapSection()`, `renameSection()` DOM manipulation helpers
  - `import-dialog.tsx` — Import modal with HTML paste/upload, ESP platform selector, progress states, section preview
  - `section-refinement-toolbar.tsx` — Merge/Split/Unwrap/Rename toolbar for section editing
  - `visual-builder-panel.tsx` — Import HTML button + dialog integration
  - `section-markers.ts` — Added `data-section-layout` to `stripAnnotations()`
- **Tests**: 18 unit tests (service, parsing, annotations, ESP token preservation, fallback, skill detection, schemas), all passing
- **Security**: CSS selector validation (length + safe chars), generic error messages (no internal leaks), input size validation (2MB)
- [x] ~~24.9 AI-powered HTML import & section annotation~~ DONE

---

## Phase 25 — Platform Ecosystem & Advanced Integrations (partial)

### 25.1 Plugin Architecture — Manifest, Discovery & Registry `[Backend]` — DONE
- `app/plugins/` — manifest schema (6 types, 7 permissions, semver), YAML/JSON discovery, dynamic import loader with entry point blocklist, `HubPluginAPI` sandboxed registration, `PluginRegistry` singleton with QA check conflict detection
- Admin endpoints: `GET/POST/DELETE /api/v1/plugins` with `require_role("admin")` + rate limiting
- QA engine integration: plugin checks run after core checks with error isolation
- Sample plugin: `plugins/sample-qa-check/`
- Config: `PLUGINS__ENABLED=false`; 50 tests
- [x] ~~25.1 Plugin architecture — manifest, discovery & registry~~ DONE

### 25.2 Plugin Sandboxed Execution & Lifecycle `[Backend]` — DONE
- `sandbox.py` — `PluginSandbox` with `asyncio.wait_for` timeout, sync/async support, `PluginHealth` dataclass, `PluginExecutionContext` with scoped logger
- `lifecycle.py` — `PluginLifecycleManager` with startup/shutdown/restart hooks, periodic health monitoring, auto-disable after N failures
- 3 new admin endpoints: health summary, per-plugin health, restart
- QA engine plugin checks wrapped in sandbox with 30s timeout
- Config: `PLUGINS__DEFAULT_TIMEOUT_S`, `PLUGINS__HEALTH_CHECK_INTERVAL_S`, `PLUGINS__MAX_CONSECUTIVE_FAILURES`
- Lifecycle manager wired into app startup/shutdown; 27 new tests (77 total plugin tests)
- [x] ~~25.2 Plugin sandboxed execution & lifecycle~~ DONE

### 25.3 Tolgee Multilingual Campaign Support `[Backend]` — DONE
- `app/connectors/tolgee/` — `TolgeeClient` (httpx + resilient_request), `TranslationKeyExtractor` (HTMLParser, ICU-aware), `LocaleEmailBuilder` (RTL/LTR, Maizzle sidecar), `TolgeeService` with BOLA + encrypted PAT
- 5 endpoints at `/api/v1/connectors/tolgee/` (connect, sync-keys, pull, build-locales, languages)
- Config: `TOLGEE__ENABLED=false`; BCP-47 validation; HTML injection prevention; 43 tests
- [x] ~~25.3 Tolgee multilingual campaign support~~ DONE

### 25.4 Tolgee Frontend & Per-Locale Maizzle Builds `[Frontend]` — DONE
- 5 components: `TranslationPanel`, `LocalePreview`, `LocaleQAResults`, `InContextOverlay`, `TolgeeConnectionDialog`
- `hooks/use-tolgee.ts` (6 SWR hooks), `types/tolgee.ts`, demo data with 6 languages
- Demo resolvers for GET + POST endpoints; all iframes sandboxed; PAT masked
- [x] ~~25.4 Tolgee frontend & per-locale Maizzle builds~~ DONE

### 25.5 Kestra Workflow Orchestration `[Backend]` — DONE
- `app/workflows/` — `KestraClient` (shared httpx.AsyncClient), `WorkflowService` (flow CRUD, YAML validation, template sync)
- 6 task wrappers: `BlueprintRunTask`, `QACheckTask`, `ChaosTestTask`, `ESPPushTask`, `LocaleBuildTask`, `ApprovalGateTask`
- 4 YAML flow templates: email-build-and-qa, multilingual-campaign, weekly-newsletter, design-import-pipeline
- 6 HTTP endpoints at `/api/v1/workflows/` with auth + rate limiting; admin-only custom flow creation
- Config: `KESTRA__ENABLED=false`; conditional router registration + startup template sync; 41 tests
- [x] ~~25.5 Kestra workflow orchestration~~ DONE

### 25.6 Penpot Design-to-Email Pipeline `[Backend]` — DONE
- `app/design_sync/penpot/` — `PenpotClient` (async context manager, Penpot v2 RPC API), `PenpotDesignSyncService` implementing `DesignSyncProvider` protocol (5 methods)
- CSS-to-email converter: color palette heuristics, typography detection, table-layout generator with y-position row grouping
- Registered in `SUPPORTED_PROVIDERS` + URL extraction routing
- Config: `DESIGN_SYNC__PENPOT_ENABLED`, `DESIGN_SYNC__PENPOT_BASE_URL`; 24 tests
- [x] ~~25.6 Penpot design-to-email pipeline~~ DONE

### 25.7 Typst QA Report Generator `[Backend]` — DONE
- `app/reporting/` — `TypstRenderer` (subprocess compilation with timeout, temp file management), `ReportBuilder` (data assembly from QA/rendering/blueprint services, image base64 embedding), `ReportingService` (Redis-cached PDF generation with TTL)
- 3 report types: QA report, approval package, regression report + cached retrieval
- 4 endpoints at `/api/v1/reports/` with auth + rate limiting (5/min generate, 20/min retrieve)
- Config: `REPORTING__ENABLED=false`, `REPORTING__TYPST_BINARY`, `REPORTING__CACHE_TTL_H=24`, `REPORTING__COMPILATION_TIMEOUT_S=10`
- Conditional router registration in `app/main.py`; 19 tests
- [x] ~~25.7 Typst QA report generator~~ DONE

### 25.8 Frontend Ecosystem Dashboard `[Frontend]` — DONE
- `cms/apps/web/src/components/ecosystem/` — `EcosystemDashboard` (4 stat cards + 4 quadrant panels with health/flow/connection counts), `PluginManagerPanel` (status filter tabs, health summary badges, admin toggle/restart), `PluginRow` (role-based enable/disable/restart with session auth), `WorkflowPanel` (flow cards with template/scheduled badges, trigger dialog with JSON validation, Gantt timeline execution view, log viewer), `ReportPanel` (session-persisted history table, generate dialog with type-specific fields, PDF preview iframe, download via base64), `PenpotPanel` (connection browser)
- SWR hooks: `use-plugins` (list, health, enable, disable, restart), `use-workflows` (list, status, logs, trigger), `use-reports` (generate QA/approval/regression, download), `use-penpot` (connections)
- Types: `plugins.ts`, `workflows.ts`, `reports.ts`, `ecosystem.ts`
- Route at `/ecosystem` with all-role RBAC, tab navigation
- [x] ~~25.8 Frontend ecosystem dashboard~~ DONE

### 25.9 Tests & Documentation `[Full-Stack]` — DONE
- 248 tests across Phase 25 modules (77 plugin + 43 Tolgee + 41 workflow + 24 Penpot + 20 reporting + 43 frontend ecosystem)
- Frontend tests: `ecosystem-dashboard.test.tsx` (10 tests), `plugin-manager.test.tsx` (12 tests), `workflow-panel.test.tsx` (11 tests), `report-panel.test.tsx` (10 tests)
- Sample plugin fixture: `app/plugins/tests/fixtures/sample_qa_plugin/` with `plugin.yaml` manifest + `check.py` QA check module using proper `QACheckResult`/`QACheckConfig` types
- ADR-012: Platform Ecosystem Architecture in `docs/ARCHITECTURE.md` — feature-flagged vertical slices, protocol compliance, client isolation, security boundaries, unified dashboard
- [x] ~~25.9 Tests & documentation~~ DONE

### 25.12 Template-to-Eval Pipeline `[Backend]` — DONE
- `app/ai/agents/evals/template_eval_generator.py` — `TemplateEvalGenerator` producing 5 deterministic eval cases per uploaded template (selection positive/negative, slot fill, assembly golden, QA passthrough), zero LLM calls
- `app/ai/agents/evals/template_eval_schemas.py` — Pydantic schemas (`EvalCaseType` StrEnum, `TemplateEvalCase`, `TemplateEvalCaseSet`, `TemplateEvalSummary`)
- `app/ai/agents/evals/template_eval_routes.py` — 3 REST endpoints at `/api/v1/evals/templates` (GET list, GET by template, DELETE) with `require_role("developer")`/`require_role("admin")` + rate limiting
- Per-template JSON case storage in `data/uploaded_golden/` directory with path traversal validation (`_validate_template_name`)
- `golden_cases.py` extended with `load_uploaded_golden_cases()` merging uploaded assembly cases into `run_golden_cases()`
- `runner.py` extended with `--include-uploaded` flag merging uploaded selection cases into scaffolder eval runs
- `service.py` replaced old `EvalGenerator` with `TemplateEvalGenerator` — upload confirm auto-generates 5 eval cases
- Routes registered behind `TEMPLATES__UPLOAD_ENABLED` feature flag; 33 tests (14 generator + 9 golden cases + 10 service)
- [x] ~~25.12 Template-to-eval pipeline~~ DONE

### 25.14 Multi-Variant Campaign Assembly `[Backend]` — DONE
- `app/ai/agents/scaffolder/variant_schemas.py` — 6 frozen dataclasses (`VariantPlan`, `VariantResult`, `SlotDifference`, `ComparisonMatrix`, `CampaignVariantSet`) + `StrategyName` Literal type with 6 strategies (urgency_driven, benefit_focused, social_proof, curiosity_gap, personalization_heavy, minimal)
- `app/ai/agents/scaffolder/variant_generator.py` — `select_strategies()` (LLM picks best N for brief), `build_strategy_prompt_modifier()` (content pass steering), `build_comparison_matrix()` (slot-level diff detection)
- `app/ai/agents/scaffolder/pipeline.py` — `execute_variants()` method: shared layout+design passes, parallel content passes with strategy modifiers, parallel assembly+QA, comparison matrix generation
- `app/ai/agents/scaffolder/variant_routes.py` — `POST /api/v1/agents/scaffolder/generate-variants` with `require_role("admin", "developer")` + `@limiter.limit("3/hour")`
- `app/ai/agents/scaffolder/schemas.py` — `VariantRequest` (brief, variant_count 2-5, brand_config), `VariantSetResponse`, `ComparisonMatrixResponse`
- `app/ai/agents/scaffolder/service.py` — `generate_variants()` with feature flag gate + configurable `max_variants` enforcement
- `app/core/config.py` — `VariantsConfig(enabled, max_variants, rate_limit_per_hour)` + `settings.variants`
- Config: `VARIANTS__ENABLED=false`, `VARIANTS__MAX_VARIANTS=5`, `VARIANTS__RATE_LIMIT_PER_HOUR=3`
- Conditional router registration in `app/main.py`; 13 tests in `test_variant_generator.py`
- [x] ~~25.14 Multi-variant campaign assembly~~ **DONE**

---

## Phase 27 — Email Client Rendering Fidelity & Pre-Send Testing

### 27.1 Expand Email Client Emulators `[Backend]` — DONE
- Extended `EmailClientEmulator` chain-of-rules system from 2 emulators (Gmail, Outlook.com) to 8 clients / 14 profiles
- New emulators: Yahoo Mail (class rewriting), Samsung Mail (dark mode), Apple Mail, Thunderbird, Outlook desktop (Word CSS stripping), Android Gmail, Outlook.com dark mode
- Each rule publishes `confidence_impact` used by scoring in 27.2
- [x] ~~27.1 Expand email client emulators~~ DONE

### 27.2 Rendering Confidence Scoring `[Backend]` — DONE
- 4-signal confidence scorer combining emulator rule coverage, layout complexity, calibration history, and CSS feature support
- `GET /api/v1/rendering/confidence/{client_id}` endpoint
- Config: `RENDERING__CONFIDENCE_ENABLED`
- [x] ~~27.2 Rendering confidence scoring~~ DONE

### 27.3 Pre-Send Rendering Gate `[Backend + Frontend]` — DONE
- `app/rendering/gate.py` — `RenderingSendGate` with `evaluate()` returning `GateResult` (per-client confidence vs tiered thresholds, blocking reasons, remediation suggestions)
- `app/rendering/gate_config.py` — per-project config with 3 gate modes (enforce/warn/skip), 3-tier thresholds (85%/70%/60%)
- Frontend: `GatePanel` (traffic-light summary), `GateClientRow` (per-client confidence bar with threshold line), `GateSummaryBadge`
- Wired into export dialog + push-to-ESP dialog; admin override with audit logging
- Alembic migration: `rendering_gate_config` JSON column on `projects`
- [x] ~~27.3 Pre-send rendering gate~~ DONE

### 27.4 Emulator Calibration Loop `[Backend]` — DONE
- `EmulatorCalibrator` comparing local screenshots against Litmus/EoA ground truth via ODiff
- EMA accuracy tracking (alpha=0.3), regression detection (>10% drop), budget cap enforcement
- `CalibrationSampler` selecting diverse HTML samples for calibration runs
- Config: `RENDERING__CALIBRATION__ENABLED`
- [x] ~~27.4 Emulator calibration loop~~ DONE

### 27.5 Headless Email Client Sandbox `[Backend]` — DONE
- SMTP-based Mailpit capture pipeline: send email via SMTP, capture rendered DOM, compare with `DOMDiff`
- `SandboxProfile` registry for real client environments
- Playwright Roundcube integration for webmail DOM extraction
- Sandbox results weighted at 0.5x in confidence scoring
- Config: `RENDERING__SANDBOX__ENABLED`
- [x] ~~27.5 Headless email client sandbox~~ DONE

### 27.6 Frontend Rendering Dashboard & Tests `[Frontend + Full-Stack]` — DONE
- `cms/apps/web/src/components/rendering/rendering-dashboard.tsx` — preview grid (14 client profiles, 4-col responsive), confidence summary bar (weighted by market share), gate status panel, calibration health panel (sparkline trends, recalibrate buttons)
- `cms/apps/web/src/components/rendering/confidence-bar.tsx` — reusable component extracted for shared use
- `cms/apps/web/src/hooks/use-rendering-dashboard.ts` — SWR hooks for previews, gate evaluation, calibration summary/history
- 27 frontend tests across 3 test files; 90+ backend tests across Phase 27 modules
- [x] ~~27.6 Frontend rendering dashboard & tests~~ DONE

---

## Phase 28 — Export Quality Gates & Approval Workflow

### 28.1 QA Enforcement in Export Flow `[Backend]` — DONE
- `app/connectors/qa_gate.py` — `ExportQAGate` running 14 QA checks with per-project blocking/warning/ignored classification
- `app/connectors/qa_gate_config.py` — `ExportQAConfig` (enforce/warn/skip modes, configurable blocking checks list)
- Pre-check endpoint: `POST /api/v1/connectors/export/pre-check` returning combined QA + rendering gate results
- Export pipeline: QA gate → rendering gate → ESP provider, with `skip_qa_gate` admin override + audit
- Frontend: export-dialog.tsx and push-to-esp-dialog.tsx updated with QA failure/warning sections alongside rendering confidence
- `cms/apps/web/src/hooks/use-export-pre-check.ts` — combined pre-check SWR hook
- Alembic migration: `export_qa_config` JSON column on `projects`; 15+ backend tests, 5+ frontend tests
- [x] ~~28.1 QA enforcement in export flow~~ DONE

### 28.2 Approval Workflow → Export Integration `[Backend]` — DONE
- `app/connectors/approval_gate.py` — `ExportApprovalGate` checking `ApprovalRequest` status for build, third gate in export pipeline (QA → rendering → approval → ESP)
- Per-project `require_approval_for_export` toggle, `ApprovalRequiredError` on unapproved builds
- `app/approval/service.py` extended with `get_approval_for_build()` and `is_approved()` methods
- Pre-check endpoint returns approval status alongside QA and rendering results; `skip_approval` admin override; 12+ tests
- [x] ~~28.2 Approval workflow → export integration~~ DONE

### 28.3 Approval Frontend UI `[Frontend]` — DONE
- `cms/apps/web/src/components/approvals/` — `approval-request-dialog.tsx` (submit for review with QA summary + note), `approval-gate-panel.tsx` (reviewer decision panel with preview/QA/rendering, approve/revise/reject actions), feedback thread, audit timeline, status badge, version compare
- `cms/apps/web/src/hooks/use-approvals.ts` — 8 SWR hooks (list, detail, feedback, audit, create, decide, add feedback, useApprovalStatus)
- `cms/apps/web/src/types/approval.ts` — ApprovalStatus, ApprovalRequest, ApprovalDecision, Feedback, AuditEntry types
- Integrated into workspace page (submit button), export dialog (gate panel), project settings (require approval toggle)
- List page `/approvals`, detail page `/approvals/[id]`; 8+ review panel tests, 5+ hook tests
- [x] ~~28.3 Approval frontend UI~~ DONE

---

## Phase 29 — Design Import Enhancements

### 29.1 Brief-Only Template Creation `[Backend + Frontend]` — DONE
- Brief-only template creation path — allows users to create templates from a text brief without requiring a live Figma/Penpot design file connection
- [x] ~~29.1 Brief-only template creation~~ DONE

### 29.2 Penpot CSS-to-Email Converter Integration `[Backend]` — DONE
- `app/design_sync/penpot/converter_service.py` — `PenpotConverterService.convert()` walking design tree, producing table-based email HTML with inline styles and MSO conditionals
- Enhanced `app/design_sync/penpot/converter.py` — `node_to_email_html()` with COMPONENT/INSTANCE handling, auto-layout→table conversion, background/border/padding extraction; `_group_into_rows()` with overlap handling, hero image detection, CTA button detection
- `app/design_sync/import_service.py` — Penpot imports pass initial HTML to Scaffolder as `initial_html` for enhancement (vs generating from brief alone)
- Config: `DESIGN_SYNC__PENPOT_CONVERTER_ENABLED`; 15+ integration tests in `app/design_sync/penpot/tests/test_converter_integration.py`
- [x] ~~29.2 Penpot CSS-to-email converter integration~~ DONE

---

## Phase 30 — End-to-End Testing & CI Quality

### 30.1 Playwright E2E User Journey Suite `[Frontend + Full-Stack]` — DONE
- 9 spec files in `cms/apps/web/e2e/`: auth (3 tests), dashboard (3), workspace (5), builder (5), export (5), approval (4), design-sync (3), collaboration (2), ecosystem (2) — 32+ test cases total
- Shared fixtures: `cms/apps/web/e2e/fixtures/` (auth, project, template, mock-esp)
- `cms/apps/web/e2e/global-setup.ts` + `global-teardown.ts` for API-based test data seeding/cleanup
- `cms/apps/web/playwright.config.ts` — screenshot-on-failure, 30s timeout, HTML report
- Makefile: `make e2e` (headless), `make e2e-ui` (interactive), `make e2e-report` (open HTML report)
- [x] ~~30.1 Playwright e2e user journey suite~~ DONE

### 30.2 Visual Regression Testing in CI `[Full-Stack + CI]` — DONE
- `app/rendering/tests/visual_regression/` — `BaselineGenerator` (5 golden templates x 14 profiles), `VisualRegressionRunner` (ODiff comparison, 0.5% pixel diff threshold)
- Baselines committed in `app/rendering/tests/visual_regression/baselines/` with manifest.json
- `.gitattributes` for PNG handling
- Makefile: `make rendering-baselines` (regenerate), `make rendering-regression` (CI-safe comparison)
- Tests marked `@pytest.mark.visual_regression` for selective execution; 5+ regression tests
- [x] ~~30.2 Visual regression testing in CI~~ DONE

### 30.3 Multi-Browser & CLI E2E Coverage `[Frontend + CI]` — DONE
- `cms/apps/web/playwright.config.ts` extended with Firefox and WebKit projects
- Browser-specific test selection: builder/workspace/auth on all 3 browsers, export/approval Chromium-only, collaboration Chromium+Firefox
- Cross-browser hardening: Firefox DnD workarounds, WebKit contentEditable waits
- `cms/apps/web/e2e/CLI_E2E_TESTING.md` — documents CLI-based exploratory e2e (13 journeys via agent-browser)
- Makefile: `make e2e-all-browsers` (full Chromium+Firefox+WebKit matrix), `make e2e-firefox`, `make e2e-webkit`
- CI: PR checks = Chromium-only, nightly = full matrix, release gate = full matrix + manual CLI review
- [x] ~~30.3 Multi-browser & CLI e2e coverage~~ DONE

---

## Phase 31 — HTML Import Fidelity & Preview Accuracy

### 31.1 Maizzle Passthrough for Pre-Compiled HTML `[Backend + Sidecar]` — DONE
- `services/maizzle-builder/precompiled-detect.js` — `isPreCompiledEmail(source)` with 4 heuristics (no Maizzle syntax, inline styles ≥3, table layout ≥2, document shell)
- `/build` and `/preview` handlers skip `render()` for pre-compiled HTML, return `passthrough: true`
- CSS optimization (PostCSS ontology plugin + Lightning CSS) still runs on passthrough
- `app/email_engine/schemas.py` — `passthrough: bool` on `PreviewResponse`/`BuildResponse`
- [x] ~~31.1 Maizzle passthrough for pre-compiled HTML~~ DONE

### 31.2 Inline CSS Compilation via Ontology Pipeline `[Backend + Sidecar]` — DONE
- Layer A (Sidecar): `optimizeInlineStyles()` wraps inline `style=""` in synthetic PostCSS selectors for proper CSS parsing; shorthand expansion (`font`, `padding`, `margin`, `background`, `border`); media query responsive token extraction
- Layer B (Python): `EmailCSSCompiler._process_css_block()` replaced regex `line.split(":")` with Lightning CSS `process_stylesheet()`
- Layer C: `DesignSystemMapper` maps imported font/color/spacing tokens against project design system; `TokenDiff` preview in upload API response
- [x] ~~31.2 Inline CSS compilation via ontology pipeline~~ DONE

### 31.3 Preserve Wrapper Table Metadata in Section Analyzer `[Backend]` — DONE
- `app/templates/upload/analyzer.py` — `WrapperInfo` dataclass (tag, width, align, style, bgcolor, cellpadding, cellspacing, border, role, inner_td_style, mso_wrapper)
- `TemplateAnalyzer._detect_wrapper()` extracts outer centering table metadata before section unwrapping
- `AnalysisResult.wrapper: WrapperInfo | None` — None when no single-wrapper pattern detected
- [x] ~~31.3 Preserve wrapper table metadata in section analyzer~~ DONE

### 31.4 Wrapper Reconstruction on Template Assembly `[Backend]` — DONE
- `app/templates/upload/wrapper_utils.py` — `detect_centering()` and `inject_centering_wrapper()` with MSO ghost table support
- `TemplateBuilder.build()` calls `ensure_wrapper()` when `WrapperInfo` present; stores `wrapper_metadata` dict on `GoldenTemplate`
- Idempotent — no double-wrapping on already-centered HTML
- [x] ~~31.4 Wrapper reconstruction on template assembly~~ DONE

### 31.5 Preview Iframe Dark Mode Text Safety & Sandbox Fix `[Frontend]` — DONE
- `cms/apps/web/src/lib/dark-mode-contrast.ts` — `ensureDarkModeContrast()` replaces dark inline colors (luminance < 0.3) with `#e5e5e5 !important`
- `cms/apps/web/src/lib/color-utils.ts` — `relativeLuminance()` WCAG 2.1 formula, `isDarkColor()` threshold check
- `preview-iframe.tsx` — `sandbox="allow-same-origin"` (blocks scripts, allows image loading); dark mode contrast injection before srcdoc write
- [x] ~~31.5 Preview iframe dark mode text safety & sandbox fix~~ DONE

### 31.6 Enriched Typography & Spacing Token Pipeline `[Backend]` — DONE
- `TokenInfo` extended with `font_weights`, `line_heights`, `letter_spacings`, `color_roles` buckets
- `TokenExtractor.extract()` resolves enriched typography roles from multi-occurrence voting
- `TemplateAssembler` — 4 new replacement steps: `_apply_font_size_replacement()`, `_apply_line_height_replacement()`, `_apply_font_weight_replacement()`, `_apply_spacing_replacement()`
- `DesignNode` extended with `font_family`, `font_size`, `font_weight`, `line_height`, `item_spacing`, `padding_*` from Figma auto-layout
- [x] ~~31.6 Enriched typography & spacing token pipeline~~ DONE

### 31.7 Image Asset Import & Dimension Preservation `[Backend]` — DONE
- `app/templates/upload/image_importer.py` — `ImageImporter` with HTTP download, content-type validation, dimension detection (Pillow), `<img>` src rewriting to hub-hosted URLs
- `ImportedImage` dataclass with original_url, hub_url, display/intrinsic dimensions, alt, file_size
- `TemplateUploadService.upload_and_analyze()` — image import step between CSS optimization and analysis
- `ImagePreview` schema for API response; `AnalysisPreview.images` list
- 11 tests covering download, dimension detection, rewriting, error handling
- [x] ~~31.7 Image asset import & dimension preservation~~ DONE

### 31.8 Tests & Integration Verification `[Full-Stack]` — DONE
- `TokenPreview` schema fix — added `font_weights`, `line_heights`, `letter_spacings` fields; `_serialize_analysis()` updated
- `test_analyzer_wrapper.py` — 6 tests (center tag, inner td style, multi-table no wrapper)
- `test_token_extractor_enriched.py` — 8 tests (font weights, line heights, letter spacings, color roles, backward compat)
- `test_template_builder_wrapper.py` — 4 tests (centering, metadata storage, MSO wrapper, no-wrapper)
- `passthrough.test.js` — 2 extended tests (newsletter detection, all 13 golden templates sweep)
- `preview-iframe.test.tsx` — 4 tests (sandbox attribute, compile prompt, loading spinner)
- `import-fidelity.spec.ts` — 3 E2E tests (paste+preview, sandbox security, dark mode toggle)
- `pre-compiled-email.html` — E2E fixture from `promotional_hero` golden template
- [x] ~~31.8 Tests & integration verification~~ DONE

---
## Phase 33 — Design Token Pipeline Overhaul (Figma → Email HTML)

> **Continues Phase 31.5–31.6 design sync work.** Phase 31.6 enriched `layout_analyzer.py` with typography data (`TextBlock.font_family/weight/line_height/letter_spacing`, `EmailSection.buttons/column_layout/item_spacing`) and added `spacing_bridge.py` for token extraction — but the converter (`converter.py`, `converter_service.py`) never consumes this data. Phase 33 refactors the existing converter to use the rich layout analysis already available, improves HTML output quality (semantic elements, MSO fallbacks, dark mode, proportional widths), and adds a validation layer. No new pipeline — same files, same entry points, same data flow. The converter just gets smarter.
>
> The current system silently drops opacity, gradients, spacing, line-height, and dark mode tokens; misidentifies colors via fragile heuristics; ignores auto-layout direction; produces broken multi-column layouts; and doesn't support Figma's modern Variables API. Knowledge from agent skill files (`table_layouts.md`, `mso_bug_fixes.md`, `dark-mode-css.md`, `color_remapping.md`, `cta-buttons.md`, `vml_reference.md`), ontology data (`css_properties.yaml`, `support_matrix.yaml`), and data files (`email_client_fonts.yaml`) is encoded directly into the converter code — not connected at runtime.

> **Dependency note:** Direct continuation of Phase 31.5–31.6. Independent of Phase 32 (Agent Rendering Intelligence). Can be implemented in parallel with Phase 32. However, Phase 33 fixes are *upstream* of Phase 32 — agents receiving better tokens and HTML from this phase will produce better results. Recommended to start Phase 33 first or concurrently.

- [x] ~~33.0 Wire layout analyzer into converter (prerequisite for 33.4–33.9)~~ DONE
- [x] ~~33.1 Figma Variables API + opacity compositing~~ DONE
- [x] ~~33.2 Email-safe token transforms & validation layer~~ DONE
- [x] ~~33.3 Typography pipeline: line-height, letter-spacing, font mapping~~ DONE
- [x] ~~33.4 Spacing token pipeline & auto-layout → table mapping~~ DONE
- [x] ~~33.5 Multi-column layout & proportional width calculation~~ DONE
- [x] ~~33.5b Client-aware conversion — ontology wire-up (prerequisite for 33.7)~~ DONE
- [x] ~~33.6 Semantic HTML generation (headings, paragraphs, buttons)~~ DONE
- [x] ~~33.7 Dark mode token extraction & gradient fallbacks~~ DONE
- [x] ~~33.8 Design context enrichment & Scaffolder integration~~ DONE
- [x] ~~33.9 Builder annotations for visual builder sync~~ DONE
- [x] ~~33.10 Image asset import for design sync pipeline~~ DONE
- [x] ~~33.11 Tests & integration verification~~ DONE

### 33.0 Wire Layout Analyzer into Converter `[Backend]`
**What:** Connect the existing `analyze_layout()` function in `app/design_sync/figma/layout_analyzer.py` to `DesignConverterService.convert()` in `app/design_sync/converter_service.py`. Currently the converter calls `node_to_email_html()` directly on raw `DesignNode` trees, bypassing the layout analyzer entirely. The analyzer already detects column layouts, buttons, heading hierarchy, item spacing, element gaps, and section types — but none of this data reaches the HTML generation step. This subtask bridges the gap so that subsequent subtasks (33.4–33.9) can consume rich `EmailSection` data instead of reimplementing detection logic. Additionally, fix `_build_props_map_from_nodes()` to extract all `DesignNode` fields (currently only `bg_color`), add MSO reset styles to the email skeleton and inline table/image output, and extend `_NodeProps` and `ConversionResult` dataclasses for downstream use.
**Why:** `converter_service.py` line 110 calls `node_to_email_html(frame, ...)` on raw frames. The layout analyzer's `EmailSection` dataclass already carries: `column_layout` (single/two/three/multi), `column_count`, `texts` (with `is_heading`), `images`, `buttons` (with dimensions + text), `spacing_after`, `bg_color`, `padding_*`, `item_spacing`, and `element_gaps`. Without this connection, every Phase 33 subtask must reimplement detection that already exists — e.g., 33.6 describes button detection rules that are identical to `layout_analyzer._walk_for_buttons()`. Additionally, `_build_props_map_from_nodes()` only extracts `bg_color` from `DesignNode` fields, silently discarding `font_family`, `font_size`, `font_weight`, `padding_*`, and `layout_mode` — data that the Penpot path (`_build_props_map`) already handles. The `EMAIL_SKELETON` style block lacks mandatory MSO table resets (`mso-table-lspace:0pt;mso-table-rspace:0pt`), image resets (`-ms-interpolation-mode:bicubic`), and the inline table/image styles don't include them either — Gmail clips emails at 102KB and strips `<style>` blocks, so inline styles must be self-sufficient.
**Knowledge sources (encode as code, do not connect at runtime):**
- `app/ai/agents/scaffolder/skills/email_structure.md` — document skeleton requirements: VML/Office XML namespace (`xmlns:v`, `xmlns:o`), DPI fix (`o:PixelsPerInch=96`), required meta tags (`format-detection`, `x-apple-disable-message-reformatting`, `color-scheme`, `supported-color-schemes`, `-webkit-text-size-adjust:100%`, `word-spacing:normal`). Verify `EMAIL_SKELETON` in `converter_service.py` includes all elements — currently missing `<meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">` and `<meta name="x-apple-disable-message-reformatting">`
- `app/ai/agents/outlook_fixer/skills/mso_bug_fixes.md` — 15 Outlook bug patterns. MSO reset styles that must be present: (1) every `<table>`: `border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt;` — prevents 1px white lines between cells, (2) every `<img>`: `-ms-interpolation-mode:bicubic;display:block;border:0;outline:none;text-decoration:none;` — prevents image spacing and DPI scaling artifacts, (3) `<body>`: `margin:0;padding:0;` reset. These must be both in the `<style>` block AND inline on each element (belt-and-suspenders for Gmail which strips `<style>` in clipped emails >102KB)
- `app/knowledge/data/seeds/best_practices/table-based-layout.md` — structural wrapper pattern: 100% outer table for body background + fixed-width (600px) content table with `align="center"` + `role="presentation"` on ALL layout tables. `cellpadding="0" cellspacing="0" border="0"` on every table (already present in `node_to_email_html()`). Avoid nesting tables deeper than 6 levels (Outlook rendering degrades). Current skeleton has a single-level wrapper — verify the converter doesn't produce nesting >6 on deeply nested Figma trees
- `app/knowledge/data/seeds/css_support/box-model.md` — padding works ONLY on `<td>` cells (Outlook ignores on `<p>`/`<div>`/`<a>`). Never use `margin: 0 auto` for centering — use `align="center"` HTML attribute. Width must be set as both HTML attribute (`width="600"`) AND CSS (`style="width:600px"`) for Outlook compatibility. `box-sizing` is ignored by Outlook — always use content-box math. Percentage widths are reliable on `<td>` elements
**Implementation:**
- Update `DesignConverterService.convert()` in `app/design_sync/converter_service.py`:
  - Add import: `from app.design_sync.figma.layout_analyzer import analyze_layout, DesignLayoutDescription, EmailSection`
  - After `frames = self._collect_frames(structure, selected_nodes)`, call layout analysis:
    ```python
    layout = analyze_layout(structure)
    sections_by_node_id: dict[str, EmailSection] = {
        section.node_id: section for section in layout.sections
    }
    ```
  - Build button ID lookup for O(1) hit testing during recursion:
    ```python
    button_node_ids: set[str] = set()
    for section in layout.sections:
        for btn in section.buttons:
            button_node_ids.add(btn.node_id)
    ```
  - Build text ID lookup for heading detection during recursion:
    ```python
    text_meta: dict[str, TextBlock] = {}
    for section in layout.sections:
        for tb in section.texts:
            text_meta[tb.node_id] = tb
    ```
  - Pass all lookups to `node_to_email_html()`:
    ```python
    section_html = node_to_email_html(
        frame,
        indent=1,
        props_map=props_map or None,
        section_map=sections_by_node_id,
        button_ids=button_node_ids,
        text_meta=text_meta,
    )
    ```
  - Use `layout.overall_width` as container width when available:
    ```python
    container_width = int(layout.overall_width) if layout.overall_width else 600
    ```
    Replace hardcoded `width="600"` and `max-width:600px` in `EMAIL_SKELETON.format()` with `container_width`. Update MSO wrapper table width to match.
  - Add inter-section spacer rows using `section.spacing_after`:
    ```python
    for idx, frame in enumerate(frames):
        section = sections_by_node_id.get(frame.id)
        section_html = node_to_email_html(frame, ...)
        section_parts.append(f'<tr><td>\n{section_html}\n</td></tr>')
        if section and section.spacing_after and section.spacing_after > 0:
            spacer_h = int(section.spacing_after)
            section_parts.append(
                f'<tr><td style="height:{spacer_h}px;font-size:1px;'
                f'line-height:1px;mso-line-height-rule:exactly;" '
                f'aria-hidden="true">&nbsp;</td></tr>'
            )
    ```
  - Store layout on result:
    ```python
    return ConversionResult(
        html=result_html,
        sections_count=len(frames),
        warnings=warnings,
        layout=layout,
    )
    ```
- Update `node_to_email_html()` signature in `app/design_sync/converter.py`:
  - Add new optional parameters:
    ```python
    def node_to_email_html(
        node: DesignNode,
        *,
        indent: int = 0,
        props_map: dict[str, _NodeProps] | None = None,
        parent_bg: str | None = None,
        parent_font: str | None = None,
        section_map: dict[str, EmailSection] | None = None,
        button_ids: set[str] | None = None,
        text_meta: dict[str, TextBlock] | None = None,
        current_section: EmailSection | None = None,
        body_font_size: float = 16.0,
    ) -> str:
    ```
  - At the top of FRAME/GROUP/COMPONENT/INSTANCE handling, look up section data:
    ```python
    section = current_section
    if section_map and node.id in section_map:
        section = section_map[node.id]
    ```
  - Thread `current_section=section`, `button_ids`, `text_meta`, `section_map`, and `body_font_size` through all recursive calls to `node_to_email_html()` for child nodes
  - When `section` is available:
    - Use `section.column_layout` and `section.column_count` to decide row grouping strategy (consumed by 33.5 — for now, store on context, 33.5 will use it)
    - Use `section.item_spacing` to insert spacer `<tr>` rows or cell padding between children (consumed by 33.4)
    - Check `button_ids` for button detection (consumed by 33.6 — for now, pass through)
    - Check `text_meta` for heading classification (consumed by 33.6 — for now, pass through)
- Fix `_build_props_map_from_nodes()` in `app/design_sync/converter_service.py` (lines 169-181):
  - Replace the current `_walk()` that only extracts `bg_color`:
    ```python
    def _build_props_map_from_nodes(self, frames: list[DesignNode]) -> dict[str, _NodeProps]:
        """Build props_map from DesignNode fields (provider-agnostic)."""
        props: dict[str, _NodeProps] = {}

        def _walk(node: DesignNode) -> None:
            has_data = (
                node.fill_color or node.font_family or node.font_size
                or node.font_weight or node.padding_top or node.padding_right
                or node.padding_bottom or node.padding_left or node.layout_mode
                or node.line_height_px or node.letter_spacing_px
            )
            if has_data:
                props[node.id] = _NodeProps(
                    bg_color=node.fill_color,
                    font_family=node.font_family,
                    font_size=node.font_size,
                    font_weight=str(node.font_weight) if node.font_weight else None,
                    padding_top=node.padding_top or 0,
                    padding_right=node.padding_right or 0,
                    padding_bottom=node.padding_bottom or 0,
                    padding_left=node.padding_left or 0,
                    layout_direction=(
                        "row" if node.layout_mode == "HORIZONTAL"
                        else "column" if node.layout_mode == "VERTICAL"
                        else None
                    ),
                    line_height_px=node.line_height_px,
                    letter_spacing_px=node.letter_spacing_px,
                )
            for child in node.children:
                _walk(child)

        for frame in frames:
            _walk(frame)
        return props
    ```
  - This aligns the Figma path with the Penpot path (`_build_props_map`, lines 183-213) which already extracts font, padding, and layout data from raw file objects
- Extend `_NodeProps` dataclass in `app/design_sync/converter.py` (lines 30-44):
  - Add typography fields consumed by 33.3 and 33.6:
    ```python
    @dataclass(frozen=True)
    class _NodeProps:
        """Supplementary visual properties not carried by DesignNode."""
        bg_color: str | None = None
        font_family: str | None = None
        font_size: float | None = None
        font_weight: str | None = None
        padding_top: float = 0
        padding_right: float = 0
        padding_bottom: float = 0
        padding_left: float = 0
        border_color: str | None = None
        border_width: float = 0
        layout_direction: str | None = None  # "row" | "column" | None
        line_height_px: float | None = None  # NEW: explicit line-height in px
        letter_spacing_px: float | None = None  # NEW: letter-spacing in px
    ```
- Extend `ConversionResult` dataclass in `app/design_sync/converter_service.py` (lines 56-61):
  - Add layout field for downstream consumers (33.8 Scaffolder integration, 33.9 builder annotations):
    ```python
    @dataclass(frozen=True)
    class ConversionResult:
        """Result of converting a design tree to email HTML."""
        html: str
        sections_count: int
        warnings: list[str] = field(default_factory=list)
        layout: DesignLayoutDescription | None = None  # NEW: rich layout data
    ```
- Update `EMAIL_SKELETON` in `app/design_sync/converter_service.py` (lines 26-52):
  - Add missing meta tags to `<head>` (before `{style_block}`):
    ```html
    <meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no">
    <meta name="x-apple-disable-message-reformatting">
    ```
  - Expand `{style_block}` generation to include MSO reset styles:
    ```python
    style_block = (
        "<style>\n"
        f"  body {{ font-family: {safe_body_font}; margin: 0; padding: 0; }}\n"
        "  table { border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }\n"
        "  img { -ms-interpolation-mode: bicubic; border: 0; display: block; outline: none; text-decoration: none; }\n"
        "</style>"
    )
    ```
  - Make container width dynamic (replace hardcoded `600`):
    ```python
    result_html = EMAIL_SKELETON.format(
        style_block=style_block,
        bg_color=bg_color,
        text_color=text_color,
        body_font=safe_body_font or "Arial, Helvetica, sans-serif",
        sections=sections_html,
        container_width=container_width,
    )
    ```
    Update `EMAIL_SKELETON` template to use `{container_width}` in place of `600` (3 occurrences: MSO table `width`, CSS `max-width`, and outer table `width` attribute)
- Update `node_to_email_html()` table output in `app/design_sync/converter.py` (lines 301-303):
  - Add MSO reset styles inline on every `<table>` element (belt-and-suspenders for Gmail clipping):
    ```python
    table_style_parts = [
        "border-collapse:collapse",
        "mso-table-lspace:0pt",
        "mso-table-rspace:0pt",
    ]
    if any(v > 0 for v in pad_vals):
        table_style_parts.append(
            f"padding:{int(props.padding_top)}px {int(props.padding_right)}px "
            f"{int(props.padding_bottom)}px {int(props.padding_left)}px"
        )
    style_attr = f' style="{";".join(table_style_parts)}"'
    ```
  - This replaces the current `style_parts` list that only includes padding
- Update `node_to_email_html()` image output in `app/design_sync/converter.py` (lines 246-254):
  - Expand inline image styles (partially present, add missing properties):
    ```python
    return (
        f'{pad}<img src="" alt="{alt}"{node_id_attr}{w}{h}'
        f' style="display:block;border:0;outline:none;text-decoration:none;'
        f'-ms-interpolation-mode:bicubic;width:100%;height:auto;" />'
    )
    ```
  - Currently missing: `outline:none`, `text-decoration:none`, `-ms-interpolation-mode:bicubic`
- Guard against excessive table nesting depth:
  - Add `max_depth: int = 6` parameter to `node_to_email_html()`
  - Track `current_depth` through recursion, increment when entering FRAME/GROUP/COMPONENT/INSTANCE
  - If `current_depth > max_depth`: flatten remaining children as `<tr><td>` without nesting a new `<table>`, log warning `"design_sync.nesting_depth_exceeded"` with node ID
  - This prevents Outlook rendering degradation on deeply nested Figma trees (per `best_practices/table-based-layout.md`)
**Security:** No new input paths. Layout analysis is pure computation on existing `DesignNode` data — no I/O, no external calls. MSO reset styles are static CSS strings. Container width comes from `layout.overall_width` (a `float | None` derived from node dimensions) — clamped to `400 <= width <= 800` before use in `EMAIL_SKELETON.format()` to prevent injection via absurd values. Table nesting depth guard is a safety limit, not a security boundary. No user input reaches the new code paths.
**Verify:** `analyze_layout(structure)` is called during `convert()` and returns valid `DesignLayoutDescription` with correct section count matching frame count. `sections_by_node_id` lookup maps at least one node ID to an `EmailSection` object. `button_node_ids` set contains IDs of all detected buttons. `text_meta` dict maps TEXT node IDs to `TextBlock` objects with `is_heading` set. `node_to_email_html()` accepts new parameters without error — existing callers using keyword args still work (all new params have defaults). `_build_props_map_from_nodes()` populates all `_NodeProps` fields from `DesignNode` — frame with `padding_top=24, font_family="Inter", layout_mode="HORIZONTAL"` → `_NodeProps(padding_top=24, font_family="Inter", layout_direction="row")`. `_NodeProps` has `line_height_px` and `letter_spacing_px` fields. `ConversionResult.layout` is populated with `DesignLayoutDescription`. `EMAIL_SKELETON` contains `<meta name="format-detection">` and `<meta name="x-apple-disable-message-reformatting">`. Style block contains `border-collapse: collapse`, `mso-table-lspace: 0pt`, `-ms-interpolation-mode: bicubic`. All `<table>` elements have `border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt` inline. All `<img>` elements have `display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic` inline. Container width from `layout.overall_width=700` → `width="700"` and `max-width:700px` in output. Container width `None` → falls back to 600. Container width `1200` → clamped to `800`. Inter-section spacer rows present when `spacing_after > 0`, with `mso-line-height-rule:exactly` and `aria-hidden="true"`. Nesting depth >6 → children flattened, warning logged. Existing conversion tests still pass (all changes are additive — new params default to `None`). `make test` passes. `make types` passes.

### 33.1 Figma Variables API + Opacity Compositing `[Backend]`
**What:** Add support for Figma's Variables API (`/v1/files/:key/variables/local` and `/v1/files/:key/variables/published`) as the primary token extraction source, falling back to the legacy Styles API for older files. Implement opacity compositing that flattens fill opacity × layer opacity into final hex values. Fix gradient and multi-fill handling to extract the topmost visible solid fill with a fallback midpoint color for linear gradients. Stop mixing stroke colors into the fill palette.
**Why:** The current pipeline uses only the legacy Styles endpoint (`/v1/files/{key}/styles`). Figma's Variables API — GA since late 2023 — is now the default way designers define tokens. Files using Variables (which is the majority of modern Figma files) extract **zero tokens** from the styles endpoint. Additionally, `_rgba_to_hex()` discards the alpha channel entirely, node-level `opacity` is never read, gradients silently vanish, and stroke colors pollute the palette. A semi-transparent blue overlay on white currently extracts as solid blue; a gradient hero section extracts nothing.
**Implementation:**
- Extend `FigmaDesignSyncService` in `app/design_sync/figma/service.py`:
  - Add `_fetch_variables()` method:
    - Call `GET /v1/files/{file_key}/variables/local` (returns variable collections, modes, values)
    - Call `GET /v1/files/{file_key}/variables/published` (returns published library variables)
    - Handle 403 (Variables API requires paid plan) — graceful fallback to Styles API
    - Parse variable collections into groups: "Primitives", "Semantic", "Component" (by collection name)
    - Extract modes: light/dark/brand variants from collection modes
    - Resolve aliases: `{color.brand.primary}` → walk reference chain to literal value (detect circular refs, max depth 10)
  - Update `sync_tokens_and_structure()` to try Variables API first, fall back to Styles:
    ```
    try: variables = await _fetch_variables(file_ref, access_token)
    except (SyncFailedError, httpx.HTTPStatusError): variables = None
    if variables: colors, typography = _parse_variables(variables)
    else: colors = _parse_colors(file_data, styles_data)  # existing path
    ```
  - Add `_rgba_to_hex_with_opacity()`:
    - Accept `r, g, b, a` (fill) + `node_opacity` (layer) as parameters
    - Compute effective alpha: `fill_alpha * node_opacity`
    - If effective alpha < 1.0, composite against assumed background (white `#FFFFFF` default, configurable):
      `final_r = round(r * eff_alpha + bg_r * (1 - eff_alpha))`
    - Return hex string of composited color
    - Keep existing `_rgba_to_hex()` as fast path for fully opaque colors
  - Fix `_walk_for_colors()`:
    - Read `node.get("opacity", 1.0)` and pass to `_rgba_to_hex_with_opacity()`
    - For nodes with multiple fills: iterate fills top-to-bottom (last in array = topmost), take the first visible (`visible != false`) solid fill
    - For `GRADIENT_LINEAR` fills: extract the two endpoint colors, compute midpoint hex, add with name suffix " (gradient midpoint)"
    - Separate strokes from fills: add strokes to a separate `stroke_colors` list (not mixed into `colors`). Expose `stroke_colors` on `ExtractedTokens` as optional field but don't feed them into `convert_colors_to_palette()`
  - Fix `_parse_node()` fill extraction (lines 560-576):
    - Read node-level `opacity` and composite with fill opacity
    - Iterate fills top-to-bottom instead of breaking on first match
    - Skip fills with `visible: false`
- Update `ExtractedTokens` in `app/design_sync/protocol.py`:
  - Add optional `variables_source: bool = False` field to indicate extraction source (Variables vs Styles)
  - Add optional `modes: dict[str, str] | None = None` to carry mode names (e.g., `{"light": "mode_id_1", "dark": "mode_id_2"}`)
  - Add optional `stroke_colors: list[ExtractedColor] = field(default_factory=list)` to keep strokes separate
- Add `ExtractedVariable` dataclass:
  ```python
  @dataclass(frozen=True)
  class ExtractedVariable:
      name: str
      collection: str
      type: str  # "COLOR", "FLOAT", "STRING", "BOOLEAN"
      values_by_mode: dict[str, Any]  # mode_name → resolved value
      is_alias: bool = False
      alias_path: str | None = None  # e.g., "color/brand/primary"
  ```
**Security:** Figma API calls use existing encrypted PAT from `DesignConnection.access_token`. No new secrets. Variables API response contains design token values only — no PII. Alias resolution has max-depth guard (10) to prevent infinite loops.
**Verify:** Figma file using Variables API → tokens extracted with correct hex values. Semi-transparent fill (opacity 0.5 blue on white) → extracts as `#8080FF` (composited), not `#0000FF`. Gradient fill → midpoint color extracted with "(gradient midpoint)" suffix. Stroke colors → not present in `convert_colors_to_palette()` output. Node with layer opacity 0.5 + fill opacity 0.5 → effective opacity 0.25 applied. File without Variables (legacy) → falls back to Styles path, existing tests pass. `make test` passes. `make types` passes.

### 33.2 Email-Safe Token Transforms & Validation Layer `[Backend]`
**What:** Add a token validation and transformation layer between extraction (33.1) and consumption (converter, Scaffolder, design system). Validate that all extracted tokens meet email-safe requirements: colors are 6-digit hex (no rgba, no CSS custom properties), sizes are in px (no rem/em/%), font families include fallback stacks, and no unresolved aliases remain. Transform non-conforming values to email-safe equivalents. Reject invalid tokens with descriptive errors.
**Why:** Currently there is zero validation between extraction and conversion. An empty font family becomes `", Arial, Helvetica, sans-serif"` in the output. A color extracted as `rgba(0,0,0,0.5)` (if the pipeline were extended) would pass through verbatim, breaking email clients. There's no way to detect that tokens are incomplete before the Scaffolder generates HTML with missing values. A validation layer catches these issues early and ensures every downstream consumer receives clean, email-safe values.
**Implementation:**
- Create `app/design_sync/token_transforms.py`:
  - `validate_and_transform(tokens: ExtractedTokens) -> tuple[ExtractedTokens, list[TokenWarning]]`:
    - Color validation:
      - Verify hex format matches `#[0-9A-Fa-f]{6}` — reject 3-digit shorthand (expand to 6), reject named colors (map `"red"` → `"#FF0000"` via lookup table of CSS named colors)
      - Reject `rgba()`, `hsl()`, `oklch()` format strings — convert to hex via utility
      - Clamp opacity to 0.0-1.0 range
      - Warn on fully transparent colors (opacity < 0.01)
    - Typography validation:
      - Verify `family` is non-empty string — warn and default to `"Arial"` if empty
      - Verify `size` > 0 and < 200 (sanity bounds) — warn on unreasonable sizes
      - Verify `weight` is valid CSS weight string (100-900 or "normal"/"bold") — map numeric strings to nearest valid weight
      - Verify `line_height` > 0 — if unitless ratio (< 5.0), multiply by font size to get px value
      - Convert any `em` values to px using font size as base
    - Spacing validation:
      - Verify `value` > 0 and < 500 (sanity bounds)
      - Verify no negative spacing values
    - Cross-token validation:
      - At least 1 color extracted — warn (not error) if zero
      - At least 1 typography style extracted — warn if zero
      - No duplicate token names within same type
  - `TokenWarning` dataclass: `(level: "info" | "warning" | "error", field: str, message: str, original_value: str | None, fixed_value: str | None)`
  - CSS named color map: 147 CSS named colors → hex (from CSS Color Level 4 spec)
- Integrate into `DesignSyncService.sync_connection()` and `DesignImportService.run_conversion()`:
  - Call `validate_and_transform()` immediately after token extraction
  - Store warnings in `DesignSyncSnapshot.structure_json["token_warnings"]`
  - Log warnings at appropriate levels
  - Surface warnings in API response via `DesignTokensResponse.warnings` field
- Add `warnings: list[str] | None` to `DesignTokensResponse` in `app/design_sync/schemas.py`
**Knowledge sources (encode as code, do not connect at runtime):**
- `ontology/data/css_properties.yaml` (365 properties) — use as the authoritative source for which CSS properties exist and their valid value types. Load at module level. When validating a generated CSS property, check it against the ontology instead of hardcoding safe/unsafe lists
- `ontology/data/support_matrix.yaml` — per-client support flags (25+ email clients). Use to determine which CSS properties are safe to emit for target clients. E.g., `border-radius` is ⚠️ (partial) — emit but add VML fallback; `position` is ❌ — never emit
- `code_reviewer/skills/css_syntax_validation.md` — error patterns and severity levels to implement: empty value (error), missing semicolon (error), unclosed braces (error), invalid property (warning), unitless numeric (warning for non-zero, info for zero). Use these severity classifications in the `TokenWarning` dataclass
- `code_reviewer/skills/css_client_support.md` — vendor prefix rules (all invalid except `-webkit-text-size-adjust`); external resources (`@font-face`/`@import` stripped by Gmail); `!important` guidelines (expected in dark mode, flag if >10 non-dark uses)
- `css_support/colors-backgrounds.md` — Outlook rejects `rgba()`/`hsl()` — always convert to 6-digit hex. Gmail strips `background-image` from inline styles. Use these rules in color validation
**Security:** Pure data validation. No I/O, no user input in transform logic. Named color map is a static dict.
**Verify:** Empty font family → warning + replaced with "Arial". 3-digit hex `#F00` → expanded to `#FF0000`. Named color "red" → `#FF0000`. Unitless line-height `1.5` with font size `16px` → `24px`. Size of `-5` → error warning. Zero colors extracted → warning in response. Existing extraction tests still pass. `make test` passes.

### 33.3 Typography Pipeline: Line-Height, Letter-Spacing, Font Mapping `[Backend]`
**What:** Fix the typography pipeline to preserve line-height and letter-spacing through the entire extraction → design system → HTML path. Add a configurable web-font → email-safe-font mapping table. Map Figma font weights to email-safe values (400/700). Extract text-transform and text-decoration from Figma nodes. Update the `Typography` model to carry these properties.
**Why:** Currently: (1) `ExtractedTypography.line_height` is extracted from Figma but discarded by `convert_typography()` — the `Typography` model has no `line_height` field. (2) Letter-spacing is extracted at the node level but not in `ExtractedTypography`. (3) The `_font_stack()` function keeps web fonts as the primary font (e.g., `"Inter, Arial, Helvetica, sans-serif"`) — Inter won't render in any email client except Apple Mail with `@font-face`. (4) Font weights like `300` and `500` pass through verbatim — system fonts only support `normal` (400) and `bold` (700). (5) Figma's `textCase` (UPPER/LOWER/TITLE) and `textDecoration` are never read. Uppercase headings in the design render as mixed-case.
**Implementation:**
- Update `ExtractedTypography` in `app/design_sync/protocol.py`:
  - Add `letter_spacing: float | None = None` (px value)
  - Add `text_transform: str | None = None` (uppercase/lowercase/capitalize/none)
  - Add `text_decoration: str | None = None` (underline/line-through/none)
- Update `_parse_typography()` and `_walk_for_typography()` in `app/design_sync/figma/service.py`:
  - Extract `letterSpacing` from Figma style dict → store in `ExtractedTypography.letter_spacing`
  - Extract `textCase` → map: `UPPER` → `"uppercase"`, `LOWER` → `"lowercase"`, `TITLE` → `"capitalize"`, else `None`
  - Extract `textDecoration` → map: `UNDERLINE` → `"underline"`, `STRIKETHROUGH` → `"line-through"`, else `None`
- Update `Typography` in `app/projects/design_system.py`:
  - Add `heading_line_height: str | None = None` (e.g., `"36px"`)
  - Add `body_line_height: str | None = None` (e.g., `"24px"`)
  - Add `heading_letter_spacing: str | None = None` (e.g., `"-0.5px"`)
  - Add `body_letter_spacing: str | None = None` (e.g., `"0px"`)
  - Add `heading_text_transform: str | None = None`
- Update `convert_typography()` in `app/design_sync/converter.py`:
  - Map line-height from heading/body styles to `Typography` fields (convert to px string)
  - Map letter-spacing similarly
  - Map text-transform from heading style
  - **Load font fallback map from `data/email_client_fonts.yaml`** at module level instead of hardcoding. The YAML file already contains:
    - `fallback_map`: web-font → email-safe fallback chain (e.g., `Inter: [Arial, Helvetica, sans-serif]`, `Playfair Display: [Georgia, "Times New Roman", serif]`)
    - `clients`: per-client font support data including `requires_mso_font_alt: true` for Outlook desktop
    ```python
    import yaml
    from pathlib import Path

    _FONT_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "email_client_fonts.yaml"
    _FONT_DATA = yaml.safe_load(_FONT_DATA_PATH.read_text())
    _FALLBACK_MAP: dict[str, list[str]] = _FONT_DATA.get("fallback_map", {})
    _MSO_FONT_ALT_CLIENTS = {
        k for k, v in _FONT_DATA.get("clients", {}).items()
        if isinstance(v, dict) and v.get("requires_mso_font_alt")
    }
    ```
  - Update `_font_stack()` to use the YAML mapping: look up `family_clean` in `_FALLBACK_MAP`, build stack from YAML fallback chain, use original font as progressive enhancement: `f"{family_clean}, {', '.join(fallback_chain)}"`
  - When `requires_mso_font_alt` is true for target clients: add `mso-font-alt` CSS property to the inline style (e.g., `mso-font-alt:Arial;`) so Outlook uses the mapped system font
  - Map font weight: `int(weight)` → `"bold"` if ≥ 500, `"normal"` if < 500
- Update `node_to_email_html()` in `app/design_sync/converter.py`:
  - When rendering TEXT nodes: include `line-height:{value}px;` if available from node or props
  - Include `letter-spacing:{value}px;` if non-zero
  - Include `text-transform:{value};` if set
  - Include `text-decoration:{value};` if set
  - Use mapped font weight (`normal`/`bold`) instead of raw numeric weight
**Knowledge sources (encode as code, do not connect at runtime):**
- `data/email_client_fonts.yaml` — **primary data source** for font fallback mapping and per-client font support. Load at module level (replaces hardcoded `_WEB_FONT_MAP`). Contains `fallback_map` (10 web fonts → email-safe chains) and `clients` (11 email clients with `type`, `fonts`, `requires_mso_font_alt` fields)
- `css_support/typography.md` — px units only for `font-size`/`line-height` (unitless line-height breaks Outlook); `-webkit-text-size-adjust: 100%` required for iOS; intermediate font weights (300, 500) may fail in Outlook — only `normal` (400) and `bold` (700) are safe; reset heading margins explicitly (`margin:0`)
- `outlook_fixer/skills/mso_bug_fixes.md` — `mso-font-alt` property for Outlook font fallback; `mso-line-height-rule: exactly` required when setting explicit line-height in Outlook (without this, Outlook may override line-height)
- `scaffolder/skills/client_compatibility.md` — font-family, font-size, font-weight, line-height, text-align, text-decoration are universally safe CSS properties; letter-spacing is partially supported (safe to include but may be ignored by some clients)
**Security:** Static mapping table loaded from YAML. No user input processing changes.
**Verify:** Figma TEXT node with `Inter` font → HTML has `font-family:Inter, Arial, Helvetica, sans-serif` (from YAML `fallback_map`). `mso-font-alt:Arial` included in inline style. Font weight `300` → `font-weight:normal`. Font weight `600` → `font-weight:bold`. Line-height `28.8` → `line-height:29px` in HTML with `mso-line-height-rule:exactly`. Letter-spacing `0.5` → `letter-spacing:1px` in HTML (rounded). Text with `textCase: UPPER` → `text-transform:uppercase` in HTML. `Typography` model populated with `heading_line_height`, `body_line_height`. Unknown font not in `fallback_map` → falls back to `Arial, Helvetica, sans-serif` (generic sans-serif). Existing typography tests still pass. `make test` passes. `make types` passes.

### 33.4 Spacing Token Pipeline & Auto-Layout → Table Mapping `[Backend]`
**What:** Wire spacing tokens through the full pipeline: extraction → design system → HTML conversion. Map Figma auto-layout `itemSpacing` to spacer `<tr>` rows (vertical) or cell padding (horizontal). Apply `padding_top/right/bottom/left` from `DesignNode` directly in `node_to_email_html()` instead of relying on the `_NodeProps` indirection that currently drops padding. Pass spacing tokens to the Scaffolder via the design context.
**Why:** Currently: (1) `ExtractedSpacing` tokens are extracted from Figma but never consumed — there's no `convert_spacing()` function and they're absent from the design context sent to the Scaffolder. (2) `node_to_email_html()` reads padding from `props_map` but `_build_props_map_from_nodes()` only populates `bg_color`, silently discarding padding. (3) `item_spacing` from auto-layout is stored on `DesignNode` but never generates spacer rows or cell padding. The result: every Figma design's carefully crafted spacing is completely lost in the converted HTML.
**Implementation:**
- Create `convert_spacing()` in `app/design_sync/converter.py`:
  - Accept `list[ExtractedSpacing]`, return a spacing scale dict: `dict[str, float]` mapping names to px values
  - Detect common patterns: 4/8/12/16/24/32/48 → standard spacing scale
  - Name normalization: `spacing-8` → `xs`, `spacing-16` → `sm`, `spacing-24` → `md`, `spacing-32` → `lg`, `spacing-48` → `xl` (if values align to multiples of 4 or 8)
- Update `node_to_email_html()` in `app/design_sync/converter.py`:
  - Read padding directly from `DesignNode` fields (not just `props_map`):
    ```python
    pad_top = node.padding_top or (props.padding_top if props else 0)
    pad_right = node.padding_right or (props.padding_right if props else 0)
    pad_bottom = node.padding_bottom or (props.padding_bottom if props else 0)
    pad_left = node.padding_left or (props.padding_left if props else 0)
    ```
  - Apply padding as inline style on the wrapping `<table>` or on inner `<td>` elements
  - Read `node.layout_mode` to determine row grouping strategy:
    - `HORIZONTAL` → children become cells in a single `<tr>` (side by side)
    - `VERTICAL` → children each get their own `<tr>` (stacked)
    - `None` (no auto-layout) → fall back to existing `_group_into_rows()` by y-position
  - Apply `item_spacing`:
    - Vertical layout: insert spacer `<tr><td style="height:{item_spacing}px;font-size:1px;line-height:1px;">&nbsp;</td></tr>` between child rows
    - Horizontal layout: add `padding-left:{item_spacing}px` on all cells except the first
  - Apply `counter_axis_spacing` as padding on the cross-axis direction
- Update `_build_props_map_from_nodes()` in `app/design_sync/converter_service.py`:
  - Populate padding, font_family, font_size, font_weight, and layout_direction from `DesignNode` fields (currently only `bg_color` is set)
- Update `_build_design_context()` in `app/design_sync/import_service.py`:
  - Add `"spacing"` key to `design_tokens`:
    ```python
    "spacing": [
        {"name": s.name, "value": s.value} for s in tokens.spacing
    ]
    ```
  - Include `spacing_map` from layout analysis in the design context
**Knowledge sources (encode as code, do not connect at runtime):**
- `css_support/box-model.md` — **critical rules**: padding works ONLY on `<td>` cells (Outlook ignores padding on `<p>`/`<div>`/`<a>`). Never use `margin: 0 auto` for centering — use `align="center"` HTML attribute. Width must be set as both HTML attribute (`width="600"`) and CSS (`style="width:600px"`) for Outlook compatibility. `box-sizing` is ignored by Outlook. Percentage widths are reliable on `<td>` elements
- `outlook_fixer/skills/mso_bug_fixes.md` — spacer row pattern must include `font-size:1px;line-height:1px;mso-line-height-rule:exactly` to prevent Outlook from expanding spacer rows to default line height (~18px). Without `mso-line-height-rule:exactly`, a `height:12px` spacer row renders as 18px in Outlook
- `css_support/layout-properties.md` — `display:inline-block` fails in Outlook (use ghost tables instead); `float` is ignored by Gmail and Outlook; flexbox/grid are Apple Mail only. Table layout is the only reliable approach for multi-client emails
- `best_practices/table-based-layout.md` — always include `cellpadding="0" cellspacing="0" border="0"` on layout tables; `role="presentation"` on all non-data tables; avoid nesting tables deeper than 6 levels (Outlook rendering degrades)
**Security:** No new input paths. Spacing values are numeric, already validated in 33.2.
**Verify:** Figma frame with `paddingTop: 24, paddingLeft: 16` → HTML `<td>` has `style="padding:24px 0px 0px 16px"` (padding on `<td>`, NOT on `<table>`). Vertical auto-layout with `itemSpacing: 12` → spacer `<tr>` rows with `height:12px;font-size:1px;line-height:1px;mso-line-height-rule:exactly` between children. Horizontal auto-layout with `itemSpacing: 8` → cells have `padding-left:8px` (except first). Centering uses `align="center"` attribute, not `margin:0 auto`. Spacing tokens appear in Scaffolder design context. `make test` passes.

### 33.5 Multi-Column Layout & Proportional Width Calculation `[Backend]`
**What:** Fix multi-column rendering so that child nodes receive proportional widths based on their Figma dimensions relative to the parent. Replace the current `width="100%"` on all nested tables with calculated widths. Use `layout_mode` from auto-layout to determine horizontal vs. vertical arrangement instead of relying solely on y-position proximity.
**Why:** Currently every nested `<table>` gets `width="100%"`. In a two-column layout (e.g., 200px + 400px in a 600px parent), both columns render at 100% width and stack vertically instead of sitting side by side. The `_group_into_rows()` function uses a 10px y-tolerance to guess which nodes are on the same row, but: (a) auto-layout nodes often lack absolute positions, (b) 11px offset splits columns into separate rows, and (c) it ignores the explicit `layoutMode: "HORIZONTAL"` that Figma provides.
**Implementation:**
- Update `node_to_email_html()` in `app/design_sync/converter.py`:
  - When rendering child nodes in a `<tr>` (horizontal row):
    - Calculate width percentage: `child_width_pct = round((child.width / parent_width) * 100)` if both widths are known
    - Apply as `width="{pct}%"` on the child `<td>` wrapper and `width="100%"` on the inner `<table>` (so the table fills its cell)
    - For unknown widths: distribute equally (`100 / len(row_children)`)%
  - When `node.layout_mode == "HORIZONTAL"`:
    - Override `_group_into_rows()` — treat ALL children as a single row regardless of y-position
    - Skip y-position sorting for this node's children
  - When `node.layout_mode == "VERTICAL"`:
    - Override `_group_into_rows()` — treat EACH child as its own row
  - Only call `_group_into_rows()` when `layout_mode` is `None` (absolute positioning)
  - Add Outlook ghost table wrapping for multi-column rows:
    ```html
    <!--[if mso]><table role="presentation" width="100%"><tr><![endif]-->
    <td width="50%" style="display:inline-block;vertical-align:top;">...</td>
    <!--[if mso]></tr></table><![endif]-->
    ```
- Update `_group_into_rows()`:
  - Increase y-tolerance from 10px to 20px (common offset in manually positioned designs)
  - Handle `y=None` nodes: if ALL children have `y=None`, return them as a single row (assume horizontal auto-layout)
  - If SOME children have y and SOME don't, group y-bearing children normally and append y-less children to the last row
- Update `DesignConverterService.convert()` in `converter_service.py`:
  - Pass `selected_nodes` to `node_to_email_html()` context so width calculation has access to parent frame dimensions
  - Make container width configurable (default 600px) based on design's `overall_width` from layout analysis
**Knowledge sources (encode as code, do not connect at runtime):**
- `scaffolder/skills/table_layouts.md` — **complete HTML patterns** for 2-column (50/50 with MSO ghost table), 3-column (33/33/33), hero + content grid, 70/30 sidebar, fluid-hybrid spongy layout. Use these as parameterized templates in `node_to_email_html()` rather than generating from scratch. Each pattern includes MSO conditional ghost table wrapper, `display:inline-block;vertical-align:top;` for modern clients, and `width` on both `<td>` cells and MSO table cells
- `outlook_fixer/skills/mso_conditionals.md` — ghost table nesting rules: NEVER nest MSO conditionals (causes Word engine stack corruption). Always close `<![endif]-->` before opening another `<!--[if mso]>`. Version targeting operators: `gte mso 12` (Outlook 2007+), `lte mso 16` (Outlook 2021 and earlier). Count conditional pairs to verify balanced open/close
- `outlook_fixer/skills/mso_bug_fixes.md` — MSO table reset styles: `mso-table-lspace:0pt;mso-table-rspace:0pt` on every `<table>` (prevents 1px white lines between cells). Ghost table pattern must include `cellpadding="0" cellspacing="0"`. DPI scaling fix (`PixelsPerInch=96`) already in `EMAIL_SKELETON` — verify it's not duplicated
- `css_support/layout-properties.md` — `display:inline-block` requires `vertical-align:top` and `width` set via both attribute and CSS. Gmail clips emails at 102KB — monitor generated HTML size for multi-column layouts
- `import_annotator/skills/column_patterns.md` — column detection patterns for reverse mapping: table-based columns (each `<td>` = column), inline-block columns (parent = section), and the key rule that individual columns are NOT sections (parent gets the section annotation)
**Security:** No new input paths. Width calculations use numeric node dimensions only.
**Verify:** Two children (200px + 400px) in a 600px parent with `layoutMode: "HORIZONTAL"` → `<td width="33%">` and `<td width="67%">` with ghost table wrapper. Three equal columns → `<td width="33%">` each with MSO ghost table. Ghost table includes `cellpadding="0" cellspacing="0"` and `mso-table-lspace:0pt;mso-table-rspace:0pt`. No nested MSO conditionals (balanced open/close count). Vertical auto-layout → each child in its own `<tr>`. Mixed y-position nodes with >10px offset but <20px → grouped in same row. All children with `y=None` → single row. Existing single-column layouts unaffected. `make test` passes.

### 33.6 Semantic HTML Generation (Headings, Paragraphs, Buttons) `[Backend]`
**What:** Update `node_to_email_html()` to emit semantic HTML elements inside `<td>` cells: `<h1>`-`<h3>` for headings, `<p>` for body text, and styled `<a>` tags for button components. Use font size relative to the design's body size to determine heading level. Recognize COMPONENT/INSTANCE nodes named as buttons and convert to bulletproof `<a>` buttons with VML fallback.
**Why:** Currently all text becomes a bare `<td>` tag regardless of semantic role. This violates the codebase's own email HTML rules ("Use `<h1>`-`<h6>` with inline styles inside `<td>` cells" and "Use `<p style='margin:0 0 10px 0;'>` inside `<td>` cells"). Screen readers can't distinguish headings from body text. Button components (FRAME/COMPONENT with a single short TEXT child) render as `<table>` wrappers instead of clickable `<a>` elements.
**Implementation:**
- Update TEXT node rendering in `node_to_email_html()`:
  - Determine semantic role from font size + design context:
    - `font_size >= body_size * 2.0` → `<h1>` (or within 80% of largest font in parent)
    - `font_size >= body_size * 1.5` → `<h2>`
    - `font_size >= body_size * 1.2` → `<h3>`
    - Otherwise → `<p>` (not bare text in `<td>`)
  - Body size: determined from `convert_typography()` result or default 16px
  - Wrap semantic element inside the `<td>`:
    ```html
    <td>
      <h1 style="margin:0;font-family:...;font-size:...;font-weight:...;color:...;line-height:...;">
        Heading Text
      </h1>
    </td>
    ```
  - `<p>` tags get `style="margin:0 0 10px 0;"` per codebase convention
  - Multi-line TEXT nodes (containing `\n`): split into multiple `<p>` tags
- Add button detection and rendering:
  - **Reuse `layout_analyzer` output**: 33.0 wires `analyze_layout()` into the converter, producing `EmailSection.buttons` (list of `ButtonElement` with `node_id`, `text`, `width`, `height`). Check if the current node's `id` matches a button in the section's buttons list rather than re-detecting. Fallback detection for nodes outside analyzed sections: COMPONENT/INSTANCE with name containing "button"/"btn"/"cta" AND a single TEXT child ≤30 chars AND height ≤80px (same rules as `layout_analyzer._walk_for_buttons`)
  - Render as bulletproof button:
    ```html
    <td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="border-radius:4px;background-color:{fill_color};">
            <a href="#" style="display:inline-block;padding:12px 24px;font-family:...;font-size:...;color:{text_color};text-decoration:none;">
              {button_text}
            </a>
          </td>
        </tr>
      </table>
      <!--[if mso]>
      <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" style="width:{width}px;height:{height}px;" arcsize="8%" fillcolor="{fill_color}" stroke="f">
        <v:textbox inset="0,0,0,0" style="mso-fit-shape-to-text:true;">
          <center style="font-family:Arial,sans-serif;font-size:{font_size}px;color:{text_color};">{button_text}</center>
        </v:textbox>
      </v:roundrect>
      <![endif]-->
    </td>
    ```
  - Extract button dimensions from node.width/height, bg color from node.fill_color, text color from child TEXT node
- Pass body font size as parameter to `node_to_email_html()` for heading level calculation
- **Reuse `layout_analyzer` heading detection**: 33.0 wires `analyze_layout()` into the converter, producing `EmailSection.texts` with `is_heading=True/False` already set by `_detect_content_hierarchy()`. Use `TextBlock.is_heading` from the section's text list to determine whether a TEXT node is a heading, rather than re-computing font size ratios. The heading level (h1/h2/h3) still uses the font size thresholds described above — `is_heading` determines *whether* it's a heading, the size ratio determines *which level*
**Knowledge sources (encode as code, do not connect at runtime):**
- `best_practices/cta-buttons.md` — **complete bulletproof button patterns**: padding-based table button (widest support), VML roundrect for Outlook (with `arcsize` percentage), and border-based approach (fallback). Design rules: 44px minimum touch target height, 4.5:1 contrast ratio between button text and background, action verb copy (2-4 words), multiple CTAs should have visual hierarchy (primary = filled, secondary = outlined). The VML `<v:roundrect>` pattern includes `stroke="f"` (no border), `<v:textbox inset="0,0,0,0">`, and `<center>` for text alignment
- `outlook_fixer/skills/vml_reference.md` — VML shape syntax: `<v:roundrect>` for buttons (with `arcsize` as percentage of shortest side), `<v:fill type="solid" color="{hex}">`, `<v:textbox>` with `mso-fit-shape-to-text:true` to auto-size. VML namespace must be declared on `<html>` (already in `EMAIL_SKELETON`). Always include `xmlns:v="urn:schemas-microsoft-com:vml"` and `xmlns:o="urn:schemas-microsoft-com:office:office"`
- `accessibility/skills/screen_reader_behavior.md` — `role="presentation"` on ALL layout tables (already present but verify button wrapper tables get it too). Headings create navigation landmarks — ensure heading hierarchy doesn't skip levels (h1 → h3 without h2). `aria-hidden="true"` on decorative spacer rows. Reading order follows DOM order, not visual order — verify the converter outputs elements in the same order as the design's top-to-bottom reading flow
- `accessibility/skills/color_contrast.md` — WCAG AA contrast: 4.5:1 for normal text (<18px or <14px bold), 3:1 for large text (≥18px or ≥14px bold). Apply to button text vs button background color. The converter already has `_relative_luminance()` and `_contrast_ratio()` — extend to validate button contrast and warn if below threshold
- `outlook_fixer/skills/mso_bug_fixes.md` — `mso-line-height-rule:exactly` required on ALL elements with explicit `line-height` (headings, paragraphs). Without it, Outlook overrides line-height with its own default. Paragraph margins: use `mso-margin-top-alt` and `mso-margin-bottom-alt` for Outlook-specific margin control
**Security:** HTML content is escaped via `html.escape()` (already in place). Button `href="#"` is a placeholder — no user-controlled URLs in conversion output. VML attributes use escaped values.
**Verify:** TEXT node with font-size 32px (body 16px) → `<h1>` inside `<td>` with `mso-line-height-rule:exactly`. TEXT node with font-size 16px → `<p style="margin:0 0 10px 0;">` inside `<td>`. COMPONENT named "CTA Button" with "Shop Now" text → bulletproof `<a>` button with VML `<v:roundrect>` fallback, `role="presentation"` on button wrapper table, contrast ratio ≥ 4.5:1 validated. Button height ≥ 44px (touch target). Multi-line text → multiple `<p>` tags. Heading hierarchy is sequential (no skipped levels). Layout tables have `role="presentation"`. Existing conversion output still has valid email HTML structure. `make test` passes.

### ~~33.7 Dark Mode Token Extraction & Gradient Fallbacks~~ DONE `[Backend]`
**What:** Extract dark mode color variants from Figma Variables API modes. When a variable collection has a "Dark" mode, extract parallel token sets for light and dark. Generate `prefers-color-scheme: dark` CSS overrides and `[data-ogsc]` / `[data-ogsb]` attribute selectors for Outlook dark mode. Add gradient linear fallback support: emit CSS `background: linear-gradient(...)` with a solid `bgcolor` fallback for Outlook.
**Why:** Currently the pipeline extracts zero dark mode tokens. The Dark Mode agent downstream must guess dark colors algorithmically — often producing poor contrast or off-brand colors. Figma Variables natively support light/dark modes, but the extraction pipeline ignores mode data entirely. Additionally, gradient backgrounds are silently dropped (33.1 extracts a midpoint color, but the actual gradient information is lost). Many modern email designs use subtle gradients in hero sections.
**Implementation:**
- Extend `ExtractedTokens` in `app/design_sync/protocol.py`:
  - Add `dark_colors: list[ExtractedColor] = field(default_factory=list)` — dark mode counterparts
  - Add `gradients: list[ExtractedGradient] = field(default_factory=list)`
- Add `ExtractedGradient` dataclass:
  ```python
  @dataclass(frozen=True)
  class ExtractedGradient:
      name: str
      type: str  # "linear" | "radial"
      angle: float  # degrees (linear only)
      stops: list[tuple[str, float]]  # (hex_color, position 0.0-1.0)
      fallback_hex: str  # midpoint solid fallback for Outlook
  ```
- Update `_fetch_variables()` in `app/design_sync/figma/service.py`:
  - When parsing variable collections: detect modes with names containing "dark", "night", "dim" (case-insensitive)
  - For each color variable: extract both default mode value and dark mode value
  - Create parallel `ExtractedColor` lists: light mode → `colors`, dark mode → `dark_colors`
  - Match by variable name: `dark_colors[i].name` == `colors[i].name` for easy pairing
- Update `_walk_for_colors()`:
  - For `GRADIENT_LINEAR` fills:
    - Extract `gradientHandlePositions` (angle calculation) and `gradientStops` (colors + positions)
    - Compute angle from handle positions: `atan2(handle2.y - handle1.y, handle2.x - handle1.x) * 180 / pi`
    - Build `ExtractedGradient` with stops and fallback midpoint hex
- Update `converter.py`:
  - Add `_gradient_to_css()`: convert `ExtractedGradient` → `background: linear-gradient({angle}deg, {stop1} {pos1}%, {stop2} {pos2}%, ...)`
  - When a node's fill is a gradient: emit both `bgcolor="{fallback_hex}"` for Outlook and `style="background:{gradient_css};"` for modern clients
- Update `converter_service.py`:
  - Add `dark_mode_style_block()`: generate `@media (prefers-color-scheme: dark)` CSS rules mapping light → dark colors
  - Add `[data-ogsc]` and `[data-ogsb]` selectors for Outlook.com dark mode
  - Include dark mode CSS in the `<style>` block of `EMAIL_SKELETON`
- Update `_build_design_context()` in `import_service.py`:
  - Include `dark_colors` in design context when available
  - Include `gradients` list
**Knowledge sources (encode as code, do not connect at runtime):**
- `css_support/dark-mode-css.md` — **complete dark mode email template** with all techniques combined. Three-tier approach: (1) `<meta name="color-scheme" content="light dark">` + `<meta name="supported-color-schemes" content="light dark">` in `<head>`, (2) `@media (prefers-color-scheme: dark)` with `!important` on all overrides (for Apple Mail, iOS, Samsung), (3) `[data-ogsc]` (text) and `[data-ogsb]` (background) attribute selectors for Outlook.com. CSS `color-scheme: light dark;` property on `<body>`. All three must be present for full coverage
- `dark_mode/skills/color_remapping.md` — **magic color values**: use `#010101` instead of `#000000` and `#fefefe` instead of `#ffffff` to prevent Outlook auto-inversion (Outlook categorizes pure black and pure white for automatic dark mode swapping). Luminance-based color categorization zones: light (lum > 0.5) → may be darkened, dark (lum < 0.2) → may be lightened, mid-range (0.2-0.5) → usually preserved. Pre-verified dark mode color pairs with WCAG AA contrast ratios
- `dark_mode/skills/outlook_dark_mode.md` — Outlook.com-specific patterns: `[data-ogsc]` targets text color, `[data-ogsb]` targets background color. The 1x1 pixel background trick prevents Outlook from inverting CTA button backgrounds: set a 1x1 transparent PNG as `background-image` on the button `<td>` (`background-image:url(data:image/png;base64,...)`) — Outlook won't invert elements with background images. Class-based selectors required (not element selectors) because Outlook.com rewrites class names
- `dark_mode/skills/client_behavior.md` — client behavior matrix: Apple Mail = full control (color-scheme + @media), Outlook.com = partial (`[data-ogsc]`/`[data-ogsb]` only), Outlook Desktop = no dark mode control, Gmail = no dark mode control, **Samsung = double-inversion risk** (Samsung inverts colors, then re-inverts `prefers-color-scheme` overrides — test carefully). Implementation priority: Apple/iOS first (largest dark mode market share), then Outlook.com, then Samsung
- `dark_mode/skills/meta_tag_injection.md` — required meta tags (must be in `<head>`, before any `<style>` block): `<meta name="color-scheme" content="light dark">` and `<meta name="supported-color-schemes" content="light dark">`. Without these, Apple Mail ignores `@media (prefers-color-scheme: dark)` entirely
- `dark_mode/skills/image_handling.md` — image swap techniques for dark mode: `<picture><source media="(prefers-color-scheme: dark)" srcset="dark-logo.png">` for Apple Mail; CSS show/hide with `display:none` / `display:block !important` for broader support; transparent PNG logos work natively in dark mode. Product images: add 1-2px white border to prevent blend-in on dark backgrounds
- `css_support/colors-backgrounds.md` — gradient CSS support: only Apple Mail/iOS/Samsung support `background: linear-gradient(...)`. All other clients need solid `bgcolor` fallback. For Outlook: use VML `<v:fill type="gradient" color="{start_hex}" color2="{end_hex}" angle="{angle}">` (from `outlook_fixer/skills/vml_reference.md`). Always emit both CSS gradient AND `bgcolor` attribute on the same element
- `accessibility/skills/color_contrast.md` — dark mode colors must ALSO meet WCAG AA contrast: validate all dark color pairs (dark text on dark background) at 4.5:1 for normal text, 3:1 for large text. Use `_relative_luminance()` and `_contrast_ratio()` already in `converter.py`
**Security:** No new input paths. Gradient angle clamped to 0-360. Color hex values validated by 33.2 transform layer. Magic color values (#010101, #fefefe) are static constants.
**Verify:** Figma file with "Light"/"Dark" variable modes → both `colors` and `dark_colors` populated. Dark mode CSS block contains all three tiers: meta tags, `@media (prefers-color-scheme: dark)` rules with `!important`, and `[data-ogsc]`/`[data-ogsb]` selectors. Magic colors used: generated dark CSS uses `#010101` instead of `#000000` and `#fefefe` instead of `#ffffff`. Dark color pairs validated for WCAG AA contrast. Gradient fill → `background: linear-gradient(...)` in CSS + `bgcolor="{fallback_hex}"` attribute + VML `<v:fill type="gradient">` for Outlook. Gradient with 3 stops → all stops present in CSS. CTA buttons have 1x1 pixel background trick to prevent Outlook inversion. No dark mode in Figma → `dark_colors` empty, no dark CSS generated, no meta tags added. `make test` passes.

### ~~33.8 Design Context Enrichment & Scaffolder Integration~~ DONE `[Backend + Frontend]`
**What:** Ensure the full enriched token set (colors, typography with line-height/letter-spacing, spacing, dark mode colors, gradients, token warnings) flows through the design context to the Scaffolder and is visible in the frontend token viewer. Fix the `_layout_to_design_nodes()` reconstruction to preserve typography, padding, and text content. Add token diff display on the design sync page showing what changed between syncs.
**Why:** Currently: (1) `_build_design_context()` drops line_height and spacing from the dict sent to the Scaffolder. (2) `_layout_to_design_nodes()` builds hollow `DesignNode` objects that lose all typography, padding, and text content. (3) The frontend `DesignTokensView` only shows colors, typography families, and spacing values — no line-height, letter-spacing, dark mode variants, or gradient previews. (4) Users can't see what changed between syncs — they must compare manually.
**Implementation:**
- Update `_build_design_context()` in `app/design_sync/import_service.py`:
  - Add `line_height` and `letter_spacing` to typography entries
  - Add `spacing` array from `ExtractedSpacing` tokens
  - Add `dark_colors` array when available
  - Add `gradients` array when available
  - Add `token_warnings` list from validation layer (33.2)
- Fix `_layout_to_design_nodes()` in `app/design_sync/import_service.py`:
  - Preserve `text_content`, `font_family`, `font_size`, `font_weight`, `line_height_px`, `letter_spacing_px` from `TextBlock` data in layout analysis
  - Preserve `padding_top/right/bottom/left` and `item_spacing` from section data
  - Preserve `fill_color` and `text_color` where available
  - Create TEXT-type child nodes from `section.texts` with full typography data
- Update `DesignTokensResponse` schema in `app/design_sync/schemas.py`:
  - Add `dark_colors: list[ColorResponse] | None`
  - Add `gradients: list[GradientResponse] | None`
  - Add `warnings: list[str] | None`
  - Add `typography[].line_height`, `typography[].letter_spacing`, `typography[].text_transform`
- Update frontend `design-tokens-view.tsx`:
  - Show dark mode colors alongside light mode colors (side-by-side swatches)
  - Show gradient previews (CSS gradient rendered in a swatch div)
  - Show line-height and letter-spacing in typography cards
  - Show token warnings as dismissible alerts
- Add token diff logic:
  - Backend: `DesignSyncService.get_token_diff(connection_id)` → compares current snapshot tokens vs previous snapshot
  - Return: `{added: [...], removed: [...], changed: [{name, old_value, new_value}]}`
  - Frontend: show diff summary after sync with color-coded added/removed/changed badges
**Security:** Token warnings are system-generated strings, not user input. No XSS risk in frontend display (React auto-escapes).
**Verify:** Scaffolder receives typography with line_height and letter_spacing in design context. `_layout_to_design_nodes()` produces nodes with font_family, font_size, text_content populated. Frontend shows dark mode swatches when available. Token diff after re-sync shows changed colors. Token warnings visible in UI. `make check-fe` passes. `make test` passes.

### ~~33.9 Builder Annotations for Visual Builder Sync~~ DONE `[Backend]`
**What:** Add `data-section-id`, `data-component-name`, and `data-slot-name` attributes to the HTML output of `node_to_email_html()` and `DesignConverterService.convert()`. These annotations are what the frontend builder sync (`ast-mapper.ts` → `visual-builder-panel.tsx`) uses to populate slot definitions, render actual content instead of placeholders, and enable drag-and-drop editing of imported designs.
**Why:** Phase 31 fixed slot definition inference for the HTML upload/paste path (via `inferSlotDefinitions()` fallback in `visual-builder-panel.tsx`). But the Figma design sync pipeline produces HTML without any builder annotations. The frontend sync engine's Strategy 1 (annotated HTML with `data-section-id`) never matches — it falls through to Strategy 2 (structural content-root analysis), which produces `SectionNode` objects with `componentId=0` and empty `slotValues`. The `sectionNodeToBuilderSection()` function then calls `inferSlotDefinitions()` on the HTML fragment, but since the converter emits bare `<td>` elements (no `data-slot-name` attributes), inference returns `[]` → slot fills are never applied → the visual builder shows "Body content goes here" placeholders instead of the actual Figma content. The fix is to annotate the converter output at generation time, so the builder sync path works end-to-end without relying on fallback inference.
**Implementation:**
- Update `node_to_email_html()` in `app/design_sync/converter.py`:
  - Add `data-section-id="section_{idx}"` on each top-level frame's wrapping `<tr>` element (the `<tr><td>` wrapper in `converter_service.py` line 111)
  - Add `data-component-name="{node.name}"` on the section's outer `<table>` element (using the Figma frame/component name, sanitized via `html.escape()`)
  - Add `data-slot-name="{slot_id}"` on content-bearing elements inside sections:
    - TEXT nodes rendered as `<h1>`/`<h2>`/`<h3>` (from 33.6) → `data-slot-name="heading"` (or `heading_2`, `heading_3` for subsequent headings in the same section)
    - TEXT nodes rendered as `<p>` → `data-slot-name="body"` (or `body_2`, `body_3` for subsequent paragraphs)
    - IMAGE nodes → `data-slot-name="image"` (or `image_2` for subsequent images)
    - Button `<a>` elements (from 33.6) → `data-slot-name="cta"` (or `cta_2` for subsequent buttons)
  - Slot ID generation: maintain a per-section counter dict `{slot_type: count}` to generate unique IDs like `heading`, `body`, `body_2`, `image`, `cta`
  - Pass section index as parameter to `node_to_email_html()` for `data-section-id` generation
- Update `DesignConverterService.convert()` in `converter_service.py`:
  - Pass frame index to `node_to_email_html()` so section IDs are sequential
  - Add `data-section-id` to the `<tr><td>` wrapper:
    ```python
    section_parts.append(
        f'<tr data-section-id="section_{idx}"><td>\n{section_html}\n</td></tr>'
    )
    ```
- Frontend compatibility verification:
  - `ast-mapper.ts` Strategy 1 should now match on `data-section-id` attributes → produces annotated `SectionNode[]`
  - `sectionNodeToBuilderSection()` receives `slotValues` populated from `data-slot-name` elements → slot fills applied → actual content visible in preview
  - `inferSlotDefinitions()` fallback still works for HTML without annotations (backward compatible)
  - `stripAnnotations()` in `section-markers.ts` already handles `data-section-id`, `data-slot-name`, `data-component-name` removal on export (no changes needed)
**Security:** Annotation attributes use `html.escape()` for all values derived from Figma node names. `data-*` attributes are inert HTML — no script execution risk. `stripAnnotations()` removes all builder metadata before export, so annotations never reach the final email output.
**Verify:** Import Figma design via design sync → converter output contains `data-section-id="section_0"`, `data-section-id="section_1"`, etc. on `<tr>` elements. Content elements have `data-slot-name` attributes matching their semantic role. Visual builder preview shows actual Figma content (headings, body text, images) instead of placeholders. `ast-mapper.ts` Strategy 1 matches annotated sections. `stripAnnotations()` removes all `data-*` builder attributes on export. Existing upload/paste path still works (annotations are additive). `make test` passes. `make check-fe` passes.

### 33.10 Image Asset Import for Design Sync Pipeline `[Backend]`
**What:** Wire the existing `ImageImporter` (built in Phase 31.7 for the upload pipeline) into the design sync conversion pipeline. After `DesignConverterService.convert()` produces the HTML skeleton with `<img src="" ...>` placeholders, download the actual images from Figma's image export API, store them locally, and rewrite the `src` attributes to hub-hosted URLs. Preserve image dimensions from both Figma node data and downloaded image metadata.
**Why:** Currently `node_to_email_html()` renders IMAGE nodes as `<img src="" alt="..." width="..." height="..." />` — the `src` is always empty. The Figma API provides image export endpoints (`/v1/images/{file_key}?ids={node_ids}&format=png`) that return temporary CDN URLs for rendered images. Phase 31.7 built a complete `ImageImporter` class with SSRF prevention, magic byte validation, dimension extraction via Pillow, content-hash deduplication, and semaphore-limited concurrent downloads — but it's only wired into the upload pipeline (`TemplateUploadService`). The design sync pipeline needs the same capability to produce complete, renderable HTML from Figma imports.
**Implementation:**
- Update `DesignConverterService` in `converter_service.py`:
  - Add `async convert_with_images()` method that wraps `convert()` + image import:
    - Call `convert()` to produce the HTML skeleton (existing flow)
    - Collect all IMAGE node IDs from the design tree (the `data-node-id` attributes already emitted by `node_to_email_html()` on `<img>` tags)
    - Call `provider.export_images(file_ref, access_token, node_ids, format="png", scale=2.0)` to get temporary Figma CDN URLs
    - Build a mapping: `{node_id: figma_cdn_url}`
    - Rewrite `<img src="" data-node-id="{node_id}"` → `<img src="{figma_cdn_url}" data-node-id="{node_id}"` in the HTML
    - Pass the HTML through `ImageImporter.import_images(html, upload_id=import_id)` to download, validate, store, and rewrite URLs to hub-hosted paths
    - Return `ConversionResult` with the image-complete HTML + `ImportedImage` list
  - Keep `convert()` synchronous and image-free (for tests and cases where image import isn't needed)
- Update `DesignImportService.run_conversion()` in `import_service.py`:
  - Call `convert_with_images()` instead of `convert()` when `generate_html=True`
  - Pass `import_id` for image storage path (same pattern as upload pipeline)
  - Store `ImportedImage` metadata in the import record's `structure_json["images"]`
- Reuse `ImageImporter` from `app/templates/upload/image_importer.py`:
  - No modifications needed — the class is already generic (accepts HTML string, returns modified HTML + image list)
  - Configuration via `settings.templates.import_images`, `max_image_download_size`, etc. (already in place from Phase 31.7)
- Serve imported images via the existing asset endpoint:
  - `GET /api/v1/templates/upload/assets/{upload_id}/{filename}` already serves images with path traversal protection and CSP headers
  - For design sync imports, use `import_id` as the storage directory key (same pattern, different ID namespace)
  - Add a parallel endpoint or alias: `GET /api/v1/design-sync/imports/{import_id}/assets/{filename}` that delegates to the same `DesignAssetService`
- Update `<img>` rendering in `node_to_email_html()`:
  - Preserve `data-node-id` attribute (already present) — used by the image rewriting step to match Figma export URLs to elements
  - Use Figma node dimensions (`width`, `height`) for HTML attributes, but update with actual downloaded dimensions if they differ (Pillow measurement from `ImageImporter`)
  - Set `style="display:block;border:0;width:100%;max-width:{width}px;height:auto;"` for responsive images
**Security:** Figma CDN URLs are temporary (expire after ~30 minutes) — images are downloaded and stored locally immediately. `ImageImporter` already validates: HTTP/HTTPS only (no `file://`), magic byte verification (PNG/JPEG/GIF/WebP/SVG), 5MB size limit per image, 50 images per import. Asset serving endpoint has path traversal prevention via `.resolve()` + `is_relative_to()`. No user-controlled URLs — all URLs come from Figma's API response.
**Verify:** Import Figma design with 3 images → converter fetches Figma export URLs → `ImageImporter` downloads and stores locally → HTML `src` attributes point to hub-hosted URLs. Images render correctly in builder preview. Image dimensions from Figma preserved in HTML attributes. Figma export failure (CDN timeout) → graceful fallback, `src` stays as Figma CDN URL (temporary but functional). Import without images → no errors (empty image list). `ImageImporter` deduplication: same image in two sections → downloaded once. Asset serving endpoint returns correct content-type and CSP headers. `make test` passes.

### 33.11 Tests & Integration Verification `[Full-Stack]`
**What:** Comprehensive tests verifying the full design token pipeline from Figma API response through to email HTML output: Variables API parsing, opacity compositing, token validation, typography transforms, spacing application, multi-column layout, semantic HTML, dark mode extraction, and Scaffolder integration.
**Implementation:**
- **Variables API extraction tests** — `app/design_sync/figma/tests/test_variables_api.py`:
  - Mock Variables API response with color, float, and string variables → `ExtractedTokens` with `variables_source=True`
  - Variable with alias `{color.brand.primary}` → resolved to literal hex value
  - Circular alias `A → B → A` → raises `SyncFailedError("Circular variable alias")`
  - Collection with "Light" and "Dark" modes → separate `colors` and `dark_colors` lists
  - 403 response (no paid plan) → graceful fallback to Styles API path
  - Existing Styles API tests still pass (regression)
- **Opacity compositing tests** — `app/design_sync/figma/tests/test_opacity.py`:
  - `_rgba_to_hex_with_opacity(0, 0, 1.0, a=0.5, node_opacity=1.0)` → `#8080FF` (blue composited on white)
  - `_rgba_to_hex_with_opacity(0, 0, 1.0, a=1.0, node_opacity=0.5)` → `#8080FF` (same via layer opacity)
  - `_rgba_to_hex_with_opacity(0, 0, 1.0, a=0.5, node_opacity=0.5)` → `#C0C0FF` (25% effective opacity)
  - Fully opaque → `_rgba_to_hex()` fast path, identical to current behavior
  - Multiple fills: top solid fill is extracted, lower fills ignored
  - Gradient fill → midpoint color extracted + `ExtractedGradient` created
  - Stroke colors → not in `tokens.colors` list
- **Token validation tests** — `app/design_sync/tests/test_token_transforms.py`:
  - Empty font family → warning + replaced with `"Arial"`
  - 3-digit hex `#F00` → expanded to `#FF0000`
  - Named color `"red"` → `#FF0000`
  - `rgba(255, 0, 0, 0.5)` string → converted to composited hex
  - Unitless line-height `1.5` with font size `16` → `24.0` (px)
  - Negative spacing `-5` → error-level warning
  - Zero colors → info-level warning
  - Valid tokens → zero warnings, pass-through unchanged
- **Typography pipeline tests** — `app/design_sync/tests/test_typography_pipeline.py`:
  - `convert_typography()` with `Inter 400 16px` → `Typography(body_font="Inter, Arial, Arial, Helvetica, sans-serif")`
  - `_font_stack("Inter")` → `"Inter, Arial, Arial, Helvetica, sans-serif"`
  - `_font_stack("Playfair Display")` → `"Playfair Display, Georgia, Georgia, Times New Roman, serif"`
  - `_font_stack("Unknown Custom Font")` → `"Unknown Custom Font, Arial, Helvetica, sans-serif"` (no mapping, default fallback)
  - Font weight `300` → `"normal"`, weight `600` → `"bold"`
  - Line-height `28.8` from Figma → `"29px"` in `Typography.heading_line_height`
  - Letter-spacing preserved through pipeline
  - Text transform `UPPER` → `"uppercase"` in output
- **Spacing and layout tests** — `app/design_sync/tests/test_spacing_layout.py`:
  - Vertical auto-layout with `itemSpacing: 12` → spacer `<tr>` rows in HTML
  - Horizontal auto-layout with `itemSpacing: 8` → `padding-left:8px` on cells (skip first)
  - Node padding `(24, 16, 24, 16)` → `style="padding:24px 16px 24px 16px"` on table
  - Spacing tokens in design context dict for Scaffolder
  - `convert_spacing()` with `[8, 16, 24, 32]` values → named scale
- **Multi-column layout tests** — `app/design_sync/tests/test_multi_column.py`:
  - Two children (200px + 400px) in 600px parent, `layoutMode: "HORIZONTAL"` → `<td width="33%">` and `<td width="67%">`
  - Three equal children → `<td width="33%">` each
  - MSO ghost table wrappers present in multi-column output
  - `layoutMode: "VERTICAL"` → each child in own `<tr>` regardless of position
  - `layoutMode: None` → fallback to `_group_into_rows()` by y-position
  - All children `y=None` → single row (assumes horizontal)
  - `_group_into_rows()` with 15px offset (> old 10px, < new 20px tolerance) → same row
- **Semantic HTML tests** — `app/design_sync/tests/test_semantic_html.py`:
  - TEXT node font-size 32px (body 16px) → `<h1>` inside `<td>`
  - TEXT node font-size 24px → `<h2>` inside `<td>`
  - TEXT node font-size 16px → `<p style="margin:0 0 10px 0;">` inside `<td>`
  - Button component → `<a>` with VML `<v:roundrect>` fallback
  - Multi-line text with `\n` → multiple `<p>` tags
  - All semantic elements have inline styles (font-family, size, weight, color)
- **Dark mode & gradient tests** — `app/design_sync/tests/test_dark_mode_gradients.py`:
  - Variables with "Dark" mode → `dark_colors` populated with matching names
  - Dark mode CSS block has `@media (prefers-color-scheme: dark)` rules
  - Dark mode CSS block has `[data-ogsc]` selectors
  - Linear gradient → `background: linear-gradient(...)` + `bgcolor` fallback
  - Gradient with 3 stops → correct CSS output
  - No dark mode → no dark CSS block (clean output)
- **Builder annotation tests** — `app/design_sync/tests/test_builder_annotations.py`:
  - Single-frame conversion → `<tr data-section-id="section_0">` on outer wrapper
  - Multi-frame conversion → sequential `data-section-id` values (`section_0`, `section_1`, `section_2`)
  - TEXT node rendered as `<h1>` → has `data-slot-name="heading"` attribute
  - Second TEXT node rendered as `<p>` in same section → has `data-slot-name="body"` (not `heading`)
  - Third TEXT node → `data-slot-name="body_2"` (counter increments)
  - IMAGE node → `data-slot-name="image"` attribute
  - Button `<a>` → `data-slot-name="cta"` attribute
  - Multiple buttons in same section → `cta`, `cta_2` (unique IDs)
  - Frame/component name → `data-component-name` attribute on section `<table>` (HTML-escaped)
  - Frame with special characters in name (`"Hero Section / v2"`) → properly escaped in attribute
  - `stripAnnotations()` removes all `data-section-id`, `data-slot-name`, `data-component-name` attributes (existing function, verify coverage)
  - Frontend `ast-mapper.ts` Strategy 1 matches annotated HTML → produces `SectionNode[]` with populated `slotValues`
  - `sectionNodeToBuilderSection()` with annotated sections → `slotDefinitions` populated from `data-slot-name` elements → preview shows actual content (not placeholders)
- **Image import for design sync tests** — `app/design_sync/tests/test_design_sync_images.py`:
  - `convert_with_images()` calls `provider.export_images()` for IMAGE node IDs → receives Figma CDN URLs
  - Figma CDN URLs rewritten into HTML `<img src="">` placeholders before `ImageImporter` processes them
  - `ImageImporter.import_images()` downloads from CDN URLs → stores locally → rewrites `src` to hub-hosted paths
  - 3 images in Figma design → 3 `ImportedImage` entries in result with correct dimensions
  - Duplicate image (same content hash) → downloaded once, reused (deduplication)
  - Figma export failure (mock 500 response) → graceful fallback, `src` retains Figma CDN URL
  - Image exceeding 5MB limit → skipped with warning, original URL preserved
  - SVG image node → validated via magic bytes, stored as `.svg`
  - Asset serving endpoint returns imported image with correct content-type header
  - `import_images=false` in config → images skipped, `src=""` preserved
  - Image dimensions from Figma node match HTML `width`/`height` attributes
  - Image dimensions updated if Pillow measurement differs from Figma node data (actual file dimensions take precedence)
- **End-to-end pipeline test** — `app/design_sync/tests/test_e2e_pipeline.py`:
  - Mock Figma file response with Variables, auto-layout, gradients, dark mode:
    - Variables API returns 6 colors (3 light, 3 dark), 2 typography styles, 4 spacing values
    - Document tree: vertical frame with header (horizontal: logo + nav), hero (gradient bg + heading + CTA button), content (two-column), footer
    - 3 IMAGE nodes (logo, hero image, content image) with mock export URLs
  - Pipeline produces:
    - Valid HTML email with `<!DOCTYPE>`, MSO conditionals, 600px container
    - Header section with proportional columns
    - Hero with gradient CSS + solid fallback + `<h1>` heading + bulletproof button
    - Two-column content with proportional `<td>` widths + MSO ghost tables
    - Dark mode `<style>` block with `prefers-color-scheme` + OGS selectors
    - All spacing from auto-layout applied (padding + spacer rows)
    - Typography with mapped email-safe fonts, line-height, letter-spacing
    - No token validation warnings (all clean)
    - Builder annotations: `data-section-id` on all section `<tr>` elements, `data-slot-name` on content elements, `data-component-name` on section tables
    - Images: all `<img src>` attributes point to hub-hosted URLs (not empty, not Figma CDN)
  - HTML validates (no unclosed tags, proper nesting)
  - Visual builder integration: annotated HTML loaded into builder → sections detected via Strategy 1 → slot fills applied → preview renders actual Figma content
**Security:** Tests only. Mock Figma API responses with synthetic data. No real PATs, no real API calls, no PII. Mock image downloads use `httpx` transport mocking — no real HTTP requests.
**Verify:** `make test` passes (all new test files). `make check` all green. `make types` passes. No regression in existing design sync tests. `make bench` shows no performance regression in conversion pipeline.

---

## Security Checklist (Run Before Each Sprint Demo)

- [ ] All new endpoints have auth dependency injection
- [ ] All new endpoints have rate limiting configured
- [ ] All request schemas validate input (no raw strings to DB)
- [ ] All response schemas exclude sensitive fields
- [ ] No credentials in logs (grep for password, secret, key, token in log output)
- [ ] New database tables have appropriate RLS policies
- [ ] Frontend forms sanitise input before API calls
- [ ] Preview iframes use sandbox attribute
- [ ] Error responses don't leak internal details
- [ ] Audit entries created for all state-changing operations
- [ ] CORS configuration checked (no wildcards)
- [ ] Docker containers run as non-root
- [ ] New environment variables documented in `.env.example`

---

## Success Criteria (Phases 32–33 — Next)

| Metric | Status |
|--------|--------|
| Campaign build time | Under 1 hour (deterministic CSS pipeline) |
| Cross-client rendering defects | Near-zero + enforced QA + rendering + approval gates |
| QA checks | 17+ (enforced at export) |
| CSS pipeline latency | <500ms (single-pass sidecar) |
| Template CSS precompilation | Amortized at registration (0ms at build time) |
| CSS compatibility visibility | Full gate panel: QA + rendering + approval status |
| Email client emulators | 8 clients, 14 profiles (Gmail, Outlook, Apple Mail, Yahoo, Samsung, Thunderbird, Android Gmail, Outlook.com) |
| Rendering confidence scoring | Per-client 0–100 with breakdown + recommendations + dashboard |
| Pre-send rendering gate | Rendering + QA + approval gates in export pipeline (enforce/warn/skip) |
| Approval workflow | Full UI: request, review, decide, feedback, audit trail |
| E2E test coverage | 32+ Playwright scenarios + visual regression + 3 browsers (Chromium + Firefox + WebKit) |
| Design import paths | Figma + Penpot + brief-only + enhanced Penpot converter |
| HTML import fidelity | Pre-compiled email HTML imports with preserved centering, fonts, colors, images, and dark mode readability |
| Maizzle passthrough | Pre-compiled HTML bypasses render() — no double-inlining or structural scrambling |
| Typography token pipeline | font-weight, line-height, letter-spacing extracted + font-size/spacing applied during assembly + project design system mapping |
| Font compilation | Client-specific font stacks (Outlook mso-font-alt, Gmail web font `<link>`), project design system font mapping with diff preview |
| Image asset import | External images downloaded, re-hosted, dimensions preserved (display + intrinsic) |
| Client rendering matrix | Single authoritative YAML — all 8 client families, CSS support, dark mode, known bugs, synced with ontology |
| Agent knowledge lookup | Runtime `lookup_client_support` tool — <1ms deterministic queries, replaces static L3 duplication |
| Content agent email awareness | Client-aware preheader/subject/CTA lengths, character encoding safety, column-width-adapted copy |
| Import annotator recognition | Stripo, Bee, Mailchimp, MJML patterns recognized + ESP edge cases (AMPscript, nested Liquid, Handlebars partials) |
| Cross-agent learning | Insight bus propagates rendering discoveries between agents — within-run handoff learnings + across-run semantic memory |
| Eval-driven skill updates | Semi-automated pipeline: pass rate drop → failure cluster → skill file patch → PR for review |
| Visual QA feedback loop | Pre-Maizzle visual precheck + screenshot-attached recovery routing + post-render drift comparison |
| Figma Variables API | Modern token extraction via Variables API with Styles API fallback — zero-token files eliminated |
| Opacity compositing | Fill opacity × layer opacity flattened to final hex — semi-transparent colors render correctly |
| Token validation layer | All tokens validated before consumption: hex format, px units, non-empty fonts, no unresolved aliases |
| Web font → email mapping | 25+ web fonts mapped to email-safe system fonts — no raw web fonts in final HTML |
| Auto-layout → table mapping | Figma `layoutMode` drives HTML structure: HORIZONTAL → columns, VERTICAL → rows, with proportional widths |
| Spacing token pipeline | `itemSpacing` → spacer rows/cell padding, `padding_*` → table padding, spacing tokens in Scaffolder context |
| Multi-column proportional widths | Child widths calculated relative to parent — no more `width="100%"` on all nested tables |
| Semantic email HTML | Headings → `<h1>`-`<h3>`, body → `<p>`, buttons → bulletproof `<a>` with VML fallback |
| Dark mode token extraction | Light/dark variable modes extracted in parallel — no more algorithmic guessing |
| Gradient fallbacks | Linear gradients → CSS `linear-gradient()` + solid `bgcolor` fallback for Outlook |
| Design context enrichment | Full token set (typography + spacing + dark + gradients + warnings) flows to Scaffolder |
| CRAG accept/reject gate | Corrections verified via before/after issue count — regressions rejected, originals preserved |

---

---

## ~~Phase 32 — Agent Email Rendering Intelligence~~ DONE

> Upgrade all 11 AI agents from distributed, duplicated email knowledge to a unified rendering intelligence layer: centralized client matrix, runtime knowledge lookup, cross-agent learning, content-aware rendering constraints, deeper import skills, eval-driven skill evolution, MCP integration for IDE-native agent access, skill versioning for safe automated updates, and per-client skill overlays for multi-tenant customization.

- [x] ~~32.1 Centralized email client rendering matrix~~ DONE
- [x] ~~32.2 Content agent email rendering awareness~~ DONE
- [x] ~~32.3 Import annotator skill depth~~ DONE
- [x] ~~32.4 Agent knowledge lookup tool~~ DONE
- [x] ~~32.5 Cross-agent insight propagation~~ DONE
- [x] ~~32.6 Eval-driven skill file updates~~ DONE
- [x] ~~32.7 Visual QA feedback loop tightening~~ DONE
- [x] ~~32.8 Tests & integration verification~~ DONE
- [x] ~~32.9 MCP server exposure for agent tools~~ DONE
- [x] ~~32.10 Skill versioning with rollback~~ DONE
- [x] ~~32.11 Per-client skill overlays~~ DONE
- [x] ~~32.12 Tests for 32.9–32.11~~ DONE

### 32.1 Centralized Email Client Rendering Matrix `[Backend + Data]`
**What:** Create a single authoritative `data/email-client-matrix.yaml` file that defines every email client's rendering engine, CSS property support, dark mode behavior, known bugs, size limits, and quirks. Replace the 5+ duplicated client-compatibility references scattered across agent L3 skill files (`client_compatibility.md`, `client_behavior.md`, `email_client_engines.md`, `css_client_support.md`, `dom_rendering_reference.md`) with a loader that reads from this matrix. Integrate with the existing ontology sync pipeline so the matrix stays current with CanIEmail data.
**Why:** Client rendering knowledge is currently duplicated across Scaffolder (`client_compatibility.md`), Dark Mode (`client_behavior.md`, `dom_rendering_reference.md`), Code Reviewer (`css_client_support.md`), and Knowledge (`email_client_engines.md`). These files overlap but aren't identical — they drift as one gets updated and others don't. The Scaffolder says Gmail clips at 102KB; the Code Reviewer says the same; the Dark Mode agent doesn't mention it at all. Outlook VML requirements appear in 3 different files with slightly different syntax examples. When ontology data updates via `make sync-ontology`, none of these skill files update. A centralized matrix eliminates drift, creates a single update point, and enables runtime queries (32.4) instead of static skill file loading.
**Implementation:**
- Create `data/email-client-matrix.yaml`:
  - Structure per client:
    ```yaml
    clients:
      outlook_365_windows:
        display_name: "Outlook 365 (Windows)"
        engine: word
        engine_version: "Word 2019+"
        css_support:
          layout:
            flexbox: { support: none, workaround: "Use nested tables with fixed widths" }
            grid: { support: none, workaround: "Use nested tables" }
            float: { support: none, workaround: "Use align attribute on table/img" }
            position: { support: none }
          box_model:
            max-width: { support: none, workaround: "Use width attribute + MSO table wrapper" }
            border-radius: { support: none, workaround: "Use VML <v:roundrect>" }
            box-shadow: { support: none }
            margin: { support: partial, notes: "Supported on block elements, not table cells" }
          typography:
            font-family: { support: partial, notes: "System fonts only — no web fonts. Use mso-font-alt for fallback" }
            line-height: { support: partial, workaround: "Use mso-line-height-rule:exactly" }
          color:
            background-image: { support: none, workaround: "Use VML <v:fill>" }
            linear-gradient: { support: none, workaround: "Use VML fill patterns" }
          selectors:
            media_queries: false
            attribute_selectors: false
            pseudo_classes: [":hover (partial)"]
        dark_mode:
          type: forced_inversion
          developer_control: none
          selectors: []
          notes: "Outlook desktop (Windows) applies forced color inversion. No CSS override available."
        vml_required: true
        mso_conditionals: true
        known_bugs:
          - id: ghost_table
            symptom: "Multi-column layout collapses to single column"
            fix: "Wrap columns in MSO conditional ghost table"
          - id: dpi_scaling
            symptom: "Images render at wrong size on high-DPI displays"
            fix: "Set explicit width/height attributes on <img> + use CSS width for fluid"
          - id: line_height
            symptom: "Inconsistent line spacing"
            fix: "Add mso-line-height-rule:exactly to elements"
          - id: p_spacing
            symptom: "Extra vertical spacing on <p> tags"
            fix: "Add mso-margin-top-alt:0; mso-margin-bottom-alt:0 or use margin:0 inline"
          - id: font_fallback
            symptom: "Text renders in Times New Roman instead of specified font"
            fix: "Add mso-font-alt: Arial (or appropriate system font) to font-family declaration"
        size_limits: {}
        supported_fonts: [Arial, Georgia, Verdana, "Times New Roman", Tahoma, "Trebuchet MS", "Courier New", "Comic Sans MS", Impact, "Lucida Console"]

      gmail_web:
        display_name: "Gmail (Web)"
        engine: blink_restricted
        css_support:
          layout:
            flexbox: { support: none, workaround: "Use display:inline-block with widths" }
            grid: { support: none, workaround: "Use nested tables" }
          box_model:
            border-radius: { support: full }
            max-width: { support: full }
          typography:
            font-family: { support: full, notes: "Web fonts via <link> in <head>" }
          selectors:
            media_queries: false
            attribute_selectors: true
            pseudo_classes: [":hover"]
        dark_mode:
          type: forced_inversion
          developer_control: none
          selectors: []
          notes: "Gmail forces full color inversion. No developer override. Avoid pure #ffffff/#000000."
        known_bugs: []
        size_limits:
          clip_threshold_kb: 102
          style_block: "Stripped in some contexts (non-AMP, forwarded)"
        supported_fonts: "*"
        requires_link_tag: true

      apple_mail:
        display_name: "Apple Mail"
        engine: webkit
        css_support:
          layout:
            flexbox: { support: full }
            grid: { support: full }
          box_model:
            border-radius: { support: full }
            max-width: { support: full }
          typography:
            font-family: { support: full }
          selectors:
            media_queries: true
            attribute_selectors: true
            pseudo_classes: [":hover", ":active", ":focus"]
        dark_mode:
          type: developer_controlled
          developer_control: full
          selectors: ["@media (prefers-color-scheme: dark)"]
          notes: "Full developer control. Supports <picture> source swap for image dark mode."
        known_bugs: []
        size_limits: {}
        supported_fonts: "*"

      outlook_com:
        display_name: "Outlook.com"
        engine: blink_restricted
        css_support:
          layout:
            flexbox: { support: none }
            grid: { support: none }
          box_model:
            border-radius: { support: full }
          typography:
            font-family: { support: full }
          selectors:
            media_queries: false
        dark_mode:
          type: partial_developer
          developer_control: partial
          selectors: ["[data-ogsc]", "[data-ogsb]"]
          notes: "data-ogsc for text color, data-ogsb for background color. Only these selectors work."

      samsung_mail:
        display_name: "Samsung Mail"
        engine: webview
        dark_mode:
          type: double_inversion_risk
          developer_control: partial
          selectors: ["@media (prefers-color-scheme: dark)"]
          notes: "Applies BOTH custom dark CSS AND its own partial inversion. Risk of double-inversion."
        supported_fonts: "system_plus_google"

      yahoo_mail:
        display_name: "Yahoo Mail"
        engine: blink_restricted
        css_support:
          layout:
            flexbox: { support: none }
          selectors:
            media_queries: true
        dark_mode:
          type: partial_inversion
          developer_control: limited
        known_bugs:
          - id: class_renaming
            symptom: "CSS classes renamed with random prefix"
            fix: "Use inline styles as primary, <style> block as progressive enhancement"

      thunderbird:
        display_name: "Thunderbird"
        engine: gecko
        css_support:
          layout:
            flexbox: { support: full }
          selectors:
            media_queries: true
        dark_mode:
          type: developer_controlled
          developer_control: full
          selectors: ["@media (prefers-color-scheme: dark)"]
    ```
  - Include all 8 client families with 14 profiles as defined in the existing emulator system
- Create `app/knowledge/client_matrix.py`:
  - `ClientMatrix` class:
    - `load(path: Path = DATA_DIR / "email-client-matrix.yaml") -> ClientMatrix` — parse YAML, validate with Pydantic model
    - `get_client(client_id: str) -> ClientProfile` — lookup single client
    - `get_css_support(client_id: str, property: str) -> CSSSupport` — lookup CSS property support for a client
    - `get_dark_mode(client_id: str) -> DarkModeProfile` — dark mode behavior
    - `get_known_bugs(client_id: str) -> list[KnownBug]` — known rendering bugs
    - `get_constraints_for_clients(client_ids: list[str]) -> AudienceConstraints` — aggregate constraints for a set of target clients (intersection of support = lowest common denominator)
    - `format_audience_context(client_ids: list[str]) -> str` — generate the formatted `--- TARGET AUDIENCE CONSTRAINTS ---` string currently hardcoded in `audience_context.py`
  - `ClientProfile`, `CSSSupport`, `DarkModeProfile`, `KnownBug`, `AudienceConstraints` — Pydantic models
  - Cache parsed matrix in module-level singleton (YAML doesn't change at runtime)
- Modify `app/ai/blueprints/audience_context.py`:
  - Replace hardcoded constraint strings with `ClientMatrix.format_audience_context(client_ids)`
  - The current `_build_css_constraints()` function has client CSS knowledge embedded in Python code — replace with matrix lookups
  - Preserve the existing `AudienceProfile` interface — `audience_context` output format stays the same for downstream agents
- Modify `app/ai/agents/scaffolder/skills/`, `app/ai/agents/dark_mode/skills/`, `app/ai/agents/code_reviewer/skills/`, `app/ai/agents/knowledge/skills/`:
  - Remove duplicated client compatibility content from L3 skill files
  - Replace with brief reference: "Client rendering constraints are injected via audience context. For specific client capabilities, use the `lookup_client_support` tool (32.4)."
  - Keep agent-specific behavioral guidance (e.g., Dark Mode's "how to apply data-ogsc selectors" stays — but "which clients support data-ogsc" moves to matrix)
- Integration with ontology sync (`make sync-ontology`):
  - Modify `scripts/sync-ontology.js` (or add `scripts/sync-client-matrix.py`):
    - After ontology sync, cross-reference CanIEmail CSS property data with `email-client-matrix.yaml`
    - Flag drift: if ontology says a property is now supported in a client but the matrix says `none` → warning log
    - Auto-update `css_support` entries where ontology data is more recent (with human review flag for breaking changes)
    - Manual review for dark mode, known bugs, and size limits (these aren't in CanIEmail)
**Security:** Read-only YAML file parsed at startup. No user input reaches the parser. Pydantic validation rejects malformed data. No new API endpoints.
**Verify:** `ClientMatrix.get_css_support("outlook_365_windows", "flexbox")` returns `CSSSupport(support="none", workaround="Use nested tables...")`. `ClientMatrix.format_audience_context(["gmail_web", "outlook_365_windows"])` produces constraint string mentioning flexbox unsupported, 102KB clip limit. Agent L3 skill files no longer contain client CSS matrices. `audience_context.py` produces identical output format as before (diff test). `make test` passes. `make sync-ontology` runs without errors and logs any matrix drift warnings.

### ~~32.2 Content Agent Email Rendering Awareness~~ `[Backend]` DONE
**What:** Add a new L3 skill file `content_rendering_constraints.md` to the Content agent that teaches it how email client rendering constraints affect the text content it generates. Add skill detection triggers so the file loads when the agent is generating subject lines, preheaders, CTAs, or body copy destined for specific email clients.
**Why:** The Content agent generates text in a vacuum — it doesn't know that preheader visible length varies by client (Gmail ~100 chars, Apple Mail ~140, Outlook ~50), that subject lines truncate at different points on mobile vs desktop (35 chars vs 60 chars), that CTA button text renders inside VML `<v:roundrect>` elements with fixed dimensions (long text breaks layout), that body copy inside narrow `<td>` cells wraps differently than web, or that certain characters (smart quotes, em dashes, non-ASCII) break rendering in Outlook's Word engine. The agent's existing `operation_best_practices.md` has generic length guidelines but no client-aware constraints. When building for Outlook-heavy audiences, the Content agent should generate shorter, simpler text. When building for Apple Mail users, it can be more expressive.
**Implementation:**
- Create `app/ai/agents/content/skills/l3/content_rendering_constraints.md`:
  - **Preheader rendering by client:**
    - Gmail web/mobile: ~100-110 visible characters (after subject line), rest hidden
    - Apple Mail: ~140 characters visible in list view
    - Outlook desktop: ~50-60 characters (narrow preview pane)
    - Yahoo: ~100 characters
    - Samsung: ~90 characters
    - Rule: write preheader with critical message in first 50 chars (universal safe zone), supporting detail in chars 51-100 (most clients), optional detail in 101-140 (Apple Mail bonus)
  - **Subject line truncation:**
    - Mobile (all clients): ~35-40 characters visible in notification, ~50-55 in inbox list
    - Desktop Gmail: ~70 characters
    - Desktop Outlook: ~55-60 characters (depends on preview pane width)
    - Desktop Apple Mail: ~70-80 characters
    - Rule: front-load value proposition in first 35 chars, keep total under 60 for safety
  - **CTA button text constraints:**
    - VML buttons (Outlook): fixed width element — text must fit within declared width or overflows/clips
    - Rule: 2-5 words maximum, prefer action verbs, test at 120px-200px button widths
    - Avoid: long CTAs like "Learn More About Our Latest Features" — use "See Features" or "Learn More"
  - **Body copy in table cells:**
    - `<td>` cells have fixed widths (typically 300-560px depending on column layout)
    - Long words without hyphens can overflow cells in Outlook (Word engine doesn't hyphenate)
    - Rule: avoid words longer than 20 characters without soft hyphens (`&shy;`)
    - Outlook ignores `word-break` CSS — only `word-wrap: break-word` partially works
  - **Character encoding gotchas:**
    - Smart quotes (`\u201C` `\u201D` `\u2018` `\u2019`): render as `?` or `â€™` in some older Outlook versions and non-UTF-8 ESP configurations
    - Em dash (`\u2014`): safe in modern clients but breaks in some legacy systems — prefer ` — ` with spaces or ` - `
    - Ellipsis (`\u2026`): safe in modern clients, but `...` is universally safe
    - Non-ASCII characters (accented, CJK): require proper `<meta charset="UTF-8">` in HTML `<head>` — Content agent should flag if generating non-ASCII content
    - Rule: when audience includes Outlook Desktop or unknown clients, prefer ASCII-safe alternatives
  - **Line length and readability:**
    - Optimal reading line length: 45-75 characters per line
    - At 600px email width with 32px padding: ~50-60 chars per line at 16px font
    - At 300px column width (2-col layout): ~25-35 chars per line — requires shorter sentences
    - Rule: adapt sentence length to column width context when provided
- Modify `app/ai/agents/content/prompt.py` — skill detection:
  - Add trigger patterns for `content_rendering_constraints.md`:
    - Always load when `audience_context` is present in node metadata (means we know target clients)
    - Always load for `subject_line` and `preheader` operations (always client-sensitive)
    - Load for `cta` operation (VML button width constraints)
    - Load for `body_copy` when metadata indicates multi-column layout
  - Integrate with audience context: if node metadata includes `audience_client_ids`, inject client-specific preheader/subject limits into the skill context
- Modify Content agent's `SKILL.md` L2 section:
  - Add to L2 capabilities: "Client-aware text generation: adapts preheader length, subject line truncation, CTA word count, and character encoding to target email client constraints"
  - Add to L2 rules: "When audience context is available, respect per-client character limits. When no audience specified, use universal safe defaults (50-char preheader, 35-char subject front-load, 3-word CTA)"
**Security:** Read-only skill file addition. No new code paths, API endpoints, or user input handling. Skill detection uses existing metadata fields.
**Verify:** Content agent generating a preheader with Outlook Desktop in audience → output ≤50 significant characters in first sentence. Content agent generating CTA → ≤5 words. Content agent generating subject line → value proposition in first 35 characters. Content agent without audience context → universal safe defaults applied. Existing Content agent tests still pass. `make test` passes.

### ~~32.3 Import Annotator Skill Depth~~ `[Backend]` DONE
**What:** Add 4 new L3 skill files to the Import Annotator agent (`app/ai/agents/import_annotator/`) that teach it to recognize HTML patterns from popular email builders, normalize imported CSS, detect wrapper structures, and handle edge-case ESP token patterns. Update skill detection to load these files based on input HTML characteristics.
**Why:** The Import Annotator is the newest agent (Phase 24.9) with the fewest L3 skill files (4: `table_layouts.md`, `div_layouts.md`, `esp_tokens.md`, `column_patterns.md`). Users importing HTML from external tools — Stripo, Bee Free, Mailchimp, MJML-compiled output, Litmus Builder — hit edge cases the annotator doesn't handle: tool-specific ghost table patterns, non-standard comment markers, proprietary CSS class naming (`mc:edit`, `bee-row`, `stripo-*`), MJML's compiled nested table structure, and vendor-specific meta tags. Improving the annotator's recognition directly supports Phase 31's import fidelity goals.
**Implementation:**
- Create `app/ai/agents/import_annotator/skills/l3/common_email_builders.md`:
  - **Stripo patterns:**
    - CSS classes: `esd-structure`, `esd-container`, `esd-block`, `es-content-body`, `es-p-default`
    - Comment markers: `<!--[if !mso]><!-- -->` (standard MSO) + `<!-- stripo-module: -->` (section markers)
    - Structure: deeply nested tables (4-5 levels), `<div class="es-wrapper">` as outer container
    - Ghost tables: Stripo uses MSO conditionals with `mso-table-lspace:0pt; mso-table-rspace:0pt`
    - Annotation rule: preserve `stripo-module` comments as section boundaries, map `esd-*` classes to semantic roles
  - **Bee Free patterns:**
    - CSS classes: `bee-row`, `bee-col`, `bee-block`, `bee-content`
    - Structure: `<div class="bee-page-container">` → `<div class="bee-row">` → `<div class="bee-col">`
    - Note: Bee exports div-heavy layouts that need table conversion for email
    - Annotation rule: map `bee-row` → section boundary, `bee-col` → column, flag div-based layout for table conversion
  - **Mailchimp patterns:**
    - Merge tags: `*|MERGE|*` format, `*|IF:MERGE|*...*|END:IF|*` conditionals
    - Editable regions: `mc:edit="region_name"` attributes
    - CSS classes: `mc-*` prefixed, `templateContainer`, `templateBody`, `templateFooter`
    - Comment markers: `<!-- BEGIN MODULE: -->` section boundaries
    - Annotation rule: preserve `mc:edit` attributes as slot markers, map `BEGIN MODULE` comments to section boundaries, preserve merge tags as ESP tokens
  - **MJML compiled output:**
    - Structure: deeply nested 3-table pattern per section (outer align table → inner width table → content table)
    - CSS classes: `mj-*` removed during compilation, replaced with inline styles
    - Comment markers: `<!-- [mj-column] -->` (sometimes preserved)
    - Width pattern: every structural `<td>` has explicit `width` attribute + `style="width:Npx"`
    - Annotation rule: recognize the 3-table nesting pattern, collapse to single section table in annotation
  - **Litmus Builder patterns:**
    - Similar to hand-coded: clean table structure, minimal classes
    - Comment markers: `<!-- MODULE: -->` section markers
    - Annotation rule: map `MODULE` comments to section boundaries
- Create `app/ai/agents/import_annotator/skills/l3/css_normalization.md`:
  - **Shorthand expansion**: reference 31.2's CSS compiler output — by the time the annotator sees the HTML, shorthands are already expanded (if the upload pipeline ran the compiler). If annotating raw HTML (no compiler step), flag unexpanded shorthands for the compiler.
  - **Vendor prefix cleanup**: `-webkit-`, `-moz-`, `-ms-`, `-o-` prefixes — map to standard property names for annotation, preserve in output (still needed for some clients)
  - **!important handling**: count `!important` declarations — high count (>20) indicates Mailchimp/Stripo export (they use `!important` defensively). Don't strip — but annotate as "tool-generated defensive styles"
  - **Duplicate property detection**: same property declared twice in one `style=""` attribute (common in tool exports as progressive enhancement — e.g., `background: #fff; background: linear-gradient(...)`). Annotate the intent: first value = fallback, second = progressive.
  - **Class-to-inline reconciliation**: when `<style>` block classes AND inline styles both set the same property, annotate which wins (inline wins in email — `<style>` block is progressive enhancement only)
- Create `app/ai/agents/import_annotator/skills/l3/wrapper_detection.md`:
  - **Centering wrapper patterns** (complements 31.3 analyzer work):
    - Pattern 1: `<table width="600" align="center">` (classic email centering)
    - Pattern 2: `<div style="max-width:600px; margin:0 auto;">` (modern, needs table fallback for Outlook)
    - Pattern 3: `<center>` tag (legacy, still used by some builders)
    - Pattern 4: MSO ghost table wrapper `<!--[if mso]><table align="center"><tr><td><![endif]-->` around a `<div>`
    - Pattern 5: Nested wrapper — MSO ghost table outside, div inside, content table innermost
  - **Background wrapper patterns**:
    - Full-width background: `<table width="100%" bgcolor="#f2f2f2">` wrapping centered content table
    - VML background: `<!--[if gte mso 9]><v:rect>...<v:fill>...</v:fill>...<![endif]-->` wrapping content
    - Annotation rule: identify background wrappers separately from centering wrappers — they serve different reconstruction purposes
  - **Preheader wrapper patterns**:
    - Hidden preheader: `<div style="display:none; max-height:0; overflow:hidden;">` or `<span style="display:none;">`
    - Annotation rule: annotate as `preheader_wrapper`, preserve for reconstruction
- Create `app/ai/agents/import_annotator/skills/l3/esp_token_edge_cases.md`:
  - **AMPscript edge cases:**
    - Nested function calls: `%%=Concat(Uppercase(FirstName), " ", LastName)=%%`
    - Inline AMPscript blocks inside attributes: `<a href="%%=RedirectTo(...)=%%">`
    - `TreatAsContent` / `ContentBlockByKey` references (external content inclusion)
    - Multi-line AMPscript blocks: `%%[ ... ]%%` spanning multiple lines with SET/IF/ENDIF
  - **Nested Liquid:**
    - Filters chained: `{{ name | capitalize | truncate: 20 }}`
    - Liquid inside HTML attributes: `<div style="color: {{ brand_color }};">`
    - `{% capture %}` blocks that define variables used later
    - Connected Content: `{% connected_content https://api.example.com :save response %}` (Braze-specific)
  - **Handlebars partials:**
    - `{{> partial_name }}` — external template inclusion
    - `{{#each items}}...{{/each}}` — loop with `{{@index}}`, `{{@first}}`, `{{@last}}`
    - Triple-stache `{{{unescaped}}}` for raw HTML injection
  - **ERB (Ruby-based ESPs):**
    - `<%= expression %>` — output
    - `<% code %>` — logic
    - `<%- include 'partial' %>` — partial inclusion
  - **Annotation rules:** preserve ALL ESP tokens as opaque blocks during structural analysis. Never split an ESP token across section boundaries. When an ESP conditional (`{% if %}...{% endif %}`) wraps multiple sections, annotate the conditional as spanning those sections.
- Modify `app/ai/agents/import_annotator/prompt.py` — skill detection:
  - Load `common_email_builders.md` when HTML contains: `esd-`, `bee-`, `mc:edit`, `mj-`, `stripo`, or `<!-- BEGIN MODULE` / `<!-- MODULE`
  - Load `css_normalization.md` when HTML contains: `!important` (>5 occurrences), vendor prefixes, or duplicate inline properties
  - Load `wrapper_detection.md` always (wrapper detection is core to import fidelity)
  - Load `esp_token_edge_cases.md` when HTML contains: `%%[`, `%%=`, `{%`, `{{`, `<%`, `*|`, or `{{>`
**Security:** Read-only skill file additions. No new code paths. ESP tokens are treated as opaque strings — never evaluated or executed. The annotator is analysis-only (no HTML modification).
**Verify:** Import Stripo-exported HTML → annotator identifies `esd-structure` sections and `stripo-module` comments. Import Mailchimp template → annotator preserves `mc:edit` attributes and merge tags. Import MJML-compiled output → annotator recognizes 3-table nesting pattern. Import HTML with nested AMPscript → ESP tokens preserved intact across section boundaries. Import HTML with `<center>` wrapper → annotator identifies centering pattern. Existing Import Annotator tests pass. `make test` passes.

### 32.4 Agent Knowledge Lookup Tool `[Backend]`
**What:** Create a `lookup_client_support` tool callable by all agents during LLM execution, backed by the centralized client matrix (32.1). Instead of pre-loading full L3 reference files into the prompt, agents can query specific facts at decision time: "Does Outlook 365 support border-radius?" → structured answer with support level, workaround, and confidence. Integrate as an LLM tool/function call in the blueprint engine's agent execution flow.
**Why:** L3 skill files are loaded based on HTML pattern detection — clever but limited. Pattern detection can miss edge cases (HTML has no MSO conditionals, but Outlook IS in the target audience — the Scaffolder should still know Outlook constraints). Loading full reference files burns tokens even when the agent only needs one fact. With a tool, agents ask the right question at the right time, prompt size drops (no pre-loaded reference files for "just in case"), and the system naturally logs what agents need to know (useful for eval improvement and skill file refinement in 32.6). The Knowledge agent already provides RAG-based Q&A, but it's a heavy pipeline (embedding search → reranking → LLM synthesis). The lookup tool is a lightweight, deterministic alternative for structured facts.
**Implementation:**
- Create `app/ai/agents/tools/client_lookup.py`:
  - `ClientLookupTool` class implementing the agent tool interface:
    - Tool name: `lookup_client_support`
    - Tool description: "Look up email client rendering support for a CSS property, dark mode behavior, known bugs, or size limits. Returns structured data from the authoritative client rendering matrix."
    - Parameters schema:
      ```python
      class ClientLookupParams(BaseModel):
          query_type: Literal["css_support", "dark_mode", "known_bugs", "size_limits", "font_support"]
          client_id: str  # e.g., "outlook_365_windows", "gmail_web"
          property: str | None = None  # CSS property name for css_support queries
      ```
    - Returns:
      ```python
      class ClientLookupResult(BaseModel):
          client: str
          query_type: str
          result: dict[str, Any]  # varies by query_type
          workaround: str | None = None
          confidence: float = 1.0  # always 1.0 for matrix data (deterministic)
      ```
    - Implementation: direct lookup from `ClientMatrix` (32.1) — no LLM, no embedding search, no network calls
    - Fallback: if `client_id` not found, return `{"error": "Unknown client", "available_clients": [...]}` so the LLM can self-correct
  - `MultiClientLookupTool` — batch variant:
    - Tool name: `lookup_client_support_batch`
    - Accepts `client_ids: list[str]` + `properties: list[str]`
    - Returns matrix of support levels — useful for "which of my target clients support flexbox?"
    - Reduces round-trips: one tool call instead of N×M individual lookups
- Modify `app/ai/blueprints/engine.py` — tool registration:
  - In `_build_tools_for_node()` (or equivalent tool setup):
    - Register `ClientLookupTool` and `MultiClientLookupTool` for all agentic nodes
    - Tools are available alongside existing tools (memory recall, knowledge search)
  - Tool execution: synchronous (matrix lookup is <1ms) — no async overhead needed
- Modify agent system prompts (Scaffolder, Dark Mode, Outlook Fixer, Accessibility, Code Reviewer, Innovation):
  - Add to L2 section: "You have access to `lookup_client_support` for real-time client rendering queries. Use it instead of guessing CSS support. Available query types: css_support, dark_mode, known_bugs, size_limits, font_support."
  - Remove or reduce L3 skill files that duplicate matrix data (already trimmed in 32.1)
- Add tool usage logging:
  - Log every tool call: `agent_name`, `query_type`, `client_id`, `property`, `timestamp`
  - Aggregate logs feed into 32.6 (eval-driven skill updates): frequently queried facts should be promoted to L2 skill file content (always loaded), rarely queried facts stay in the matrix (on-demand)
**Security:** Tool returns read-only data from a static YAML file. No user input reaches the tool except through LLM function calling (which is already sandboxed). Tool results are structured data, not executable code. No new API endpoints — tool is internal to the blueprint engine.
**Verify:** Scaffolder agent generating email for Outlook audience → calls `lookup_client_support("css_support", "outlook_365_windows", "border-radius")` → receives `{support: "none", workaround: "Use VML <v:roundrect>"}`. Dark Mode agent → calls `lookup_client_support("dark_mode", "samsung_mail")` → receives `{type: "double_inversion_risk", ...}`. Batch lookup for 3 clients × 2 properties → single tool call returns 6 results. Unknown client ID → error response with available clients list. Tool call logging captures all queries. Agent prompt token count reduced vs pre-32.4 baseline (measure before/after). `make test` passes.

### 32.5 Cross-Agent Insight Propagation `[Backend]`
**What:** Create a structured insight bus that extracts learnings from each agent's execution within a blueprint run and propagates them to relevant downstream agents — both within the same run (via handoff metadata) and across runs (via semantic memory with cross-agent routing). When the Dark Mode agent discovers "Samsung Mail double-inverts #1a1a1a backgrounds," the Scaffolder agent should know to avoid that color in future builds for Samsung audiences.
**Why:** Agent learning is currently siloed. Each agent stores its failure patterns in semantic memory tagged with its own name. When the Dark Mode agent discovers a Samsung Mail rendering issue, that insight lives in `source_agent="dark_mode"` memory entries. The Scaffolder never recalls those memories because it queries `agent_type="scaffolder"`. The handoff chain passes structured decisions between agents in a single run, but handoffs describe *what was done* — not *what was learned*. The result: the Scaffolder keeps generating patterns that the Dark Mode agent keeps fixing, run after run.
**Implementation:**
- Create `app/ai/blueprints/insight_bus.py`:
  - `AgentInsight` dataclass:
    ```python
    @dataclass
    class AgentInsight:
        source_agent: str        # "dark_mode"
        target_agents: list[str] # ["scaffolder", "code_reviewer"]
        client_ids: list[str]    # ["samsung_mail"]
        insight: str             # "Avoid #1a1a1a backgrounds — Samsung double-inverts to near-white"
        category: str            # "color", "layout", "typography", "dark_mode", "accessibility", "mso"
        confidence: float        # 0.85 (derived from evidence count / total runs)
        evidence_count: int      # 3 occurrences
        first_seen: str          # ISO timestamp
        last_seen: str           # ISO timestamp
    ```
  - `InsightBus` class:
    - `extract_insights(run_result: BlueprintRunResult) -> list[AgentInsight]`:
      - Parse QA failure details + agent handoffs from the completed run
      - For each QA failure that was fixed by an agent:
        - Identify the *root cause agent* (which upstream agent generated the problematic pattern?)
        - Identify the *fixer agent* (which agent corrected it?)
        - Generate insight: "When building for {clients}, avoid {pattern} — {fixer_agent} had to correct it because {reason}"
        - Route insight to root cause agent + code reviewer
      - For each agent that made a structured decision with confidence < 0.7:
        - Generate insight: "Low confidence on {decision_type} for {clients} — consider {alternative}"
      - Deduplication: hash on (source_agent, category, client_ids, insight_core_text) — merge duplicates by incrementing `evidence_count` and updating `last_seen`
    - `persist_insights(insights: list[AgentInsight])`:
      - Store each insight as a semantic memory entry via `MemoryService.store()`:
        - `memory_type="procedural"` (learned pattern)
        - `agent_type` = comma-joined `target_agents` (so target agents can recall it)
        - `metadata = {"source_agent": ..., "client_ids": ..., "category": ..., "evidence_count": ...}`
        - `content` = formatted insight text
      - Use `is_evergreen=True` for insights with `evidence_count >= 5` (stable patterns shouldn't decay)
    - `recall_insights(agent_name: str, client_ids: list[str] | None, categories: list[str] | None) -> list[AgentInsight]`:
      - Query semantic memory with `agent_type` containing `agent_name`
      - Filter by `client_ids` overlap if provided
      - Filter by `category` if provided
      - Return top 5 most relevant (by recency × evidence_count × similarity)
- Modify `app/ai/blueprints/engine.py` — add insight injection layer:
  - New context layer (after Layer 16 cross-agent failure patterns):
    - `cross_agent_insights = insight_bus.recall_insights(agent_name, audience_client_ids, relevant_categories)`
    - Format as:
      ```
      --- CROSS-AGENT INSIGHTS ---
      From dark_mode agent (3 occurrences, Samsung Mail):
        Avoid #1a1a1a backgrounds — Samsung double-inverts to near-white.
      From outlook_fixer agent (5 occurrences, Outlook 365):
        Always add mso-font-alt when using non-system fonts — Outlook falls back to Times New Roman.
      ```
    - Inject into `NodeContext.metadata["cross_agent_insights"]`
  - Post-run hook: after blueprint completes, call `insight_bus.extract_insights(run_result)` → `persist_insights(insights)`
- Modify `app/ai/blueprints/protocols.py` — `BlueprintRunResult`:
  - Add `insights_extracted: int = 0` — count of insights generated this run (for observability)
- Within-run propagation (immediate, same blueprint execution):
  - Modify handoff metadata in `_build_handoff()`:
    - Add `learnings: list[str]` field to handoff — agent can declare "I learned X about this specific email"
    - Downstream agents see `upstream_handoff.learnings` alongside existing `upstream_handoff.constraints`
    - Example: Dark Mode agent's handoff includes `learnings: ["Samsung dark mode inverted the hero background — added explicit data-ogsb override"]`
    - Scaffolder on next retry sees this learning and adjusts generation
**Security:** Insights are derived from internal agent execution data — no user input in insight generation. Memory storage uses existing `MemoryService` with project scoping. Insight content is descriptive text about rendering patterns — no executable code, no PII, no credentials. Cross-agent recall uses existing memory query paths.
**Verify:** Run blueprint with Samsung Mail audience → Dark Mode agent fixes a color issue → insight extracted: `{source: "dark_mode", target: ["scaffolder"], client: "samsung_mail", insight: "..."}` → stored in semantic memory. Next blueprint run for Samsung Mail → Scaffolder agent receives cross-agent insight in context. Insight deduplication: same pattern extracted twice → `evidence_count` increments, no duplicate memory entry. Insight with `evidence_count >= 5` → `is_evergreen=True`. Handoff learnings: Dark Mode handoff includes `learnings` list visible to downstream agents. `make test` passes.

### ~~32.6 Eval-Driven Skill File Updates~~ `[Backend + CI]` DONE
**What:** Build a semi-automated pipeline that monitors agent eval pass rates, detects persistent failure patterns, generates proposed skill file patches grounded in failure evidence, and opens PRs for human review. When an agent's pass rate on a criterion drops below threshold for N consecutive eval runs, the pipeline extracts the failure cluster, drafts a skill file addition, and creates a branch with the proposed change.
**Why:** L3 skill files are static — written once by a developer, updated only when someone remembers to. The eval system (`analysis.json`) already tracks per-agent per-criterion pass rates. Failure warnings are injected as ephemeral prompt text, but they don't improve the underlying skill files. The gap: a failure pattern persists for weeks, the warning text keeps compensating, but the root cause (missing knowledge in the skill file) is never fixed. This pipeline closes the loop — eval data drives permanent skill improvements, reviewed by a human before merge.
**Implementation:**
- Create `app/ai/agents/evals/skill_updater.py`:
  - `SkillUpdateDetector` class:
    - `detect_update_candidates(analysis_path: Path = TRACES_DIR / "analysis.json") -> list[SkillUpdateCandidate]`:
      - Load `analysis.json` (per-agent per-criterion pass rates + failure samples)
      - For each agent + criterion pair:
        - If pass rate < `SKILL_UPDATE_THRESHOLD` (default 0.80) AND failure count >= `MIN_FAILURE_COUNT` (default 5):
          - Extract failure cluster: common patterns in failure reasons (group by text similarity)
          - Create `SkillUpdateCandidate(agent, criterion, pass_rate, failure_count, failure_cluster, sample_reasons)`
      - Return candidates sorted by impact (lowest pass rate × highest failure count)
    - `generate_patch(candidate: SkillUpdateCandidate) -> SkillFilePatch`:
      - Identify the relevant L3 skill file for this agent + criterion:
        - Map criterion → skill file (e.g., "dark_mode_coverage" → `client_behavior.md`, "mso_validity" → `mso_bug_fixes.md`)
        - Maintain mapping in `CRITERION_SKILL_MAP: dict[str, dict[str, str]]` (agent → criterion → skill file path)
      - Generate a proposed addition to the skill file:
        - Format:
          ```markdown
          ## Recently Observed Failure: {cluster_summary}

          **Pattern:** {common_pattern_description}
          **Fix:** {recommended_approach}
          **Evidence:** {failure_count} failures in recent eval runs ({pass_rate}% pass rate).
          **Sample failures:**
          - {reason_1}
          - {reason_2}
          - {reason_3}
          ```
        - The patch content is generated by LLM (single call, temperature=0.0) given: failure samples, existing skill file content, agent name, criterion name
        - LLM is instructed: "Generate a concise, actionable addition to this skill file that addresses the observed failure pattern. Use the same formatting style as the existing file. Do NOT repeat existing content."
      - Return `SkillFilePatch(skill_file_path, patch_content, candidate)`
    - `apply_patches(patches: list[SkillFilePatch], branch_name: str) -> str`:
      - Create git branch: `skill-update/{agent}/{criterion}/{date}`
      - For each patch: append content to the relevant skill file
      - Commit with message: `fix(agents): update {agent} skill file for {criterion} (eval-driven)`
      - Return branch name for PR creation
  - `SkillUpdateCandidate`, `SkillFilePatch` — Pydantic models
- Create `scripts/eval-skill-update.py` (CLI entry point):
  - Parse args: `--dry-run` (print candidates, don't create branch), `--threshold` (override), `--agent` (filter to one agent)
  - Call `SkillUpdateDetector.detect_update_candidates()`
  - If candidates found: call `generate_patch()` for each → `apply_patches()` → log branch name
  - If `--dry-run`: print candidates and proposed patches without git operations
  - Exit code: 0 if no updates needed, 1 if patches generated (for CI gating)
- Add to `Makefile`:
  - `eval-skill-update`: run `scripts/eval-skill-update.py --dry-run` (safe default)
  - `eval-skill-update-apply`: run `scripts/eval-skill-update.py` (creates branch)
- Add tool usage analytics integration (from 32.4):
  - `SkillUpdateDetector` also reads tool call logs from 32.4
  - Frequently queried facts (>10 queries across runs for the same agent + property + client) → candidate for promotion to L2 skill file (always-loaded content)
  - Rarely queried L3 content (loaded but never referenced in agent output) → candidate for demotion or removal
- CI integration (optional, future):
  - After `make eval-full` completes, run `eval-skill-update --dry-run`
  - If candidates found: comment on the eval PR with proposed updates
  - Developer can approve → script creates branch → PR opened
**Security:** LLM-generated skill file patches are text-only (Markdown) — no executable code. Patches are always human-reviewed before merge (PR workflow). The script reads `analysis.json` (internal eval data) and skill files (checked into repo) — no external input. Git operations use standard branching (no force-push, no main branch modification). The LLM call for patch generation uses the same API key and rate limits as eval judges.
**Verify:** Run `make eval-full` → `analysis.json` updated. Run `eval-skill-update --dry-run` → candidates printed for agents with pass rate < 80%. Run `eval-skill-update-apply` → git branch created with skill file patches. Patches are well-formatted Markdown matching existing skill file style. No duplicate content (patch doesn't repeat what's already in the skill file). `make test` passes (no production code changes — this is a dev tooling task).

### 32.7 Visual QA Feedback Loop Tightening `[Backend]`
**What:** Integrate the Visual QA agent more tightly into the blueprint recovery loop by adding a pre-Maizzle visual check stage and a post-render screenshot comparison against the original imported design. When Visual QA detects a rendering defect, route it back to the relevant fixer agent with the screenshot attached (via Layer 20 multimodal context). Add per-client defect reports to the QA gate output.
**Why:** The Visual QA agent exists but sits partially outside the main agent loop. It can detect rendering defects from screenshots (Outlook layout collapse, Gmail style stripping, dark mode inversion, responsive breakage), but the feedback path back to fixer agents is indirect — defects appear in QA results as text descriptions without the visual evidence. Fixer agents (Dark Mode, Outlook Fixer, Accessibility) would be significantly more effective if they could *see* the defect they're fixing. The system already has multimodal context support (Layer 20) — we just need to wire it into the recovery loop. Additionally, post-render screenshot comparison against the original design catches drift that text-based QA checks miss (e.g., subtle spacing changes, color shifts, font rendering differences).
**Implementation:**
- Modify `app/ai/blueprints/nodes/qa_gate_node.py`:
  - Add optional `visual_qa_precheck` stage before the 14 standard QA checks:
    - Feature gate: `BLUEPRINT__VISUAL_QA_PRECHECK=true` (default: false — opt-in to avoid latency impact)
    - When enabled: render the current HTML via `RenderingService.render()` for top 3 target clients (from audience profile)
    - Pass screenshots to Visual QA agent (or run the VLM directly — lighter than full agent invocation)
    - Visual QA returns `VisualDefect` list: `{type, severity, client, bounding_box, description, suggested_agent}`
    - Defects with severity >= "high" are added to the QA failure list alongside standard check results
    - Each defect carries its screenshot reference (content block ID) for downstream injection
  - Modify QA failure routing in `RecoveryRouterNode`:
    - When routing a visual defect to a fixer agent, attach the screenshot via Layer 20 multimodal context:
      - `node_context.metadata["multimodal_context"] = [TextBlock(defect_description), ImageBlock(screenshot)]`
    - Fixer agent sees: "Outlook 365 screenshot shows hero image overflowing container. See attached screenshot." + the actual screenshot
    - Agent can use visual context to generate a more targeted fix
- Create `app/ai/blueprints/nodes/visual_comparison_node.py`:
  - `VisualComparisonNode` — runs after Maizzle build, before final output:
    - Compares rendered email screenshots against:
      - (a) Original imported design screenshot (if available from upload phase — stored in `multimodal_context`)
      - (b) Previous iteration's screenshot (if retry — detect regression)
    - Uses ODiff (already in the stack from Phase 17) for pixel-level comparison
    - Threshold: >5% pixel difference → flag as visual drift
    - Output: `VisualComparisonResult` with `drift_score`, `diff_regions`, `diff_image_path`
    - Advisory only — does not block output, but adds drift warnings to build response
    - Feature gate: `BLUEPRINT__VISUAL_COMPARISON=true` (default: false)
- Modify `app/ai/agents/visual_qa/service.py`:
  - Add `detect_defects_lightweight(screenshot: bytes, client_id: str) -> list[VisualDefect]`:
    - Lighter-weight VLM call than full agent invocation (smaller prompt, focused detection)
    - Returns structured defects without fix recommendations (fixes are the fixer agents' job)
    - Used by the QA gate precheck (fast path)
  - Add `compare_screenshots(original: bytes, rendered: bytes, client_id: str) -> VisualComparisonResult`:
    - VLM-assisted comparison: ODiff for pixel diff + VLM for semantic interpretation
    - "The rendered version has 3% pixel difference. Differences: (1) heading font slightly larger, (2) hero section padding reduced by ~4px."
    - Returns structured result with human-readable explanation
- Modify `app/qa_engine/schemas.py`:
  - Add `VisualDefect` model: `type: str`, `severity: Literal["low", "medium", "high", "critical"]`, `client_id: str`, `description: str`, `suggested_agent: str | None`, `screenshot_ref: str | None`, `bounding_box: dict | None`
  - Add `visual_defects: list[VisualDefect] = []` to `QAGateResult`
- Modify `app/email_engine/schemas.py`:
  - Add `visual_drift: VisualComparisonResult | None = None` to `BuildResponse`
**Security:** Screenshots are rendered from the email HTML already in the pipeline — no external content fetched. VLM calls use the same API key and rate limits as other agent calls. ODiff is a deterministic image comparison tool — no code execution. Screenshots are ephemeral (not persisted unless visual regression baselines are enabled). Feature gates default to off — no latency impact unless opted in.
**Verify:** Enable `BLUEPRINT__VISUAL_QA_PRECHECK=true`. Run blueprint for Outlook audience with a flexbox layout → Visual QA precheck detects "layout collapse in Outlook 365" → routes to Outlook Fixer with screenshot → fixer generates ghost table fix. Disable feature gate → no precheck, standard QA flow. Enable `BLUEPRINT__VISUAL_COMPARISON=true` → after Maizzle build, drift score reported in build response. Original design screenshot available (from upload) → comparison shows <5% drift (acceptable). Force a large change → comparison shows >5% drift + VLM description of differences. `make test` passes. `make bench` shows acceptable latency increase (<2s per visual check).

### 32.8 Tests & Integration Verification `[Full-Stack]`
**What:** Comprehensive tests verifying the full agent intelligence pipeline: centralized matrix queries, tool-based lookups, cross-agent insight propagation, content rendering constraints, import annotator recognition, eval-driven updates, and visual QA feedback.
**Implementation:**
- **Client matrix tests** — `app/knowledge/tests/test_client_matrix.py`:
  - `ClientMatrix.load()` parses `email-client-matrix.yaml` without errors
  - `get_css_support("outlook_365_windows", "flexbox")` → `CSSSupport(support="none", workaround=...)`
  - `get_css_support("apple_mail", "flexbox")` → `CSSSupport(support="full")`
  - `get_dark_mode("gmail_web")` → `DarkModeProfile(type="forced_inversion", developer_control="none")`
  - `get_dark_mode("apple_mail")` → `DarkModeProfile(type="developer_controlled", developer_control="full")`
  - `get_known_bugs("outlook_365_windows")` → list with `ghost_table`, `dpi_scaling`, etc.
  - `format_audience_context(["gmail_web", "outlook_365_windows"])` → string contains "flexbox: unsupported", "102KB clip"
  - `format_audience_context(["apple_mail"])` → no layout restrictions mentioned
  - Unknown client ID → raises `ClientNotFoundError`
  - Matrix validation: all client IDs match emulator system's client ID list
- **Client lookup tool tests** — `app/ai/agents/tools/tests/test_client_lookup.py`:
  - `ClientLookupTool.execute(query_type="css_support", client_id="outlook_365_windows", property="border-radius")` → result with `support="none"`, `workaround` containing "VML"
  - `MultiClientLookupTool.execute(client_ids=["gmail_web", "outlook_365_windows"], properties=["flexbox", "border-radius"])` → 4 results (2×2 matrix)
  - Unknown client → error result with available client list
  - Unknown property → result with `support="unknown"`
  - Tool registered for agentic nodes in blueprint engine
- **Content rendering awareness tests** — `app/ai/agents/content/tests/test_content_rendering.py`:
  - Skill detection: `audience_context` present → `content_rendering_constraints.md` loaded
  - Skill detection: `subject_line` operation → constraints loaded regardless of audience
  - Skill detection: `body_copy` without audience → constraints NOT loaded (L3 not needed)
  - Verify skill file parseable and contains: preheader limits, subject truncation, CTA constraints, character encoding section
- **Import annotator skill tests** — `app/ai/agents/import_annotator/tests/test_annotator_skills.py`:
  - Skill detection: HTML with `esd-structure` class → `common_email_builders.md` loaded
  - Skill detection: HTML with `mc:edit` attribute → `common_email_builders.md` loaded
  - Skill detection: HTML with >5 `!important` → `css_normalization.md` loaded
  - Skill detection: HTML with `%%[` (AMPscript) → `esp_token_edge_cases.md` loaded
  - Skill detection: all HTML → `wrapper_detection.md` loaded (always-on)
  - Verify all 4 new skill files parseable and contain expected sections
- **Cross-agent insight tests** — `app/ai/blueprints/tests/test_insight_bus.py`:
  - `InsightBus.extract_insights()` from a mock run result with QA failure fixed by dark_mode agent → returns insight with `target_agents=["scaffolder"]`
  - `persist_insights()` stores insight in semantic memory with correct `agent_type` tag
  - `recall_insights("scaffolder", ["samsung_mail"])` → returns insights tagged for scaffolder + samsung_mail
  - Deduplication: same insight extracted twice → `evidence_count` incremented, single memory entry
  - Insight with `evidence_count >= 5` → `is_evergreen=True`
  - Context injection: insight appears in `NodeContext.metadata["cross_agent_insights"]`
  - Handoff learnings: agent handoff includes `learnings` list
- **Eval skill updater tests** — `app/ai/agents/evals/tests/test_skill_updater.py`:
  - `detect_update_candidates()` with mock `analysis.json` (agent at 70% pass rate, 8 failures) → returns candidate
  - `detect_update_candidates()` with all agents above threshold → returns empty list
  - `generate_patch()` produces valid Markdown with expected structure (## header, **Pattern:**, **Fix:**, **Evidence:**)
  - `--dry-run` mode prints candidates without git operations
  - Criterion-to-skill-file mapping covers all agent + criterion pairs
- **Visual QA integration tests** — `app/ai/blueprints/tests/test_visual_qa_feedback.py`:
  - Feature gate off → no visual precheck, standard QA flow
  - Feature gate on → `detect_defects_lightweight()` called with rendered screenshot
  - Visual defect with severity "high" → added to QA failure list → routes to fixer agent
  - Fixer agent receives `multimodal_context` with screenshot
  - Visual comparison: ODiff <5% → `drift_score` below threshold
  - Visual comparison: ODiff >5% → `drift_score` above threshold + description
- **Audience context integration test** — `app/ai/blueprints/tests/test_audience_context_matrix.py`:
  - `audience_context.py` produces identical output format before and after migration to `ClientMatrix`
  - Regression test: compare output of old hardcoded function vs new matrix-backed function for all 14 client profiles
  - Output diff = zero (format compatibility preserved)
**Security:** Tests only. No production code changes. Mock data contains no real credentials or PII. VLM calls in visual QA tests use test fixtures (pre-captured screenshots), not live rendering.
**Verify:** `make test` passes (all new test files). `make check` all green. `make bench` shows no performance regression in non-visual-QA code paths. Agent prompt token counts with tool access < agent prompt token counts with full L3 skill files (measured via test). Cross-agent insight recall latency < 50ms (semantic memory query). Client matrix lookup latency < 1ms.

### ~~32.9 MCP Server Exposure for Agent Tools~~ `[Backend + Integration]` DONE
**What:** Expose all 9 production agents as MCP (Model Context Protocol) tools via a stdio-based MCP server, so coding agents (Claude Code, Cursor, Windsurf) can invoke email generation, dark mode processing, accessibility fixes, and code review directly from the IDE without going through the REST API. Package as `email-hub-mcp` binary alongside the existing FastAPI server.
**Why:** The current integration surface is REST-only — developers must use the web UI or make API calls. Coding agents like Claude Code already support MCP tool calling natively. When a developer is editing an email template in their IDE, they should be able to ask their coding agent "fix Outlook rendering" and have it call the Outlook Fixer agent directly, receiving structured results in-context. This eliminates the tab-switch to the web UI, enables agent-to-agent composition (Claude Code orchestrating email-hub agents as tools), and opens the door for community integrations. The pattern is proven: Context Hub (open-source doc platform) uses exactly this architecture — CLI + MCP server exposing search/get/annotate tools via `@modelcontextprotocol/sdk`, with Zod schema validation and structured error responses. Email-hub can follow the same pattern but expose domain-specific agent tools instead of doc retrieval.
**Implementation:**
- Create `app/mcp/server.py`:
  - Use `mcp` Python SDK (`pip install mcp`) with stdio transport
  - Redirect stdout to stderr (MCP uses stdout for JSON-RPC — all logging must go to stderr)
  - Register one tool per agent:
    ```python
    @server.tool("email_scaffold", "Generate Maizzle email HTML from a campaign brief")
    async def handle_scaffold(brief: str, brand: str | None = None,
                               output_mode: str = "html") -> ToolResult:
        service = get_scaffolder_service()
        request = ScaffolderRequest(brief=brief, brand_voice=brand, output_mode=output_mode)
        result = await service.run(request)
        return text_result({"html": result.html, "confidence": result.confidence,
                           "qa_passed": result.qa_passed, "warnings": result.warnings})

    @server.tool("email_dark_mode", "Generate dark mode styles for email HTML")
    async def handle_dark_mode(html: str, target_clients: list[str] | None = None) -> ToolResult:
        ...

    @server.tool("email_content", "Generate email copy: subject lines, CTAs, body text")
    async def handle_content(operation: str, text: str, tone: str | None = None,
                              num_alternatives: int = 3) -> ToolResult:
        ...

    @server.tool("email_outlook_fix", "Fix Outlook rendering issues in email HTML")
    async def handle_outlook_fix(html: str) -> ToolResult:
        ...

    @server.tool("email_accessibility", "Add alt text and WCAG improvements to email HTML")
    async def handle_accessibility(html: str) -> ToolResult:
        ...

    @server.tool("email_code_review", "Review email HTML for quality and compatibility issues")
    async def handle_code_review(html: str) -> ToolResult:
        ...

    @server.tool("email_personalise", "Add dynamic content blocks to email HTML")
    async def handle_personalise(html: str, esp: str | None = None) -> ToolResult:
        ...

    @server.tool("email_innovate", "Suggest structural improvements for email HTML")
    async def handle_innovate(html: str) -> ToolResult:
        ...

    @server.tool("email_knowledge", "Look up brand/product knowledge for email content")
    async def handle_knowledge(query: str, brand: str | None = None) -> ToolResult:
        ...
    ```
  - Each handler follows the pattern: validate input → build domain request → call service singleton → format structured result → return `text_result()` or `error_result()`
  - Tool parameter schemas use Pydantic models converted to JSON Schema (reuse existing `schemas.py` per agent)
- Create `app/mcp/helpers.py`:
  - `text_result(data: dict) -> ToolResult` — wraps response as MCP content block
  - `error_result(message: str) -> ToolResult` — wraps error with `isError=True`
  - `html_result(html: str, metadata: dict) -> ToolResult` — returns HTML as a separate content block for easy extraction by the calling agent
- Create `bin/email-hub-mcp` entry point:
  - Loads config, initializes services (same startup as FastAPI but without HTTP server)
  - Starts MCP server on stdio transport
  - Graceful shutdown on SIGTERM/SIGINT
- Add MCP resource: `email-hub://agents` — returns list of available agents with capabilities, model tiers, and supported operations (analogous to Context Hub's `chub://registry` resource)
- Add to `pyproject.toml`:
  - `[project.scripts]` entry: `email-hub-mcp = "app.mcp.server:main"`
  - Add `mcp` dependency
- Create `mcp-config.example.json` for Claude Code integration:
  ```json
  {
    "mcpServers": {
      "email-hub": {
        "command": "email-hub-mcp",
        "env": {
          "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
          "EMAIL_HUB_DB_URL": "${EMAIL_HUB_DB_URL}"
        }
      }
    }
  }
  ```
- Rate limiting: reuse existing `RateLimiter` from the FastAPI layer — same per-agent limits apply via MCP as via REST
- Authentication: MCP runs locally (stdio) so no API key auth needed — the user's own environment credentials are used for LLM calls
**Security:** MCP stdio transport is local-only — no network exposure. Tool inputs are validated through the same Pydantic schemas as REST endpoints (XSS sanitization, length limits, input validation all apply). No new attack surface beyond what the REST API already exposes. LLM API keys come from the user's environment, not from the MCP protocol. Tool results contain HTML output — same sanitization profile as REST responses.
**Verify:** `email-hub-mcp` starts without errors. Claude Code can discover all 9 tools via MCP handshake. Calling `email_scaffold` with a brief → returns valid HTML with confidence score. Calling `email_code_review` with HTML → returns structured review. Calling `email_content` with `operation="subject_line"` → returns alternatives list. Error cases: invalid operation → `error_result` with message. Missing required params → MCP validation error. `email-hub://agents` resource → returns agent list with capabilities. `make test` passes.

### ~~32.10 Skill Versioning with Rollback~~ `[Backend]` DONE
**What:** Add version metadata to all L3 skill file frontmatter, implement version tracking in the skill loader, and provide a rollback mechanism that can pin a project to a previous skill file version when a 32.6 eval-driven update causes a regression. Store version history in a `skill-versions.yaml` manifest per agent directory.
**Why:** Phase 32.6 introduces automated skill file patching — the eval pipeline detects failure patterns, generates patches, and opens PRs. But once merged, there's no clean rollback path beyond `git revert`. If a skill patch improves pass rate on one criterion but regresses another (common with prompt changes), the team needs to: (a) know which version of the skill file was active during a given eval run, (b) quickly revert to the prior version without touching git history, and (c) A/B test the old vs new version using the existing `skill_override.py` infrastructure. Without versioning, the 32.6 pipeline creates churn — patches get merged, regress, get reverted, get re-applied. Versioning adds the control surface that makes 32.6's automation safe to trust.
**Implementation:**
- Add version metadata to L3 skill file frontmatter:
  ```yaml
  ---
  token_cost: 1500
  priority: 2
  version: "1.2.0"
  updated: "2026-03-20"
  changelog:
    - "1.2.0: Added Samsung double-inversion workaround (eval-driven, 32.6)"
    - "1.1.0: Expanded Outlook.com data-ogsc selector examples"
    - "1.0.0: Initial release"
  ---
  ```
- Create `skill-versions.yaml` manifest per agent:
  ```yaml
  # app/ai/agents/dark_mode/skill-versions.yaml
  skills:
    client_behavior:
      current: "1.2.0"
      pinned: null  # null = use current, or "1.1.0" to pin
      versions:
        "1.2.0":
          hash: "a3f8c2d"  # git short hash of the commit that introduced this version
          date: "2026-03-20"
          source: "eval-driven"  # or "manual"
          eval_pass_rate: 0.87  # pass rate at time of introduction
        "1.1.0":
          hash: "b7e1f4a"
          date: "2026-03-01"
          source: "manual"
          eval_pass_rate: 0.82
        "1.0.0":
          hash: "c9d2e5b"
          date: "2026-01-15"
          source: "manual"
          eval_pass_rate: null
    dark_mode_queries:
      current: "1.0.0"
      pinned: null
      versions:
        "1.0.0":
          hash: "c9d2e5b"
          date: "2026-01-15"
          source: "manual"
          eval_pass_rate: null
  ```
- Modify `app/ai/agents/skill_loader.py`:
  - `load_skill_file(agent_name, skill_name)`:
    - Read `skill-versions.yaml` for the agent
    - If `pinned` is set for this skill → load the pinned version from git (`git show {hash}:{skill_file_path}`)
    - If `pinned` is null → load current file from disk (existing behavior)
    - Add `loaded_version` to the skill metadata returned to the agent (appears in `skills_loaded` response field)
  - `pin_skill(agent_name, skill_name, version: str)` → sets `pinned` in `skill-versions.yaml`
  - `unpin_skill(agent_name, skill_name)` → clears `pinned` (resume using current)
  - `list_skill_versions(agent_name, skill_name) -> list[SkillVersion]` → returns version history with eval pass rates
- Modify `app/ai/agents/evals/skill_updater.py` (32.6 integration):
  - After `generate_patch()`: bump version in skill file frontmatter (semver minor bump)
  - After `apply_patches()`: update `skill-versions.yaml` with new version entry including git hash and current eval pass rate
  - Add `--rollback` flag to `scripts/eval-skill-update.py`:
    - `--rollback {agent} {skill} {version}` → pins skill to specified version, logs reason
    - Validates version exists in manifest before pinning
- Modify `app/ai/agents/skill_override.py` — version-aware override:
  - `set_override_from_version(agent_name, skill_name, version: str)`:
    - Loads skill content from git at the specified version hash
    - Sets it as the active override (same mechanism as A/B testing)
    - Enables comparing two versions head-to-head in eval runs without changing the on-disk file
- Add to `Makefile`:
  - `skill-versions`: list all agents' skill versions and pin status
  - `skill-pin`: pin a skill to a version (`make skill-pin AGENT=dark_mode SKILL=client_behavior VERSION=1.1.0`)
  - `skill-unpin`: unpin a skill (`make skill-unpin AGENT=dark_mode SKILL=client_behavior`)
- Backfill: create initial `skill-versions.yaml` for all 9 agents with current files as `1.0.0`, `hash` = current HEAD, `pinned = null`
**Security:** Version pinning reads skill file content via `git show` — no shell injection risk (hash and path are validated against the manifest). `skill-versions.yaml` is checked into the repo — changes are reviewed via PR. Pinning does not modify skill files on disk — it loads an older version at runtime only. No new API endpoints.
**Verify:** `load_skill_file("dark_mode", "client_behavior")` with no pin → loads current file, returns `loaded_version: "1.2.0"`. Pin to `1.1.0` → loads content from git hash `b7e1f4a`, returns `loaded_version: "1.1.0"`. Unpin → resumes loading current. `eval-skill-update-apply` → bumps version in frontmatter and updates manifest. `--rollback dark_mode client_behavior 1.1.0` → pins and logs. `set_override_from_version` → loads old version as override for A/B eval. `make skill-versions` → prints table of all agents' skill versions. `make test` passes.

### 32.11 Per-Client Skill Overlays `[Backend]`
**What:** Allow project-level skill file overlays that extend or override core agent L3 skills with client-specific behavioral guidance. A project linked to brand "Acme Corp" can have custom skill files at `data/clients/acme/agents/scaffolder/skills/brand_patterns.md` that are loaded alongside (or instead of) core skills when processing that project's emails. Integrate with the existing skill loader's budget-aware progressive disclosure system.
**Why:** The centralized client matrix (32.1) solves data duplication for email client rendering facts, but different brands need different agent *behaviors* — not just different data. Acme Corp's brand guidelines require 2-column layouts with a hero image pattern that the Scaffolder should follow; BrandX prefers single-column with heavy typography. The Content agent's tone for a luxury brand differs from a SaaS product. Currently, per-brand customization only happens through L4 knowledge (brand guidelines fetched at runtime) — but L4 is unstructured RAG retrieval, not curated skill instructions. Brand-specific L3 overlays provide structured, version-controlled, budget-aware behavioral customization that slots into the existing skill loading pipeline. This also supports agency use cases where email-hub serves multiple clients from a single deployment.
**Implementation:**
- Define overlay directory structure:
  ```
  data/clients/
  └── acme/
      └── agents/
          ├── scaffolder/
          │   └── skills/
          │       └── brand_patterns.md      # Acme-specific layout patterns
          ├── content/
          │   └── skills/
          │       └── brand_voice.md         # Acme tone & style override
          └── dark_mode/
              └── skills/
                  └── brand_colors.md        # Acme dark mode color mappings
  ```
- Skill file frontmatter for overlays:
  ```yaml
  ---
  token_cost: 800
  priority: 1
  overlay_mode: "extend"  # "extend" (append to core) or "replace" (substitute core skill)
  replaces: null           # skill name to replace when overlay_mode="replace", e.g., "brand_voice"
  client_id: "acme"
  ---
  ```
  - `extend` (default): overlay content is appended after the core skill file content. Both are loaded within the same budget allocation. Use for additive brand guidance.
  - `replace`: overlay completely substitutes the named core skill file. The core skill's `token_cost` budget is freed and reallocated to the overlay. Use when brand guidelines fundamentally contradict core defaults (e.g., brand insists on patterns the core skill file advises against).
- Modify `app/ai/agents/skill_loader.py`:
  - `discover_overlays(agent_name: str, client_id: str | None) -> dict[str, OverlaySkill]`:
    - If `client_id` is None → return empty (no overlays)
    - Scan `data/clients/{client_id}/agents/{agent_name}/skills/` for `.md` files
    - Parse frontmatter → return mapping of skill name → `OverlaySkill(content, mode, replaces, token_cost, priority)`
    - Cache per `(agent_name, client_id)` pair — overlays don't change at runtime
  - Modify `load_skills_for_agent(agent_name, request, client_id=None)`:
    - After loading core L3 skills via `detect_relevant_skills()`:
      - Call `discover_overlays(agent_name, client_id)`
      - For each overlay with `mode="replace"`: remove the named core skill from the loaded set, add overlay in its place
      - For each overlay with `mode="extend"`: append overlay content to the end of the loaded skill set
      - Budget accounting: overlay `token_cost` counts against the agent's `skill_docs_max` budget (same as core skills)
      - Priority ordering: overlays respect the same priority system (1=critical, 2=standard, 3=supplementary) — under budget pressure, low-priority overlays are dropped before high-priority core skills
    - Add `overlays_loaded: list[str]` to skill loading metadata (returned in agent response's `skills_loaded` field as `"overlay:acme/brand_patterns"`)
- Modify `app/ai/agents/base.py` — `BaseAgentService.run()`:
  - Extract `client_id` from request metadata (project → client mapping from database)
  - Pass `client_id` to skill loading pipeline
  - No changes to agent prompt building — overlays are transparent to the agent (they appear as additional or replacement skill content)
- Modify `app/ai/blueprints/engine.py`:
  - Extract `client_id` from project context at blueprint start
  - Pass through `NodeContext.metadata["client_id"]` to all agent nodes
  - Agent nodes pass `client_id` to their service's `run()` method
- Create `scripts/validate-overlays.py`:
  - Validates all overlay files in `data/clients/`:
    - Frontmatter is valid (required fields present, `overlay_mode` is valid enum)
    - `replaces` skill name exists in the core agent's `SKILL_FILES` mapping (catch typos)
    - `token_cost` is within budget (overlay + remaining core skills ≤ `skill_docs_max`)
    - No conflicting overlays (two overlays both replacing the same core skill)
  - Run as part of `make check` and as a pre-commit hook
- Add to `Makefile`:
  - `validate-overlays`: run `scripts/validate-overlays.py`
  - `list-overlays`: list all client overlays grouped by client and agent
- Create starter overlay for documentation/testing:
  - `data/clients/_example/agents/content/skills/brand_voice.md`:
    ```yaml
    ---
    token_cost: 500
    priority: 2
    overlay_mode: "extend"
    client_id: "_example"
    ---
    ## Example Brand Voice Overlay

    This is a template for creating client-specific content agent overlays.
    Replace this content with the client's brand voice guidelines.

    **Tone:** [Professional / Casual / Playful / Authoritative]
    **Vocabulary:** [Industry-specific terms to use or avoid]
    **CTA style:** [Direct / Soft / Question-based]
    ```
**Security:** Overlay files are checked into the repo under `data/clients/` — changes go through PR review. No user input reaches the overlay loader (client_id comes from the database project record, not from the request body). Overlay content is treated identically to core skill content — same sanitization, same budget limits, same token counting. `validate-overlays.py` catches malformed files before they reach production. The `replace` mode cannot inject content outside the skill loading pipeline — it only substitutes one skill file for another within the existing budget. No new API endpoints.
**Verify:** Project linked to client "acme" → Scaffolder loads core skills + `brand_patterns.md` overlay (extend mode). Response `skills_loaded` includes `"overlay:acme/brand_patterns"`. Project with no client → no overlays loaded. Overlay with `mode="replace"` and `replaces="brand_voice"` → core `brand_voice.md` not loaded, overlay loaded instead. Budget pressure: overlay has `priority=3`, budget < 70% → overlay dropped. `validate-overlays.py` catches: missing frontmatter fields, `replaces` pointing to nonexistent skill, two overlays replacing the same skill. `_example` overlay loads without errors. `make test` passes. `make validate-overlays` passes.

### 32.12 Tests for 32.9–32.11 `[Full-Stack]`
**What:** Tests covering MCP server exposure, skill versioning, and per-client skill overlays.
**Implementation:**
- **MCP server tests** — `app/mcp/tests/test_mcp_server.py`:
  - MCP server starts and completes handshake (tool listing)
  - All 9 agent tools registered with correct parameter schemas
  - `email_scaffold` tool call with valid brief → returns HTML + confidence + qa_passed
  - `email_content` tool call with `operation="subject_line"` → returns alternatives list
  - `email_code_review` tool call with HTML → returns structured review results
  - Invalid operation → `error_result` with descriptive message
  - Missing required parameter → MCP validation error (not a crash)
  - `email-hub://agents` resource → returns JSON with 9 agents, each with name, capabilities, model_tier
  - Rate limiting applies: rapid successive calls → rate limit error after threshold
- **Skill versioning tests** — `app/ai/agents/tests/test_skill_versioning.py`:
  - `load_skill_file()` with no pin → loads current version from disk, returns correct `loaded_version`
  - `pin_skill("dark_mode", "client_behavior", "1.1.0")` → updates `skill-versions.yaml`
  - `load_skill_file()` after pin → loads content from git hash, returns pinned version
  - `unpin_skill()` → clears pin, resumes loading current
  - `list_skill_versions()` → returns version history with eval pass rates
  - Pin to nonexistent version → raises `VersionNotFoundError`
  - `set_override_from_version()` → loads old version content as override
  - `eval-skill-update-apply` → bumps version in frontmatter, updates manifest with new entry
  - `--rollback` flag → pins skill and logs reason
  - Backfill: all 9 agents have `skill-versions.yaml` with `1.0.0` entries
- **Per-client overlay tests** — `app/ai/agents/tests/test_skill_overlays.py`:
  - `discover_overlays("scaffolder", "acme")` → finds overlay files in `data/clients/acme/agents/scaffolder/skills/`
  - `discover_overlays("scaffolder", None)` → returns empty dict
  - `discover_overlays("scaffolder", "nonexistent")` → returns empty dict
  - Extend mode: core skill + overlay both loaded, overlay appended after core content
  - Replace mode: core skill removed, overlay loaded in its place
  - Budget accounting: overlay `token_cost` deducted from `skill_docs_max`
  - Priority drop: overlay with `priority=3` dropped when budget < 70%
  - `skills_loaded` response includes `"overlay:acme/brand_patterns"` for extend, replaces core entry for replace
  - `validate-overlays.py` rejects: missing `overlay_mode`, invalid `replaces` target, duplicate replacements
  - `validate-overlays.py` passes for `_example` overlay
  - Caching: `discover_overlays` called twice with same args → second call uses cache
**Security:** Tests only. No production code changes. Test fixtures use `_example` client and mock skill files — no real client data. Git operations in versioning tests use test repo fixtures.
**Verify:** `make test` passes (all new test files). `make check` all green. `make validate-overlays` passes.


---

## ~~Phase 34 — CRAG Accept/Reject Gate~~ DONE

> The CRAG validation loop (Phase 16.5) detects unsupported CSS in agent-generated HTML, retrieves ontology fallbacks, and asks the LLM to apply them. But its acceptance gate is blind: if the corrected output is longer than 50 characters, it ships. The LLM can break MSO conditionals, drop sections, introduce new unsupported CSS, or bloat past Gmail's 102KB clip threshold — and CRAG will accept it. QA catches these regressions *after* CRAG, but by then the original pre-CRAG HTML is gone. The response ships with the damaged version plus QA warnings.
>
> This phase adds a before/after compatibility check: re-run `unsupported_css_in_html()` on the corrected output and reject corrections that didn't reduce qualifying issues. Zero LLM cost — the function is a pure regex scan already imported in the same file. Also adds structured logging for observability and targeted tests for the new gate.
>
> **Dependency note:** Independent of Phases 32–33. Can be implemented at any time. The fix is contained to `validation_loop.py` + its test file.

- [x] ~~34.1 Accept/reject gate on CRAG corrections~~ DONE
- [x] ~~34.2 Structured CRAG observability logging~~ DONE
- [x] ~~34.3 Tests for accept/reject gate~~ DONE

### 34.1 Accept/Reject Gate on CRAG Corrections `[Backend]`
**What:** After CRAG calls the LLM and extracts corrected HTML, re-scan the corrected output with `unsupported_css_in_html()` using the same severity threshold. Compare qualifying issue counts before vs. after. Only accept the correction if the post-correction count is strictly lower. Otherwise reject and return the original HTML unchanged.
**Why:** The current acceptance gate (`validation_loop.py:129-131`) only checks `len(corrected) < 50`. This means any non-trivial LLM output is accepted regardless of whether it actually fixed the compatibility issues or introduced new ones. The LLM is instructed to "preserve all other HTML exactly as-is" but frequently: (1) breaks MSO conditional balancing while swapping CSS properties, (2) drops sections or structural elements during the rewrite, (3) introduces new unsupported CSS alongside the fallback code, (4) inflates HTML size with verbose table fallbacks. All of these produce output >50 chars, so they pass the current gate. `unsupported_css_in_html()` is already imported and called 10 lines earlier in the same method — reusing it adds zero new dependencies and near-zero latency (pure regex scan over CSS contexts).
**Implementation:**
- In `app/ai/agents/validation_loop.py`, after the existing length gate (line 129–131) and before the success log (line 133), add post-correction scanning:
  ```python
  # Accept/reject gate: verify correction actually improved compatibility
  post_issues = unsupported_css_in_html(corrected)
  post_qualifying = [
      issue for issue in post_issues
      if severity_order.get(str(issue["severity"]), 2) <= threshold
  ]

  if len(post_qualifying) >= len(qualifying):
      logger.warning(
          "agents.crag.correction_rejected",
          pre_issues=len(qualifying),
          post_issues=len(post_qualifying),
          reason="correction did not reduce qualifying issues",
      )
      return html, []
  ```
- The `severity_order` and `threshold` variables are already in scope from step 2 of the method — no new locals needed
- The `qualifying` list (pre-correction issues) is already computed at line 48–50 — reuse it for the comparison
- Keep the existing `len(corrected) < 50` gate above this new gate — it's a fast short-circuit for degenerate outputs that avoids the regex scan entirely
- Move the `corrections` list construction and success log below the new gate so they only execute on accepted corrections
**Security:** No new input paths. `unsupported_css_in_html()` operates on sanitized HTML (already passed through `extract_html()` + `sanitize_html_xss()` at line 126–127). No new LLM calls, no new config, no new dependencies.
**Verify:** Unit test: CRAG correction that introduces new unsupported CSS → rejected, original returned. Unit test: CRAG correction that fixes 2 of 3 issues but adds 1 new → net reduction, accepted. Unit test: CRAG correction that fixes all issues → accepted. Existing tests still pass (the new gate is transparent when corrections improve things). `make check` passes.

### 34.2 Structured CRAG Observability Logging `[Backend]`
**What:** Enhance CRAG logging to emit structured fields that enable monitoring correction acceptance rates, rejection reasons, and per-property fix effectiveness.
**Why:** Currently CRAG logs `agents.crag.correction_applied` on success and `agents.crag.output_too_short` on length failure — but there's no visibility into *what* was fixed vs. *what* regressed. When the accept/reject gate starts rejecting corrections, operators need to understand: which CSS properties are the LLM failing to fix? Which fallback techniques produce regressions? Is the rejection rate climbing (suggesting prompt degradation or ontology drift)? Structured logging fields enable dashboards and alerting without log parsing.
**Implementation:**
- Update the success log (`agents.crag.correction_applied`) to include before/after counts and per-property outcomes:
  ```python
  logger.info(
      "agents.crag.correction_accepted",
      pre_issues=len(qualifying),
      post_issues=len(post_qualifying),
      issues_fixed=len(qualifying) - len(post_qualifying),
      corrections=corrections,
      original_length=len(html),
      corrected_length=len(corrected),
  )
  ```
- The rejection log (`agents.crag.correction_rejected`) added in 34.1 already includes `pre_issues`, `post_issues`, and `reason` — no changes needed
- Update `agents.crag.issues_detected` to include property IDs for correlation:
  ```python
  logger.info(
      "agents.crag.issues_detected",
      total_issues=len(issues),
      qualifying_issues=len(qualifying),
      qualifying_property_ids=[str(i["property_id"]) for i in qualifying],
      min_severity=min_severity,
  )
  ```
- Rename `agents.crag.correction_applied` → `agents.crag.correction_accepted` for symmetry with `agents.crag.correction_rejected`
- Update the `base.py` caller log at line 313 to use the same event name:
  ```python
  logger.info(
      f"agents.{self.agent_name}.crag_accepted",
      corrections=crag_corrections,
  )
  ```
**Security:** Logging only — no new endpoints, no PII in log fields (property IDs and counts only). Verify no CSS values (which could contain user content) appear in log output.
**Verify:** Enable CRAG, trigger a correction → `agents.crag.correction_accepted` log includes `pre_issues`, `post_issues`, `issues_fixed`. Trigger a rejection → `agents.crag.correction_rejected` log includes `pre_issues`, `post_issues`, `reason`. Grep production log output for PII — none found in CRAG events. `make check` passes.

### 34.3 Tests for Accept/Reject Gate `[Backend]`
**What:** Add targeted tests in `app/ai/agents/tests/test_validation_loop.py` covering the new accept/reject gate behavior: regressions rejected, partial improvements accepted, full fixes accepted, and edge cases (same count, new property types).
**Why:** The existing test suite (`TestCRAGMixin`) covers: no issues, severity filtering, successful correction, LLM failure, empty output, no-fallback instructions, and severity threshold. None of these tests verify that a "successful" LLM call with bad output gets rejected. The accept/reject gate is the critical safety mechanism — it must be tested explicitly.
**Implementation:**
- Add new test class `TestCRAGAcceptRejectGate` in `test_validation_loop.py`:
  ```python
  class TestCRAGAcceptRejectGate:
      """Test the before/after compatibility gate."""

      @pytest.mark.asyncio
      async def test_correction_introducing_new_issues_rejected(self) -> None:
          """LLM 'fixes' flex but introduces gap → same issue count → rejected."""
          # Pre: 1 qualifying issue (display:flex)
          # Post: 1 qualifying issue (gap) — different property, same count
          # Expected: rejection, original returned

      @pytest.mark.asyncio
      async def test_correction_increasing_issues_rejected(self) -> None:
          """LLM output has MORE issues than input → rejected."""
          # Pre: 1 qualifying issue
          # Post: 2 qualifying issues
          # Expected: rejection, original returned

      @pytest.mark.asyncio
      async def test_partial_fix_accepted(self) -> None:
          """LLM fixes 2 of 3 issues → net reduction → accepted."""
          # Pre: 3 qualifying issues
          # Post: 1 qualifying issue
          # Expected: accepted, corrected HTML returned

      @pytest.mark.asyncio
      async def test_full_fix_accepted(self) -> None:
          """LLM fixes all issues → 0 post issues → accepted."""
          # Pre: 2 qualifying issues
          # Post: 0 qualifying issues
          # Expected: accepted, corrected HTML returned

      @pytest.mark.asyncio
      async def test_length_gate_runs_before_compatibility_gate(self) -> None:
          """Empty output rejected by length gate — compatibility scan never runs."""
          # LLM returns "" → length gate rejects → unsupported_css_in_html not called on ""
  ```
- Mock strategy: patch `unsupported_css_in_html` with `side_effect` that returns different results for the original HTML vs. the corrected HTML. Use the call order (first call = pre-scan on original, inside the method at line 43; the pre-scan result is already captured in `qualifying`) — but since `unsupported_css_in_html` is called TWICE now (once on original at line 43, once on corrected after the new gate), the mock's `side_effect` can return `[issue_list_1, issue_list_2]` to simulate before/after.
- Verify that rejected corrections return `(original_html, [])` — empty corrections list signals no changes applied
- Verify that accepted corrections return `(corrected_html, [property_ids])` — non-empty corrections list
**Security:** Tests only — no production code paths, no PII, no real LLM calls.
**Verify:** `python -m pytest app/ai/agents/tests/test_validation_loop.py -v` — all existing + new tests pass. `make check` passes. No test relies on real ontology data (all mocked).


---

## ~~Phase 35 — Next-Gen Design-to-Email Pipeline (MJML + AI Intelligence + Standards)~~ ALL DONE

> **The design-to-email pipeline (Phases 31–33) works end-to-end but has structural limitations.** The converter (`converter.py`) hand-rolls every email HTML pattern — ghost tables, MSO conditionals, responsive column stacking, VML buttons — duplicating battle-tested logic that MJML already handles. The layout analyzer classifies sections by naming convention heuristics that fail on arbitrarily-named Figma frames. There's no visual fidelity validation (no comparison between Figma design and converted output). Token input is Figma-only (no W3C Design Tokens standard). Sync is manual (no Figma webhooks). And AI agents fix converter mistakes repeatedly without feeding corrections back into the converter itself.
>
> This phase addresses all of these with 5 pillars: **(1)** MJML as an intermediate representation — offload responsive email compilation to a mature library, **(2)** Figma node tree normalization — clean input produces better output, **(3)** AI-powered layout intelligence — LLM fallback for unclassifiable sections + vision-based fidelity scoring + self-improving converter, **(4)** W3C Design Tokens + caniemail.com data — standards compliance and live client support data, **(5)** Figma webhooks + incremental conversion — real-time sync with section-level caching.
>
> **Dependency note:** Builds on Phase 33 (token pipeline) and Phase 27 (rendering infrastructure). Independent of Phase 32 (agent intelligence) and Phase 34 (CRAG gate). The MJML sidecar endpoint (35.1) is prerequisite for all MJML subtasks. AI subtasks (35.5–35.7) can run in parallel with MJML work.

- [x] ~~35.1 MJML compilation service in Maizzle sidecar~~ DONE
- [x] ~~35.2 Figma node tree normalizer~~ DONE
- [x] ~~35.3 MJML generation backend in converter~~ DONE
- [x] ~~35.4 MJML email section templates~~ DONE
- [x] ~~35.5 AI layout intelligence & semantic detection~~ DONE
- [x] ~~35.6 AI visual fidelity scoring pipeline~~ DONE
- [x] ~~35.7 AI conversion learning loop~~ DONE
- [x] ~~35.8 W3C Design Tokens & caniemail.com integration~~ DONE
- [x] ~~35.9 Figma webhooks & live preview sync~~ DONE
- [x] ~~35.10 Incremental conversion & section caching~~ DONE
- [x] ~~35.11 Tests & integration verification~~ DONE

### 35.1 MJML Compilation Service in Maizzle Sidecar `[Sidecar]`
**What:** Add MJML as an npm dependency to the Maizzle sidecar and expose a `POST /compile-mjml` endpoint that accepts MJML markup and returns compiled, production-ready email HTML with inline CSS, MSO conditionals, and responsive media queries.
**Why:** MJML (`mjmlio/mjml`, MIT, ~17k GitHub stars) is the industry standard for email HTML compilation. It handles the hardest parts of email rendering — responsive column stacking, ghost tables for Outlook, MSO conditional comments, CSS inlining, image sizing, `@media` queries — with output battle-tested across 50+ email clients. Our converter currently hand-rolls all of these patterns in `converter.py:_render_multi_column_row()`, `node_to_email_html()`, and the `EMAIL_SKELETON` template. MJML compilation eliminates ~60% of the low-level HTML generation code and produces more reliable output. The Maizzle sidecar already runs Node.js and accepts HTML via HTTP — adding MJML is a natural extension.
**Implementation:**
- Add `mjml` npm dependency to `services/maizzle-builder/package.json` (MIT license, ~2MB)
- Add `POST /compile-mjml` endpoint to `services/maizzle-builder/index.js`:
  ```
  Request:  { mjml: string, options?: { minify?: bool, beautify?: bool, validationLevel?: "strict"|"soft"|"skip" } }
  Response: { html: string, errors: MjmlError[], build_time_ms: number }
  ```
- MJML compilation options: `keepComments: false`, `fonts: {}` (we inject font links ourselves), `minify: production`, `validationLevel: "soft"` (warn but don't fail on custom attributes like `data-slot-name`)
- After MJML compilation, run existing `postcss-email-optimize.js` if `target_clients` provided — MJML output still benefits from ontology-driven CSS elimination
- Add health check extension: `GET /health` response includes `mjml_version` field
- Wire `MaizzleClient` in `app/design_sync/converter_service.py` to call the new endpoint via the existing HTTP client pattern used for `/build`
- Add `compile_mjml()` method to `MaizzleClient`:
  ```python
  async def compile_mjml(self, mjml: str, *, minify: bool = True, target_clients: list[str] | None = None) -> MjmlCompileResult
  ```
- `MjmlCompileResult` dataclass: `html: str`, `errors: list[MjmlError]`, `build_time_ms: float`
**Security:** MJML is a template compiler — no network calls, no eval, no file system access. Input is our own generated MJML (not user-provided). Output is HTML that still passes through `sanitize_html_xss()` before reaching users. No new attack surface.
**Verify:** `POST /compile-mjml` with `<mjml><mj-body><mj-section><mj-column><mj-text>Hello</mj-text></mj-column></mj-section></mj-body></mjml>` returns valid HTML with `<table>` layout, MSO conditionals, and inline CSS. Invalid MJML returns errors array. `/health` includes `mjml_version`. Existing `/build` and `/preview` endpoints unchanged. `npm test` passes in sidecar.

### 35.2 Figma Node Tree Normalizer `[Backend]`
**What:** Add a `normalize_tree()` pre-processing pass in `app/design_sync/figma/tree_normalizer.py` that cleans and simplifies the Figma node tree before it reaches the layout analyzer or converter. Handles: instance resolution, group flattening, hidden node removal, auto-layout inference, and contiguous text merging.
**Why:** The Figma REST API returns the raw document tree including invisible nodes, deeply nested GROUP wrappers, unresolved COMPONENT_INSTANCE overrides, and frames without auto-layout that use absolute positioning. The converter and layout analyzer each work around these issues independently (`_has_visible_content()` in `converter_service.py:263`, y-position grouping with 20px tolerance in `layout_analyzer.py`, 6-level depth guard in `converter.py`). A single normalization pass produces a cleaner tree that all downstream stages benefit from, similar to Locofy's "Design Optimizer" pre-processing step.
**Implementation:**
- Create `app/design_sync/figma/tree_normalizer.py`:
  ```python
  def normalize_tree(root: DesignNode, *, raw_file_data: dict[str, Any] | None = None) -> DesignNode:
  ```
- **Transform 1 — Remove invisible nodes:** Drop nodes where `visible=False` or `opacity=0.0`. Recurse depth-first, prune leaf-up. Preserves nodes inside `<!--[if mso]>` blocks (MSO-only content is intentionally hidden from visual tree).
- **Transform 2 — Flatten redundant groups:** If a GROUP node has exactly one child and no meaningful properties (no fill, no stroke, no effects, no auto-layout), replace the GROUP with its child, inheriting position. Reduces nesting depth by 1–3 levels in typical Figma files.
- **Transform 3 — Resolve component instances:** If `raw_file_data` provided, resolve INSTANCE nodes by overlaying override properties onto the source component's node tree. Uses Figma's `overrides` array format: `{"id": "node_id", "overriddenFields": ["characters", "fills"]}`. Result: INSTANCE nodes become FRAME nodes with resolved values.
- **Transform 4 — Infer auto-layout from positioning:** For FRAME nodes without `layout_mode`, analyze children's x/y coordinates:
  - If all children share the same x (within 5px tolerance) and are stacked vertically → infer `layout_mode=VERTICAL`, compute `item_spacing` from y-deltas
  - If all children share the same y (within 5px tolerance) and are side-by-side → infer `layout_mode=HORIZONTAL`, compute `item_spacing` from x-deltas
  - Otherwise → leave as-is (true absolute positioning)
  - Set `inferred_layout=True` flag so downstream code can distinguish real vs. inferred auto-layout
- **Transform 5 — Merge contiguous text nodes:** Adjacent TEXT children within the same parent that share identical styling (family, size, weight, color) and are vertically contiguous (y-delta equals line-height) → merge into single TEXT node with combined content. Reduces text fragmentation common in Figma exports.
- Wire into `converter_service.py:convert()` — call `normalize_tree()` on each page's root before `analyze_layout()`:
  ```python
  normalized = normalize_tree(page_root, raw_file_data=raw_file_data)
  layout = analyze_layout(normalized, ...)
  ```
- Add `NormalizationStats` dataclass returned alongside: `nodes_removed: int`, `groups_flattened: int`, `instances_resolved: int`, `layouts_inferred: int`, `texts_merged: int` — logged as structured event `design_sync.tree_normalized`
**Security:** Pure tree transformation — no network calls, no file system access. Input is already-parsed Figma API response. `raw_file_data` is the same dict used in `converter_service.py` today. No new user input vectors.
**Verify:** Tree with 3 hidden nodes → `normalize_tree()` returns tree without them, `nodes_removed=3`. GROUP with single FRAME child → flattened. FRAME with 3 vertically-stacked children at x=0 → `layout_mode=VERTICAL` inferred. Two adjacent TEXT nodes with same style → merged. Existing converter output unchanged for auto-layout frames (normalization is additive). `make test` passes.

### ~~35.3 MJML Generation Backend in Converter~~ `[Backend]` DONE
**What:** Add a third conversion path `_convert_mjml()` in `converter_service.py` that generates MJML markup from the layout analysis, then compiles via the sidecar's `/compile-mjml` endpoint. This replaces the hand-rolled table generation for the common case while keeping the recursive converter as fallback.
**Why:** The existing `_convert_recursive()` path manually generates every email HTML pattern — multi-column ghost tables (`_render_multi_column_row()`), VML buttons (`_render_button()`), MSO resets, responsive stacking, spacer rows. This is ~800 lines of intricate HTML generation in `converter.py` that duplicates what MJML handles automatically. By generating `<mj-section>/<mj-column>/<mj-text>/<mj-button>/<mj-image>` markup and letting MJML compile it, we get: (a) responsive stacking on mobile for free, (b) Outlook ghost tables generated by MJML's battle-tested compiler, (c) CSS inlining handled by MJML, (d) fewer edge-case bugs in our code. The recursive converter remains for designs that use advanced features MJML can't express (deep nesting, arbitrary VML, custom MSO blocks).
**Implementation:**
- Add `_convert_mjml()` method to `DesignConverterService`:
  ```python
  async def _convert_mjml(
      self, layout: DesignLayoutDescription, palette: BrandPalette,
      typography: dict, tokens: ExtractedTokens, *, container_width: int = 600,
      target_clients: list[str] | None = None,
  ) -> ConversionResult:
  ```
- **Section-to-MJML mapping** (one function per section type):

  | EmailSectionType | MJML output |
  |------------------|-------------|
  | HEADER | `<mj-section>` with `<mj-column>` + `<mj-image>` (logo) + `<mj-text>` (nav) |
  | HERO | `<mj-hero>` or `<mj-section>` with `background-url` + `<mj-text>` (heading) + `<mj-button>` |
  | CONTENT | `<mj-section>` + `<mj-column>` + `<mj-text>` (body) |
  | CTA | `<mj-section>` + `<mj-button>` with brand colors |
  | FOOTER | `<mj-section>` + `<mj-text>` (small, muted) |
  | TWO_COLUMN | `<mj-section>` with 2x `<mj-column width="50%">` |
  | THREE_COLUMN | `<mj-section>` with 3x `<mj-column width="33.33%">` |
  | MULTI_COLUMN | `<mj-section>` with N x `<mj-column>` using proportional widths from `_calculate_column_widths()` |
  | IMAGE | `<mj-section>` + `<mj-image>` with `src`, `alt`, `width` |
  | SPACER | `<mj-section>` + `<mj-spacer height="Npx">` |

- **Token injection into MJML attributes:**
  - Colors: `background-color`, `color` attributes on `<mj-*>` elements from `palette`
  - Typography: `font-family`, `font-size`, `font-weight`, `line-height`, `letter-spacing` from `typography` dict
  - Spacing: `padding` on `<mj-section>` and `<mj-column>` from `section.padding_*` fields
  - Dark mode: `<mj-attributes>` with `<mj-all>` defaults + custom `<mj-class>` for dark-mode-aware elements
- **MJML wrapper template:**
  ```xml
  <mjml>
    <mj-head>
      <mj-attributes>
        <mj-all font-family="{body_font_stack}" />
        <mj-text font-size="{body_size}px" color="{text_color}" line-height="{line_height}" />
        <mj-button background-color="{primary}" color="{btn_text}" font-size="16px" inner-padding="12px 24px" />
      </mj-attributes>
      <mj-style>{dark_mode_css}</mj-style>
      <mj-style>{custom_styles}</mj-style>
    </mj-head>
    <mj-body width="{container_width}px" background-color="{bg_color}">
      {sections_mjml}
    </mj-body>
  </mjml>
  ```
- Preserve `data-slot-name` and `data-component-name` attributes via MJML's `mj-html-attributes` or by post-processing compiled HTML
- Call `self._maizzle_client.compile_mjml(mjml_str, target_clients=target_clients)` to compile
- Add `output_format: Literal["html", "mjml"] = "html"` parameter to `convert()` method — when `"mjml"`, use `_convert_mjml()` path
- Fallback logic: if MJML compilation returns errors with `validationLevel="strict"`, log warning and fall back to `_convert_recursive()`
**Security:** Generated MJML contains only values from validated `ExtractedTokens` (already passed through `validate_and_transform()`). Text content is HTML-escaped via `html.escape()`. No user-provided MJML. Compiled HTML still passes through `sanitize_html_xss()`.
**Verify:** Convert the 15 golden templates via MJML path → all produce valid email HTML. Compare MJML output vs. recursive output for the same Figma file → MJML output renders correctly in Litmus/EOA for 14 client profiles (Phase 27). Multi-column layouts stack on mobile (< 480px). VML buttons render in Outlook. `make test` passes.

### 35.4 MJML Email Section Templates `[Backend + Sidecar]`
**What:** Create a library of pre-built, token-injectable MJML section templates in `app/design_sync/mjml_templates/` for the 10 common email section types. These templates are used by `_convert_mjml()` and by `ComponentMatcher` as an alternative to the existing HTML component templates.
**Why:** The MJML generation in 35.3 builds MJML programmatically from section data. For well-known patterns (hero with background image, 2-column product grid, CTA with VML button), pre-built MJML templates produce higher-quality output than programmatic generation because they encode email-specific best practices (image-over-text layering, mobile-first CTA sizing, footer legal text patterns). Emailify and Stripo both use template libraries for their section types — this is the industry standard approach.
**Implementation:**
- Create `app/design_sync/mjml_templates/` directory with Jinja2-templated MJML files:
  - `hero.mjml.j2` — Full-width hero with background image/color, heading, subheading, CTA button. Supports: image `src`/`alt`/`width`, heading text + styling, body text, button text + URL + colors. `<mj-hero>` with `mode="fluid-height"` for responsive.
  - `content_single.mjml.j2` — Single-column text content. Heading + body paragraphs + optional image. Uses `<mj-text>` with heading detection from `TextBlock.is_heading`.
  - `content_two_col.mjml.j2` — Two equal columns. Each column: optional image + heading + text. Uses 2x `<mj-column width="50%">` with `<mj-image>` + `<mj-text>`.
  - `content_three_col.mjml.j2` — Three equal columns. Feature cards or product grid. 3x `<mj-column width="33.33%">`.
  - `content_multi_col.mjml.j2` — N columns with proportional widths from layout analysis. Uses `mj-column width="{{ col.width_pct }}%"`.
  - `cta.mjml.j2` — Centered call-to-action section. `<mj-button>` with brand colors, border-radius, inner-padding. 44px min touch target enforced via `height` attribute.
  - `header.mjml.j2` — Logo + optional navigation links. `<mj-image>` for logo with `href` link, `<mj-navbar>` for nav items.
  - `footer.mjml.j2` — Legal text, social links, unsubscribe. `<mj-social>` with `<mj-social-element>` for social icons. Small muted text for legal.
  - `image_full.mjml.j2` — Full-width image section. `<mj-image>` with `fluid-on-mobile="true"`, `alt`, `src`, `width`, `href`.
  - `spacer.mjml.j2` — Vertical spacer. `<mj-section><mj-column><mj-spacer height="{{ height }}px" /></mj-column></mj-section>`.
- All templates accept a `ctx` dict with: `palette` (BrandPalette), `typography` (heading/body font stacks + sizes), `spacing` (padding values), `dark_colors` (optional), `content` (section-specific: texts, images, buttons)
- Create `MjmlTemplateEngine` class in `app/design_sync/mjml_template_engine.py`:
  ```python
  class MjmlTemplateEngine:
      def render_section(self, section: EmailSection, ctx: MjmlTemplateContext) -> str:
      def render_email(self, sections: list[EmailSection], ctx: MjmlTemplateContext) -> str:
  ```
- Wire into `_convert_mjml()`: for each `EmailSection`, look up matching template → render with section data → assemble into full MJML document → compile
- Wire into `ComponentMatcher`: add `mjml_template` field to `ComponentMatch` alongside existing `component_slug` — when MJML mode active, use MJML template instead of HTML component
**Security:** Templates are Jinja2 with `autoescape=True` — all injected values are HTML-escaped. No user-provided template paths (templates are hardcoded in the engine). Template directory is read-only at runtime.
**Verify:** Each of the 10 templates renders valid MJML (pass MJML strict validation). Compiled HTML for each template renders correctly in Gmail Web + Outlook desktop + Apple Mail (3-client smoke test via local rendering). Templates with dark mode context produce `prefers-color-scheme` media queries. `make test` passes.

### 35.5 AI Layout Intelligence & Semantic Detection `[Backend + AI]`
**What:** Add AI-powered fallback for layout analysis when heuristic classification fails, plus semantic content detection (logo, social links, unsubscribe, legal text) from visual/structural cues rather than naming conventions alone. This is the biggest differentiator vs. tools like Emailify that require annotated layers.
**Why:** The current `layout_analyzer.py` classifies sections by matching frame names against `_SECTION_PATTERNS` regex patterns. This works for well-named designs (MJML convention, descriptive names) but fails for generic names (`Frame 1`, `Group 42`, auto-generated Figma names). Market analysis shows Kombai uses deep learning for similar intent detection. Our approach uses targeted LLM calls (cheaper, more controllable) as a fallback when heuristics fail, plus a vision model for content role detection.
**Implementation:**
- **AI Layout Classifier** — `app/design_sync/ai_layout_classifier.py`:
  ```python
  async def classify_section(
      section: EmailSection, *, node_data: DesignNode, siblings: list[EmailSection],
  ) -> SectionClassification:
  ```
  - Called only when `layout_analyzer.py` assigns `EmailSectionType.UNKNOWN` or confidence < 0.5
  - Builds a compact prompt with: node tree structure (types + dimensions + colors, not raw JSON), sibling section types (positional context — "this is between a HERO and a FOOTER"), text content snippets (first 100 chars per text block), image count + dimensions
  - Uses lightweight model (Haiku) with structured output: `{ section_type: EmailSectionType, column_layout: ColumnLayout, confidence: float, reasoning: str }`
  - Cost: ~200 tokens input + ~50 tokens output per unclassified section = ~$0.0001 per call
  - Cache classification by node tree hash — same structure won't trigger LLM twice
- **Semantic Content Detector** — `app/design_sync/ai_content_detector.py`:
  ```python
  async def detect_content_roles(sections: list[EmailSection]) -> list[ContentRoleAnnotation]:
  ```
  - Detects roles: `logo`, `social_links`, `unsubscribe_link`, `legal_text`, `navigation`, `preheader`, `view_in_browser`, `address`
  - Two-pass approach:
    1. **Heuristic pass** (free, fast): regex patterns on text content — "unsubscribe" → `unsubscribe_link`, "©" or "copyright" → `legal_text`, URL patterns for social platforms → `social_links`, image in first section with small height → `logo`
    2. **LLM pass** (only for undetected roles in sections where heuristics found nothing): send text content + position info → structured output with role annotations
  - Annotations stored in `EmailSection.content_roles: list[str]` — used by MJML template selection (footer template for sections with `legal_text` + `unsubscribe_link`, header template for sections with `logo`)
- **Section Position Intelligence:**
  - First section in email → boost `HEADER` probability
  - Last section → boost `FOOTER` probability
  - Section after `HERO` → boost `CONTENT` probability
  - Section with single large image and text overlay → boost `HERO` probability
  - These positional heuristics are added to `layout_analyzer.py` directly (no LLM needed)
- Wire into `layout_analyzer.py:analyze_layout()`:
  ```python
  # After heuristic classification
  unknown_sections = [s for s in sections if s.section_type == EmailSectionType.UNKNOWN]
  if unknown_sections:
      classifications = await classify_sections_batch(unknown_sections, node_data=...)
      for section, classification in zip(unknown_sections, classifications):
          section.section_type = classification.section_type
          section.column_layout = classification.column_layout
  ```
- Add `DESIGN_SYNC__AI_LAYOUT_ENABLED` config flag (default `True`) — disable for deterministic-only mode
**Security:** LLM receives only structural metadata (dimensions, types, text snippets) — no auth tokens, no user PII, no Figma API credentials. Structured output constrains LLM to enum values only. Content detection regex runs before LLM — most roles detected without AI.
**Verify:** Figma file with generic frame names (`Frame 1` through `Frame 6`) → AI classifier correctly identifies header/hero/content/cta/content/footer with confidence > 0.7. Section containing "© 2026 Acme Corp | Unsubscribe" → `legal_text` + `unsubscribe_link` roles detected by heuristic (no LLM call). Classification cache: same node tree hash → second call returns cached result, no LLM invocation. `DESIGN_SYNC__AI_LAYOUT_ENABLED=false` → no LLM calls, UNKNOWN sections stay UNKNOWN. `make test` passes.

### 35.6 AI Visual Fidelity Scoring Pipeline `[Backend + Rendering]`
**What:** After converting a Figma design to HTML, automatically capture a screenshot of the rendered HTML and compare it against the Figma frame image. Produce a per-section visual fidelity score (0–100%) and flag regions where the converter output drifts from design intent. Uses the existing rendering infrastructure (Phase 27) and Figma's image export API.
**Why:** No Figma-to-email tool currently offers automated visual fidelity scoring. Locofy claims 95%+ match scores for web conversion but doesn't publish their methodology. For email, visual fidelity is harder because table layout is inherently less precise than CSS flexbox — but measuring it is essential for knowing whether the converter is improving. This closes the feedback loop: design → convert → render → score → identify drift → fix converter. Without scoring, we only discover visual regressions when humans compare screenshots manually.
**Implementation:**
- **Figma frame capture** — extend `FigmaDesignSyncService` with:
  ```python
  async def export_frame_image(self, file_key: str, node_id: str, *, scale: float = 2.0, format: str = "png") -> bytes:
  ```
  Uses Figma REST API `GET /v1/images/{file_key}?ids={node_id}&scale=2&format=png` — returns CDN URL, download image bytes.
- **HTML rendering** — use existing `LocalRenderingProvider` from `app/rendering/local/`:
  ```python
  async def render_html_to_image(self, html: str, *, width: int = 600, device_scale_factor: float = 2.0) -> bytes:
  ```
  Playwright headless Chromium renders the converted email HTML at the container width. Returns PNG bytes.
- **Visual comparison engine** — `app/design_sync/visual_scorer.py`:
  ```python
  @dataclass(frozen=True)
  class FidelityScore:
      overall: float          # 0.0–1.0
      ssim: float             # Structural Similarity Index
      sections: list[SectionScore]  # Per-section breakdown
      diff_image: bytes | None      # Visual diff overlay (red = differences)

  async def score_fidelity(
      figma_image: bytes, html_image: bytes, *, sections: list[EmailSection],
  ) -> FidelityScore:
  ```
  - **SSIM comparison** (Structural Similarity Index): Uses `scikit-image` `structural_similarity()` — standard metric for image quality, returns 0–1. Handles different aspect ratios by padding shorter image.
  - **Per-section scoring**: Slice both images into horizontal bands matching section y-coordinates from `DesignLayoutDescription`. Compute SSIM per band. Identify which sections have lowest fidelity.
  - **Diff image generation**: Overlay red highlights on regions where pixel difference exceeds threshold (20% luminance delta). Store as PNG for frontend display.
  - **Tolerance adjustments**: Text anti-aliasing differences are normal (Figma uses Skia, Chromium uses different sub-pixel rendering). Apply Gaussian blur (σ=1.0) before comparison to smooth anti-aliasing artifacts. Color tolerance of ΔE < 3.0 (imperceptible to human eye).
- **Integration into conversion pipeline** — add optional `score_fidelity: bool = False` parameter to `DesignImportService.run_conversion()`:
  - When enabled: after conversion, fetch Figma frame images for each section → render HTML → compute fidelity scores → store in `ConversionResult.fidelity_scores`
  - Store scores in `DesignImport.metadata_json["fidelity"]` for historical tracking
  - Frontend: display fidelity badge (green > 85%, yellow 70–85%, red < 70%) on import results
- Add `GET /api/v1/design-sync/imports/{id}/fidelity` endpoint returning scores + diff image
- Add `scikit-image` to `requirements.txt` (BSD license, already a transitive dep via other scientific packages)
**Security:** Figma frame export requires existing auth token (already stored encrypted in `DesignConnection`). Screenshot rendering is local (Playwright in sandbox). Image comparison is pure computation — no network calls. Diff images contain design content only (no secrets). Fidelity endpoint requires same auth as import endpoint.
**Verify:** Convert a Figma file with known simple layout (single-column, 3 sections) → fidelity score > 85%. Intentionally break converter output (wrong colors, missing section) → score drops below 70%. Per-section scores correctly identify the broken section. Diff image highlights the difference region. `make test` passes.

### ~~35.7 AI Conversion Learning Loop~~ `[Backend + AI]` DONE
**What:** When AI agents (Outlook Fixer, Dark Mode, Code Reviewer) repeatedly fix the same converter output patterns, automatically extract those patterns as converter rules. This creates a self-improving pipeline where agent corrections feed back into the converter, reducing future agent work and improving first-pass quality.
**Why:** Currently, agents fix converter mistakes at runtime — every email goes through the same fix cycle. Example: if the converter consistently produces `<td style="padding:20px">` but the Outlook Fixer always rewrites it to `<td style="padding:20px 20px 20px 20px;">` (longhand for Word engine), that pattern should become a converter rule so the Outlook Fixer doesn't need to fix it every time. This is the "learning" part of the AI pipeline — moving validated corrections upstream. Locofy's "Design Optimizer" learns from user corrections in a similar feedback loop.
**Implementation:**
- **Correction pattern tracker** — `app/design_sync/correction_tracker.py`:
  ```python
  @dataclass(frozen=True)
  class CorrectionPattern:
      agent: str                    # "outlook_fixer", "dark_mode", etc.
      pattern_hash: str             # Hash of (input_pattern, output_pattern)
      input_pattern: str            # Regex matching converter output
      output_pattern: str           # Agent's correction
      occurrences: int              # How many times seen
      first_seen: datetime
      last_seen: datetime
      confidence: float             # Consistency score (same correction every time?)

  class CorrectionTracker:
      async def record_correction(self, agent: str, original_html: str, corrected_html: str) -> None:
      async def get_frequent_patterns(self, *, min_occurrences: int = 5, min_confidence: float = 0.9) -> list[CorrectionPattern]:
      async def suggest_converter_rules(self) -> list[ConverterRuleSuggestion]:
  ```
- **Diff extraction**: When an agent returns modified HTML, compute a structural diff (not text diff) using `htmldiff` — identifies which elements/attributes changed. Group changes by pattern (e.g., "shorthand padding → longhand padding on `<td>`" is one pattern regardless of which `<td>` or what values).
- **Pattern storage**: Store in `data/correction_patterns.jsonl` (append-only log). Periodic aggregation into `data/correction_rules.json` (deduplicated, ranked by frequency).
- **Rule suggestion engine**: When a pattern reaches threshold (5+ occurrences, 90%+ consistency), generate a `ConverterRuleSuggestion`:
  ```python
  @dataclass
  class ConverterRuleSuggestion:
      description: str              # Human-readable: "Expand shorthand padding to longhand on <td>"
      agent_source: str             # Which agent discovered this
      pattern: CorrectionPattern
      suggested_code: str           # Python snippet for converter.py
      status: Literal["suggested", "approved", "rejected", "applied"]
  ```
- **Integration points**:
  - Hook into `BaseAgentService.validate_output()` — after agent returns HTML, call `tracker.record_correction(agent_name, input_html, output_html)` if HTML changed
  - Add `GET /api/v1/design-sync/correction-patterns` endpoint (admin only) — list frequent patterns with suggested converter rules
  - Add `POST /api/v1/design-sync/correction-patterns/{id}/approve` — mark a suggestion as approved (developer reviews before applying)
  - Approved rules are NOT auto-applied to `converter.py` — they're surfaced as developer tasks. The system suggests, humans decide.
- **Dashboard integration**: Frontend card in design-sync settings showing: top 5 correction patterns, suggested rules, approval status. Links to specific converter code locations.
**Security:** Correction patterns contain HTML snippets from agent input/output — these are already sanitized. Pattern storage is local JSONL (no external calls). Admin-only endpoints require `admin` role. No auto-modification of converter code — human approval required.
**Verify:** Run 10 conversions where Outlook Fixer consistently expands shorthand padding → `get_frequent_patterns()` returns pattern with `occurrences=10`, `confidence=1.0`. `suggest_converter_rules()` generates a suggestion with Python snippet. Pattern with only 3 occurrences → not suggested (below threshold). Admin endpoint returns patterns with suggested code. `make test` passes.

### ~~35.8 W3C Design Tokens & caniemail.com Integration~~ `[Backend]` DONE
**What:** Add W3C Design Tokens v1.0 JSON as an alternative token input format (alongside Figma Variables API), and integrate caniemail.com's open-source CSS support data as a live data source for `compatibility.py` and `token_transforms.py`.
**Why:** The W3C Design Tokens spec reached v1.0 stable in October 2025. Figma announced native W3C import/export for November 2026. Supporting W3C tokens now future-proofs the pipeline for: (a) Figma's native export when it ships, (b) Tokens Studio users who already export W3C format, (c) any design tool that supports the standard (Penpot, Sketch via plugins). For caniemail.com: the existing `compatibility.py` uses our ontology YAML (`css_properties.yaml`, `support_matrix.yaml`) which requires manual updates. caniemail.com tracks 303 HTML/CSS features across all major email clients with community-maintained data on GitHub — syncing this data keeps our compatibility checks current.
**Implementation:**
- **W3C Design Tokens parser** — `app/design_sync/w3c_tokens.py`:
  ```python
  def parse_w3c_tokens(tokens_json: dict[str, Any]) -> ExtractedTokens:
  ```
  - Parses W3C Design Tokens v1.0 JSON format: `{ "color": { "$type": "color", "$value": "#ff0000" }, "spacing": { "sm": { "$type": "dimension", "$value": "8px" } } }`
  - Maps W3C types to `ExtractedTokens` fields: `color` → `ExtractedColor`, `dimension` → spacing, `fontFamily`/`fontWeight`/`fontSize` → `ExtractedTypography`, `duration`/`cubicBezier` → ignored (not email-relevant)
  - Resolves aliases: `{ "$value": "{color.primary}" }` → follow reference chain with cycle detection (max depth 10)
  - Handles composite tokens: `shadow`, `border`, `gradient` → map to relevant `ExtractedTokens` fields
  - Supports multi-file tokens: `$extensions.mode` for light/dark → `dark_colors` population
- **W3C token export** — `app/design_sync/w3c_export.py`:
  ```python
  def export_w3c_tokens(tokens: ExtractedTokens) -> dict[str, Any]:
  ```
  - Converts validated `ExtractedTokens` back to W3C v1.0 JSON for downstream tooling (Style Dictionary, Tokens Studio)
- **API endpoints**:
  - `POST /api/v1/design-sync/tokens/import-w3c` — accepts W3C JSON, validates, stores as `DesignTokenSnapshot`
  - `GET /api/v1/design-sync/connections/{id}/tokens/export-w3c` — export current tokens in W3C format
- **caniemail.com data sync** — `scripts/sync-caniemail.py`:
  - Fetches `https://github.com/hteumeuleu/caniemail` data files (JSON/YAML)
  - Parses feature support matrix: property → client → support level (yes/no/partial + notes)
  - Outputs `data/caniemail-support.json` — 303 features × N clients
  - `make sync-caniemail` command
- **Integration with compatibility.py**:
  - `ConverterCompatibility` gains `caniemail_data` parameter — when provided, supplements ontology data with caniemail.com data
  - Merge strategy: if both sources have data for a property+client, use the more restrictive support level (safer)
  - `check_property()` returns `source: "ontology" | "caniemail" | "both"` field for transparency
- **Integration with token_transforms.py**:
  - `validate_and_transform()` gains `caniemail_data` parameter — used for client-aware warnings alongside existing ontology checks
**Security:** W3C token import accepts JSON — validate schema strictly before parsing (reject unknown `$type` values, limit nesting depth to 20, limit file size to 1MB). caniemail sync is a developer script, not a runtime endpoint — data is committed to repo. No user input reaches the sync script.
**Verify:** Import W3C tokens JSON with 5 colors + 3 typography + 2 spacing → `parse_w3c_tokens()` returns `ExtractedTokens` with correct values. Alias resolution: `{color.primary}` → resolved hex. Export round-trip: `export_w3c_tokens(parse_w3c_tokens(input)) ≈ input` (normalized). `sync-caniemail` produces `data/caniemail-support.json` with 300+ features. `ConverterCompatibility` with caniemail data correctly identifies `gap` as unsupported in Outlook. `make test` passes.

### 35.9 Figma Webhooks & Live Preview Sync `[Backend + Frontend]`
**What:** Add Figma webhook handling for `FILE_UPDATE` events to trigger automatic token re-sync and conversion preview updates. Push changes to the frontend via WebSocket so designers see their Figma edits reflected in the email preview within seconds.
**Why:** The current workflow is: designer edits Figma → manually clicks "Sync" in the UI → waits for API call → views updated tokens. This breaks the design-to-code feedback loop. Figma webhooks (`FILE_UPDATE` event) fire within seconds of a save. Combined with the existing token diff engine (Phase 33.8 `_compute_token_diff()`) and WebSocket infrastructure (Phase 24 collaboration), this enables near-real-time preview: design change → webhook → token diff → re-convert changed sections → push preview update.
**Implementation:**
- **Webhook endpoint** — `app/design_sync/routes.py`:
  ```python
  @router.post("/webhooks/figma", status_code=200)
  async def handle_figma_webhook(request: Request) -> dict:
  ```
  - Verify webhook signature using `X-Figma-Signature` header with HMAC-SHA256 (Figma signs payloads with the webhook passcode)
  - Parse event: `{ "event_type": "FILE_UPDATE", "file_key": "abc123", "file_name": "...", "timestamp": "..." }`
  - Look up `DesignConnection` by `file_key` — if found, enqueue async sync job
  - Return `200 OK` immediately (Figma requires < 5s response)
- **Webhook registration** — `app/design_sync/service.py`:
  ```python
  async def register_figma_webhook(self, connection_id: int, *, team_id: str) -> str:
  ```
  - Calls Figma API `POST /v2/webhooks` with `event_type: "FILE_UPDATE"`, `team_id`, `endpoint`, `passcode`
  - Stores webhook ID in `DesignConnection.webhook_id` column (new nullable column, Alembic migration)
  - Returns webhook ID for management
- **Debounced sync job** — designers save frequently, so debounce webhook events:
  - On webhook received: set Redis key `figma_webhook:{file_key}` with 5s TTL
  - Background worker checks key expiry → only trigger sync after 5s of no new webhooks
  - Sync job: `sync_connection()` → `_compute_token_diff()` → if tokens changed, re-convert
- **WebSocket push** — extend existing collaboration WebSocket (`app/collaboration/`):
  - New message type: `{ "type": "design_sync_update", "connection_id": N, "diff": TokenDiffResponse, "preview_url": "..." }`
  - Frontend `useDesignSync` hook receives update → refreshes token display + email preview
- **Frontend live preview** — `cms/apps/web/src/hooks/use-design-sync-live.ts`:
  - Subscribes to `design_sync_update` WebSocket messages
  - Shows toast: "Design updated — 3 tokens changed" with diff summary
  - Auto-refreshes email preview if the preview panel is open
  - Debounces UI updates to avoid flickering
- **Config:** `DESIGN_SYNC__FIGMA_WEBHOOK_ENABLED` (default `False`), `DESIGN_SYNC__FIGMA_WEBHOOK_PASSCODE` (secret for HMAC validation), `DESIGN_SYNC__WEBHOOK_DEBOUNCE_SECONDS` (default `5`)
**Security:** Webhook endpoint validates HMAC-SHA256 signature before processing — rejects unsigned/tampered payloads. Passcode stored in settings (not in DB). Rate limit webhook endpoint to 60/min per IP. Webhook registration requires admin role. WebSocket messages only sent to authenticated users with access to the project.
**Verify:** Register webhook for a test connection → Figma API returns webhook ID, stored in DB. Simulate `FILE_UPDATE` event with valid signature → sync job enqueued after 5s debounce. Invalid signature → 401 rejected. Two rapid webhook events → only one sync job (debounce works). WebSocket client receives `design_sync_update` message with token diff. Frontend toast appears. `make test` passes.

### 35.10 Incremental Conversion & Section Caching `[Backend]`
**What:** Cache conversion results at the section level and only re-convert sections whose node tree or tokens changed. On re-conversion, assemble the email from cached + fresh sections.
**Why:** A full Figma-to-email conversion for a typical 6-section email takes 2–5 seconds (layout analysis + recursive HTML generation + MJML compilation + optional fidelity scoring). When a designer changes only one section's text, re-converting all 6 sections wastes 80% of the work. Section-level caching reduces re-conversion time to < 1 second for incremental changes — critical for the live preview sync (35.9) to feel responsive.
**Implementation:**
- **Section hash computation** — `app/design_sync/section_cache.py`:
  ```python
  def compute_section_hash(section: EmailSection, tokens: ExtractedTokens) -> str:
  ```
  - Hash inputs: section's node tree (types + dimensions + styles + text content), relevant tokens (colors used in section, typography, spacing), container_width, target_clients
  - Uses `hashlib.sha256` on a canonical JSON representation
  - Stable ordering: sort dict keys, round floats to 2 decimal places
- **Section cache storage**:
  - In-memory LRU cache: `functools.lru_cache` with 500 entries (covers ~80 emails × 6 sections)
  - Redis cache with 1-hour TTL for persistence across restarts: key = `section_cache:{connection_id}:{section_hash}`, value = rendered HTML + MJML
  - Cache entry: `{ html: str, mjml: str | None, fidelity_score: float | None, generated_at: datetime }`
- **Incremental conversion** — extend `DesignConverterService.convert()`:
  ```python
  # After layout analysis
  section_hashes = {s.id: compute_section_hash(s, tokens) for s in layout.sections}
  cached = await self._cache.get_many(connection_id, section_hashes)

  to_convert = [s for s in layout.sections if s.id not in cached]
  fresh_results = await self._convert_sections(to_convert, ...)  # Only convert changed sections

  all_sections_html = []
  for section in layout.sections:
      if section.id in cached:
          all_sections_html.append(cached[section.id].html)
      else:
          all_sections_html.append(fresh_results[section.id])
          await self._cache.set(connection_id, section_hashes[section.id], fresh_results[section.id])
  ```
- **Cache invalidation**: Clear all cache entries for a connection when: (a) token diff detects structural changes (not just value changes), (b) `target_clients` change, (c) `container_width` changes, (d) manual cache clear via admin endpoint
- **Metrics**: Log `design_sync.conversion_cache_hit_rate` — ratio of cached vs. fresh sections per conversion. Include in `ConversionResult.metadata`.
- Add `DELETE /api/v1/design-sync/connections/{id}/cache` admin endpoint for manual cache clear
**Security:** Cache keys are SHA-256 hashes — no user content in keys. Cache values are rendered HTML (already sanitized). Redis cache uses same auth as existing Redis connection. Admin-only cache clear endpoint.
**Verify:** Convert a 6-section email → all 6 sections cached. Change text in 1 section → re-convert → only 1 section re-converted, 5 from cache (`cache_hit_rate=0.83`). Change `target_clients` → full cache invalidation → all 6 re-converted. Cache TTL: wait 1 hour → entries expired → full re-conversion. `make test` passes.

### ~~35.11 Tests & Integration Verification~~ `[Full-Stack]` DONE
**What:** Comprehensive test suite covering all Phase 35 subtasks: MJML compilation, tree normalization, MJML generation, AI classification, visual fidelity, correction learning, W3C tokens, webhooks, and caching. Plus end-to-end integration test: Figma file → normalize → classify → convert (MJML) → compile → score fidelity → cache.
**Implementation:**
- **MJML sidecar tests** (`services/maizzle-builder/test/`):
  - `test-mjml-compile.js`: Valid MJML → HTML with tables. Invalid MJML → error array. Empty input → 400. Large MJML (100 sections) → compiles within 5s.
  - `test-mjml-postcss.js`: MJML output + `target_clients=["outlook_2019"]` → PostCSS strips unsupported CSS from compiled HTML.
- **Tree normalizer tests** (`app/design_sync/tests/test_tree_normalizer.py`):
  - Hidden node removal, GROUP flattening, auto-layout inference (vertical, horizontal, mixed), text merging, instance resolution. Edge: empty tree, single-node tree, max-depth tree.
- **MJML generation tests** (`app/design_sync/tests/test_mjml_generation.py`):
  - Each section type → valid MJML output. Token injection → correct attributes. Dark mode → `<mj-style>` block. Multi-column → correct `mj-column width`. Full email assembly → valid MJML document.
- **MJML template tests** (`app/design_sync/tests/test_mjml_templates.py`):
  - Each of 10 templates renders valid MJML. Autoescape prevents XSS in text content. Missing optional fields → graceful defaults.
- **AI layout tests** (`app/design_sync/tests/test_ai_layout.py`):
  - Mock LLM returns valid classification → section type updated. LLM error → graceful fallback to UNKNOWN. Cache hit → no LLM call. Config disabled → no LLM call. Heuristic content roles: unsubscribe, copyright, social links detected without LLM.
- **Visual fidelity tests** (`app/design_sync/tests/test_visual_scorer.py`):
  - Identical images → score 1.0. Completely different → score < 0.3. Known diff → per-section scores identify correct section. Anti-aliasing tolerance → minor rendering differences don't tank score.
- **Correction tracker tests** (`app/design_sync/tests/test_correction_tracker.py`):
  - Record 10 identical corrections → pattern with `occurrences=10`. Below threshold → not suggested. Approve pattern → status changes. Different corrections for same input → low confidence, not suggested.
- **W3C token tests** (`app/design_sync/tests/test_w3c_tokens.py`):
  - Parse valid W3C JSON → correct `ExtractedTokens`. Alias resolution → chain followed. Circular alias → error. Export round-trip → consistent. Unknown `$type` → skipped with warning.
- **Webhook tests** (`app/design_sync/tests/test_webhooks.py`):
  - Valid signature → accepted. Invalid signature → 401. Unknown file_key → 200 (acknowledged, no action). Debounce: 3 rapid events → 1 sync job.
- **Cache tests** (`app/design_sync/tests/test_section_cache.py`):
  - Cache miss → full convert. Cache hit → skip convert. Invalidation on token change. TTL expiry. Hash stability (same input → same hash).
- **E2E integration test** (`app/design_sync/tests/test_e2e_mjml_pipeline.py`):
  - Uses mock Figma API response (real structure from golden template)
  - Full pipeline: normalize → analyze → classify → MJML generate → compile → verify HTML output has tables + MSO conditionals + responsive media queries + dark mode
  - Verify section count matches layout analysis
  - Verify `data-slot-name` attributes preserved through MJML compilation
**Security:** Tests only — no production code paths, no real Figma API calls, no real LLM calls (all mocked).
**Verify:** `make test` — all new test files pass. `make check` — full suite green. `make bench` — MJML compilation benchmark added (target: < 500ms for 6-section email). Test count: estimated 80–100 new tests across all subtasks.


---

## Phase 36 — Universal Email Design Document & Multi-Format Import Hub

> **The pipeline has a coupling problem.** Design tool providers (Figma, Penpot) produce Python objects (`ExtractedTokens`, `DesignFileStructure`) consumed directly by the converter in-process. This means: (1) new input formats (MJML files, raw HTML, manual JSON) must produce these exact Python types, (2) the converter can't run independently or be tested without a provider, (3) there's no formal contract — any field can be missing or shaped differently per provider, and (4) tokens and structure flow through separate paths that must be kept in sync manually. Meanwhile, the import annotator agent (Phase 32.3) detects Stripo/Beefree/MJML/Mailchimp patterns but can't extract structural data, and ESP export covers 3 of the Big 5 (Braze + SFMC + Adobe Campaign — missing Klaviyo + HubSpot).
>
> This phase introduces the **`EmailDesignDocument`** — a single, formally specified JSON Schema that serves as the universal contract between ALL input sources and the converter. Every provider (Figma, Penpot, MJML import, HTML import, manual API) produces this JSON. The converter consumes ONLY this JSON. The schema is versioned, validated, cacheable, and testable with fixtures. Plus: MJML import adapter, AI-powered HTML reverse engineering adapter, and Klaviyo + HubSpot ESP export to complete the Big 5.
>
> **Why not import proprietary builder formats (Beefree JSON, Stripo modules, Chamaileon JSON, Unlayer JSON)?** Competitive analysis shows these are undocumented/proprietary schemas with tiny migration audiences and high maintenance burden. When enterprises leave those tools, they export HTML — which the HTML import adapter handles. MJML is the only structured email format worth parsing directly (open, formal schema, 17k GitHub stars, used by Email Love + Topol.io + Parcel).
>
> **Dependency note:** Builds on Phase 35 (MJML compilation service, node tree normalizer, AI layout intelligence). Requires 35.1 (MJML sidecar) for MJML round-trip and 35.5 (AI layout intelligence) for HTML reverse engineering. ESP export subtask (36.5) is independent — can start immediately using existing `ESPSyncProvider` protocol in `app/connectors/sync_protocol.py`.

- [x] 36.1 EmailDesignDocument JSON Schema v1 ~~DONE~~
- [x] 36.2 Refactor converter to consume EmailDesignDocument ~~DONE~~
- [x] 36.3 Refactor Figma + Penpot adapters to produce EmailDesignDocument ~~DONE~~
- [x] 36.4 MJML import adapter ~~DONE~~
- [x] 36.5 AI-powered HTML reverse engineering adapter ~~DONE~~
- [x] 36.6 Klaviyo + HubSpot ESP export ~~DONE~~
- [x] 36.7 Tests & integration verification ~~DONE~~

### 36.1 EmailDesignDocument JSON Schema v1 `[Backend]`
**What:** Define a formal JSON Schema (Draft 2020-12) for the `EmailDesignDocument` — the single canonical intermediate representation between any input source and the converter. Create the schema file, Python dataclass mirror, serialization/deserialization, and validation.
**Why:** The pipeline currently passes Python objects in-memory between providers and the converter. This creates tight coupling, makes testing harder (need a provider to test the converter), prevents external tools from feeding the pipeline, and has no validation (missing fields cause runtime errors deep in the converter). A formal JSON Schema makes the contract explicit, enables schema validation at the boundary, allows JSON fixtures for testing, supports caching/versioning/diffing of the full input, and opens the door for external tools to target the schema directly via API.
**Implementation:**
- Create `app/design_sync/schemas/email_design_document.json` — JSON Schema Draft 2020-12:
  ```json
  {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "email-design-document/v1",
    "type": "object",
    "required": ["version", "tokens", "sections", "layout"],
    "properties": {
      "version": { "const": "1.0" },
      "source": {
        "type": "object",
        "properties": {
          "provider": { "enum": ["figma", "penpot", "mjml", "html", "manual", "sketch", "canva"] },
          "file_ref": { "type": "string" },
          "synced_at": { "type": "string", "format": "date-time" }
        }
      },
      "tokens": { "$ref": "#/$defs/tokens" },
      "sections": { "type": "array", "items": { "$ref": "#/$defs/section" } },
      "layout": { "$ref": "#/$defs/layout" },
      "compatibility_hints": { ... },
      "token_warnings": { ... }
    }
  }
  ```
- **Tokens sub-schema** (`$defs/tokens`): maps directly to existing `ExtractedTokens` fields — `colors[]` (name, hex, opacity, role), `typography[]` (name, family, size, weight, line_height, letter_spacing, text_transform, text_decoration), `spacing[]` (name, value), `dark_colors[]`, `gradients[]` (angle, stops[], fallback_hex), `variables[]` (name, type, value, mode). All fields optional with sensible defaults — minimal valid document needs only `version` + empty `tokens` + empty `sections` + `layout.container_width`.
- **Section sub-schema** (`$defs/section`): maps to existing `EmailSection` dataclass — `id`, `type` (enum: header/preheader/hero/content/cta/footer/social/divider/spacer/nav/unknown), `column_layout` (enum: single/two-column/three-column/multi-column), `width`, `height`, `padding` (top/right/bottom/left), `item_spacing`, `background_color`, `texts[]` (content, is_heading, font_family, font_size, font_weight, color, line_height, letter_spacing), `images[]` (node_id, width, height, alt, src), `buttons[]` (text, url, background_color, text_color, border_radius, padding), `columns[]` (width_pct, texts, images, buttons — for multi-column), `content_roles[]`, `spacing_after`.
- **Layout sub-schema** (`$defs/layout`): `container_width` (int, 400–800, default 600), `naming_convention` (enum), `overall_width`.
- Create Python mirror in `app/design_sync/email_design_document.py`:
  ```python
  @dataclass(frozen=True)
  class EmailDesignDocument:
      version: str
      tokens: DocumentTokens
      sections: list[DocumentSection]
      layout: DocumentLayout
      source: DocumentSource | None = None
      compatibility_hints: list[CompatibilityHint] = field(default_factory=list)
      token_warnings: list[TokenWarning] = field(default_factory=list)

      @classmethod
      def from_json(cls, data: dict[str, Any]) -> EmailDesignDocument: ...
      def to_json(self) -> dict[str, Any]: ...
      @staticmethod
      def validate(data: dict[str, Any]) -> list[str]: ...  # Returns validation errors
  ```
- `DocumentTokens`, `DocumentSection`, `DocumentLayout`, `DocumentSource` — frozen dataclasses mirroring the JSON schema. These are thin wrappers, NOT duplicates of `ExtractedTokens`/`EmailSection` — they have `to_extracted_tokens()` and `to_email_sections()` bridge methods for backward compatibility during migration.
- Schema validation via `jsonschema` library (already a dependency via other packages) — validate at the boundary (when JSON arrives from adapter or API), not inside the converter.
- Add `POST /api/v1/design-sync/validate-document` endpoint — accepts JSON, returns validation errors. Useful for external tools testing their output.
- Add `GET /api/v1/design-sync/schema/v1` endpoint — serves the JSON Schema for external consumers.
- Store validated `EmailDesignDocument` JSON in `DesignTokenSnapshot.document_json` (new column, nullable — coexists with existing `tokens_json` during migration). Alembic migration adds column.
**Security:** Schema validation prevents malformed input from reaching the converter. Max document size: 5MB (enforced at API boundary). JSON Schema `maxItems` on arrays (sections: 100, texts per section: 50, colors: 500) prevents DoS via oversized documents. No `additionalProperties: true` on inner objects — unknown fields are rejected.
**Verify:** Valid EmailDesignDocument JSON → `validate()` returns empty list. Missing required field → validation error with path. Section with invalid type → rejected. Document with 101 sections → rejected (maxItems). `from_json(to_json(doc))` round-trips correctly. Schema endpoint returns valid JSON Schema. `make test` passes.

### ~~36.2 Refactor Converter to Consume EmailDesignDocument~~ `[Backend]` DONE
**What:** Modify `DesignConverterService.convert()` to accept `EmailDesignDocument` as its primary input, replacing the current `(DesignFileStructure, ExtractedTokens)` pair. The existing signature remains as a deprecated compatibility shim during migration.
**Why:** The converter currently accepts `DesignFileStructure` + `ExtractedTokens` + 8 keyword arguments (`raw_file_data`, `selected_nodes`, `target_clients`, `use_components`, `connection_config`, `image_urls`). This signature is Figma-centric (e.g., `raw_file_data` is the raw Figma API response). Moving to `EmailDesignDocument` as the single input: (a) makes the converter input-source-agnostic, (b) reduces the parameter surface from 10 args to 1 object, (c) enables testing with JSON fixtures instead of mock providers, (d) enables caching by document hash.
**Implementation:**
- Add new method `DesignConverterService.convert_document()`:
  ```python
  async def convert_document(
      self, document: EmailDesignDocument, *, target_clients: list[str] | None = None,
      output_format: Literal["html", "mjml"] = "html",
  ) -> ConversionResult:
  ```
- Internally: `document.tokens.to_extracted_tokens()` → feed to `validate_and_transform()`. `document.sections` → feed to `_convert_mjml()` (Phase 35.3) or `_convert_with_components()`. `document.layout.container_width` → thread through all rendering calls.
- The existing `convert()` method becomes a shim:
  ```python
  async def convert(self, structure, tokens, **kwargs) -> ConversionResult:
      # Build EmailDesignDocument from legacy inputs
      document = self._build_document_from_legacy(structure, tokens, **kwargs)
      return await self.convert_document(document, target_clients=kwargs.get("target_clients"))
  ```
- `_build_document_from_legacy()` bridges the old inputs → `EmailDesignDocument`:
  - Runs `analyze_layout(structure)` to get `EmailSection[]`
  - Maps `ExtractedTokens` → `DocumentTokens`
  - Maps `EmailSection[]` → `DocumentSection[]`
  - This is the ONLY place layout analysis happens for Figma/Penpot inputs (Option A from architecture discussion)
- Update `import_service.py:run_conversion()` to call `convert_document()` with the `EmailDesignDocument` stored in `DesignTokenSnapshot.document_json` when available, falling back to legacy path when not.
- Update `service.py:sync_connection()` to build and store `EmailDesignDocument` JSON in the snapshot after token extraction + layout analysis.
- **No changes to `converter.py` internals** (`node_to_email_html()`, `_render_semantic_text()`, etc.) — these receive `EmailSection` data from the document's `.to_email_sections()` bridge. The refactor is at the orchestration layer only.
**Security:** `convert_document()` requires a validated `EmailDesignDocument` — call `validate()` before passing. The shim validates legacy inputs by construction (they come from trusted provider code). No new user input paths.
**Verify:** `convert_document()` with a JSON fixture produces identical HTML to `convert()` with the same data via legacy path. All existing design_sync tests pass without modification (shim handles backward compatibility). `convert_document()` with invalid document → raises `AppError`. `make test` passes. `make check` all green.

### ~~36.3 Refactor Figma + Penpot Adapters to Produce EmailDesignDocument~~ `[Backend]` DONE
**What:** Modify `FigmaDesignSyncService` and `PenpotDesignSyncService` to output `EmailDesignDocument` JSON as their primary result, in addition to the existing `ExtractedTokens` + `DesignFileStructure` return types. Each adapter encapsulates all provider-specific logic — API calls, node parsing, layout analysis — and outputs the universal document.
**Why:** Currently, the Figma provider returns raw `ExtractedTokens` + `DesignFileStructure`, and the converter runs layout analysis. This means layout analysis is in the converter's responsibility, but it's really a provider-specific concern (Figma nodes need y-position grouping; MJML sections are explicit; HTML needs DOM traversal). Moving layout analysis into the adapter means each adapter can use the right analysis strategy for its format, and the converter receives pre-analyzed sections.
**Implementation:**
- Add `build_document()` method to `FigmaDesignSyncService`:
  ```python
  async def build_document(
      self, file_ref: str, access_token: str, *, selected_nodes: list[str] | None = None,
      connection_config: dict[str, Any] | None = None,
  ) -> EmailDesignDocument:
  ```
  - Calls existing `sync_tokens_and_structure()` → `ExtractedTokens` + `DesignFileStructure`
  - Calls `validate_and_transform(tokens)` → validated tokens + warnings
  - If Phase 35.2 available: calls `normalize_tree(structure)` → cleaned tree
  - Calls `analyze_layout(structure)` → `DesignLayoutDescription` with `EmailSection[]`
  - If Phase 35.5 available: calls `classify_unknown_sections()` for AI fallback
  - Assembles all results into `EmailDesignDocument`
  - Returns the document (also stores as JSON in snapshot)
- Add same `build_document()` to `PenpotDesignSyncService` — same flow, different API client.
- Update `DesignSyncService.sync_connection()`:
  ```python
  # New path: build full document
  provider = self._get_provider(connection.provider)
  if hasattr(provider, "build_document"):
      document = await provider.build_document(file_ref, token, ...)
      snapshot.document_json = document.to_json()
  else:
      # Legacy path for stub providers (Sketch, Canva)
      tokens, structure = await provider.sync_tokens_and_structure(file_ref, token)
      snapshot.tokens_json = tokens.to_dict()
  ```
- The `DesignSyncProvider` protocol gains an optional `build_document()` method (not required — stubs don't implement it). Use `hasattr` check, not protocol enforcement, so existing providers aren't broken.
- **Layout analysis moves from converter to adapter.** The converter no longer calls `analyze_layout()` — it receives pre-analyzed sections in the document. This is the key architectural shift.
**Security:** No new input paths. `build_document()` uses the same authenticated API calls as existing methods. Document JSON is validated before storage. Existing auth, rate limiting, and encryption unchanged.
**Verify:** `sync_connection()` for a Figma connection → stores `document_json` with valid EmailDesignDocument. `document_json` contains sections with types, texts, images, buttons. `convert_document(document)` produces same HTML as legacy `convert(structure, tokens)` path. Penpot connection → same flow. Stub providers (Sketch, Canva) → legacy path, no `document_json`. `make test` passes.

### ~~36.4 MJML Import Adapter `[Backend]`~~ DONE
**What:** Create `app/design_sync/mjml_import/adapter.py` — a parser that reads MJML markup (`<mjml>/<mj-body>/<mj-section>/<mj-column>/<mj-text>/<mj-button>/<mj-image>`) and produces an `EmailDesignDocument`. This enables importing existing MJML templates into the platform for editing, AI enhancement, and multi-client rendering. Combined with Phase 35.3 (MJML generation), this completes the MJML round-trip.
**Why:** MJML is the de facto standard intermediate representation for email. Enterprise email teams have hundreds of MJML templates from Maizzle, Parcel, Email Love, Topol.io, or hand-coded workflows. Importing these templates unlocks: (a) AI agent enhancement (dark mode, accessibility, outlook fixes) on existing MJML templates, (b) visual editing in the builder, (c) multi-client rendering via the emulators, (d) QA engine checks on legacy templates. MJML's XML structure maps cleanly to `EmailDesignDocument` — `<mj-section>` → section, `<mj-column>` → column, `<mj-text>` → text block, `<mj-button>` → button, `<mj-image>` → image. This is a 1:1 mapping, not heuristic inference.
**Implementation:**
- Create `app/design_sync/mjml_import/adapter.py`:
  ```python
  class MjmlImportAdapter:
      def parse(self, mjml_source: str) -> EmailDesignDocument: ...
  ```
- **MJML parsing** — use `lxml.etree` with MJML namespace handling:
  - Parse MJML as XML tree
  - Walk `<mj-head>` → extract tokens:
    - `<mj-attributes>/<mj-all>` → default typography (font-family, font-size, color)
    - `<mj-attributes>/<mj-text>` → text typography overrides
    - `<mj-attributes>/<mj-button>` → button defaults (background-color, color, font-size, inner-padding, border-radius)
    - `<mj-style>` → parse CSS for color variables, dark mode rules (`prefers-color-scheme`)
    - `<mj-font>` → web font references
  - Walk `<mj-body>` → extract sections:
    - Each `<mj-section>` → one `DocumentSection`:
      - `background-color` attr → `background_color`
      - `padding` attr → parse to `padding_top/right/bottom/left`
      - Count child `<mj-column>` → determine `column_layout` (1=SINGLE, 2=TWO_COLUMN, 3=THREE_COLUMN, 4+=MULTI_COLUMN)
    - Each `<mj-column>` → column group with `width` → `width_pct`
    - Each `<mj-text>` → `TextBlock`:
      - Inner HTML content (strip tags for plain text, detect headings from `<h1>`-`<h6>` tags or font-size)
      - `font-family`, `font-size`, `font-weight`, `color`, `line-height`, `letter-spacing` from attributes + inline style
    - Each `<mj-image>` → `ImagePlaceholder` with `src`, `alt`, `width`, `height`
    - Each `<mj-button>` → `ButtonElement` with `href`, inner text, `background-color`, `color`, `border-radius`, `inner-padding`
    - Each `<mj-spacer>` → section with type=SPACER and `height`
    - Each `<mj-divider>` → section with type=DIVIDER
    - `<mj-hero>` → section with type=HERO + background image from `background-url`
    - `<mj-social>/<mj-social-element>` → section with type=SOCIAL + content roles
    - `<mj-navbar>/<mj-navbar-link>` → section with type=NAV
  - **Section type inference**: MJML doesn't have explicit section types. Infer from position + content:
    - First section with image and no text → HEADER
    - Section with `<mj-hero>` or large background image + heading → HERO
    - Last section with small text or `<mj-social>` → FOOTER
    - Section with only `<mj-button>` → CTA
    - Everything else → CONTENT
  - `document.source.provider = "mjml"`
  - `document.layout.container_width` from `<mj-body width="600px">` or default 600
- **API endpoints**:
  - `POST /api/v1/design-sync/import/mjml` — accepts MJML string in request body, returns `EmailDesignDocument` JSON + conversion preview
  - Reuses auth + rate limiting from existing design_sync routes
- **Integration with visual builder**: imported `EmailDesignDocument` can be opened in the builder for editing, then exported as MJML (Phase 35.3) or HTML (converter)
- Max MJML size: 2MB (matches import annotator limit). Validate XML well-formedness before parsing.
**Security:** MJML input is parsed as XML via `lxml` with `resolve_entities=False`, `no_network=True` to prevent XXE attacks. Text content from `<mj-text>` is passed through `html.escape()` when extracting plain text. `src` URLs from `<mj-image>` are validated (http/https only, no `javascript:` or `data:` URIs). Import endpoint requires authentication.
**Verify:** Import the 10 MJML section templates from Phase 35.4 → each produces valid `EmailDesignDocument` with correct section types, column layouts, and content. Round-trip: MJML → import → `EmailDesignDocument` → MJML generation (35.3) → compile (35.1) → produces equivalent HTML. `<mj-hero>` → HERO section. 2-column section → TWO_COLUMN layout with 2 column groups. Dark mode `<mj-style>` → `dark_colors` tokens extracted. Malformed XML → descriptive error, no crash. XXE payload → rejected. `make test` passes.

### ~~36.5 AI-Powered HTML Reverse Engineering Adapter `[Backend + AI]`~~ DONE
**What:** Create `app/design_sync/html_import/adapter.py` — a parser that takes arbitrary email HTML and reverse-engineers an `EmailDesignDocument`. Uses the existing import annotator agent (Phase 32.3) for pattern detection, plus new DOM traversal logic to extract `EmailSection[]` with full content (texts, images, buttons, styling). This is the #1 enterprise migration feature — enterprises have thousands of legacy HTML templates that need to become editable.
**Why:** The import annotator agent already detects section boundaries and adds `data-section-id` attributes, identifies builder patterns (Stripo, Beefree, Mailchimp, MJML), and recognizes ESP tokens (AMPscript, Liquid, Handlebars). But it does NOT extract structured data — no `EmailSection` objects, no text blocks, no image metadata, no button detection. The gap is the 60% between "annotated HTML" and "structured EmailDesignDocument." Beefree launched their HTML Importer API in 2025 (rule-based). Chamaileon has an HTML import plugin. Both produce mediocre results on messy real-world email HTML. AI-powered extraction using the import annotator's pattern detection + LLM fallback for ambiguous structures would be a genuine differentiator.
**Implementation:**
- Create `app/design_sync/html_import/adapter.py`:
  ```python
  class HtmlImportAdapter:
      async def parse(self, html: str, *, use_ai: bool = True) -> EmailDesignDocument: ...
  ```
- **Phase 1 — DOM-based section extraction** (deterministic, no LLM):
  - Parse HTML via `lxml.html` (same library as import annotator)
  - Find the outermost content table (skip MSO wrapper tables via `<!--[if mso]>` detection)
  - Walk top-level `<tr>` rows → each row is a candidate section
  - For each candidate section:
    - **Text extraction**: Find all text-bearing elements (`<td>`, `<p>`, `<h1>`-`<h6>`, `<span>`, `<a>`) → create `TextBlock` objects with content + inline style parsing (font-family, font-size, font-weight, color, line-height from `style` attribute)
    - **Image extraction**: Find all `<img>` tags → create `ImagePlaceholder` with `src`, `alt`, `width`, `height` (from attributes or inline style)
    - **Button extraction**: Detect buttons via multiple patterns — `<a>` with background-color in style, `<table>` with single `<a>` child (bulletproof button pattern), VML `<v:roundrect>` (Outlook button), `role="button"` attribute → create `ButtonElement` with text, href, styling
    - **Column detection**: Count immediate child `<td>` elements in a row. 1 td = SINGLE, 2 = TWO_COLUMN, 3 = THREE_COLUMN, 4+ = MULTI_COLUMN. Also detect `display:inline-block` column pattern (fluid hybrid).
    - **Background color**: Extract from `bgcolor` attribute or `background-color` in style on `<td>`/`<table>`
    - **Padding**: Parse `padding` from inline style on section-level `<td>`
- **Phase 2 — Section type classification** (heuristic + AI fallback):
  - **Heuristic rules** (free, fast):
    - Section with image and no/little text in first position → HEADER
    - Section with large font heading (> 24px) + optional image + optional button → HERO
    - Section with only `<a>` button → CTA
    - Last section with small text (< 14px) or "unsubscribe"/"©" content → FOOTER
    - Section with social media image links (facebook/twitter/linkedin/instagram URL patterns) → SOCIAL
    - Section with `<hr>` or 1px-height element → DIVIDER
    - Section with no content, height-only → SPACER
  - **AI fallback** (only for sections classified as UNKNOWN after heuristics): reuse Phase 35.5 `classify_section()` with text snippets + position context → Haiku structured output
- **Phase 3 — Token extraction from CSS**:
  - Parse `<style>` blocks and inline styles → build color palette (deduplicate hex values, assign roles by frequency: most common bg = background, most common text = body_text, etc.)
  - Extract typography: find distinct font-family + font-size combinations → heading vs. body by size
  - Extract spacing: common padding values → spacing scale
  - Detect dark mode: `@media (prefers-color-scheme: dark)` rules → `dark_colors`
  - Detect web fonts: `@import` or `<link>` with font URLs
- **Integration with import annotator**: if import annotator was already run on this HTML (has `data-section-id` attributes), use those annotations as section boundaries instead of inferring from `<tr>` rows. This leverages the agent's builder-specific pattern detection.
- **API endpoint**: `POST /api/v1/design-sync/import/html` — accepts HTML string, returns `EmailDesignDocument` JSON
- **Config**: `DESIGN_SYNC__HTML_IMPORT_AI_ENABLED` (default `True`) — disable AI fallback for deterministic-only mode
**Security:** HTML input parsed via `lxml.html` (inherently sanitizes). `src` URLs validated (http/https only). Text content passed through `html.escape()` on extraction. AI fallback receives only structural metadata (dimensions, text snippets), not raw HTML. Import endpoint requires authentication. Max HTML size: 2MB.
**Verify:** Import a golden template HTML → produces `EmailDesignDocument` with correct section count, types, and content. Import a Stripo-exported HTML → section boundaries detected (leveraging import annotator skills). Import a Beefree-exported HTML → same. Import hand-coded email with bulletproof buttons → buttons correctly extracted. Import email with dark mode CSS → `dark_colors` populated. AI disabled → UNKNOWN sections stay UNKNOWN. Malformed HTML → best-effort parsing, no crash. `make test` passes.

### ~~36.6 Klaviyo + HubSpot ESP Export `[Backend]`~~ DONE
**What:** Add Klaviyo and HubSpot ESP export providers to complete the Big 5 coverage (joining existing Braze, SFMC, Adobe Campaign in `app/connectors/`). Implements the existing `ESPSyncProvider` protocol from `app/connectors/sync_protocol.py`.
**Why:** Braze, SFMC, and Adobe Campaign export already works. Klaviyo and HubSpot are the remaining two of the five most-used enterprise ESPs. Without them, enterprise prospects using these platforms can't push templates from the platform — a deal-breaker. The existing `ESPSyncProvider` protocol + `ConnectorService` dispatch pattern makes adding new providers straightforward (same pattern as `BrazeSyncProvider`, `SFMCSyncProvider`).
**Implementation:**
- **Klaviyo provider** — `app/connectors/klaviyo/`:
  - `service.py` — `KlaviyoConnectorService`:
    - Auth: API key (private key, `Authorization: Klaviyo-API-Key {key}`)
    - Base URL: `https://a.klaviyo.com/api`
    - API revision header: `revision: 2025-07-15` (Klaviyo requires version pinning)
  - `sync_provider.py` — `KlaviyoSyncProvider` implementing `ESPSyncProvider`:
    - `validate_credentials()` → `GET /api/accounts/` (returns account info if key valid)
    - `list_templates()` → `GET /api/templates/` with pagination (`page[cursor]`). Map response to `ESPTemplate` (id, name, html, updated_at). Klaviyo uses JSON:API format — unwrap `data[].attributes`.
    - `get_template(id)` → `GET /api/templates/{id}/`
    - `create_template(name, html)` → `POST /api/templates/` with `{ "data": { "type": "template", "attributes": { "name": name, "html": html } } }`
    - `update_template(id, html)` → `PATCH /api/templates/{id}/` with same JSON:API format
    - `delete_template(id)` → `DELETE /api/templates/{id}/`
  - Rate limit: Klaviyo allows 75 requests/sec for private API keys. Add `RateLimiter` with 60/sec safety margin.
- **HubSpot provider** — `app/connectors/hubspot/`:
  - `service.py` — `HubSpotConnectorService`:
    - Auth: Private app access token (`Authorization: Bearer {token}`)
    - Base URL: `https://api.hubapi.com`
  - `sync_provider.py` — `HubSpotSyncProvider` implementing `ESPSyncProvider`:
    - `validate_credentials()` → `GET /account-info/v3/details` (returns portal ID if valid)
    - `list_templates()` → `GET /marketing/v3/emails/` with pagination (`after` cursor). Map to `ESPTemplate`. Note: HubSpot's Marketing Email API is the modern path — the older Template API is for CMS templates, not email templates.
    - `get_template(id)` → `GET /marketing/v3/emails/{id}`
    - `create_template(name, html)` → `POST /marketing/v3/emails/` with `{ "name": name, "content": { "html": html }, "type": "REGULAR" }`
    - `update_template(id, html)` → `PATCH /marketing/v3/emails/{id}` with content update
    - `delete_template(id)` → `DELETE /marketing/v3/emails/{id}` (moves to trash, not permanent)
  - Rate limit: HubSpot allows 100 requests/10sec for private apps. Add `RateLimiter` with 8/sec safety margin.
- Register both in `ConnectorService`:
  ```python
  # app/connectors/service.py
  PROVIDERS["klaviyo"] = KlaviyoSyncProvider
  PROVIDERS["hubspot"] = HubSpotSyncProvider
  ```
- Add config: `ESPSyncConfig` gains `klaviyo_api_key`, `hubspot_access_token` fields
- Add pre-check support: both providers in `export_pre_check()` for dry-run validation
**Security:** API keys stored encrypted via existing `encrypt_credentials()` in `app/connectors/`. Keys never logged (structured logging excludes credential fields). Rate limiters prevent API abuse. HubSpot delete is soft-delete (trash) — not destructive. Klaviyo API key scopes validated on `validate_credentials()` (need `templates:read`, `templates:write`).
**Verify:** Klaviyo: `validate_credentials()` with valid key → `True`. `create_template("Test", "<html>...")` → returns `ESPTemplate` with Klaviyo ID. `list_templates()` → returns list including created template. `update_template(id, new_html)` → HTML updated. `delete_template(id)` → `True`. Invalid key → `validate_credentials()` returns `False`. HubSpot: same test matrix. Both providers work through existing `POST /api/v1/connectors/export` endpoint. `make test` passes (mocked API calls).

### ~~36.7 Tests & Integration Verification `[Full-Stack]`~~ DONE
**What:** Comprehensive test suite covering all Phase 36 subtasks plus end-to-end integration tests for the full multi-format pipeline.
**Implementation:**
- **Schema tests** (`app/design_sync/tests/test_email_design_document.py`):
  - Valid document → passes validation. Missing `version` → error. Invalid section type → error. `from_json(to_json())` round-trip. Max size limits enforced. Bridge methods: `to_extracted_tokens()`, `to_email_sections()` produce correct types.
- **Converter refactor tests** (`app/design_sync/tests/test_converter_document.py`):
  - `convert_document()` with JSON fixture → same HTML as legacy `convert()` with equivalent data. Invalid document → `AppError`. Empty sections → valid empty email skeleton. All existing converter tests pass via shim.
- **Figma adapter tests** (`app/design_sync/tests/test_figma_adapter.py`):
  - `build_document()` with mock Figma response → valid `EmailDesignDocument`. Document contains sections with classified types. Tokens validated and warnings present. Penpot adapter: same test matrix.
- **MJML import tests** (`app/design_sync/tests/test_mjml_import.py`):
  - Each MJML element type → correct mapping. `<mj-section>` with 2 `<mj-column>` → TWO_COLUMN. `<mj-button>` → button with href + styling. `<mj-hero>` → HERO type. `<mj-social>` → SOCIAL type. Dark mode `<mj-style>` → dark_colors. Malformed XML → error. XXE → rejected. Round-trip: import → generate (35.3) → compile (35.1) → valid HTML.
- **HTML import tests** (`app/design_sync/tests/test_html_import.py`):
  - Import golden template HTML (use real fixtures from `app/components/data/seeds.py`) → correct section count and types. Bulletproof button pattern → detected as button. Inline styles → tokens extracted. Dark mode CSS → dark_colors. Builder-specific HTML (Stripo/Beefree patterns) → correct section boundaries. AI disabled → UNKNOWN sections preserved. Empty HTML → empty document, no crash.
- **ESP export tests** (`app/connectors/tests/test_klaviyo.py`, `test_hubspot.py`):
  - Mock API: CRUD operations for both providers. Rate limiter: burst of 100 requests → throttled. Invalid credentials → `False`. JSON:API format handling (Klaviyo). Pagination (both).
- **E2E integration tests** (`app/design_sync/tests/test_e2e_document_pipeline.py`):
  - **Figma E2E**: Mock Figma API → `build_document()` → `convert_document()` → valid email HTML with tables + MSO conditionals.
  - **MJML E2E**: MJML template → `MjmlImportAdapter.parse()` → `EmailDesignDocument` → `convert_document(output_format="mjml")` → MJML compile (35.1) → valid email HTML. Verify round-trip fidelity.
  - **HTML E2E**: Golden template HTML → `HtmlImportAdapter.parse()` → `EmailDesignDocument` → `convert_document()` → valid email HTML. Verify section count matches original.
  - **Cross-format**: Import same email as MJML and as HTML → both produce `EmailDesignDocument` with same section count and types (content may differ in extraction precision).
  - **ESP push E2E**: `convert_document()` → HTML → `ConnectorService.export("klaviyo", html)` → mock API called with correct payload. Same for HubSpot.
**Security:** Tests only. No real API calls (all mocked). Golden template fixtures from existing seeds — no external data.
**Verify:** `make test` — all new test files pass. `make check` — full suite green. Estimated 60–80 new tests. Existing design_sync tests (514+) unchanged (backward compatibility via shim).

---

## Phase 37 — Golden Reference Library for AI Judge Calibration (Complete)

> 14 golden reference templates wired into all 9 AI judge prompts as few-shot examples. YAML-indexed loader with criterion mapping, 2000-token budget cap per judge call. Full eval re-run against file-based component output (40.7), 540 human-labeled rows, calibration validated TPR ≥ 0.85 / TNR ≥ 0.80.

### ~~37.1 Expand Golden Component Library `[Templates]`~~ DONE

14 new golden reference templates in `email-templates/components/golden-references/`: VML backgrounds, rounded button variants, nested MSO conditionals, complex hybrid layout, dark mode complete, accessibility compliant, 4 ESP token templates (Braze Liquid, SFMC AMPscript, Adobe Campaign, Klaviyo Django), 4 innovation technique templates (CSS carousel, accordion dropdown, AMP email, kinetic hover). Each annotated with `<!-- golden-ref: criteria=[...], agents=[...] -->` frontmatter.

### ~~37.2 Build Golden Reference Loader & Criterion Mapping `[Backend]`~~ DONE

`app/ai/agents/evals/golden_references.py` — `GoldenReference` frozen dataclass, `load_golden_references()` with `@lru_cache`, `get_references_for_criterion()` (max 3 snippets), `get_references_for_agent()`. `email-templates/components/golden-references/index.yaml` registry. 80-line snippet cap, ~2000 token budget per judge call. 18 tests.

### ~~37.3 Wire Golden References into Judge Prompts `[Backend, Evals]`~~ DONE

All 7 HTML-evaluating judges inject golden reference snippets via `build_prompt()`. Platform-conditional filtering (Personalisation: ESP-specific), category-conditional (Innovation: technique-specific), inverted framing (Code Reviewer: "do NOT flag these"). Content/Knowledge/Visual QA excluded (text-only criteria). 22 tests.

### ~~37.4 Re-run Eval Pipeline Against File-Based Component Output `[Evals]`~~ DONE

Re-generated agent traces and re-ran judges against file-based component output (40.7). Backed up inline-seed verdicts to `traces/pre_file_based/`. ~2,700 LLM judge calls. Verdict comparison via `scripts/eval-compare-verdicts.py` — 21/45 criteria flagged >20% flip rate. Analysis and regression check passed.

### ~~37.5 Complete Human Labeling with Improved Judges `[Manual + Evals]`~~ DONE

540 rows labeled via `docs/eval-labeling-tool.html`. Prioritized high-flip criteria from 37.4. Calibration validated: TPR ≥ 0.85 and TNR ≥ 0.80 per judge criterion. QA check agreement ≥ 75%.

---

## Phase 38 — Design-to-Email Pipeline Fidelity Fix (Complete)

### ~~38.1 Figma Parser Data Fidelity Fixes `[Backend]`~~ DONE

**Completed:** 2026-03-28

Fixed 5 bugs + added text color extraction in `figma/service.py:_parse_node()`:

| # | Bug | Fix |
|---|-----|-----|
| 1 (CRITICAL) | `opacity=0.0 or 1.0` falsy trap | `float(x) if x is not None else 1.0` |
| 2 (HIGH) | Auto-layout only extracted for FRAME | Extended to COMPONENT/COMPONENT_SET/INSTANCE |
| 3 (MEDIUM) | Fill extraction order-dependent with early `break` | Single-pass, collect all fill types |
| 4 (LOW) | Only GRADIENT_LINEAR handled | Added GRADIENT_RADIAL midpoint extraction |
| 5 (LOW) | `visible: null` treated as truthy by accident | `bool(node_data.get("visible", True))` |
| NEW (CRITICAL) | TEXT node fills never extracted | Extract `text_color` from TEXT `fills[]` |

**Key deliverables:** `app/design_sync/figma/service.py` fixes, `app/design_sync/figma/tests/test_parse_node_fidelity.py` (15+ new tests). Opacity, auto-layout, fill order, gradient, visibility, and text color all verified.

---

### ~~38.2 Tree Normalizer & Normalization Pipeline Fixes `[Backend]`~~ DONE

**Completed:** 2026-03-28

Fixed 5 bugs in `figma/tree_normalizer.py` that corrupted spacing, dropped INSTANCE data, and lost dimensions:

| # | Bug | Fix |
|---|-----|-----|
| 6 (HIGH) | `item_spacing` used position diffs (included child height) | Compute edge-to-edge gaps with `statistics.median`, clamp ≥0 |
| 7 (MEDIUM) | `_resolve_instances` gated on unused `raw_file_data` param | Removed guard, resolve INSTANCE→FRAME unconditionally |
| 8 (MEDIUM) | Group flattening dropped width/height | Inherit dimensions from parent GROUP when child has None |
| 9 (MEDIUM) | Text merge spacing used CSS `line_height` accumulation | Use `node.height` with `line_height_px` fallback, skip when no size data |
| 10 (LOW) | Empty containers not pruned after invisible removal | Prune childless GROUP/FRAME without fill_color/image_ref |

**Key deliverables:** `app/design_sync/figma/tree_normalizer.py` (5 bug fixes), `app/design_sync/figma/tests/test_tree_normalizer.py` (14 new tests, 33 total). All 48 related tests pass. Pyright 0 errors, mypy 0 errors.

---

### ~~38.3 Layout Analyzer & Section Classification Fixes `[Backend]`~~ DONE

**Completed:** 2026-03-28

Fixed 9 bugs + 1 critical new issue in `figma/layout_analyzer.py` covering heading detection, footer classification, column grouping, button detection, and button text exclusion:

| # | Bug | Fix |
|---|-----|-----|
| 11-12 (HIGH) | Heading threshold 0.8x max → over-triggers; uniform sizes all headings | 1.3x median threshold + `len(set(sizes)) == 1` early return |
| 13 (MEDIUM) | Footer false positive on legal text anywhere | Require `index >= total - 2` AND legal text |
| 14 (MEDIUM) | Substring pattern "text" matches "context" | Word-boundary `re.search(rf'\b{pattern}\b')` |
| 15 (MEDIUM) | Image child only checks direct children | Recurse 2 levels into FRAME children |
| 16 (MEDIUM) | Column Y-grouping order-dependent | Sort by Y first, greedy bands, sort each row by X |
| 17 (MEDIUM) | `_calculate_spacing` drops fields in section rebuild | `dataclasses.replace()` instead of manual constructor |
| 18 (LOW) | CTA classified by height alone (60-150px) | Require button-like child content |
| 19 (LOW) | Ghost/outline buttons missed without fill | Accept by name hint regardless of fill |
| NEW (CRITICAL) | Button text appears in `section.texts` | Extract buttons first → exclude node IDs from `_walk_for_texts()` |

Button exclusion applied at all 3 extraction sites: top-level `analyze_layout()`, `_detect_mj_columns()`, and `_build_column_groups()`.

**Key deliverables:** `app/design_sync/figma/layout_analyzer.py` (10 fixes), `app/design_sync/tests/test_layout_analyzer.py` (19 new tests, 67 total). All 99 related tests pass (layout + column grouping + naming conventions). Pyright errors unchanged at baseline (5 pre-existing).

---

### ~~38.4 Converter, MJML Generator & Template Engine Fixes `[Backend]`~~ DONE

**Completed:** 2026-03-28

Fixed 12 bugs across `converter.py`, `mjml_generator.py`, `mjml_template_engine.py`, and `section_cache.py`. Enforced golden template quality patterns (G-REF-2, G-REF-6, G12). Security hardening of CSS sanitizer with correct operation ordering.

| # | Bug | Fix |
|---|-----|-----|
| 20 (CRITICAL) | `_sanitize_css_value` strips `()` — kills `rgb()` | Allow balanced parens; block `expression()`, `url(javascript:)` specifically via `_DANGEROUS_CSS_RE` |
| 21 (HIGH) | `padding_top or 0` treats `0.0` as falsy | `x if x is not None else default` across converter + mjml_generator (6 sites) |
| 22 (HIGH) | Duplicate Outlook button (VML + HTML both render) | VML in `<!--[if mso]>`, HTML in `<!--[if !mso]><!-->` |
| 23-24 (HIGH) | Templates ignore per-text styling | `text_styles` list threaded into Jinja2 context |
| 25 (HIGH) | Section cache hash missing text styling | Added `font_size`, `font_weight`, `font_family`, `is_heading` to canonical dict |
| 26 (MED) | Missing `mso-line-height-rule:exactly` on headings | Added to `<h>` tag inner style |
| 27 (MED) | VML `stroke="f"` not proper XML | Changed to `stroke="false"` |
| 28 (MED) | Dark mode falsy: `if dark:` skips `#000000` | `if dark is not None:` |
| 31 (MED) | Template engine dark mode CSS falsy check | Explicit `== ""` check |
| 35 (LOW) | `sanitize_web_tags_for_email` CSS gaps | Shared `_DANGEROUS_CSS_RE` constant |

**Golden pattern enforcement:**
- G-REF-6: `<meta name="format-detection">` added to both MJML generators; `[data-ogsc]`/`[data-ogsb]` Outlook dark mode selectors added alongside `@media`
- G1, G-REF-2, G12 already implemented (verified during preflight)

**Security hardening (from code review):**
- Control char stripping moved BEFORE dangerous function regex (prevents `expre\x01ssion()` bypass)
- `javascript\s*:` regex allows whitespace before colon (prevents `javascript :` dodge)
- Removed unsafe `sanitized or original` fallback patterns (skip rule if sanitizer returns empty)
- Extracted shared `_DANGEROUS_CSS_RE` compiled regex constant

**Key deliverables:** 4 source files fixed, 30 new tests across 5 test files, 1511 design_sync tests pass. Pyright 0 errors (baseline), mypy 5 errors (baseline).

---

### 38.5 Import Service, HTML Import Adapter & Regression Tests `[Backend]`

**Completed:** 2026-03-28

Fixed 13 bugs across `html_import/dom_parser.py`, `service.py`, `ai_layout_classifier.py`, `html_import/style_parser.py`, `html_import/section_classifier.py`, `email_design_document.py`, `repository.py`. Added golden component round-trip regression suite.

| # | Bug | Fix |
|---|-----|-----|
| 36 (CRITICAL) | `_get_direct_text` drops `<b>`/`<strong>` content | Recurse into `_INLINE_TAGS`; expand `_TEXT_TAGS` with 7 inline formatting tags |
| 37 (HIGH) | `_filter_structure` drops `fill_color`, typography, padding (16+ fields) | `dataclasses.replace(node, children=filtered_children)` instead of manual DesignNode construction |
| 38 (HIGH) | Spacing tokens not populated | Already functional — `_extract_spacing` collects from section padding |
| 39 (HIGH) | Fidelity scores lost on process restart | `repository.py:update_import_fidelity`: `flush()` → `commit()` (called after status already committed) |
| 40 (HIGH) | `_build_prompt` IndexError on mismatched sibling_types | Bounds guard on `sibling_types` index; added column layout + padding context to prompt |
| 41 (MED) | Non-deterministic node IDs (UUID) | Hash of `tag:text:sourceline:sibling_idx` via MD5 |
| 42 (MED) | `transparent` parsed as black | `normalize_hex_color` returns `None` for `transparent`/`rgba(0,0,0,0)` |
| 43 (MED) | Text color not extracted from inline styles | New `color` field on `DocumentText` + JSON schema + extraction in `_walk_for_texts` |
| 44 (MED) | Unitless line-height (e.g. `1.5`) not parsed | `extract_font_size_px` bare number fallback |
| 45 (LOW) | Column detection missing inline-block pattern | Already functional — `_detect_columns` handles `display: inline-block` divs |
| 46 (LOW) | `max-width` not parsed for container width | Already functional — `_detect_container_width` checks `max-width` |
| 47 (LOW) | Preheader sections not detected | New Rule 1b: hidden/zero-height text-only sections near top |
| 48 (LOW) | Social classification misses image-based social strips | Check image `node_name` for social keywords; require ≥2 matches |

**Golden template regression suite** (`test_golden_roundtrip.py`, 19 tests):
- 5 schema validation tests (hero-block, column-layout-2, article-card, product-card, footer)
- 6 import fidelity tests (heading detection, button extraction, unsubscribe text, column layout, text color)
- 5 round-trip conversion tests (role="presentation", heading tags, `<p>` tags, `<a>` buttons)
- 2 Bug 36 regression tests (bold/strong/em preservation)
- 1 Bug 37 regression test (fill_color + 8 other fields preserved through `_filter_structure`)

**Key deliverables:** 8 source files fixed, 1 JSON schema updated, 19 new golden regression tests, 1530 design_sync tests pass. Pyright 0 errors on target files, security lint clean.

---

### ~~38.6 Component Matcher & Renderer Fidelity Fixes `[Backend]`~~ DONE

**Completed:** 2026-03-28

Fixed 11 bugs in `component_matcher.py`, `component_renderer.py`, `figma/layout_analyzer.py`, and `email_design_document.py`. Buttons now render as CTA elements, text colors propagate from design data, column fills produce structured semantic HTML, and placeholder text is suppressed.

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 49 | CRITICAL | Button text as body paragraphs in columns | `_build_column_fill_html()` renders `<a>` with inline styles per G-REF-3 |
| 50 | CRITICAL | No text color → dark on colored bg | `text_color` field on TextBlock, extracted from DesignNode, threaded to token overrides |
| 51 | HIGH | Column fills = raw text dump | Semantic `<h3>`/`<p>`/`<a>` structure per G-REF-5 via `_build_column_fill_html()` |
| 52 | HIGH | Article-card for ANY images+texts | Guard: column_groups → text-block; >2 images → image-grid |
| 53 | HIGH | Only first body paragraph | `_fills_text_block`/`_fills_article_card` wrap each body text in `<p>` |
| 54 | HIGH | Placeholder text leaks | `_is_placeholder()` regex + `_strip_placeholder_urls()` post-render |
| 55 | MED | CTA URLs hardcoded `#` | `_safe_url()` validates and passes `btn.url` from design data |
| 56 | MED | Button fill_color not extracted | `fill_color` field on ButtonElement, extracted from DesignNode.fill_color |
| 57 | MED | Text-block sections ignore buttons | CTA HTML appended to body slot when buttons present |
| 58 | MED | Color CSS injection possible | `_safe_color()` hex validator + `(?<!-)` lookbehind in renderer regex |
| 59 | LOW | EDD bridge drops new fields | `getattr(t, "text_color", None)` propagation in `email_design_document.py` |

**Security hardening:**
- `_safe_color()` — hex color validator rejects CSS injection (`#333;position:fixed`)
- `_safe_url()` — URL scheme allowlist (http/https/mailto/tel/relative only)
- `(?<!-)` negative lookbehind in `_replace_heading_color`/`_replace_body_color` prevents `background-color:` corruption
- `_HEX_COLOR_RE` validation gate on token override color values

**New tests** (31 tests across 2 files):
- `test_component_matcher.py` — 8 test classes: TestSemanticColumnHTML (5), TestTextColorOverrides (2), TestArticleCardGuard (2), TestMultiParagraphBody (2), TestPlaceholderSuppression (2), TestButtonInTextBlock (1), TestURLValidation (4), TestColorValidation (3), plus `_make_section` factory extended with `column_groups`
- `test_component_renderer.py` — 5 tests: heading/body color overrides, background-color regression, placeholder URL strip

**Key deliverables:** 4 source files fixed, 2 test files updated (31 new tests), 1443 design_sync tests pass. Pyright 10 errors (= baseline, 0 new), security lint clean.

---

### 38.8 Image Alt Text, Font Family Preservation & Background Images `[Backend]` — DONE

Fixed 3 cross-cutting data fidelity issues: (1) `_meaningful_alt()` generates contextual alt text from node names, adjacent headings, or section type — eliminates all `alt="mj-image"` output, (2) `_font_stack()` preserves Figma-specified font families with progressive fallback instead of hardcoded Arial, (3) background images render via CSS `background-image` + VML `v:fill` for Outlook. Alt text via `html.escape()`, background URLs validated (http/https only), font names sanitized. 12 new tests.

---

## Phase 39 — Pipeline Hardening, Figma Enrichment & Quality Infrastructure (Complete)

### 39.5 Custom Lint Rules for Pipeline Anti-Patterns `[Backend]` — Completed 2026-03-28

**Problem:** `0.0 or 1.0` evaluates to `1.0` in Python because `0.0` is falsy. This was Phase 38's most common bug class — found in opacity, padding, font size, and positioning across 13 files (45 instances).

**Solution:** Three-layer static analysis preventing reintroduction:

1. **Semgrep rule** (`.semgrep/rules/falsy-numeric-trap.yaml`) — AST-aware `$X or $NUMERIC` detection via `metavariable-regex` restricting `$DEFAULT` to numeric literals. Scoped to `app/design_sync/`, severity ERROR. First custom Semgrep rule in the project (`.semgrep/` directory created).
2. **Pre-commit hook** — Regex fallback (`grep -rn '\bor -\?[0-9]'`) with comment and test file exclusions. Catches multi-line expressions Semgrep might miss.
3. **Makefile target** — `make lint-numeric` wired into both `make check` and `make check-full`.

**Files created:**
- `.semgrep/rules/falsy-numeric-trap.yaml` — Semgrep rule definition
- `.semgrep/tests/falsy-numeric-trap.py` — Test file (7 true positives + 5 true negatives)

**Files modified:**
- `.github/workflows/semgrep.yml` — Added `./.semgrep/rules` to `SEMGREP_RULES`
- `.pre-commit-config.yaml` — Added `falsy-numeric-trap` local hook
- `Makefile` — Added `lint-numeric` target, wired into `check` and `check-full`
- `pyproject.toml` — Excluded `.semgrep/` from ruff
- 13 source files in `app/design_sync/` — 45 violations fixed (`x or N` → `x if x is not None else N`)

**Key deliverables:** Semgrep rule + tests passing, pre-commit hook, `make lint-numeric` clean, 45 violations fixed across 13 files, 1351 design_sync tests pass. Pyright improved (180 vs 235 baseline), mypy improved (20 vs 59 baseline), security lint clean.

---

### 39.2 Testing Infrastructure `[Backend]` — Completed 2026-03-28

**Problem:** Phase 38 found 63 bugs, most trivially detectable (`0.0 or 1.0`, missing fields, wrong thresholds). Root causes: (1) parser tests used synthetic objects, not real API responses, (2) no property-based testing for edge values like `opacity=0.0`, (3) no contracts between pipeline stages caught field-dropping, (4) no validator caught `alt="mj-image"` or missing `role="presentation"`.

**Solution:** 5 testing layers, 91 new tests:

1. **Real Figma fixtures** (39.2.1) — 5 sanitized API response JSONs in `figma/tests/fixtures/`: mammut_hero (hero+CTA+headline), ecommerce_grid (2x2 product grid with `opacity=0.0` edge case), newsletter_2col (2-column with hyperlinks+strokes), transactional (receipt line items with `visible=false` node), navigation_header (horizontal nav with mailto links). 26 tests exercise `_parse_node()` against real payloads.
2. **Hypothesis property tests** (39.2.2) — `design_nodes()` composite strategy generates arbitrary DesignNode trees. 9 tests verify: opacity roundtrip, opacity survives normalize, normalize never crashes (200 examples), output tree validity, sanitize never crashes, MSO preservation, `<p>` in `<td>` preservation, dimension roundtrip, typography values.
3. **Pipeline contract tests** (39.2.3) — 30 parametrized tests across 6 contracts: parse→normalize, normalize→analyze, text/button ID disjointness, no-None-IDs, page preservation, section node IDs exist in tree.
4. **Email HTML validity** (39.2.4) — `assert_valid_email_html()` reusable assertion checking G1 (table role), G-REF-2a (img display:block), G-REF-2b (meaningful alt), NO-DIV-LAYOUT (float/flex/grid on div). 11 unit tests + all 15 golden templates validated.
5. **Visual regression** (39.2.5) — `playwright>=1.40` added to dev deps. Existing `rendering-regression` infra (ODiff-based) already wired via `make rendering-baselines` / `make rendering-regression`.

**Files created:**
- `app/design_sync/tests/conftest.py` — `make_design_node()`, `make_file_structure()` shared factories
- `app/design_sync/figma/tests/fixtures/*.json` — 5 sanitized Figma API response fixtures
- `app/design_sync/figma/tests/test_parse_real_fixtures.py` — 26 fixture parsing tests
- `app/design_sync/tests/test_hypothesis_properties.py` — 9 property-based tests
- `app/design_sync/tests/test_pipeline_contracts.py` — 30 contract tests
- `app/design_sync/tests/test_email_html_validity.py` — 26 email validity tests

**Files modified:**
- `pyproject.toml` — Added `playwright>=1.40` to dev dependencies

**Key deliverables:** 91 new tests, 0 pyright errors on new files, all 15 golden templates pass validation, 1681 existing design_sync tests unaffected. Fixtures include edge cases: `opacity=0.0`, `visible=false`, per-corner `corner_radii`, `mailto:` hyperlinks.

---

### 39.3 Eliminate Dual MJML Generation Path `[Backend]` — Completed 2026-03-28

**Problem:** Two MJML generation paths — `mjml_generator.py` (454 LOC, programmatic) and `mjml_template_engine.py` (231 LOC, Jinja2) — produced different output for the same input. Fixing one left the other broken. The `converter_service.py` had a silent `try/except` fallback that masked template errors.

**Solution:** Unified to a single template-based path:

1. **Relocated `inject_section_markers()`** from `mjml_generator.py` to `mjml_template_engine.py` — the only function worth preserving (post-compile HTML processing for `data-section-type`/`data-node-id` attributes).
2. **Removed dual-path logic** in `converter_service.py` — deleted `use_templates` parameter, removed `try/except` fallback to `generate_mjml()`, template errors now propagate immediately.
3. **Deleted `mjml_generator.py`** (454 LOC) and `tests/test_mjml_generator.py` (545 LOC).
4. **Migrated tests** — `inject_section_markers` test moved to `test_mjml_templates.py`. `test_e2e_mjml_pipeline.py` rewritten to use `MjmlTemplateEngine` (11 tests). `test_phase35_integration.py` W3C round-trip test updated. `test_mjml_convert.py` fallback test removed.

**Template coverage:** All 11 `EmailSectionType` values covered via `_SECTION_TEMPLATE_MAP` and `_COLUMN_TEMPLATE_MAP` — HEADER, PREHEADER, HERO, CONTENT (4 column variants + image-only), CTA, FOOTER, SOCIAL, DIVIDER, SPACER, NAV, UNKNOWN.

**Files deleted:**
- `app/design_sync/mjml_generator.py` (454 LOC)
- `app/design_sync/tests/test_mjml_generator.py` (545 LOC)

**Files modified:**
- `app/design_sync/mjml_template_engine.py` — Added `inject_section_markers()` + `DesignLayoutDescription` import
- `app/design_sync/converter_service.py` — Removed `generate_mjml` import, removed fallback, removed `use_templates` param
- `app/design_sync/tests/test_mjml_templates.py` — Added `TestInjectSectionMarkers` class
- `app/design_sync/tests/test_mjml_convert.py` — Removed `TestConvertMjmlFallback` class
- `app/design_sync/tests/test_e2e_mjml_pipeline.py` — Rewrote `TestNormalizeToMjmlPipeline` to use template engine
- `app/design_sync/tests/test_phase35_integration.py` — Updated W3C round-trip test

**Key deliverables:** Single MJML generation path via `MjmlTemplateEngine`. ~1000 LOC net reduction. 74 tests pass. Pyright baseline unchanged (43 errors on target files). Security lint clean. Jinja2 autoescaping + `html.escape()` for XSS safety.

---

### ~~39.1 Figma API Enrichment & Data Model Gaps `[Backend]`~~ DONE

**What:** Extract ~12 conversion-relevant Figma API fields previously ignored. Enrich `DesignNode`, `TextBlock`, `ButtonElement` with hyperlinks, corner radius, rich text style runs, alignment, and borders. Unlocks functional CTA buttons, rounded corners, mixed-format text, and correct alignment.

**New data models:**
- `StyleRun` frozen dataclass (`start`, `end`, `bold`, `italic`, `underline`, `strikethrough`, `color_hex`, `font_size`, `link_url`) in `protocol.py`
- 9 new fields on `DesignNode`: `hyperlink`, `corner_radius`, `corner_radii`, `text_align`, `primary_axis_align`, `counter_axis_align`, `stroke_weight`, `stroke_color`, `style_runs`
- 5 new fields on `TextBlock`: `text_align`, `hyperlink`, `style_runs`, `text_transform`, `text_decoration`
- 2 new fields on `ButtonElement`: `border_radius`, `text_color`
- 3 new fields on `DocumentButton`: `url`, `border_radius`, `fill_color`
- 1 new field on `DocumentText`: `text_align`

**Figma extraction (figma/service.py):**
- `_validate_hyperlink()` — URL scheme allowlist (http/https/mailto), rejects `javascript:`, `data:`, etc.
- `_extract_stroke()` — first SOLID stroke → hex color + weight
- `_parse_style_runs()` — `characterStyleOverrides` + `styleOverrideTable` → `tuple[StyleRun, ...]`
- `_parse_node()` extended to extract all 9 new fields with mapping dicts `_TEXT_ALIGN_MAP`, `_AXIS_ALIGN_MAP`

**Rendering pipeline:**
- `_render_style_runs()` in `converter.py` — splits text by StyleRun segments, wraps with `<strong>`, `<em>`, `<s>`, `<span style="color:">`, `<a href="">`. All text `html.escape()`d.
- `_render_button()` — uses `node.corner_radius` (was hardcoded `4px`), `node.hyperlink` (was hardcoded `"#"`), computes VML `arcsize` from radius
- Frame rendering — emits `border: Npx solid color` from `stroke_weight`/`stroke_color`, `border-radius` from `corner_radius`
- Text rendering — emits `text-align:` from `text_align`
- `_mjml_button()` — uses `btn.url`, `btn.border_radius`, `btn.fill_color`, `btn.text_color`
- `_mjml_text()` — uses `text.text_align` for `align=` attribute
- `from_section()` in `email_design_document.py` — threads enriched fields to `DocumentText` and `DocumentButton`

**Files modified (8):** `protocol.py`, `figma/service.py`, `figma/layout_analyzer.py`, `converter.py`, `mjml_generator.py`, `email_design_document.py`, `tests/test_converter_fixes.py`, `tests/test_mjml_generator.py`, `figma/tests/test_parse_node_fidelity.py`

**Key deliverables:** 9 new DesignNode fields extracted from Figma API. Buttons link to real URLs (not `"#"`). Corner radius flows through CSS + VML. Rich text style runs rendered as inline HTML. Borders from strokes. Text alignment preserved. URL scheme validation (http/https/mailto only). 26 new tests. 1575 design_sync tests pass. Pyright 37 errors (baseline 36). Security lint clean.

---

### ~~39.4 Automated Quality Contracts `[Backend]`~~ DONE

`app/design_sync/quality_contracts.py` — `QualityWarning` dataclass + 3 pure sync check functions + `run_quality_contracts()` orchestrator. **Contrast:** `check_contrast()` parses inline CSS, walks ancestors for bg, computes WCAG 2.1 ratio, warns if <4.5:1 normal or <3.0:1 large text. **Completeness:** `check_completeness()` validates section/button counts. **Placeholders:** `check_placeholders()` detects placeholder text. `ConversionResult.quality_warnings` field added, wired into all 3 conversion paths. 19 tests.

---

### ~~39.6 Component Matcher Architectural Improvements `[Backend]`~~ DONE

`_score_candidates()` replaces `_match_content()` with multi-candidate scoring — product-grid (0.95), article-card (0.9), image-gallery (0.88), image-grid (0.85), category-nav (0.7). 3 new component seeds with table-based HTML, MSO conditionals, data-slot markers. `_validate_slot_fill_rate()` warns <50% slot fills. `match_confidences: dict[int, float]` on `ConversionResult`. Column assignment uses `column_groups.column_idx`. 22 tests.

---

### ~~39.7 Golden Template Conformance Gate `[Backend]`~~ DONE

`app/design_sync/tests/test_golden_conformance.py` — 12 conformance checks (G1 role=presentation, G2 display:block on images, G3 meaningful alt, G5 no div layout CSS, G6 MSO conditionals, G7 cellpadding/cellspacing, G10 email-safe meta, G11 MSO table reset, column class, VML fallback). 26 tests, 9 skipped (components without images). `make golden-conformance` wired into `make check` and `make check-full`. Runs in <1s.

---

### ~~38.7 Column HTML Structure — `<div class="column">` Pattern~~ `[Backend]` DONE

**Completed:** 2026-03-28

**What changed:** Replaced the converter's multi-column wrapper from `<table class="column" style="display:inline-block">` to `<div class="column" style="display:inline-block">` + inner `<table>`, matching all 16 golden components. Added sanitizer exemption for `class="column"` divs and asymmetric gutter padding.

**Converter (`converter.py`):**
- `_render_multi_column_row()` — column wrapper changed from `<table class="column">` to `<div class="column">` + nested inner `<table>`. MSO ghost table structure preserved. B3 empty-column path updated.
- `_col_padding()` — new helper for asymmetric gutter padding (G11 pattern): left col gets right padding, right col gets left padding, middle cols get both sides.
- `sanitize_web_tags_for_email()` — added `class="column"` exemption before `_LAYOUT_CSS_RE` check. Column divs are preserved instead of being converted to `<table>` wrappers.
- Container `<td>` already had `font-size:0; text-align:center` (G12).

**Tests (`tests/test_converter_fixes.py`):**
- `TestTableColumnWrapper` — assertions inverted: `<div class="column"` present, `<table class="column"` absent. Method renamed `test_column_uses_div_not_table`. Table count assertion (`<= 6`) unchanged (1:1 table swap).

**Files modified (2):** `converter.py`, `tests/test_converter_fixes.py`

**Key deliverables:** Column wrapper matches golden components (G-REF-1). Mobile CSS `.column { display: block !important; }` now works (div responds, table didn't). Sanitizer preserves column divs. Asymmetric gutter padding. 1379 design_sync tests pass. Pyright 0 errors on target files. Security lint clean.

---

