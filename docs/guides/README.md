# Workflow Documentation

This folder contains documentation for each workflow available in the Merkle Email Hub Ecosystem.

Workflows automate multi-step email operations — building, QA, translation, approval, and ESP delivery — into single-trigger pipelines powered by [Kestra](https://kestra.io/).

## Available Workflows

| Workflow | Description | Trigger |
|----------|-------------|---------|
| [Email Build & QA](./email-build-and-qa.md) | Build an email via AI blueprint, then run QA + chaos tests in parallel | Manual |
| [Multilingual Campaign](./multilingual-campaign.md) | Build, translate to multiple locales, approve, and push to ESP | Manual |
| [Weekly Newsletter](./weekly-newsletter.md) | Automated weekly newsletter: build, QA, approve, push | Scheduled (Mon 09:00 UTC) |
| [Design Import Pipeline](./design-import-pipeline.md) | Import a Figma design, build email from it, QA, and approve | Manual |

## Guides

| Guide | Description |
|-------|-------------|
| [Design Sync Connection Guide](./design-sync-connection-guide.md) | How to connect Figma/Sketch/Canva files, avoid rate limits, troubleshoot errors |

## How to Use

1. Navigate to **Ecosystem > Workflows** in the CMS
2. Find the workflow you need under **Available Flows**
3. Click **Trigger** to open the trigger dialog
4. Paste the required JSON inputs (documented per workflow below)
5. Click **Trigger** — monitor progress in the **Executions** panel

## Configuration

Workflows require `KESTRA__ENABLED=true` in your environment. In demo mode, the UI returns mock data without a real Kestra instance.

## API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/api/v1/workflows/` | List available flows | Any authenticated user |
| `POST` | `/api/v1/workflows/trigger` | Trigger a workflow | Any authenticated user |
| `GET` | `/api/v1/workflows/{execution_id}` | Get execution status | Any authenticated user |
| `GET` | `/api/v1/workflows/{execution_id}/logs` | Get execution logs | Any authenticated user |
| `GET` | `/api/v1/workflows/flows/{flow_id}` | Get flow definition | Any authenticated user |
| `POST` | `/api/v1/workflows/flows` | Create custom flow (YAML) | Admin only |

## Task Types

All workflows are composed from these reusable task types:

| Task Type | Description |
|-----------|-------------|
| `hub.blueprint_run` | Run the AI blueprint engine to generate email HTML |
| `hub.qa_check` | Run QA checks (HTML validation, accessibility, dark mode, spam score, etc.) |
| `hub.chaos_test` | Chaos/resilience testing on generated HTML |
| `hub.locale_build` | Build locale-specific versions of a template |
| `hub.approval_gate` | Pause execution until an admin approves |
| `hub.esp_push` | Push final HTML to an ESP (Braze, SFMC, etc.) |
