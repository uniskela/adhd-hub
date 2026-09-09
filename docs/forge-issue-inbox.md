# Forge issue inbox (cloud-agent mailbox)

Cloud agents often cannot reach a private Tailscale Hub MCP. They *can* open GitHub/Gitea issues. ADHD Hub can poll those issues and turn them into threads.

## Enable

1. Settings → Connections → Forge: turn on **Board / issues** and **Import cloud-agent issues (inbox)**.
2. Save. Optionally click **Import issue inbox** once to test.
3. The Hub also polls on `ADHD_HUB_FORGE_INBOX_CRON` (default every 15 minutes).

## Cloud agent protocol

1. Create an issue titled `[ADHD] <short summary>`.
2. Labels: `adhd-hub` and optional `project:<slug>`.
3. Body: short Now / Done / Next / Return cue (no secrets).
4. After import, Hub **closes** the issue and adds `adhd-hub-synced` (never deletes).

## Operator API

```bash
curl -sS -X POST -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  http://127.0.0.1:8787/api/forge/inbox/import
```

## Skills on cloud agents

Install Hub skills in the cloud environment install step:

```bash
npx skills add uniskela/adhd-hub -g
```

The session skill falls back to the forge mailbox when MCP is unreachable.
