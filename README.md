# Email Innovation Hub

[![CI](https://github.com/linardsb/merkle-email-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/linardsb/merkle-email-hub/actions/workflows/ci.yml)

Centralised email development platform with AI-powered agents. Build, preview, QA, and export HTML emails from a single workspace — CMS-agnostic, security-first, GDPR-compliant.

Built on open-source technologies with zero licence fees: FastAPI + Next.js 16 + PostgreSQL + Redis.

## Architecture

**Vertical Slice Architecture** — each feature owns its models, schemas, routes, and business logic under `app/{feature}/`.

| Layer | Stack | Purpose |
|-------|-------|---------|
| Presentation | Next.js 16, React 19, Tailwind, shadcn/ui | Workspace UI, code editor, live preview, AI chat, QA dashboard |
| API Gateway | FastAPI, async endpoints, WebSocket | REST + real-time API, RBAC, rate limiting |
| Core Services | Email Engine, AI Orchestrator, QA Engine, Connectors | Build, test, validate, export email HTML |
| Data | PostgreSQL + pgvector, Redis | Projects, components, templates, embeddings, cache |
| Integration | CMS Connectors, Figma API, Litmus/EoA | External tool sync and client platform export |

### Backend Modules

| Module | API Prefix | Purpose |
|--------|-----------|---------|
| `projects` | `/api/v1/projects`, `/api/v1/orgs` | Multi-tenant client org isolation, project workspaces |
| `email_engine` | `/api/v1/email` | Maizzle build pipeline via sidecar at `http://maizzle-builder:3001` |
| `components` | `/api/v1/components` | Versioned reusable email components (header, CTA, hero, etc.) |
| `qa_engine` | `/api/v1/qa` | 10-point quality gate system |
| `connectors` | `/api/v1/connectors` | ESP export (Braze Content Blocks with Liquid packaging) |
| `approval` | `/api/v1/approvals` | Client approval workflow with feedback and audit trail |
| `personas` | `/api/v1/personas` | Test subscriber profiles (device, email client, dark mode) |
| `ai` | `/api/v1/chat` | AI orchestrator with 9 specialized agents |
| `knowledge` | `/api/v1/knowledge` | RAG pipeline (pgvector, hybrid search) |

### AI Agents (9 total)

| Agent | Purpose | Phase |
|-------|---------|-------|
| Scaffolder | Generate Maizzle HTML from campaign briefs | Sprint 2 |
| Dark Mode | Inject dark mode CSS, Outlook overrides, colour remapping | Sprint 2 |
| Content | Subject lines, preheaders, CTA text, tone adjustment | Sprint 2 |
| Outlook Fixer | MSO conditionals, VML backgrounds, table fallbacks | V2 |
| Accessibility Auditor | WCAG AA checks, contrast, alt text, AI alt generation | V2 |
| Personalisation | Liquid (Braze), AMPscript (SFMC), dynamic content | V2 |
| Code Reviewer | Static analysis, redundant code, file size optimisation | V2 |
| Knowledge | RAG-powered Q&A from knowledge base | V2 |
| Innovation | Prototype new techniques, feasibility assessment | V2 |

### QA Gate System (10 checks)

Located in `app/qa_engine/checks/`:

1. HTML validation — DOCTYPE, structural tags
2. CSS support — flags unsupported email client CSS
3. File size — Gmail 102KB clipping threshold
4. Link validation — HTTPS enforcement, valid protocols
5. Spam score — trigger word detection
6. Dark mode — color-scheme meta, prefers-color-scheme, Outlook overrides
7. Accessibility — lang attribute, alt text, table roles
8. Fallback — MSO conditionals, VML namespaces
9. Image optimisation — explicit dimensions, format validation
10. Brand compliance — client brand rules (configurable)

## Security

- **Zero Trust API**: every endpoint authenticated + authorized
- **JWT HS256**: 15-min access tokens + 7-day refresh, Redis-backed revocation
- **RBAC**: admin/developer/viewer roles enforced at route level
- **Row-Level Security**: PostgreSQL RLS on `client_org_id` — database-enforced isolation
- **Brute-force protection**: exponential backoff, 5-attempt lockout (15 min)
- **Secrets**: AES-256 for stored credentials, environment variables for config
- **Audit trail**: every state-changing API call logged
- **CORS lockdown**: whitelisted origins only, no wildcards in production

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- pnpm

### Local Development

```bash
make db              # Start PostgreSQL + Redis (Docker)
make dev             # Start backend (:8891) + frontend (:3000)
make dev-be          # Backend only
make dev-fe          # Frontend only
```

### Quality Checks

```bash
make check           # All checks (lint + types + tests)
make test            # Unit tests
make lint            # Format + lint (ruff)
make types           # mypy + pyright
```

### Database

```bash
make db-migrate      # Run migrations
make db-revision m="description"  # Create new migration
```

### Docker (Full Stack)

```bash
make docker          # Full stack (port :80)
make docker-down     # Stop all services
```

Services: PostgreSQL, Redis, FastAPI backend, Next.js frontend, Maizzle builder sidecar, nginx reverse proxy.

## Project Structure

```
email-hub/
├── app/                    # Backend features (VSA)
│   ├── core/               # Infrastructure (config, database, logging, middleware, health, rate_limit, redis)
│   ├── shared/             # Cross-feature utilities (pagination, timestamps, error schemas)
│   ├── auth/               # JWT auth + RBAC + user management
│   ├── ai/                 # AI layer (protocol interfaces, provider registry, chat API)
│   ├── knowledge/          # RAG pipeline (pgvector, document processing, hybrid search)
│   ├── streaming/          # WebSocket streaming (Pub/Sub, connection manager)
│   ├── projects/           # Client-scoped workspaces
│   ├── email_engine/       # Maizzle build orchestration
│   ├── components/         # Versioned email component library
│   ├── qa_engine/          # 10-point QA gate (checks/)
│   ├── connectors/         # ESP connectors (Braze)
│   ├── approval/           # Client approval portal
│   └── personas/           # Test persona engine
├── cms/                    # Frontend monorepo (Next.js 16 + React 19)
│   ├── apps/web/           # Main web application
│   └── packages/
│       ├── ui/             # Shared UI components + design tokens
│       └── sdk/            # Auto-generated TypeScript API client
├── email-templates/        # Maizzle project (layouts, templates, components)
├── services/
│   └── maizzle-builder/    # Node.js sidecar for Maizzle builds (Express, port 3001)
├── alembic/                # Database migrations
├── nginx/                  # Reverse proxy config
└── pyproject.toml          # Python dependencies + tooling config
```

## Roadmap

### Phase 0 — Foundation Blockers
- Database migrations for all email-hub models + RLS policies
- shadcn/ui component library initialization
- OpenAPI TypeScript SDK generation
- Authenticated API client layer with token refresh

### Phase 1 — Editor + Build Pipeline (Sprint 1)
- Project dashboard page
- Split-pane workspace (editor + preview + AI chat)
- Monaco editor with HTML/CSS/Liquid syntax
- Maizzle live preview (compile-on-save)
- Test persona engine UI
- Template CRUD + versioning

### Phase 2 — Intelligence + Export (Sprint 2)
- Wire AI provider (Claude/OpenAI) with model routing
- Scaffolder, Dark Mode, Content agents
- AI chat sidebar UI
- Component library (backend + browser UI)
- 10-point QA gate UI
- Braze connector + raw HTML export
- RAG knowledge base seeding

### Phase 3 — Client Handoff + Polish (Sprint 3)
- Client approval portal (viewer role, feedback, audit)
- Rendering intelligence dashboard
- Error handling, loading states, UI polish
- CMS + Nginx Docker stack (7 services)

### Phase 4 — V2
- Remaining 6 AI agents
- SFMC, Adobe Campaign, Taxi for Email connectors
- Figma design sync
- Litmus / Email on Acid integration
- Collaborative editing, localisation, visual Liquid builder

## Configuration

Nested Pydantic settings with `env_nested_delimiter="__"`:

```
DATABASE__URL, DATABASE__POOL_SIZE
REDIS__URL
AUTH__JWT_SECRET_KEY, AUTH__ACCESS_TOKEN_EXPIRE_MINUTES
AI__PROVIDER, AI__MODEL, AI__API_KEY
```

## Roles

| Role | Access |
|------|--------|
| `admin` | Full access, user management, credential configuration |
| `developer` | Project workspace, builds, exports, AI agents |
| `viewer` | Read-only approval portal, feedback only |
