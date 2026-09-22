# Remote MCP access (tunnels for cloud agents)

Use this when a cloud agent (Cursor Cloud, Codex cloud, Claude remote, and similar) cannot reach your Hub over Tailscale or LAN, but you still want **live MCP** instead of the [forge issue mailbox](forge-issue-inbox.md).

Prefer a **private mesh** when the agent can join it. Use a **controlled HTTPS tunnel** when it cannot. Prefer the forge mailbox over any anonymous or unauthenticated public `/mcp`.

## Choose a path

| Preference | Path | When |
| --- | --- | --- |
| **1 — Primary** | [Cloudflare Tunnel](#cloudflare-tunnel-primary) (or another operator-controlled HTTPS tunnel) | Cloud agent cannot join your tailnet; you need a public HTTPS hostname you control |
| **2 — Secondary** | [Tailscale mesh](#tailscale-mesh-secondary) | Windows / Dev LXC / cloud agent can reach the Hub on the private tailnet |
| **3 — Caution** | [ngrok / ephemeral tunnels](#ngrok-and-similar-cautionary) | Short-lived demos only; rotate token and expect hostname churn |

Always-on reverse proxies (Caddy, nginx, Tailscale Serve) are covered in [Installation](installation.md#reverse-proxy-https-and-tailscale) and [Homelab deploy](deploy-homelab.md). This page is specifically about **exposing Hub MCP to remote/cloud agents**.

## Security checklist (required)

- **Strong `ADHD_HUB_AUTH_TOKEN`** — long random secret; never leave `change-me` (or empty) when the Hub is reachable beyond loopback.
- **No anonymous `/mcp`** — clients must send `Authorization: Bearer <token>` (or complete Hub OAuth). Dashboard cookies do **not** authorize MCP.
- **HTTPS + `ADHD_HUB_PUBLIC_URL`** — set the public base to the tunnel hostname (`https://…`, no trailing slash). OAuth discovery and install links must match that hostname.
- **TLS at the tunnel terminator** — do not publish Hub’s plain HTTP port on the open internet. Terminate TLS at Cloudflare Tunnel / Serve / your proxy; Hub may stay on loopback or a private interface behind it.
- **`ADHD_HUB_TRUST_PROXY_HEADERS=true` only behind a trusted terminator** — never enable proxy trust on a Hub that faces the internet directly.
- **Forge mailbox fallback** — if you cannot keep a durable private or tunnel path, use [forge issue inbox](forge-issue-inbox.md) rather than opening an unauthenticated endpoint.
- **Rotate after ephemeral URLs** — if the public hostname changes (ngrok free tier, Funnel demos), update client MCP config and consider rotating the bearer token.

Out of scope here: OpenClaw SSH tunnels used only for OAuth *callbacks* (see [OpenClaw MCP OAuth](openclaw-mcp-oauth.md)).

## Cloudflare Tunnel (primary)

Pattern: Hub listens on loopback (or a private Docker network). `cloudflared` terminates HTTPS and forwards to `http://127.0.0.1:8787`.

1. Run Hub locally or in the lab (`adhd-hub serve` / Compose) bound so only the tunnel (or localhost) can reach it.
2. Create a Cloudflare Tunnel that routes `https://hub.example.com` → `http://127.0.0.1:8787` (exact `cloudflared` steps follow Cloudflare’s current docs).
3. On the Hub host:

```env
ADHD_HUB_AUTH_TOKEN=<long-random-secret>
ADHD_HUB_PUBLIC_URL=https://hub.example.com
ADHD_HUB_TRUST_PROXY_HEADERS=true
```

4. Confirm health and MCP over HTTPS:

```bash
curl -fsS "$ADHD_HUB_PUBLIC_URL/api/health"
curl -fsS -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  -H "Accept: application/json, text/event-stream" \
  "$ADHD_HUB_PUBLIC_URL/mcp"
```

5. Point cloud MCP clients at `https://hub.example.com/mcp` with the same bearer token (see [Cursor Cloud wiring](#cursor-cloud--cloud-agent-wiring)).

Tailscale **Funnel** can play a similar role (HTTPS hostname → local Hub). Treat Funnel like any other public terminator: strong token, `ADHD_HUB_PUBLIC_URL`, TLS at the edge, proxy trust only when Funnel/Serve is the trusted front.

## Tailscale mesh (secondary)

When Cursor on a PC, a Dev LXC, or a cloud agent **can join the same tailnet**, keep Hub private:

- Publish `:8787` on the Tailscale interface only (homelab Compose pattern).
- MCP URL: `http://<tailscale-host-or-magicdns>:8787/mcp` (plain HTTP on Tailscale is acceptable; HTTPS still preferred if you terminate with Serve).
- Still require Bearer (or OAuth). Do not disable auth because the path is “private.”

Canonical layout: [Homelab deployment](deploy-homelab.md). If the cloud runner **cannot** install Tailscale or reach the tailnet, use Cloudflare Tunnel or the forge mailbox — do not assume mesh reachability from Cursor Cloud.

## ngrok and similar (cautionary)

Ephemeral public URLs are easy to misconfigure:

- Hostname changes break `ADHD_HUB_PUBLIC_URL`, OAuth discovery, and saved MCP configs.
- Free/shared tunnels are easier to guess or leave running after a demo.
- Logging side channels (request logs, shared dashboards) may capture `Authorization` headers if you are careless.

If you must use ngrok (or similar) briefly:

1. Put a strong bearer token in place **before** the tunnel is up.
2. Set `ADHD_HUB_PUBLIC_URL` to the current `https://…` hostname every time it changes.
3. Enable `ADHD_HUB_TRUST_PROXY_HEADERS` only if that tool is your trusted TLS terminator.
4. Tear the tunnel down when finished; rotate `ADHD_HUB_AUTH_TOKEN` afterward.
5. Prefer forge mailbox for ongoing cloud work if you cannot maintain a stable tunnel.

## Cursor Cloud / cloud-agent wiring

Cloud agents need the **Streamable HTTP** MCP URL and a secret they can read from env or the product’s MCP secret store — not a pasted token in a chat transcript.

Typical values:

| Setting | Value |
| --- | --- |
| MCP URL | `https://<your-tunnel-host>/mcp` (or Tailscale URL if reachable) |
| Auth | `Authorization: Bearer <ADHD_HUB_AUTH_TOKEN>` |
| Env helpers | `ADHD_HUB_MCP_URL` / `ADHD_HUB_AUTH_TOKEN` (Marketplace plugin and adapters) |

Practical notes:

- In Cursor, configure the cloud/environment MCP server to the tunnel HTTPS URL and inject the token from secrets / environment — same shape as [adapters/cursor-mcp.json](https://github.com/uniskela/adhd-hub/blob/main/adapters/cursor-mcp.json) (`url` + `${env:ADHD_HUB_AUTH_TOKEN}`).
- Marketplace plugin installs often expect `ADHD_HUB_MCP_URL` (`{base}/mcp`) and `ADHD_HUB_AUTH_TOKEN`; keep those aligned with `ADHD_HUB_PUBLIC_URL`.
- If MCP tools are missing, errored, or unauthorized after tunnel changes, fix URL/token/HTTPS first. Until MCP works, agents should use the [forge issue inbox](forge-issue-inbox.md) and must not invent Hub continuity.
- Skip or cancel hanging **Auth / Authenticate** prompts until Hub OAuth is intentionally enabled for that public URL; static Bearer remains supported.

See also [Connect](connect.md) for local/CLI connect and [Authentication](authentication.md) for dashboard vs MCP auth.

## Related

- [Forge issue inbox](forge-issue-inbox.md) — fallback when live MCP is unreachable
- [Homelab deployment](deploy-homelab.md) — Proxmox + Tailscale
- [Installation — reverse proxy / HTTPS](installation.md#reverse-proxy-https-and-tailscale)
- [Environment variables](environment-variables.md)
- [SECURITY.md](../SECURITY.md)
