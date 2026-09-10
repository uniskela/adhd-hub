# Dashboard sign-in

The hub has two independent credentials: a dashboard password for everyday browser use, and the server access token for REST/MCP clients and password recovery. This is a single-owner, self-hosted sign-in flow.

## First-time setup

1. Set `ADHD_HUB_AUTH_TOKEN` to a private random value on the server and restart the hub. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Keep it in your environment or untracked `.env`.
2. Open `/ui/` and sign in with that access token.
3. Choose **Create password**, or **Settings → Sign-in & security → Create or change password**. Verify with your access token, then enter and confirm a password of at least 12 characters. It must differ from your access token.
4. Future visits default to password sign-in. The page supports password managers and a show/hide control.

No password is configured automatically. Local development with the default token can still run on loopback, but password setup requires a private server token first.

## Change or recover a password

In Settings, choose **Create or change password** and verify with either your current password or your recovery access token. Saving a password revokes every previous browser session and gives the current browser a new session. Assistant connections retain their access token.

If you forget your password, choose **Use recovery access token** on the sign-in page, sign in with `ADHD_HUB_AUTH_TOKEN`, and reset the password in Settings. A damaged password file can also be replaced using this flow. If the access token is lost, set a new one in the server environment and restart the hub, then use it to recover access; update your MCP clients too.

## Storage and sessions

- Passwords are salted and hashed with scrypt (`N=32768`, `r=8`, `p=3`, 32-byte output), atomically stored in `data/dashboard-password.hash` with mode `0600`. The password itself is never saved.
- Browser sessions expire after 12 hours. Cookies are HttpOnly and SameSite=Strict; HTTPS enables Secure. Credentials are never written to localStorage.
- Sessions are stored in SQLite (`data/browser_sessions.sqlite3`) and survive process restart and multiple workers. Login throttles stay in process memory, so a restart clears those counters.
- Password setup, password sign-in, and token sign-in share a limit of five attempts per client IP per minute. A successful attempt clears that client's counter. Configure trusted proxy headers correctly so a reverse proxy supplies the real client IP and HTTPS scheme.
- Cookie-authenticated writes require `X-Hub-Request: 1`; an Origin, when present, must match the server origin. Use HTTPS for remote access.
- Backup export deliberately excludes the password hash and browser sessions. Restoring project data does not overwrite credentials. On a new machine, set its server token and create a password again, or separately migrate the private hash file while retaining its permissions.

## Auth endpoints

All auth responses disable caching. Invalid auth requests return field locations and generic validation messages without echoing submitted credentials. Browser writes require `X-Hub-Request: 1`.

| Endpoint | Request |
| --- | --- |
| `GET /api/auth/status` | Reports whether a password is configured and whether development mode is active; returns no secrets. |
| `POST /api/auth/login` | Exactly one of `password` or `token`; issues a session cookie. |
| `PUT /api/auth/password` | `current_method` (`password` or `token`), `current_secret`, and a new `password`; verifies the credential again even if already signed in. |
| `POST /api/auth/logout` | Revokes the current browser session. |

Dashboard passwords cannot be used as bearer credentials for REST or MCP. Those clients continue to use `ADHD_HUB_AUTH_TOKEN`.
