# Multilingual Campaign

End-to-end campaign pipeline that builds an email, translates it to multiple locales, waits for admin approval, and pushes to an ESP.

**Flow ID:** `multilingual-campaign`
**Trigger:** Manual
**Namespace:** `merkle-email-hub`

## When to Use

- Launching a campaign that needs to ship in multiple languages
- You want a single trigger to handle build → translate → approve → deploy
- Ensuring no campaign reaches an ESP without admin sign-off

## Pipeline Steps

```
build (AI Blueprint)
  │  retries: 3 × 30s
  ▼
locale_builds (Per-Locale Translation)
  ▼
approval (Admin Gate)
  │  blocks until approved
  ▼
push (ESP Delivery)
```

1. **build** (`hub.blueprint_run`) — Generates the base email HTML from your brief. Retries up to 3 times with 30s intervals.
2. **locale_builds** (`hub.locale_build`) — Takes the base template and builds locale-specific versions for each language you specified.
3. **approval** (`hub.approval_gate`) — Pauses the pipeline and waits for an admin to approve. This is your review checkpoint — the campaign does not proceed until someone with the `admin` role approves it.
4. **push** (`hub.esp_push`) — Pushes the final HTML to your configured ESP (Braze, SFMC, etc.) as a content block.

## Inputs

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `brief` | string | Yes | — | The email build brief |
| `blueprint_name` | string | No | `"full_pipeline"` | Which blueprint to run |
| `project_id` | integer | Yes | — | Project ID (required for design system, approval routing, and ESP config) |
| `locales` | JSON array | Yes | — | Array of locale codes to build |
| `connector_type` | string | No | `"braze"` | ESP connector to push to (`"braze"`, `"sfmc"`, `"adobe"`) |

## Example JSON Input

```json
{
  "brief": "Q3 product launch announcement with hero banner and feature highlights",
  "project_id": 42,
  "locales": ["en", "de", "fr", "es"],
  "connector_type": "braze"
}
```

Full options:

```json
{
  "brief": "Holiday campaign with personalized product recommendations",
  "blueprint_name": "full_pipeline",
  "project_id": 15,
  "locales": ["en-US", "en-GB", "de-DE", "fr-FR", "ja-JP"],
  "connector_type": "sfmc"
}
```

## Outputs

| Output | Source | Description |
|--------|--------|-------------|
| `outputs.build.html` | build step | Base email HTML |
| `outputs.build.run_id` | build step | Blueprint run ID |
| Locale versions | locale_builds step | Per-locale HTML variants |
| Approval record | approval step | Who approved and when |
| ESP push result | push step | Content block name: `campaign-{project_id}` |

## Where to Find Input Values

- **`brief`** — Write it yourself, or copy from the Briefs page
- **`project_id`** — Found in the URL when viewing a project, or via `GET /api/v1/projects/`
- **`locales`** — Check your project's configured locales in Settings, or the Translations tab in Ecosystem. Common codes: `"en"`, `"de"`, `"fr"`, `"es"`, `"ja"`, `"pt-BR"`
- **`connector_type`** — Check which ESP is connected in **Ecosystem > Connectors**. Options: `"braze"`, `"sfmc"`, `"adobe"`
