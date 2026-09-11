# MCP OAuth (coding-agent Auth) + loud MCP-down visibility

**Date:** 2026-09-11  
**Status:** approved — ready for implementation plan  
**Thread:** `2fc15e481d87bd69` (project `adhd-hub`)  
**Related:** CLI connect already implements device-style user codes (`/api/connect/*`). Coding agents that show an MCP **Auth / Authenticate** button typically speak **MCP OAuth 2.1** (authorization code + PKCE), not the CLI poll loop.

---

## Goals

1. Make the MCP **Auth / Authenticate** button work against a remote Hub (`https://…/mcp`) for **any coding agent / MCP client that offers that button**, by implementing MCP-compatible OAuth 2.1 (authorization code + PKCE, discovery, and token issuance). Cursor is the first verification target; the same Hub endpoints must not be Cursor-only.
2. Keep **static Bearer** (`ADHD_HUB_AUTH_TOKEN` and existing CLI connect session tokens) working without forcing OAuth when a valid `Authorization` header is present.
3. Keep the existing **CLI user-code** flow (`ABCD-WXYZ` → Hub UI Allow) unchanged in behavior for `adhd-hub connect` / install scripts.
4. Stop agents from silently continuing when Hub MCP is down: **lead with a visible MCP-down line** in AGENTS guidance, agent rules, and session skill.

## Non-goals (this change)

- Replacing static Bearer as the default for operators who already set `ADHD_HUB_AUTH_TOKEN`.
- Implementing OAuth device-authorization grant as the driver for IDE **Auth** buttons (those clients use authorization code + PKCE; device grant remains CLI-oriented).
- Full IdP federation (Google/GitHub login as the Hub’s only identity) — Hub browser login remains the operator identity for Approve.
- Changing companion install behavior or PR #45 scope except where AGENTS/skill text is shared.
- Guaranteeing every third-party agent’s Auth UI works if that client violates MCP OAuth (we target the MCP authorization spec; client bugs may still need workarounds).

---

## Decisions (approved in brainstorm)

| Topic | Choice |
|-------|--------|
| Overall path | **C** — OAuth for IDE Auth buttons + keep CLI user-code |
| Who can Approve OAuth | **A** — anyone with a valid Hub UI browser session (same bar as CLI Allow) |
| MCP-down visibility | **Loud first-line rule** in AGENTS + agent rules + session skill (not “every N chats”) |
| Auth-button scope | **All** MCP clients that offer Auth/Authenticate (spec-compliant OAuth); verify Cursor first |

---

## Part 1 — MCP OAuth architecture

### 1.1 Roles

- **Resource server:** Hub `/mcp` (existing MCP Streamable HTTP).
- **Authorization server:** Hub itself (same origin as `ADHD_HUB_PUBLIC_URL` / request host), exposing discovery + authorize + token + (optional) dynamic client registration.
- **Client:** Any MCP client that supports OAuth for remote HTTP MCP (Cursor, and others with an Auth/Authenticate control). Redirect URIs vary by client; Hub maintains a **configurable allowlist** seeded with known Cursor desktop/web callbacks plus loopback for tests, and accepts additional URIs registered via DCR when they match policy (https or loopback).

### 1.2 Discovery

Serve (at least):

1. **Protected Resource Metadata (RFC 9728)**  
   - `GET /.well-known/oauth-protected-resource`  
   - Optionally path-aware: `/.well-known/oauth-protected-resource/mcp`  
   - Document must include `resource` (canonical MCP URL) and `authorization_servers` (Hub issuer URL).

2. **Authorization Server Metadata (RFC 8414)**  
   - `GET /.well-known/oauth-authorization-server`  
   - Advertise: `authorization_endpoint`, `token_endpoint`, `code_challenge_methods_supported: ["S256"]`, `response_types_supported: ["code"]`, `grant_types_supported: ["authorization_code", "refresh_token"]` (refresh optional v1), and `registration_endpoint` if DCR is enabled.

### 1.3 Unauthorized challenge

When `/mcp` rejects a request (no/invalid Bearer), return **401** with:

```http
WWW-Authenticate: Bearer realm="adhd-hub", resource_metadata="<absolute URL to PRM>"
```

Do **not** force OAuth when Bearer is valid (server token or connect-session token). Valid static Bearer remains the fast path.

### 1.4 Authorization code + PKCE flow (Auth / Authenticate button)

1. Client discovers metadata → opens `authorization_endpoint` with `client_id`, `redirect_uri`, `code_challenge` (S256), `state`, `resource` (MCP URL).
2. Hub authorize page:
   - If no Hub UI session → redirect to existing Hub login, then return to authorize.
   - If session valid → show **Allow / Deny** for “\<client name\> wants MCP access to this Hub.”
   - On Allow → issue one-time `code`, redirect to `redirect_uri?code=…&state=…`.
3. Client hits `token_endpoint` with `code` + `code_verifier` (+ client auth as required).
4. Hub returns `access_token` (opaque) + `token_type: Bearer` + `expires_in`.
5. Client calls `/mcp` with `Authorization: Bearer <access_token>`.
6. `bearer_authorized` accepts the new OAuth access tokens the same way it accepts CLI connect session tokens (hash lookup / expiry).

### 1.5 Client registration

**v1 recommendation:** Support **Dynamic Client Registration (RFC 7591)** at `registration_endpoint` so agents can register without a pre-shared `CLIENT_ID`, **and** keep a small allowlist of well-known static public client ids (e.g. Cursor) if DCR is flaky for a given client.

- Public clients (PKCE): no client secret required.
- Persist registered clients in SQLite next to connect auth (new tables or extended store).
- Rate-limit registration.

### 1.6 Relationship to existing CLI connect

| Concern | CLI connect (keep) | MCP OAuth (new) |
|---------|--------------------|-----------------|
| User proof | Short `user_code` typed in UI | Logged-in Hub session + Allow on authorize page |
| Client proof | PKCE + device/exchange codes | PKCE + auth code |
| Token use | Bearer on MCP / API as today | Bearer on MCP |
| Storage | `ConnectStore` grants/sessions | Prefer **extend** `ConnectStore` (or sibling `OAuthStore`) with oauth_clients / oauth_codes / oauth_tokens — avoid a third auth paradigm |

CLI endpoints (`/api/connect/start|approve|token|…`) stay. OAuth endpoints are separate (`/oauth/authorize`, `/oauth/token`, `/.well-known/…`) but may share hashing, expiry, and “session token accepted by `bearer_authorized`” logic.

### 1.7 Security requirements

- PKCE S256 required; reject plain.
- One-time auth codes; short TTL (minutes).
- Access tokens hashed at rest; configurable TTL (hours–days); revoke on logout optional later.
- Redirect URI allowlist: known IDE callbacks (seed Cursor desktop/web) + https/loopback policy for DCR + loopback for tests; reject open redirects.
- CSRF: `state` required and bound.
- Throttle authorize/token/register like connect login.
- Never log tokens or verifiers.
- Public URL must be correct (`ADHD_HUB_PUBLIC_URL`) so metadata and redirects use `https://adhd.pike.homes` (not internal Docker hostnames).

### 1.8 UX copy (Authorize page)

- One screen: Hub name, requesting client, scope summary (“MCP tools on this Hub”), **Allow** / **Deny**.
- If not signed in: “Sign in to allow MCP access” → existing UI login.
- After Allow: “You can close this tab and return to your coding agent.”

### 1.9 Failure modes

| Symptom | Likely cause | Mitigation |
|---------|--------------|------------|
| Auth / Authenticate hangs | Missing metadata / no authorize redirect | Ship discovery + authorize; doctor probes well-known |
| Auth then 401 | Token not wired into `bearer_authorized` | Shared accept path + tests |
| Valid env Bearer ignored | Client prefers OAuth when discovery exists | Spec/MCP clients often prefer OAuth; **acceptable** if Auth works; document that static Bearer still works for clients that send headers first. If a specific client ignores headers whenever discovery exists (known Cursor bug), document: use Auth **or** a headers-only path that 404s discovery (out of scope unless needed). |
| Wrong host in metadata | `PUBLIC_URL` unset | Doctor warn; refuse insecure issuer in production |

### 1.10 Tests (OAuth)

- Metadata JSON shape and absolute URLs.
- 401 includes `resource_metadata`.
- Authorize requires browser session; Deny returns error redirect; Allow + token exchange succeeds.
- PKCE mismatch fails; replayed code fails; expired code fails.
- Issued access token authorizes `/mcp` initialize.
- Static server token still authorizes `/mcp` without OAuth.
- CLI connect flow regression tests still pass.

### 1.11 Docs / doctor

- Document Auth vs env Bearer in `docs/connect.md` / setup (agent-agnostic).
- `adhd-hub doctor`: check well-known 200 when public URL set; warn if Auth would hang (no metadata).

---

## Part 2 — Loud MCP-down visibility

### 2.1 Problem

When MCP discovery fails or tools are missing, agents followed soft wording (“continue… leave a local handoff”) and operators never noticed Hub continuity was off.

### 2.2 Required behavior

Whenever Hub MCP tools are **unavailable, errored, unauthorized, or empty of expected tools** (`resolve_project` / `session_digest` / etc.):

1. The agent’s **first line** (or first bullet) of that turn must state Hub MCP is down, in plain language.
2. Include a **short fix hint**: check MCP URL (e.g. public Hub `/mcp`), `ADHD_HUB_AUTH_TOKEN`, and that IDE **Auth** needs Hub OAuth (once shipped); until then use env Bearer and skip/cancel Auth if it hangs.
3. Continue the user’s authorized work after that line.
4. On later **substantial** turns in the same session, if still down, **repeat the lead line** (not every trivial reply — but any turn that would have called Hub tools).
5. Never invent Hub state or claim writes succeeded.

“Every couple of chats” is approximated by **session-start + every substantial Hub-worthy turn**, which is more reliable than counting chats.

### 2.3 Surfaces to update

| Surface | Change |
|---------|--------|
| Managed AGENTS block (`project_setup.agent_block` / install guidance) | Replace soft “continue quietly” with loud first-line rule |
| Repo `AGENTS.md` managed section | Regenerated / patched via same block |
| `.cursor/rules/adhd-hub.mdc` (shipped + install) | Same rule |
| `skills/adhd-hub-session` (and global install source) | Same rule; keep forge-mailbox fallback for remote agents |
| Optional: `doctor` / connect report | Warn if MCP probe fails |

### 2.4 Example lead line (non-normative)

> **ADHD Hub MCP is not available in this session** (tools missing/error). Fix: MCP URL → your Hub `/mcp`, set `ADHD_HUB_AUTH_TOKEN`, restart the agent; don’t rely on Auth until Hub OAuth ships. Continuing without Hub writes…

### 2.5 Tests (visibility)

- Snapshot/string tests that `agent_block()` / rule / skill contain the mandatory first-line / unavailable wording (not the old soft-only sentence alone).

---

## Implementation phasing

| Phase | Deliverable |
|-------|-------------|
| **P0** | Loud MCP-down text in AGENTS block, agent rules, session skill (+ tests). Ship quickly even before OAuth. |
| **P1** | OAuth discovery metadata + 401 `resource_metadata` + authorize UI + token + `bearer_authorized` wiring + tests. |
| **P2** | DCR polish, refresh tokens, doctor probes, docs for Auth across agents. |
| **P3** | Optional: richer redirect allowlist UX; revoke tokens from Settings. |

P0 can merge independently of P1.

---

## Risks

- Individual agent Auth UIs may still misbehave (redirect bugs, discovery vs headers); Hub still ships spec-compliant OAuth so any compliant client can connect.
- Extending auth surface increases attack surface — throttle, PKCE, hashed tokens, redirect allowlist are mandatory.
- Loud MCP-down may feel noisy; limit to Hub-worthy turns to reduce fatigue.

## Rollback

- Feature-flag OAuth routes off → Hub returns to Bearer-only; Auth buttons may hang again but env Bearer works.
- Revert AGENTS/skill wording if too noisy.

---

## Open points (non-blocking; defaults below)

1. **Access token TTL default:** 7 days (refresh in P2) — confirm or choose shorter.  
2. **DCR in P1 vs static well-known client ids only:** default **DCR in P1** with static fallback for known agents (e.g. Cursor).  
3. **Whether Settings shows “MCP OAuth sessions” list in P1:** default **no** (P3).

---

## Success criteria

- An MCP client with an Auth/Authenticate control can complete OAuth against `https://<hub>/mcp` and use Hub tools without a pre-set env token (after UI Allow). Verified at least on Cursor; other agents follow the same Hub endpoints.
- Env Bearer still works for operators who prefer it.
- CLI connect user-code flow still works.
- With MCP broken in the agent, replies lead with an unmistakable Hub-down line on Hub-worthy turns instead of failing silently.
