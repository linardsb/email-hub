# Email Build & QA

Standard email build pipeline that generates an email via the AI blueprint engine, then runs QA checks and chaos tests in parallel.

**Flow ID:** `email-build-and-qa`
**Trigger:** Manual
**Namespace:** `email-hub`

## When to Use

- You have a brief and want to generate an email with full quality validation
- Quick iteration cycle: change brief, trigger, check QA results
- Pre-flight check before sending a campaign to the multilingual or newsletter pipeline

## Pipeline Steps

```
build (AI Blueprint)
  │  retries: 3 × 30s
  ▼
┌─────────────────────┐
│  Parallel            │
│  ├─ qa (QA Checks)   │
│  └─ chaos (Chaos)    │
└─────────────────────┘
```

1. **build** (`hub.blueprint_run`) — Runs the AI blueprint engine to generate email HTML from your brief. Retries up to 3 times with 30s intervals on failure.
2. **qa** (`hub.qa_check`) — Runs the full QA suite (HTML validation, CSS support, accessibility, dark mode, spam score, link validation, etc.) against the generated HTML.
3. **chaos** (`hub.chaos_test`) — Runs chaos/resilience tests against the generated HTML to verify it degrades gracefully.

Steps 2 and 3 run **in parallel** after the build completes.

## Inputs

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `brief` | string | Yes | — | The email build brief describing what to generate |
| `blueprint_name` | string | Yes | `"full_pipeline"` | Which blueprint to run |
| `project_id` | integer | No | — | Project ID for design system and brand rules |

## Example JSON Input

```json
{
  "brief": "Summer sale promotional email for UK market with hero image, 3 product cards, and CTA button",
  "blueprint_name": "full_pipeline",
  "project_id": 42
}
```

Minimal (using defaults):

```json
{
  "brief": "Monthly product update newsletter"
}
```

## Outputs

| Output | Source | Description |
|--------|--------|-------------|
| `outputs.build.html` | build step | The generated email HTML |
| `outputs.build.run_id` | build step | Blueprint run ID for traceability |
| QA results | qa step | Pass/fail per check with details |
| Chaos results | chaos step | Resilience test results |

## Where to Find Input Values

- **`brief`** — Write it yourself, or copy from the Briefs page
- **`blueprint_name`** — Usually `"full_pipeline"`. Other blueprints are listed in the AI agents documentation
- **`project_id`** — Found in the URL when viewing a project (e.g., `/projects/42` → `42`), or via `GET /api/v1/projects/`
