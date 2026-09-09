# OpenClaw connection and alerts

Use this optional connection only when OpenClaw is part of your private setup. It gives OpenClaw the ADHD Hub skills and lets the Hub send a short, gentle reminder when work has been left open.

## 1. Add the ADHD Hub skills to OpenClaw

Run this where OpenClaw is installed:

```bash
npx skills add uniskela/adhd-hub -g -a openclaw
```

This installs the skills in OpenClaw's global skills directory. If you are developing an unreleased checkout instead, run the command from that checkout with `./skills` in place of `uniskela/adhd-hub`.

## 2. Connect the Hub to OpenClaw

Enable hooks on the OpenClaw gateway and create a bearer token there. On the **Hub server**, save the hook details in its untracked `.env` file:

```env
ADHD_HUB_OPENCLAW_WEBHOOK_URL=http://openclaw:18789/hooks/wake
ADHD_HUB_OPENCLAW_TOKEN=<OpenClaw hook bearer token>
# Optional: lets OpenClaw turn the reminder into a friendly short message.
# ADHD_HUB_OPENCLAW_AGENT_URL=http://openclaw:18789/hooks/agent
```

Restart the Hub after changing `.env`. Keep the gateway on your LAN or Tailscale. The webhook token belongs only in the Hub server environment — never in an MCP client, skill file, or committed configuration.

## 3. Choose the alert rhythm

The Hub checks for stale open threads every day at 09:00 by default. It sends nothing when there is no stale work, and it uses the Hub's reminder cooldown to avoid repeats.

To choose a different five-field cron schedule, set this on the Hub server and restart it:

```env
ADHD_HUB_STALE_NUDGE_CRON=0 18 * * 1-5
```

That example sends one weekday check-in at 18:00. Keep the message useful: one suggested next step is better than a long list of overdue work.

## 4. Test once

Create or keep one deliberately stale open thread, then trigger the check with the Hub access token from a trusted machine:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  http://adhd-hub:8787/api/admin/stale-nudge
```

If it succeeds, OpenClaw receives a short list of unfinished work. The optional agent endpoint can turn that into a non-nagging message and save a brief memory note. The Hub's wiki remains the source of truth for project progress.

## Optional: OpenClaw reads the Hub

An OpenClaw workflow or private cron can fetch stale work directly:

```bash
curl -sS \
  -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  "http://adhd-hub:8787/api/threads?stale=true"
```

Treat the token as a secret and limit network access to trusted devices.
