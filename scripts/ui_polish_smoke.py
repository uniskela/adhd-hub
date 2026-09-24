"""Visual and interaction smoke test for the four Hub screens.

Run: uv run --with playwright python scripts/ui_polish_smoke.py
Optional: ADHD_HUB_BROWSER_EXECUTABLE=/path/to/chromium
          ADHD_HUB_SCREENSHOT_DIR=/tmp/adhd-hub-ui-polish

Starts a private temporary Hub, so no existing account or forge is touched.
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
    screenshots = Path(os.environ.get("ADHD_HUB_SCREENSHOT_DIR", "/tmp/adhd-hub-ui-polish"))
    screenshots.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    token = secrets.token_urlsafe(32)

    def seed(path: str, payload: dict) -> dict:
        request = Request(
            base + "/api" + path,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    with tempfile.TemporaryDirectory(prefix="adhd-hub-ui-polish-") as data:
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
                ("website", "Personal website", ["Creative", "Online"]),
                ("home", "Home and life admin", ["Personal"]),
                ("learning", "Learning corner", ["Learning"]),
            ]:
                seed("/projects", {"slug": slug, "title": title, "tags": tags})
            for summary, project, status, focus, next_step in [
                ("Refresh the homepage", "website", "open", "Pick a welcoming photo", "Open the photo folder"),
                ("Plan the about page", "website", "open", "Draft a short introduction", "Write one sentence"),
                ("Book a dentist visit", "home", "open", "Find a nearby clinic", "Check the opening hours"),
                ("Review saved design notes", "learning", "open", "Read the notes", "Find the first takeaway"),
                ("Collect homepage ideas", "website", "done", "Choose the direction", "Save three examples"),
                ("Pay the electricity bill", "home", "done", "Check the due date", "Open the bill"),
            ]:
                seed("/threads", {
                    "summary": summary,
                    "project_slug": project,
                    "status": status,
                    "focus": focus,
                    "goal": f"Make progress on {summary.lower()}",
                    "next_steps": [next_step],
                    "source_tool": "web",
                })
            # An untagged project makes the Wave 6 organiser preview meaningful.
            seed("/projects", {"slug": "garden", "title": "Garden planning"})
            seed("/threads", {
                "summary": "Sketch a small balcony herb garden",
                "project_slug": "garden",
                "focus": "Choose low-maintenance herbs",
                "next_steps": ["Measure the balcony"],
                "source_tool": "web",
            })
            seed("/progress", {
                "project_slug": "website",
                "title": "Website context",
                "content": "## Notes\n\nStart with the photo folder. A single sentence is enough for today.",
            })

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=os.environ.get("ADHD_HUB_BROWSER_EXECUTABLE"),
                    args=["--no-sandbox"],
                )
                page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/ui")
                page.locator("#login-token").fill(token)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator("#now-view")).to_be_visible()
                page.locator('[data-screen="work"]:visible').first.click()
                expect(page.locator("#threads [data-choose]").first).to_be_visible()
                page.locator("#threads [data-choose]").first.click()
                expect(page.locator("#next-card").get_by_role("button", name="Start")).to_be_visible()

                def open_screen(screen: str) -> None:
                    if screen == "settings":
                        page.locator("#btn-settings:visible, #btn-mobile-settings:visible").first.focus()
                        page.keyboard.press("Enter")
                        if not page.locator("#settings-preferences").is_visible():
                            page.get_by_role("tab", name="Preferences", exact=True).click()
                        expect(page.locator("#settings-preferences")).to_be_visible()
                    else:
                        page.locator(f'[data-screen="{screen}"]:visible').first.focus()
                        page.keyboard.press("Enter")
                        expect(page.locator(f"#{screen}-view" if screen != "work" else "#work-view")).to_be_visible()

                for theme in ("light", "dark"):
                    page.evaluate("theme => localStorage.setItem('adhd_hub_theme', theme)", theme)
                    page.reload()
                    expect(page.locator("html")).to_have_attribute("data-theme", theme)
                    for width, height, label in ((1440, 900, "desktop"), (768, 1024, "tablet"), (390, 844, "mobile")):
                        page.set_viewport_size({"width": width, "height": height})
                        for screen in ("now", "work", "progress", "settings"):
                            open_screen(screen)
                            page.screenshot(path=str(screenshots / f"{screen}-{theme}-{label}.png"), full_page=True, animations="disabled")
                            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                            assert overflow <= 1, f"{screen} {theme} {label}: horizontal overflow {overflow}px"

                page.set_viewport_size({"width": 1440, "height": 900})
                open_screen("now")
                # Tab focus must make a user action available without using a pointer.
                page.locator("#btn-capture").focus()
                expect(page.locator("#btn-capture")).to_be_focused()
                page.keyboard.press("Enter")
                expect(page.locator("#capture-dialog")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.locator("#capture-dialog")).to_be_hidden()
                actions = page.locator("#next-card details.focus-options")
                if actions.count():
                    expect(actions).not_to_have_attribute("open", "")
                    actions.locator("summary").focus()
                    page.keyboard.press("Enter")
                    assert actions.evaluate("el => el.open"), "More actions disclosure did not open from keyboard"
                    page.keyboard.press("Enter")
                    assert not actions.evaluate("el => el.open"), "More actions disclosure did not close"
                open_screen("work")
                page.locator("#btn-organise-projects").click()
                expect(page.locator("#organise-dialog")).to_be_visible()
                expect(page.locator("#organise-list")).not_to_contain_text("Loading suggestions")
                assert page.locator("#organise-list [data-organise-index]").count(), "Expected seeded organiser suggestions"
                page.screenshot(path=str(screenshots / "organise-dark-desktop.png"), animations="disabled")
                assert not errors, f"Browser JavaScript errors: {errors}"
                browser.close()
                print(f"PASS: 24 screen/theme/viewport combinations, keyboard actions and organiser; screenshots: {screenshots}")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
