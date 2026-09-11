# MCP OAuth + loud MCP-down visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship loud MCP-unavailable guidance for agents (P0), then MCP OAuth 2.1 so any coding agent’s Auth/Authenticate button can obtain a Hub Bearer token via Hub UI Allow (P1+), without breaking static Bearer or CLI user-code connect.

**Architecture:** P0 is copy-only across managed AGENTS block, Cursor rule template, and `adhd-hub-session` skill. P1 adds Hub-as-authorization-server: protected-resource + AS metadata, 401 `resource_metadata`, `/oauth/authorize` (browser session gate), `/oauth/token` (PKCE), optional DCR, and opaque access tokens accepted by `bearer_authorized` alongside server token and CLI sessions. Prefer extending `ConnectStore` / a sibling OAuth module over a third auth paradigm.

**Tech Stack:** FastAPI, existing `BrowserSessions` + `ConnectStore` patterns, SQLite, Jinja or minimal HTML for authorize page, pytest + httpx/TestClient, no new OAuth IdP dependencies in v1.

**Spec:** `docs/superpowers/specs/2026-09-11-mcp-oauth-and-mcp-down-visibility-design.md`

**Codex analysis (2026-09-11):** Prefer sibling `oauth.py` + `OAuthStore` (same `connect.sqlite3`, separate tables). Browser cookie `path=/api` → put authorize/token/register under **`/api/oauth/*`** (not bare `/oauth/*`). Bind auth codes to client_id, redirect_uri, resource, PKCE. Exact redirect matching. Token endpoint `application/x-www-form-urlencoded`. Advertise only `authorization_code` in P1 (no refresh). OAuth access tokens authorize **`/mcp` only** (do not wire into REST `auth_dependency`). Consent form needs CSRF (`X-Hub-Request` or synchronizer token). Issuer must prefer configured public HTTPS URL; request Host fallback only for loopback. Feature-flag OAuth routes for rollback.

## Global Constraints

- Auth-button scope: **all** MCP clients that offer Auth/Authenticate (MCP OAuth 2.1); verify Cursor first; endpoints must not be Cursor-only.
- Approve = Hub UI browser session (same bar as CLI Allow).
- Keep static Bearer (`ADHD_HUB_AUTH_TOKEN`) and CLI connect session tokens working when `Authorization` is valid.
- Keep CLI `/api/connect/*` user-code flow unchanged in behavior.
- PKCE S256 required; tokens hashed at rest; redirect URIs allowlisted (seed Cursor callbacks + https/loopback DCR policy).
- Access token TTL default **7 days** (refresh in P2).
- DCR in P1 with static well-known client-id fallback.
- No Settings MCP-session list in P1 (P3).
- Loud MCP-down: **first line** on Hub-worthy turns when tools unavailable; not soft “continue quietly.”
- Do not put commercial / hosted-product / subscription language in public repo docs, README, AGENTS, skills, or commit messages.
- Do not commit unless the operator explicitly asks (repository user rule).
- After meaningful code edits: `graphify update .` (use `%USERPROFILE%\.local\bin\graphify.exe` if PATH missing).

## File map

| File | Responsibility |
|------|----------------|
| `src/adhd_hub/project_setup.py` | Managed AGENTS continuity block (`agent_block`) |
| `AGENTS.md` | Regenerated managed section after block change |
| `.cursor/rules/adhd-hub.mdc` | Always-on Cursor rule (loud MCP-down) |
| `skills/adhd-hub-session/SKILL.md` | Session skill loud MCP-down |
| `tests/test_project_setup.py` | Assert block wording |
| `src/adhd_hub/oauth.py` (new) | OAuth store + metadata helpers + routers |
| `src/adhd_hub/app.py` | Mount OAuth routes; 401 challenge header; wire bearer |
| `src/adhd_hub/connect_auth.py` | `bearer_authorized` accepts OAuth access tokens |
| `src/adhd_hub/ui/` or templates | Authorize Allow/Deny page |
| `tests/test_oauth.py` (new) | OAuth discovery, PKCE, token, MCP auth |
| `docs/connect.md` / `docs/setup.md` | Auth vs Bearer (agent-agnostic; no commercial notes) |

**Phasing note:** Tasks 1–2 (P0) are independently shippable. Tasks 3+ are P1 OAuth. Do not block P0 on OAuth.

---

### Task 1: Loud MCP-down in `agent_block` + tests (P0)

**Files:**
- Modify: `src/adhd_hub/project_setup.py` (`agent_block`)
- Modify: `tests/test_project_setup.py`
- Modify: `AGENTS.md` (managed block via install helper or direct sync of managed section)

**Interfaces:**
- Produces: updated `agent_block()` string containing mandatory first-line unavailable rule

- [ ] **Step 1: Write failing tests**

In `tests/test_project_setup.py`, assert `agent_block()` contains phrases like:

```python
def test_agent_block_requires_loud_mcp_down() -> None:
    from adhd_hub.project_setup import agent_block

    text = agent_block()
    assert "first line" in text.lower() or "first line" in text
    assert "not available" in text.lower() or "unavailable" in text.lower()
    assert "ADHD Hub MCP" in text or "Hub MCP" in text
    # Old soft-only wording must not be the sole guidance:
    assert "leave a concise local handoff instead of claiming" not in text or "first line" in text.lower()
```

Refine assertions to match the exact final copy once written (prefer exact substring match on the lead-line instruction).

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_project_setup.py -k agent_block -v`

- [ ] **Step 3: Update `agent_block()` copy**

Replace the soft unavailable bullet with wording equivalent to:

```text
- If ADHD Hub MCP tools are missing, errored, unauthorized, or otherwise
  unavailable: the **first line** of your reply on that turn (and on later
  substantial Hub-worthy turns while still down) MUST state that Hub MCP is
  not available, plus a short fix hint (MCP URL → this Hub’s `/mcp`,
  `ADHD_HUB_AUTH_TOKEN`, restart the agent; skip/cancel Auth if it hangs
  until Hub OAuth is enabled). Then continue the authorized work. Never
  invent Hub state or claim a Hub write succeeded.
```

Keep existing rules about secrets, summaries, `resolve_project` / progress / `mark_done`.

- [ ] **Step 4: Refresh this repo’s managed AGENTS section**

Run the project’s install/update path for AGENTS (e.g. `uv run adhd-hub …` guidance helper, or manually replace between `<!-- adhd-hub:project-agent:start -->` and `end` markers with `agent_block()` output) so `AGENTS.md` matches.

- [ ] **Step 5: Re-run tests — expect PASS**

Run: `uv run pytest tests/test_project_setup.py -v`

- [ ] **Step 6: Commit only if operator asked**

---

### Task 2: Loud MCP-down in Cursor rule + session skill (P0)

**Files:**
- Modify: `.cursor/rules/adhd-hub.mdc`
- Modify: `skills/adhd-hub-session/SKILL.md`
- Optional: `tests/` string check or docs note that install copies skills from `skills/`

- [ ] **Step 1: Update `.cursor/rules/adhd-hub.mdc`**

Add an always-visible bullet matching Task 1 (first-line Hub MCP down + fix hint + continue work). Keep resolve/digest/overlap/progress/mark_done.

- [ ] **Step 2: Update `skills/adhd-hub-session/SKILL.md`**

Replace line ~16 soft “say so briefly” with the loud first-line rule. Keep forge-mailbox section for remote agents without MCP.

- [ ] **Step 3: Optional assert in tests**

```python
def test_session_skill_requires_loud_mcp_down() -> None:
    text = Path("skills/adhd-hub-session/SKILL.md").read_text(encoding="utf-8")
    assert "first line" in text.lower()
    assert "not available" in text.lower() or "unavailable" in text.lower()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_project_setup.py -v`

- [ ] **Step 5: Commit only if operator asked**

P0 is now complete and can be a standalone PR.

---

### Task 3: OAuth metadata + 401 `resource_metadata` (P1 start)

**Files:**
- Create: `src/adhd_hub/oauth.py` (metadata builders + router stubs)
- Modify: `src/adhd_hub/app.py` (`BearerGateMiddleware` WWW-Authenticate; include router)
- Create: `tests/test_oauth.py`

**Interfaces:**
- Produces:
  - `def issuer_base(settings, request) -> str`  # public URL preferred
  - `def protected_resource_metadata(settings, request) -> dict`
  - `def authorization_server_metadata(settings, request) -> dict`
  - Routes: `GET /.well-known/oauth-protected-resource`, `GET /.well-known/oauth-authorization-server`

- [ ] **Step 1: Failing tests**

```python
def test_oauth_protected_resource_metadata(client):
    r = client.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200
    body = r.json()
    assert "authorization_servers" in body
    assert "resource" in body

def test_mcp_401_includes_resource_metadata(client):
    r = client.post("/mcp", headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    www = r.headers.get("www-authenticate", "")
    assert "resource_metadata=" in www.lower() or "resource_metadata" in www
```

Use existing app TestClient fixtures from `tests/test_connect.py` / auth tests (follow repo patterns for settings + auth_token).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement metadata endpoints + middleware header**

- Absolute URLs using `settings.resolve_public_url()` or request base.
- AS metadata advertises authorize/token/(register) paths and S256 PKCE.

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit only if operator asked**

---

### Task 4: OAuth store — clients, codes, access tokens

**Files:**
- Modify/create: `src/adhd_hub/oauth.py` (SQLite schema + methods)
- Modify: `src/adhd_hub/connect_auth.py` — `bearer_authorized` also checks OAuth access tokens

**Interfaces:**
- Produces store methods roughly:
  - `register_client(...)`, `get_client(client_id)`
  - `create_auth_code(...)`, `consume_auth_code(...)`
  - `issue_access_token(...)`, `valid_access_token(token) -> bool`
- TTL: access token **7 days**

- [ ] **Step 1: Unit tests for PKCE verify, code one-time use, token accept**

- [ ] **Step 2: Implement schema + methods (hashed secrets/tokens)**

- [ ] **Step 3: Wire `bearer_authorized`:**

```python
def bearer_authorized(settings, store, value: str, oauth_store=None) -> bool:
    from adhd_hub.auth import token_matches
    if token_matches(settings, value) or store.valid_session(value):
        return True
    if oauth_store is not None and oauth_store.valid_access_token(value):
        return True
    return False
```

Update `BearerGateMiddleware` / `create_app` to pass oauth store.

- [ ] **Step 4: Tests PASS**

---

### Task 5: Authorize page + token endpoint + DCR

**Files:**
- `src/adhd_hub/oauth.py` — `/oauth/authorize` GET/POST, `/oauth/token`, `/oauth/register`
- UI: minimal HTML page (Hub chrome if easy) Allow/Deny
- Redirect allowlist helper (Cursor seed URIs + https/loopback policy)

**Flow:**
1. Authorize requires valid Hub UI cookie (`COOKIE_NAME` / `BrowserSessions`).
2. Else redirect to Hub login with return URL.
3. Allow → auth code redirect; Deny → error redirect.
4. Token endpoint: `grant_type=authorization_code` + PKCE; return Bearer access token.
5. DCR: public client registration with redirect_uris validation.

- [ ] **Step 1: Integration tests** (session cookie → allow → exchange → POST `/mcp` with token succeeds)

- [ ] **Step 2: Implement endpoints + page**

- [ ] **Step 3: Regression — CLI connect tests still pass; static token still authorizes `/mcp`**

Run: `uv run pytest tests/test_oauth.py tests/test_connect_auth.py tests/test_connect.py -q`

- [ ] **Step 4: Commit only if operator asked**

---

### Task 6: Docs + doctor probes (P1 wrap / P2 lite)

**Files:**
- `docs/connect.md`, `docs/setup.md` — Auth button vs env Bearer (agent-agnostic)
- `src/adhd_hub/connect.py` doctor — warn if well-known missing when public URL set

- [ ] **Step 1: Docs paragraphs** (no commercial/hosted-product language)

- [ ] **Step 2: Doctor check optional**

- [ ] **Step 3: `graphify update .`**

- [ ] **Step 4: Full verification**

```powershell
uv run pytest tests/test_project_setup.py tests/test_oauth.py tests/test_connect_auth.py -v
```

Manual: Cursor Auth against Hub with public URL (after deploy).

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Loud MCP-down AGENTS/rule/skill | Tasks 1–2 |
| PRM + AS metadata | Task 3 |
| 401 resource_metadata | Task 3 |
| Authorize + token + PKCE | Tasks 4–5 |
| DCR + static fallback | Task 5 |
| bearer_authorized accepts OAuth | Task 4 |
| Static Bearer + CLI connect preserved | Task 5 regression |
| Docs / doctor | Task 6 |
| Agent-agnostic Auth (not Cursor-only) | Tasks 3–5 design + docs |
| No public commercial notes | Global constraint |

## Self-review

- No TBD placeholders in task steps.
- P0 shippable without P1.
- Commercial/hosted product motivation excluded from plan and public docs (Hub progress only).
