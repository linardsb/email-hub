# Weekly Newsletter

Automated weekly newsletter pipeline that builds, QA-checks, gets approval, and pushes to an ESP on a recurring schedule.

**Flow ID:** `weekly-newsletter`
**Trigger:** Scheduled — every Monday at 09:00 UTC
**Namespace:** `merkle-email-hub`
**Cron:** `0 9 * * MON`

## When to Use

- Recurring newsletters that follow the same structure each week
- You want a hands-off pipeline that only requires admin approval before sending
- Consistent Monday morning sends with built-in quality gates

## Pipeline Steps

```
⏰ Cron (Mon 09:00 UTC)
  ▼
build (AI Blueprint)
  │  retries: 3 × 30s
  ▼
qa (QA Checks)
  ▼
approval (Admin Gate)
  │  blocks until approved
  ▼
push (ESP Delivery)
```

1. **Cron trigger** — Fires automatically every Monday at 09:00 UTC. Can also be triggered manually.
2. **build** (`hub.blueprint_run`) — Generates the newsletter HTML using the `full_pipeline` blueprint. Retries up to 3 times.
3. **qa** (`hub.qa_check`) — Runs the full QA suite against the generated HTML.
4. **approval** (`hub.approval_gate`) — Pauses and waits for an admin to review and approve.
5. **push** (`hub.esp_push`) — Pushes approved HTML to the ESP as content block `newsletter-{project_id}`.

## Inputs

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `brief` | string | No | `"Weekly newsletter"` | The newsletter brief (override for special editions) |
| `project_id` | integer | Yes | — | Project ID for design system and routing |
| `connector_type` | string | No | `"braze"` | ESP connector to push to |

## Example JSON Input

Minimal (scheduled runs use defaults):

```json
{
  "project_id": 42
}
```

Custom edition:

```json
{
  "brief": "Special edition: year-in-review newsletter with top 10 articles",
  "project_id": 42,
  "connector_type": "sfmc"
}
```

## Outputs

| Output | Source | Description |
|--------|--------|-------------|
| `outputs.build.html` | build step | Newsletter HTML |
| QA results | qa step | Pass/fail per check |
| Approval record | approval step | Who approved and when |
| ESP push result | push step | Content block name: `newsletter-{project_id}` |

## Where to Find Input Values

- **`project_id`** — Found in the URL when viewing a project, or via `GET /api/v1/projects/`
- **`connector_type`** — Check which ESP is connected in **Ecosystem > Connectors**

## Notes

- The scheduled trigger runs automatically — you only need to approve when prompted
- For manual triggers (e.g., special editions), click Trigger in the Ecosystem UI and override the brief
- If the build fails all 3 retries, the execution stops and shows as FAILED in the Executions panel
