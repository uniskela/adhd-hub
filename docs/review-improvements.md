# Repository review — September 2026

Implemented improvements:

- Browser login exchanges the hub token for an opaque, 12-hour HttpOnly session. Old localStorage credentials are removed, logout revokes the session, and cookie-authenticated writes require a browser request header and matching Origin when supplied. REST bearer tokens and MCP clients retain their existing authentication method.
- A default or empty token now prevents startup on a non-loopback bind. Bearer comparisons use constant-time comparison and MCP authentication failures include a Bearer challenge. API responses disable caching.
- Dashboard hidden panels now stay hidden. Search filters the latest 100 loaded threads, status filters expose their selected state, keyboard focus is visible, and reduced-motion preferences are honored. Settings messages remain visible inside the dialog. Project navigation, mobile wrapping, chart heights, and the chart legend are improved. External issue and forge links only accept HTTP(S).
- Settings includes a copyable MCP URL and local skill installation guidance. Codex and Cursor examples reference environment variables rather than embedding credentials. The MCP probe reads the process environment first, tolerates a missing `.env`, exits unsuccessfully on failed discovery, and no longer prints token fragments.
- MCP tools expose bounded limits, enum values, and read-only annotations where appropriate. Progress writes can explicitly avoid opening a thread. Skills retain returned thread IDs, avoid duplicate threads, and explain unavailable tools and ambiguous write retries.
- `ADHD_HUB_PUBLIC_URL` is now a declared setting. Environment overrides match the documented precedence. The lockfile package version now matches `pyproject.toml`. Scheduler cleanup also runs when the application lifespan exits with an error.

Validation:

- Full Python regression suite, including new browser-session, CSRF, expiry, configuration, MCP discovery, and invalid-input tests.
- Chromium smoke checks using a temporary local hub and temporary database: rejected and successful login, reload persistence, hidden panels, project creation, thread search/completion, settings feedback, activity chart, mobile overflow, and logout. No JavaScript page errors.
- JavaScript syntax, whitespace checks, and Ruff on changed Python files.
- Full-repository Ruff additionally reports eight existing findings in `scripts/bump_version.py`, `prefs.py`, `store.py`, and `wiki.py`. These are outside this patch. In particular, the `sqlite3.Row.keys()` findings should not be fixed mechanically: row membership checks values, not column names.
- The graph under `graphify-out/` is refreshed with `graphify update .`.

Deployment notes:

A follow-up adds a separate dashboard password, token-based recovery, and login throttling. See [authentication](authentication.md) and [dashboard preferences](dashboard.md). Individual accounts and OAuth providers are not configured. Browser sessions are stored in SQLite and survive restart; login throttles remain in-process. Use HTTPS for remote access and configure trusted proxy headers when TLS terminates upstream. Default-token unauthenticated development remains available on a loopback bind. No production deployment or external hub state was changed by this review.
