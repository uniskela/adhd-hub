# OpenClaw MCP OAuth: local and remote gateways

MCP OAuth connects **OpenClaw → Hub** and issues an MCP-only token. This is separate
from **Hub → OpenClaw** reminder hooks and their pairing flow in the
[OpenClaw guide](openclaw.md).

Configure the Hub's HTTPS `ADHD_HUB_PUBLIC_URL` and leave OAuth enabled. On the
gateway, configure OpenClaw once (replace the example URL with your Hub URL):

```bash
openclaw mcp add adhd-hub \
  --url https://hub.example/mcp \
  --transport streamable-http \
  --auth oauth
```

Do not add a duplicate if this entry already exists.

## Local browser + local gateway

Run `openclaw mcp login adhd-hub`, open its printed authorization URL, sign into
the Hub and click **Allow**. When browser and login run on the same machine,
the normal loopback callback works unchanged. Keep login running until OpenClaw
confirms that credentials were saved.

## Remote browser + gateway

**Recommended: forward the loopback callback over SSH.** No authorization-code
copying, public callback listener or Hub relay is needed. A browser's `127.0.0.1`
always refers to the browser machine, not the Hub or gateway.

For the callback `http://127.0.0.1:8989/oauth/callback`:

1. On the **browser machine**, start a tunnel to the **machine running the
   OpenClaw login process**:

   ```bash
   ssh -N -T -o ExitOnForwardFailure=yes \
     -L 127.0.0.1:8989:127.0.0.1:8989 operator@gateway.example
   ```

   Replace the SSH destination with your gateway login. Verify its SSH host key.
   Keep this terminal open. Do not use `-g` or bind to `0.0.0.0`.

2. In a second terminal connected to the **gateway**, run:

   ```bash
   openclaw mcp login adhd-hub
   ```

3. Open the newly printed authorization URL in the **browser machine's** browser
   and click **Allow**. SSH forwards the callback to the original waiting login
   process, which exchanges the code and saves the credentials.
4. Once OpenClaw confirms success, close the callback tab and stop the tunnel
   with Ctrl-C.

Use the actual callback port from the authorization request on **both** sides of
`-L`; 8989 is the reproduced OpenClaw default, not a Hub requirement. Keep the
registered URI, path, host spelling and authorization URL unchanged. An IPv6
callback requires a matching IPv6 local bind/destination; `localhost` must resolve
to the address actually forwarded. Prefer an explicit IPv4 loopback callback
when supported by the installed client.

The SSH endpoint must share the login listener's network namespace. If OpenClaw
runs in a container, forwarding to the host's loopback does not automatically
reach the container's loopback. Provide a private route to that listener; do not
publish it globally. Only forward to a gateway you control and trust.

## Architecture and security

PR #106 fixed consent-page CSP and returned the validated callback as JSON for
browser navigation. It cannot make the browser's localhost point to another host.
Hub must return the exact registered callback; rewriting it after approval would
break the authorization code's redirect binding. The remote fix is client-side
routing, supported by Hub's pre-approval loopback guidance.

OpenClaw versions exposing `--oauth-redirect-url` can configure a different URI,
but that flag alone does **not** make an HTTPS gateway listener finish CLI login.
The inspected upstream CLI invokes a loopback callback server. Check the installed
version's `openclaw mcp add --help` and client documentation before relying on
other callback types. Do not point a redirect at the Hub or an arbitrary gateway
URL. A future device grant or Hub-hosted relay requires explicit client support;
Hub CLI pairing is not an OpenClaw MCP OAuth device grant.

- Both forwarding endpoints stay on loopback. SSH authenticates and encrypts
  the inter-machine hop; no callback query crosses an HTTP reverse proxy.
- OpenClaw retains its original PKCE verifier and checks callback state against
  its pending login. Hub echoes state verbatim; the client, not the Hub token
  endpoint, validates state.
- Hub codes remain single-use, expire after 10 minutes, are stored only as
  hashes, and are bound to client ID, exact redirect URI, MCP resource and S256
  PKCE challenge. Forwarding creates no second code or session.
- Consent and callback-result responses are non-cacheable. Hub does not log
  codes. Do not enable request/response body tracing, browser HAR capture or
  callback access logs that record queries. OpenClaw and operator-added proxies
  must also avoid logging codes. Never paste callback URLs into chat.

## Troubleshooting

- **Browser localhost connection refused / CLI still waiting:** establish the
  tunnel on the browser machine, confirm its destination and port, then restart
  login and use the new authorization URL. Do not copy the code.
- **SSH “address already in use”:** close the conflicting local process/tunnel.
  Do not silently choose another forwarding port: it must match the callback.
- **SSH “administratively prohibited” or remote connection refused:** ask the
  gateway administrator to permit this specific loopback forward. Confirm login
  is still listening in the SSH endpoint's network namespace.
- **State mismatch or expired/reused code:** cancel old login and start a new one.
  Avoid concurrent logins for the same entry and old approval tabs. Never disable
  state or PKCE checks.
- **Invalid redirect URI:** registration, authorization and token exchange must
  agree exactly. Do not edit the browser URL; use the client's supported
  re-registration/reset procedure if its callback configuration changed.
- **“Could not reach the Hub” before callback:** check connectivity and that the
  deployment includes PR #106. This is distinct from callback routing failure.
- **No SSH route:** automatic completion needs a private callback route or a
  client-supported remote authorization flow. Do not expose an unauthenticated
  listener or weaken Hub validation.

## Regression coverage

`tests/test_oauth_remote.py` exercises real Hub authorization/token endpoints and
the Hub CLI's state-checking callback receiver, directly and through a TCP
forwarder. The forwarder models the SSH data path without requiring SSH keys or
two hosts in CI. It is not an end-to-end test of the external OpenClaw binary or
SSH authentication. Verify the numbered setup once with your installed OpenClaw
version and actual gateway before deployment.
