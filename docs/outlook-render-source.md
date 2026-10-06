# Classic-Outlook render source (CE-4, #422)

Where renders of converter output in classic Outlook (the Word rendering engine) come from, what exists in the repo today, and the input bundle every option consumes. Part 1 of #422; the renders and the button report are part 2.

## Status

**Decision pending** (user, 2026-10-06). The user deferred the choice between Litmus, Email on Acid, an own Windows rig and manual sends.

Interim position is HD2 (`docs/architecture/dsl-compiler.md:225`): no spend; Outlook findings come from markup inspection and are marked inferred. Every Outlook finding in the converter epic so far (R10, CE-11 AC 9, CE-19 kill test 3) is of that kind.

## Requirement

The source must render **classic Outlook for Windows**, which lays out HTML with the Word engine. A source that renders only new Outlook or Outlook.com does not meet #422: those use a browser engine and ignore the `<!--[if mso]>` path the converter writes for Word.

The render must show VML buttons (`v:roundrect`), because the open questions are about them: radius, fill, stroke, size, and whether the stroke grows the button box (CE-11 D8 / AC 9).

## What exists

Inventory of `app/rendering/` at `45d71cea` (observed, source read 2026-10-06). No existing component is a classic-Outlook source.

| Component | What it is | Classic-Outlook source? |
|---|---|---|
| `app/rendering/litmus/service.py:1-44` | Docstring "placeholder implementation"; `submit_test` returns a hash-derived id, `get_results` returns hard-coded `https://placeholder.litmus.com/...` URLs | No: no HTTP call, no key read |
| `app/rendering/eoa/service.py:1-40` | Same shape, `placeholder.emailonacid.com` URLs | No |
| `app/rendering/service.py:76-80,93-104` | Provider registry (litmus, eoa, local); `_get_provider` instantiates the class with no arguments, so no API key reaches a provider | No |
| `app/core/config/rendering.py:33` | `provider: str = "litmus"`, so real callers get the placeholder by default | No (ledger `ce-4-rendering-providers-placeholder`) |
| `app/rendering/local/profiles.py:109-116` | `outlook_desktop` profile: `browser="cr"`, labelled "Word engine — CSS preprocessing only" | No: Chromium |
| `app/rendering/local/emulators.py:338+` | Word-engine emulator: regex removal of CSS the Word engine ignores, plus MSO-conditional handling | No: a browser still draws the result and cannot draw VML |
| `app/rendering/sandbox/` | Mailpit / Roundcube SMTP sandbox | No: delivers mail, renders nothing in Outlook |
| `app/rendering/gate.py`, `visual_diff.py` | Pre-send confidence gate over local profiles; odiff wrapper | Consumers of renders, not sources |
| Converter wiring | `app/design_sync/fidelity_service.py:162-163` and `visual_verify.py:246-247,397` import the local Chromium provider, runner, crop and odiff; nothing in `app/design_sync/` imports litmus or eoa | Chromium only |

The CE-1 fidelity gate (`docs/fidelity-gate.md`) also renders in Chromium only.

## Options

Every vendor capability below is **vendor-documented, not tried**. Work-to-land figures are **expected** (not built). No pricing is given: none was verified.

| | Litmus Instant API | Email on Acid API v5 | Own rig | Manual |
|---|---|---|---|---|
| Word engine? | Yes: client list includes OL2000–OL2019 and OFFICE365 (Windows desktop) | Client list comes from a "Get Available Clients" call; Outlook desktop ids not shown in the overview read | Yes: real classic Outlook | Yes, if sent to a classic-Outlook mailbox |
| Versions / DPI | Many versions per call; DPI not documented | Per the clients call | One Outlook version and one DPI per VM image | Whatever machine opens it |
| Input | POST JSON with `html_text` → `email_guid`, then GET a preview per client | JSON over HTTP Basic auth (`api_key:password`); HTML or URL source | `MailItem.HTMLBody` set from `email.html` | Send `email.html` via an ESP or SMTP |
| Images | Absolute URLs (docs don't state it; the HTML is fetched remotely, so relative srcs cannot resolve) | Same | Absolute URLs, or CID attachments | Absolute URLs, or CID attachments |
| Credentials / spend | API key; access "evaluated on a case-by-case basis" (partners@litmus.com) | Account API key + password | Windows 11 ARM VM (Parallels/UTM) + classic Outlook licence (Microsoft 365 Apps or Office LTSC) | A classic-Outlook mailbox |
| Repeatability | Scriptable, seconds per client | Scriptable | Scriptable on a dev machine only (see below) | Human per run |
| Work to land | One client module + one script, ~150 lines | Same, ~150 lines | One pywin32 script, ~150 lines, plus VM setup | No code; screenshots by hand |

Notes per option:

- **Litmus.** Endpoints `https://instant-api.litmus.com/v1/emails` and `.../emails/{email_guid}/previews/{client}`, three image sizes (full, thumb450, thumb). Source: [Litmus Instant API docs](https://docs.litmus.com/instant), opened 2026-10-06.
- **Email on Acid.** Source: [Email on Acid API v5 docs](https://api.emailonacid.com/docs/v5), opened 2026-10-06. Email on Acid is moving into Mailgun Inspect: transitions start June 2026, and contract customers keep the API through their current term ([Mailgun Inspect announcement](https://www.mailgun.com/blog/product/mailgun-inspect-next-generation/), opened 2026-10-06). Mailgun's help article "Email on Acid to Mailgun Inspect API Migration Plan" returned 403 and is cited by title only. Whether Inspect lists classic Outlook was not found. Choosing this option means checking the API's future first.
- **Own rig.** Route: load `email.html` into `MailItem.HTMLBody`, open the inspector, export through `Inspector.WordEditor.ExportAsFixedFormat` to PDF, then convert to PNG. This route is **expected, not tried**; the fallback is a window screenshot. Microsoft does not support Office automation from "any unattended, non-interactive client application or component" ([Considerations for server-side Automation of Office](https://support.microsoft.com/help/257757), opened 2026-10-06), so the rig runs on a dev machine with a logged-in user, not in CI or as a service.
- **Manual.** Send each case to a classic-Outlook mailbox and screenshot it. No code, no repeatability; fine for a one-off answer to CE-11 AC 9.

## Images

The converter writes image refs as `/api/v1/design-sync/assets/<node>.png`, which resolve only behind the live API. A render source needs absolute URLs it can reach: upload `<out>/<case>/assets/` somewhere public, then export with `--asset-base-url` pointing at it. The own rig and manual options may instead attach images as CID parts (part 2).

`data:` URIs are excluded: classic Outlook is widely reported not to display them (expected, not verified; part 2 can confirm on a real render).

## Storing renders

Options: the repo (downscaled PNG, like the fidelity references), `.tmpscratch/` plus an external link, or an artifact store. Decided in part 2 against measured render sizes; no size figure exists yet.

## Input bundle

`scripts/export-outlook-cases.py` converts each case with the default render path and writes:

- `<out>/<case>/email.html`: converter HTML with every asset ref (`src="…"` and CSS `url('…')`) rewritten to `assets/<node>.png`, or to `<base>/<node>.png` with `--asset-base-url`. Nothing else in the markup changes (`app/design_sync/tests/test_outlook_export.py`, `test_markup_unchanged_except_asset_refs`).
- `<out>/<case>/assets/*.png`: the committed `data/debug/<case>/assets/` files the HTML references.
- `<out>/manifest.json`: one row per case with `commit`, `sha256`, `bytes`, `img_srcs`, `roundrect`, `mso_blocks`, `missing_assets`. Tie each render to a row so it names the HTML it shows.

```bash
uv run python scripts/export-outlook-cases.py                     # all gated cases, relative srcs
uv run python scripts/export-outlook-cases.py --cases 5 7
uv run python scripts/export-outlook-cases.py --cases 5 --asset-base-url https://<host>/ce4/5
```

`--out` defaults to `.tmpscratch/outlook-export`. The base URL is used as given for every case in the run, so when hosting per case, export one case per run.

Per-case figures, observed (`export-outlook-cases.py` at `45d71cea`, 2026-10-06). `bytes` is the exported file (shorter than converter output because the srcs are shorter). `img_srcs` counts every asset ref; case 5's 8 are 6 `src=` plus 2 CSS `url()` background images.

| case | bytes | img_srcs | `v:roundrect` | `<!--[if mso` | missing assets |
|---|---|---|---|---|---|
| 5 | 52567 | 8 | 16 | 58 | 0 |
| 6 | 30907 | 11 | 4 | 23 | 0 |
| 7 | 85251 | 23 | 18 | 57 | 0 |
| 8 | 40735 | 10 | 4 | 33 | 0 |
| 9 | 38228 | 11 | 4 | 28 | 0 |
| 10 | 54825 | 17 | 4 | 43 | 0 |
| reframe | 58803 | 13 | 6 | 47 | 0 |

`v:roundrect` counts occurrences of the string, so an opening and closing tag pair counts 2 (observed: case 5 has 8 `<v:roundrect` and 8 `</v:roundrect`, so 8 buttons).

## Part 2, once a source is picked

1. Build the client or rig script for the chosen source, in the shape that fits it (the `RenderingProvider` protocol in `app/rendering/protocol.py` models an async screenshot API and fits the vendors better than the rig).
2. Render each case once from the bundle, recording the manifest row it came from.
3. Write the button report: per case, what the render shows for radius, fill, stroke and size, and whether the stroke grows the VML box (CE-11 D8 / AC 9; the CE-10 baseline).
4. Close `ce-4-rendering-providers-placeholder` if the chosen provider replaces a placeholder.
