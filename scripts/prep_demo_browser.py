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
