"""Log into the demo Hub and set Now landing localStorage for Supademo.

Set ADHD_HUB_BASE to the same origin you will record (loopback or Tailscale URL).
Storage state is origin-bound — do not prep on localhost and record on a
different host.

Requires: Hub running + seeded; Playwright Chromium installed.
  uv run --with playwright python scripts/prep_demo_browser.py
  # first time: uv run --with playwright playwright install chromium

Re-open with saved state (same ADHD_HUB_BASE):
  uv run --with playwright python -c "
  from playwright.sync_api import sync_playwright
  import os
  base=os.environ['ADHD_HUB_BASE'].rstrip('/')
  path=os.environ.get('ADHD_HUB_DEMO_STORAGE','.demo-data/playwright-storage.json')
  with sync_playwright() as p:
      b=p.chromium.launch(headless=False)
      c=b.new_context(storage_state=path)
      c.new_page().goto(base+'/ui/')
      input('Recording browser open; press Enter to close…')
  "
"""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main() -> int:
    token = os.environ.get("ADHD_HUB_AUTH_TOKEN", "").strip()
    base = os.environ.get("ADHD_HUB_BASE", "http://127.0.0.1:8787").rstrip("/")
    if not token:
        print("ADHD_HUB_AUTH_TOKEN required", file=sys.stderr)
        return 2
    thread_id = os.environ.get("ADHD_HUB_DEMO_THREAD_ID", "").strip()
    if not thread_id:
        query = urlencode(
            {
                "project_slug": "sample-demo-site",
                "status": "open",
                "limit": 50,
            }
        )
        req = Request(
            f"{base}/api/threads?{query}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urlopen(req, timeout=10) as resp:
            rows = json.load(resp)
        for row in rows if isinstance(rows, list) else rows.get("threads", []):
            if (
                row.get("status") == "open"
                and row.get("summary") == "Polish the landing page"
                and row.get("project_slug") == "sample-demo-site"
            ):
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
        storage = context.storage_state()
        out = Path(
            os.environ.get("ADHD_HUB_DEMO_STORAGE", ".demo-data/playwright-storage.json")
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            out,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(storage, fh)
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
        browser.close()
    print(f"prep ok thread_id={thread_id} storage={out}")
    print(f"Recording origin must match ADHD_HUB_BASE={base}")
    print(f"Reopen with storage_state={out} (see script docstring)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
