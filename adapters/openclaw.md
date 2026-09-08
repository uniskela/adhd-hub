# OpenClaw + ADHD Hub

ADHD Hub can nudge OpenClaw when threads go stale.

## Hub → OpenClaw

In hub `.env`:

```env
ADHD_HUB_OPENCLAW_WEBHOOK_URL=http://<openclaw-host>:18789/hooks/wake
ADHD_HUB_OPENCLAW_TOKEN=<hooks-bearer-token>
# Optional richer agent turn:
ADHD_HUB_OPENCLAW_AGENT_URL=http://<openclaw-host>:18789/hooks/agent
```

Enable hooks on the OpenClaw gateway (`hooks.enabled`, shared bearer token). Keep the gateway on Tailscale/LAN only.

## OpenClaw → Hub

Ask OpenClaw (or a cron job) to fetch stale work:

```bash
curl -s -H "Authorization: Bearer $ADHD_HUB_TOKEN" \
  "http://adhd-hub:8787/api/threads?stale=true"
```

Or trigger an immediate nudge:

```bash
curl -s -X POST -H "Authorization: Bearer $ADHD_HUB_TOKEN" \
  "http://adhd-hub:8787/api/admin/stale-nudge"
```

Memory sync is best-effort: the hub asks OpenClaw (via agent hook) to retain a short “open work” note. Project truth remains in the hub wiki (`PROGRESS.md` + `INDEX.md`).
