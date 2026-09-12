# Personal wire-up checklist

## Day in the life

1. **Hub running** — use the [installation guide](installation.md) for Docker Compose (recommended), `docker run`, or source/`uv` setup.
2. **Connect once** — prefer the [Connect one-liner](connect.md). Copy it from **Settings → Agents & install**; do not export the server token into your shell. For MCP clients with an **Auth** / **Authenticate** button, set Hub `ADHD_HUB_PUBLIC_URL` and leave Hub OAuth enabled (default); Approve = Hub UI sign-in + **Allow**. Static `ADHD_HUB_AUTH_TOKEN` Bearer and CLI connect still work; set Hub `ADHD_HUB_OAUTH_ENABLED=false` to disable discovery/OAuth routes. Details: [Connect — MCP Auth / Authenticate](connect.md#mcp-auth-authenticate-oauth).

```bash
# macOS / Linux / WSL
curl -fsSL http://127.0.0.1:8787/install.sh | sh -s -- /path/to/project
```

```powershell
# Windows PowerShell
irm http://127.0.0.1:8787/install.ps1 | iex
```

```bash
adhd-hub doctor --project /path/to/project
```

3. **Start** — the coding client calls Hub MCP `resolve_project` + `session_digest` and runs `check_overlap` before creating duplicate work. **Hub continuity is for meaningful multi-step work; trivial/read-only questions and tiny edits should skip Hub tools.**
4. **Work** — when the task reaches a real checkpoint, the assistant calls `upsert_progress` on the existing thread with short **Goal / Focus / Next / Blocked / Resume** fields. For interruption-prone or multi-session work, save earlier rather than waiting for the end. Set `open_thread=false` for durable notes that should not create an open task.
5. **Pause** — the assistant calls `pause_thread` or `upsert_progress` with a concrete resume cue before changing context.
6. **Resume** — the next coding session calls `session_digest`; recent progress and resume cues are returned together.
7. **Finish** — `mark_done` closes only the known finishable-outcome thread. The project remains available for the next outcome.

The browser dashboard is optional: **Now** keeps one selected task visible, **My work** is the denser work browser, **Progress** shows activity and optional milestones, and **Settings** contains preferences/connections/data. The Hub still works through MCP/REST without the dashboard.

## What belongs in a progress note

Keep it short enough to scan after several days away:

```text
Goal: Ship the source-aware work model without changing sync semantics.
Focus: Thread identity + authority fields and safe migration.
Next: Add migration tests for legacy forge mappings.
Blocked: None.
Resume: Open store.py and continue from migrate_external_identity().
```

Do not put secrets, auth tokens, passwords, private infrastructure details, or raw chat transcripts in progress notes.
