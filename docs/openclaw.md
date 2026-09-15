# OpenClaw connection and alerts

Use this optional connection only when OpenClaw is part of your private setup. It gives OpenClaw the ADHD Hub skills and lets the Hub send a short, gentle reminder when work has been left open.

For **OpenClaw → Hub MCP OAuth login**, including a browser on a different machine
from the gateway, use the [MCP OAuth callback guide](openclaw-mcp-oauth.md). The
reminder-hook pairing below is a separate connection in the opposite direction.

## 1. Add the ADHD Hub skills to OpenClaw

Run this where OpenClaw is installed:

```bash
npx skills add uniskela/adhd-hub -g -a openclaw
```

This installs the skills in OpenClaw's global skills directory. If you are developing an unreleased checkout instead, run the command from that checkout with `./skills` in place of `uniskela/adhd-hub`.

## 2. Connect the Hub to OpenClaw

### The simple mental model

This connection involves two separate services:

- **ADHD Hub** finds stale open work and sends a reminder.
- **OpenClaw Gateway** receives that reminder through its HTTP hook.

The **hook bearer token** is the shared password for that private connection. It is created/configured on the OpenClaw Gateway, then copied once into ADHD Hub's **Settings → OpenClaw** form. It is not the ADHD Hub auth token, not the Gateway login token, and not part of either URL.

An OpenClaw agent can help inspect configuration, explain errors, or submit the pairing request, but it must not print or reveal the hook token. A human operator or the deployment's secret-management mechanism must make the token available to both services.

Before configuring ADHD Hub, the Gateway must have HTTP hooks enabled:

```json5
{
  "hooks": {
    "enabled": true,
    "token": "<dedicated-long-random-hook-token>",
    "path": "/hooks",
    "allowedAgentIds": ["main"]
  }
}
```

Use a dedicated token that is different from the Gateway's normal authentication token. You can keep the value in an untracked OpenClaw `.env` file and reference it from `openclaw.json` with environment substitution:

```dotenv
# ~/.openclaw/.env or the Gateway process's working-directory .env
OPENCLAW_HOOK_TOKEN=<dedicated-long-random-hook-token>
```

```json5
{
  "hooks": {
    "enabled": true,
    "token": "${OPENCLAW_HOOK_TOKEN}",
    "path": "/hooks",
    "allowedAgentIds": ["main"]
  }
}
```

OpenClaw supports `${UPPERCASE_ENV_NAME}` substitution in config strings. Keep the `.env` file out of Git and restrict its file permissions. Do not use the normal `OPENCLAW_GATEWAY_TOKEN` for this value: the hook token must be separate. A generic SecretRef object cannot be pasted directly into `hooks.token` on current OpenClaw versions, so use environment substitution or another supported deployment secret mechanism instead.

After hooks are enabled, configure ADHD Hub with the matching URL and token, then use **Save & send test**. The token remains in the Gateway `.env` and is entered into the Hub UI only through the protected settings form; it should not be pasted into an agent prompt.

**Pairing (recommended):** In ADHD Hub, open **Settings → OpenClaw**, click **Start OpenClaw pairing**, copy the prompt into OpenClaw, then **Approve** what it submits. OpenClaw never needs `ADHD_HUB_AUTH_TOKEN` — only the short pairing code. This is device-code style pairing, not OAuth (OpenClaw hooks have no OAuth callback).

Secure pairing has one prerequisite on the OpenClaw side: `hooks.token` must be provisioned without exposing the raw bearer token to the pairing agent. Use a protected runtime SecretRef when the installed OpenClaw version supports it, or inject the hook token through the gateway service environment when that is the supported secure path. The pairing agent must never print, echo, reveal, or paste the hook token into chat, command arguments, config files, or tool output.

The Hub still needs the **actual** hook token eventually because it authenticates outbound stale-work nudges to `/hooks/wake` and `/hooks/agent`. A SecretRef itself is meaningful only inside the OpenClaw gateway, so the successful pairing request must inject the resolved token directly into the request body without surfacing it to the agent or operator transcript.

If OpenClaw cannot securely provision `hooks.token`, the generated pairing prompt reports the structured failure `hooks_token_secretref_unsupported` to the Hub and stops. The **Settings → OpenClaw** panel then explains the prerequisite instead of leaving the pairing attempt apparently stuck. Do not work around that status by asking an agent to expose the token.

**Manual path:** Enable hooks on the OpenClaw gateway and create a bearer token there. Configure `hooks.token` securely on the gateway first. Then, as the operator, use **Settings → OpenClaw** to:

1. Add the private webhook URL, or the optional agent URL for a richer message.
2. Enter the OpenClaw hook bearer token directly into the Hub UI.
3. Choose whether alerts are enabled.
4. Save, then choose **Save & send test**.

The token is encrypted using the Hub's server access token before it is stored in `openclaw.json`. The API returns only whether a token is configured, never the token or a fragment of it. If you rotate `ADHD_HUB_AUTH_TOKEN`, enter the OpenClaw token again.

### Use an HTTPS domain

The URL in this screen is an **outbound URL from ADHD Hub to the OpenClaw gateway**. It is not the Hub's URL and it does not create a reverse proxy route. If the Hub container cannot resolve or reach the hostname, the alert test will fail even when the URL works in your browser.

If your reverse proxy publishes the OpenClaw hook endpoints at the domain root, enter:

```text
Webhook URL: https://openclaw.example.com/hooks/wake
Agent URL:   https://openclaw.example.com/hooks/agent
```

Use the `Agent URL` only when you want the richer agent-run path; the required minimum is the `Webhook URL`. The proxy must:

1. terminate TLS and forward `POST` requests to the OpenClaw gateway;
2. preserve the `/hooks/wake` and `/hooks/agent` paths and JSON request bodies; and
3. allow the Hub server's network egress while keeping the gateway hook token enabled.

Do not put the bearer token in the URL, query string, repository, `.env` committed to Git, or an MCP/agent prompt. The Hub sends it as an authentication header. The public hostname is safe to use only if the reverse proxy and OpenClaw hook authentication are already configured; otherwise prefer a Docker-network, LAN, or Tailscale hostname.

If the proxy uses a subpath rather than the domain root, include that prefix in both URLs, for example `https://example.com/openclaw/hooks/wake`. The final path must still reach OpenClaw's `/hooks/wake` or `/hooks/agent` endpoint.

For initial provisioning, you can still use an untracked `.env` file on the **Hub server**:

```env
ADHD_HUB_OPENCLAW_WEBHOOK_URL=https://openclaw.example.com/hooks/wake
ADHD_HUB_OPENCLAW_TOKEN=<OpenClaw hook bearer token>
# Optional: lets OpenClaw turn the reminder into a friendly short message.
# ADHD_HUB_OPENCLAW_AGENT_URL=https://openclaw.example.com/hooks/agent
```

Restart the Hub after changing `.env`; changes saved in the web UI apply immediately. For a public HTTPS hostname, keep the gateway hook endpoints protected by their bearer token and restrict proxy access to the Hub or your private network where possible. The webhook token belongs only in the Hub server environment or encrypted Hub configuration — never in an MCP client, skill file, or committed configuration.

## 3. Choose the alert rhythm

The Hub checks for stale open threads every day at 09:00 by default. It sends nothing when there is no stale work, and it uses the Hub's reminder cooldown to avoid repeats.

Choose the schedule, stale age, repeat cooldown, and maximum items in **Settings → OpenClaw**. Changes take effect immediately. For an environment-provisioned schedule, set this on the Hub server and restart it:

```env
ADHD_HUB_STALE_NUDGE_CRON=0 18 * * 1-5
```

That example sends one weekday check-in at 18:00. Keep the message useful: one suggested next step is better than a long list of overdue work.

## 4. Test once

Use **Save & send test** for a harmless connection check. To exercise the complete stale-work path, create or keep one deliberately stale open thread, then trigger the check with the Hub access token from a trusted machine:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  http://adhd-hub:8787/api/admin/stale-nudge
```

If it succeeds, OpenClaw receives a short list of unfinished work. The optional agent endpoint can turn that into a non-nagging message and save a brief memory digest (summaries + next steps only — never raw chats). Agents can also call MCP `push_openclaw_memory` for an on-demand short round-trip. The Hub's wiki remains the source of truth for project progress.

## Optional: OpenClaw reads the Hub

An OpenClaw workflow or private cron can fetch stale work directly:

```bash
curl -sS \
  -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  "http://adhd-hub:8787/api/threads?stale=true"
```

Treat the token as a secret and limit network access to trusted devices.

## Why reminder hooks have no OAuth callback

The supported OpenClaw hook interface uses bearer authentication and does not provide an OAuth authorization contract for ADHD Hub to complete. **Settings → OpenClaw** therefore uses the same private, token-authenticated hook flow rather than presenting a callback that cannot be verified.
