# Product Hunt Supademo Hosted Dummy Hub — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Host a Tailscale-reachable ADHD Hub web UI on this VPS, seeded with generic dummy data, ready for a Product Hunt Supademo recording.

**Architecture:** Run `adhd-hub serve` on loopback `:8787` with `ADHD_HUB_DATA_DIR=.demo-data/`. Seed via REST (`scripts/seed_demo_hub.py`) using the same generic projects/threads as README screenshots. Expose with existing `serve 8787`. Optionally pre-auth the browser storage so recording opens on Now.

**Tech Stack:** Python 3 / `uv`, Hub REST API + SQLite under data dir, Playwright (optional prep), Tailscale Serve helper `serve`.

## Global Constraints

- Generic demo content only — titles/steps must match the README dummy set (Demo website / Home admin / Learning notes); no personal or customer data.
- Bind Hub to `127.0.0.1:8787` only; preview via Tailscale Serve (not public Cloudflare).
- Pre-auth preferred for recording; no Product Hunt film (`promo/product-hunt/`) changes.
- Never commit `.demo-data/`, `.env`, or real tokens.
- Git commits require a configured author identity — skip commit steps if `git commit` fails on identity; leave changes staged/unstaged for the operator.

---

## File map

| File | Responsibility |
| --- | --- |
| `.gitignore` | Ignore `.demo-data/` |
| `scripts/seed_demo_hub.py` | Wait for health, POST seed payload, backdate one thread; docstring runbook |
| `scripts/prep_demo_browser.py` | Playwright: login + localStorage for Now landing state |
| `tests/test_seed_demo_hub.py` | Assert seed payload shape / generic titles (no live server) |

---

### Task 1: Seed payload module + unit test

**Files:**
- Create: `scripts/seed_demo_hub.py`
- Create: `tests/test_seed_demo_hub.py`

**Interfaces:**
- Consumes: none
- Produces: `PROJECTS: list[tuple[str, str, list[str]]]`, `THREADS: list[tuple[...]]`, `demo_payload()` → `dict` with keys `projects`, `threads`, `progress_note`, `stale_summary`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_demo_hub.py
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seed_demo_hub import demo_payload  # noqa: E402


def test_demo_payload_is_generic_readme_set():
    data = demo_payload()
    slugs = {p["slug"] for p in data["projects"]}
    assert slugs == {"demo-site", "home-admin", "learning"}
    titles = {t["summary"] for t in data["threads"]}
    assert "Polish the landing page" in titles
    assert "Book a dentist visit" in titles
    assert data["stale_summary"] == "Book a dentist visit"
    assert data["progress_note"]["project_slug"] == "demo-site"
    # Guard against accidental personal copy
    blob = repr(data).lower()
    assert "pike" not in blob
    assert "@" not in blob
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_seed_demo_hub.py::test_demo_payload_is_generic_readme_set -v`  
Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `seed_demo_hub`

- [ ] **Step 3: Write minimal seed module (payload + helpers only; CLI in Task 2)**

```python
# scripts/seed_demo_hub.py
"""Seed a running Hub with generic Product Hunt / Supademo dummy data.

Runbook (on unidev):
  export ADHD_HUB_AUTH_TOKEN=<long-random>
  export ADHD_HUB_DATA_DIR="$PWD/.demo-data"
  mkdir -p "$ADHD_HUB_DATA_DIR"
  uv run adhd-hub serve --host 127.0.0.1 --port 8787
  # other terminal:
  ADHD_HUB_BASE=http://127.0.0.1:8787 uv run python scripts/seed_demo_hub.py
  serve 8787
  # UI: https://dev-vps.pygora-gacrux.ts.net:8787/ui/
  # Re-seed: rm -rf .demo-data && mkdir -p .demo-data && restart serve && re-run this script
"""
from __future__ import annotations

from typing import Any


def demo_payload() -> dict[str, Any]:
    projects = [
        {"slug": "demo-site", "title": "Demo website", "tags": ["Creative"]},
        {"slug": "home-admin", "title": "Home admin", "tags": ["Personal"]},
        {"slug": "learning", "title": "Learning notes", "tags": ["Learning"]},
    ]
    threads = [
        {
            "summary": "Polish the landing page",
            "project_slug": "demo-site",
            "status": "open",
            "focus": "Tighten the hero copy",
            "goal": "Ship a calmer first viewport for the demo site.",
            "next_steps": ["Draft one clearer headline"],
            "resume": "Draft one clearer headline",
            "source_tool": "web",
        },
        {
            "summary": "Book a dentist visit",
            "project_slug": "home-admin",
            "status": "open",
            "focus": "Find a nearby clinic",
            "goal": "Schedule routine care without overthinking it.",
            "next_steps": ["Check opening hours"],
            "resume": "Check opening hours",
            "source_tool": "web",
        },
        {
            "summary": "Review design notes",
            "project_slug": "learning",
            "status": "open",
            "focus": "Skim last week's notes",
            "goal": "Keep learning notes scannable for the next session.",
            "next_steps": ["Write one takeaway"],
            "resume": "Write one takeaway",
            "source_tool": "web",
        },
        {
            "summary": "Collect homepage ideas",
            "project_slug": "demo-site",
            "status": "done",
            "focus": "Choose a direction",
            "goal": "Archive finished exploration.",
            "next_steps": ["Save three examples"],
            "resume": "Save three examples",
            "source_tool": "web",
        },
    ]
    return {
        "projects": projects,
        "threads": threads,
        "stale_summary": "Book a dentist visit",
        "progress_note": {
            "project_slug": "demo-site",
            "title": "Polish the landing page",
            "goal": "Ship a calmer first viewport for the demo site.",
            "focus": "Tighten the hero copy",
            "next_steps": ["Draft one clearer headline"],
            "resume_step": "Draft one clearer headline",
            "content": (
                "Dummy note for screenshots: keep the hero quiet — "
                "brand, one line, one CTA."
            ),
            "source_tool": "web",
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_seed_demo_hub.py::test_demo_payload_is_generic_readme_set -v`  
Expected: PASS

- [ ] **Step 5: Commit** (skip if git author identity missing)

```bash
git add scripts/seed_demo_hub.py tests/test_seed_demo_hub.py
git commit -m "$(cat <<'EOF'
feat: add generic Supademo hub seed payload

EOF
)"
```

---

### Task 2: Seed CLI against a live Hub

**Files:**
- Modify: `scripts/seed_demo_hub.py` (add `main`, HTTP seed, SQLite backdate)
- Modify: `.gitignore` (add `.demo-data/`)

**Interfaces:**
- Consumes: `demo_payload()` from Task 1; env `ADHD_HUB_BASE` (default `http://127.0.0.1:8787`), `ADHD_HUB_AUTH_TOKEN`, `ADHD_HUB_DATA_DIR` (default `.demo-data`)
- Produces: CLI exit 0 after projects/threads/progress seeded; prints first open `thread_id`

- [ ] **Step 1: Append CLI to `scripts/seed_demo_hub.py`**

Add below `demo_payload()`:

```python
import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _api(base: str, token: str, path: str, payload: dict) -> dict:
    req = Request(
        base.rstrip("/") + "/api" + path,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        return json.load(resp)


def wait_health(base: str, tries: int = 50) -> None:
    for _ in range(tries):
        try:
            urlopen(base.rstrip("/") + "/api/health", timeout=1).close()
            return
        except (URLError, OSError):
            time.sleep(0.1)
    raise SystemExit(f"Hub not healthy at {base}")


def seed(base: str, token: str, data_dir: Path) -> str:
    data = demo_payload()
    wait_health(base)
    for project in data["projects"]:
        _api(base, token, "/projects", project)
    first_open_id = ""
    for thread in data["threads"]:
        row = _api(base, token, "/threads", thread)
        if not first_open_id and thread["status"] == "open":
            first_open_id = str(row.get("id") or "")
    note = dict(data["progress_note"])
    note["thread_id"] = first_open_id
    _api(base, token, "/progress", note)
    stale_at = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    db = data_dir / "hub.sqlite3"
    if not db.is_file():
        raise SystemExit(f"Missing {db} after seed")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE threads SET updated_at = ?, last_reminded_at = NULL, "
            "triage_snooze_until = NULL WHERE summary = ? AND status = 'open'",
            (stale_at, data["stale_summary"]),
        )
    return first_open_id


def main(argv: list[str] | None = None) -> int:
    _ = argv
    token = os.environ.get("ADHD_HUB_AUTH_TOKEN", "").strip()
    if not token or token == "change-me-to-a-long-random-string":
        print("Set ADHD_HUB_AUTH_TOKEN to a non-placeholder value", file=sys.stderr)
        return 2
    base = os.environ.get("ADHD_HUB_BASE", "http://127.0.0.1:8787")
    data_dir = Path(os.environ.get("ADHD_HUB_DATA_DIR", ".demo-data")).resolve()
    thread_id = seed(base, token, data_dir)
    print(f"seeded ok thread_id={thread_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Ignore demo data dir**

Add to `.gitignore` under the Runtime / secrets section:

```
.demo-data/
```

- [ ] **Step 3: Smoke the CLI against a temp Hub (automated)**

Run from repo root (one shell):

```bash
TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
rm -rf .demo-data && mkdir -p .demo-data
ADHD_HUB_AUTH_TOKEN="$TOKEN" ADHD_HUB_DATA_DIR="$PWD/.demo-data" \
  ADHD_HUB_HOST=127.0.0.1 ADHD_HUB_PORT=8787 ADHD_HUB_FORGE_PROVIDER=none \
  ADHD_HUB_OPENCLAW_WEBHOOK_URL= \
  uv run adhd-hub serve --host 127.0.0.1 --port 8787 &
SERV_PID=$!
trap 'kill $SERV_PID 2>/dev/null' EXIT
for i in $(seq 1 50); do curl -fsS http://127.0.0.1:8787/api/health && break; sleep 0.1; done
ADHD_HUB_AUTH_TOKEN="$TOKEN" ADHD_HUB_BASE=http://127.0.0.1:8787 \
  ADHD_HUB_DATA_DIR="$PWD/.demo-data" uv run python scripts/seed_demo_hub.py
# Expected stdout: seeded ok thread_id=<uuid-or-id>
curl -fsS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/threads | head -c 400
kill $SERV_PID; trap - EXIT
```

Expected: seed prints `seeded ok thread_id=...`; threads JSON includes `Polish the landing page`.

- [ ] **Step 4: Commit** (skip if identity missing)

```bash
git add scripts/seed_demo_hub.py .gitignore
git commit -m "$(cat <<'EOF'
feat: seed running Hub for Supademo dummy data

EOF
)"
```

---

### Task 3: Browser prep script

**Files:**
- Create: `scripts/prep_demo_browser.py`

**Interfaces:**
- Consumes: env `ADHD_HUB_BASE`, `ADHD_HUB_AUTH_TOKEN`, optional `ADHD_HUB_DEMO_THREAD_ID` (else first open thread from API)
- Produces: Playwright session that logs in and sets localStorage; prints ready URL

- [ ] **Step 1: Write `scripts/prep_demo_browser.py`**

```python
"""Log into the demo Hub and set Now landing localStorage for Supademo.

Requires: Hub running + seeded; Playwright Chromium installed.
  uv run --with playwright python scripts/prep_demo_browser.py
  # first time: uv run --with playwright playwright install chromium
"""
from __future__ import annotations

import json
import os
import sys
from urllib.request import Request, urlopen


def main() -> int:
    token = os.environ.get("ADHD_HUB_AUTH_TOKEN", "").strip()
    base = os.environ.get("ADHD_HUB_BASE", "http://127.0.0.1:8787").rstrip("/")
    if not token:
        print("ADHD_HUB_AUTH_TOKEN required", file=sys.stderr)
        return 2
    thread_id = os.environ.get("ADHD_HUB_DEMO_THREAD_ID", "").strip()
    if not thread_id:
        req = Request(
            base + "/api/threads",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(req, timeout=10) as resp:
            rows = json.load(resp)
        for row in rows if isinstance(rows, list) else rows.get("threads", []):
            if row.get("status") == "open" and row.get("summary") == "Polish the landing page":
                thread_id = str(row["id"])
                break
        if not thread_id:
            print("Could not find open landing-page thread; seed first", file=sys.stderr)
            return 1
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=os.environ.get("ADHD_HUB_BROWSER_EXECUTABLE") or None,
            args=["--no-sandbox"],
            headless=True,
        )
        context = browser.new_context()
        page = context.new_page()
        page.goto(base + "/ui/")
        page.locator("#login-token").fill(token)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.locator("#now-view")).to_be_visible()
        page.evaluate(
            """(id) => {
              localStorage.setItem('adhd_hub_theme', 'light');
              localStorage.setItem('adhd_hub_chosen_thread', id);
              localStorage.setItem('adhd_hub_focus_state', 'paused');
              localStorage.setItem('adhd_hub_rewards', 'true');
            }""",
            thread_id,
        )
        page.reload()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")
        expect(page.locator("#next-card .resume-step")).to_contain_text(
            "Draft one clearer headline"
        )
        # Persist storage for a headed re-open path if operator wants
        storage = context.storage_state()
        out = os.environ.get("ADHD_HUB_DEMO_STORAGE", ".demo-data/playwright-storage.json")
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(storage, fh)
        browser.close()
    print(f"prep ok thread_id={thread_id} storage={out}")
    print(f"open {base}/ui/ (or Tailscale Serve URL) for recording")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run prep against the smoke Hub from Task 2** (or restart serve + seed if stopped)

```bash
ADHD_HUB_AUTH_TOKEN="$TOKEN" ADHD_HUB_BASE=http://127.0.0.1:8787 \
  uv run --with playwright python scripts/prep_demo_browser.py
```

Expected: `prep ok thread_id=... storage=.demo-data/playwright-storage.json`

- [ ] **Step 3: Commit** (skip if identity missing)

```bash
git add scripts/prep_demo_browser.py
git commit -m "$(cat <<'EOF'
feat: prep browser storage for Supademo Now landing

EOF
)"
```

---

### Task 4: Host on unidev + Tailscale Serve

**Files:**
- None (runtime only). Keep `.demo-data/` and token out of git.

**Interfaces:**
- Consumes: Tasks 1–3 scripts; `serve` helper; hostname `unidev`
- Produces: Live URL `https://dev-vps.pygora-gacrux.ts.net:8787/ui/`

- [ ] **Step 1: Confirm host and free/own port 8787**

```bash
hostname  # must be unidev
ss -lnt | rg '8787' || true
```

If something else owns `127.0.0.1:8787`, stop it or pick another port and pass the same port to `serve`.

- [ ] **Step 2: Start durable demo Hub**

```bash
cd /home/orca/orca/workspaces/adhd-hub/dummy-demo
TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
# Persist token for this session only — do not echo into chat logs if avoidable; report SET
mkdir -p .demo-data
printf '%s\n' "ADHD_HUB_AUTH_TOKEN=$TOKEN" > .env.demo
# .env.demo is covered by .env.* gitignore
nohup env $(grep -v '^#' .env.demo | xargs) \
  ADHD_HUB_DATA_DIR="$PWD/.demo-data" \
  ADHD_HUB_HOST=127.0.0.1 ADHD_HUB_PORT=8787 \
  ADHD_HUB_FORGE_PROVIDER=none ADHD_HUB_OPENCLAW_WEBHOOK_URL= \
  uv run adhd-hub serve --host 127.0.0.1 --port 8787 \
  >.demo-data/serve.log 2>&1 &
echo $! > .demo-data/serve.pid
for i in $(seq 1 50); do curl -fsS http://127.0.0.1:8787/api/health && break; sleep 0.1; done
set -a && source .env.demo && set +a
ADHD_HUB_BASE=http://127.0.0.1:8787 ADHD_HUB_DATA_DIR="$PWD/.demo-data" \
  uv run python scripts/seed_demo_hub.py
```

- [ ] **Step 3: Wire Tailscale Serve**

```bash
serve 8787
curl -fsS -o /dev/null http://127.0.0.1:8787/ui/
```

- [ ] **Step 4: Prep browser storage (optional but preferred)**

```bash
set -a && source .env.demo && set +a
ADHD_HUB_BASE=http://127.0.0.1:8787 \
  uv run --with playwright python scripts/prep_demo_browser.py
```

- [ ] **Step 5: Verify landing content over loopback**

```bash
set -a && source .env.demo && set +a
curl -fsS -H "Authorization: Bearer $ADHD_HUB_AUTH_TOKEN" \
  http://127.0.0.1:8787/api/threads | rg -n 'Polish the landing page|Book a dentist visit'
```

Expected: both summaries present.

- [ ] **Step 6: Report to operator**

Print (no token values):

```text
Demo Hub UI (tailnet): https://dev-vps.pygora-gacrux.ts.net:8787/ui/
Sign-in: use ADHD_HUB_AUTH_TOKEN from .env.demo (SET, not printed)
Landing: Now → Polish the landing page → "Draft one clearer headline"
Stop: kill $(cat .demo-data/serve.pid)
```

Update forge issue [#304](https://github.com/uniskela/adhd-hub/issues/304) with Goal done / Resume = record Supademo (no secrets).

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| uv serve on 127.0.0.1:8787 | Task 4 |
| `.demo-data/` + gitignore | Task 2 |
| `scripts/seed_demo_hub.py` + README-generic seed | Tasks 1–2 |
| Backdate dentist thread | Task 2 |
| Docstring runbook | Task 1 |
| Pre-auth Playwright + localStorage | Task 3 |
| `serve 8787` Tailscale URL | Task 4 |
| No film / no public tunnel / no token commit | Global + Task 4 |

## Self-review notes

- No TBD placeholders.
- Seed field names match `capture_readme_screenshots.py` (`resume` on threads, `resume_step` on progress).
- Commit steps explicitly skip when git identity is missing (matches this workspace).

## Later (not this plan)

Product idea for a future release phase: optional first-boot / Settings sample data (env flag and/or “Load sample data” in Settings) so a demo Hub does not need `scripts/seed_demo_hub.py`. Reuse the same generic payload when that lands.
