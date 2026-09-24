"""Capture clean README/docs product screenshots with dummy seed data.

Run: uv run --with playwright python scripts/capture_readme_screenshots.py
Optional: ADHD_HUB_BROWSER_EXECUTABLE, ADHD_HUB_SCREENSHOT_DIR
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = Path(
        os.environ.get(
            "ADHD_HUB_SCREENSHOT_DIR",
            str(root / "docs" / "images"),
        )
    )
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    token = secrets.token_urlsafe(32)

    def seed(path: str, payload: dict) -> dict:
        request = Request(
            base + "/api" + path,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    with tempfile.TemporaryDirectory(prefix="adhd-hub-readme-shots-") as data:
        env = {
            **os.environ,
            "ADHD_HUB_AUTH_TOKEN": token,
            "ADHD_HUB_DATA_DIR": data,
            "ADHD_HUB_HOST": "127.0.0.1",
            "ADHD_HUB_PORT": str(port),
            "ADHD_HUB_FORGE_PROVIDER": "none",
            "ADHD_HUB_OPENCLAW_WEBHOOK_URL": "",
        }
        server = subprocess.Popen(
            [sys.executable, "-m", "adhd_hub", "serve"],
            cwd=root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                try:
                    urlopen(base + "/api/health", timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Temporary Hub did not start")

            for slug, title, tags in [
                ("demo-site", "Demo website", ["Creative"]),
                ("home-admin", "Home admin", ["Personal"]),
                ("learning", "Learning notes", ["Learning"]),
            ]:
                seed("/projects", {"slug": slug, "title": title, "tags": tags})

            threads = [
                (
                    "Polish the landing page",
                    "demo-site",
                    "open",
                    "Tighten the hero copy",
                    "Draft one clearer headline",
                    "Ship a calmer first viewport for the demo site.",
                ),
                (
                    "Book a dentist visit",
                    "home-admin",
                    "open",
                    "Find a nearby clinic",
                    "Check opening hours",
                    "Schedule routine care without overthinking it.",
                ),
                (
                    "Review design notes",
                    "learning",
                    "open",
                    "Skim last week's notes",
                    "Write one takeaway",
                    "Keep learning notes scannable for the next session.",
                ),
                (
                    "Collect homepage ideas",
                    "demo-site",
                    "done",
                    "Choose a direction",
                    "Save three examples",
                    "Archive finished exploration.",
                ),
            ]
            first_thread_id = None
            for summary, project, status, focus, next_step, goal in threads:
                row = seed(
                    "/threads",
                    {
                        "summary": summary,
                        "project_slug": project,
                        "status": status,
                        "focus": focus,
                        "goal": goal,
                        "next_steps": [next_step],
                        "resume": next_step,
                        "source_tool": "web",
                    },
                )
                if first_thread_id is None and status == "open":
                    first_thread_id = row.get("id")

            seed(
                "/progress",
                {
                    "project_slug": "demo-site",
                    "thread_id": first_thread_id,
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
            )

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=os.environ.get("ADHD_HUB_BROWSER_EXECUTABLE")
                    or None,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 900},
                    reduced_motion="reduce",
                )
                page.goto(base + "/ui")
                page.locator("#login-token").fill(token)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator("#now-view")).to_be_visible()

                # Prefer light theme for public README (matches brand sheet).
                page.evaluate("localStorage.setItem('adhd_hub_theme', 'light')")
                page.reload()
                expect(page.locator("html")).to_have_attribute("data-theme", "light")

                def shot(name: str) -> None:
                    page.wait_for_timeout(250)
                    page.screenshot(
                        path=str(out / name),
                        full_page=False,
                        animations="disabled",
                    )

                # Now
                expect(page.locator("#now-view")).to_be_visible()
                shot("now-desktop.png")

                # My work with projects rail + thread cards
                page.locator('[data-screen="work"]:visible').first.click()
                expect(page.locator("#work-view")).to_be_visible()
                expect(page.locator("#threads [data-choose]").first).to_be_visible()
                page.locator('#project-list .proj[data-slug="demo-site"]').click()
                expect(page.locator("#threads")).to_contain_text("landing page")
                shot("my-work-desktop.png")

                # Notes reader (docked)
                notes_btn = page.locator(".thread-notes-inline:visible").first
                if notes_btn.count():
                    notes_btn.click()
                else:
                    page.locator(".thread-utility").first.locator("summary").click()
                    page.locator(".thread-notes-menu").first.click()
                expect(page.locator("#notes-reader")).to_be_visible()
                shot("notes-reader-desktop.png")
                page.keyboard.press("Escape")

                # Progress
                page.locator('[data-screen="progress"]:visible').first.click()
                expect(page.locator("#progress-view")).to_be_visible()
                shot("progress-desktop.png")

                # Settings → Preferences
                page.locator("#btn-settings:visible, #btn-mobile-settings:visible").first.click()
                if not page.locator("#settings-preferences").is_visible():
                    page.get_by_role("tab", name="Preferences", exact=True).click()
                expect(page.locator("#settings-preferences")).to_be_visible()
                shot("settings-desktop.png")

                browser.close()
                print(f"PASS: screenshots written to {out}")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
