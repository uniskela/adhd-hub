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
                expect(page.locator("#threads .thread").first).to_be_visible()
                page.locator("#threads .thread").first.click()
                page.locator("#btn-notes-focus").click()
                expect(page.locator("#next-card").get_by_role("button", name="Start")).to_be_visible()

                def open_screen(screen: str) -> None:
                    if screen == "settings":
                        page.locator("#btn-settings:visible, #btn-mobile-settings:visible").first.click()
                        if not page.locator("#settings-preferences").is_visible():
                            page.get_by_role("tab", name="Appearance", exact=True).click()
                        expect(page.locator("#settings-preferences")).to_be_visible()
                    else:
                        page.locator(f'[data-screen="{screen}"]:visible').first.click()
                        expect(page.locator(f"#{screen}-view" if screen != "work" else "#work-view")).to_be_visible()

                for theme in ("light", "dark"):
                    page.evaluate("theme => localStorage.setItem('adhd_hub_theme', theme)", theme)
                    page.reload()
                    expect(page.locator("html")).to_have_attribute("data-theme", theme)
                    expect(page.locator('meta[name="theme-color"]')).to_have_attribute(
                        "content", "#15171a" if theme == "dark" else "#f7f6f3"
                    )
                    for width, height, label in ((1440, 900, "desktop"), (768, 1024, "tablet"), (390, 844, "mobile")):
                        page.set_viewport_size({"width": width, "height": height})
                        for screen in ("now", "work", "progress", "settings"):
                            open_screen(screen)
                            page.screenshot(path=str(screenshots / f"{screen}-{theme}-{label}.png"), full_page=True, animations="disabled")
                            overflow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                            assert overflow <= 1, f"{screen} {theme} {label}: horizontal overflow {overflow}px"
                page.set_viewport_size({"width": 390, "height": 844})
                open_screen("work")
                expect(page.locator("#btn-open-projects-drawer")).to_be_visible()
                expect(page.locator("#work-title")).to_be_hidden()
                expect(page.locator("#thread-search")).to_be_visible()
                page.locator("#btn-open-projects-drawer").click()
                expect(page.locator("#projects-rail")).to_be_visible()
                assert page.locator("#project-list").evaluate(
                    "el => el.scrollWidth <= el.clientWidth + 1"
                ), "Mobile project list must not require horizontal scrolling"
                # Drawer drag-and-drop keeps grips visible on phones (#209).
                expect(page.locator("#project-list .proj-drag-handle:visible")).to_have_count(4)
                expect(page.locator("#btn-organise-projects")).to_be_hidden()
                page.locator("#rail-menu > summary").click()
                expect(page.locator("#btn-organise-projects")).to_be_visible()
                expect(page.locator("#rail-menu .proj-dnd-hint")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.locator("#rail-menu > summary")).to_be_focused()
                expect(page.locator("#projects-rail")).to_be_visible()  # Escape closed only the menu
                page.locator('#project-list .proj[data-slug="website"]').click()
                expect(page.locator("#work-title-mobile")).to_have_text("Personal website")
                expect(page.locator('[data-tab-count="open"]')).to_have_text("2")
                expect(page.locator("#btn-rewrite-all-scan")).to_be_hidden()
                # AI helpers are off, so the project ⋯ menu has nothing to show.
                expect(page.locator("#project-menu")).to_be_hidden()
                expect(page.locator("#btn-edit-project")).to_be_visible()
                # Long titles must not push the project ⋯ off-screen.
                long_title = "imPikeh YouTube Archive " + ("X" * 40)
                page.evaluate(
                    """(title) => {
                      const mobile = document.getElementById('work-title-mobile');
                      const desktop = document.getElementById('work-title');
                      if (mobile) mobile.textContent = title;
                      if (desktop) desktop.textContent = title;
                    }""",
                    long_title,
                )
                edit_btn = page.locator("#btn-edit-project")
                box = edit_btn.bounding_box()
                assert box and box["x"] + box["width"] <= 390 + 1, "Project Edit must stay on-screen with a long title"
                page.locator("#thread-search").fill("homepage")
                expect(page.locator("#threads")).to_contain_text("homepage")
                expect(page.locator("#thread-count")).to_be_visible()
                page.locator("#thread-search").fill("")
                page.locator("#threads .thread").first.click()
                expect(page.locator("#notes-reader")).to_be_visible()
                page.locator("#notes-reader-menu > summary").click()
                panel = page.locator("#notes-reader-menu .thread-utility-panel")
                expect(panel).to_be_visible()
                pbox = panel.bounding_box()
                assert pbox and pbox["x"] >= -1 and pbox["x"] + pbox["width"] <= 390 + 1, "Reader ⋯ menu must stay on-screen"
                page.keyboard.press("Escape")
                expect(page.locator("#notes-reader")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.locator("#notes-reader")).to_be_hidden()
                page.set_viewport_size({"width": 1440, "height": 900})
                open_screen("now")
                # Tab focus must make a user action available without using a pointer.
                page.locator("#btn-capture").focus()
                expect(page.locator("#btn-capture")).to_be_focused()
                page.keyboard.press("Enter")
                expect(page.locator("#capture-dialog")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.locator("#capture-dialog")).to_be_hidden()
                actions = page.locator("#focus-menu")
                if actions.is_visible():
                    expect(actions).not_to_have_attribute("open", "")
                    actions.locator("summary").focus()
                    page.keyboard.press("Enter")
                    assert actions.evaluate("el => el.open"), "More actions menu did not open from keyboard"
                    page.keyboard.press("Escape")
                    assert not actions.evaluate("el => el.open"), "More actions menu did not close on Escape"
                    expect(actions.locator("summary")).to_be_focused()
                open_screen("work")
                # Search and tags stay tucked behind the filter button.
                expect(page.locator("#project-filters")).to_be_hidden()
                page.locator("#btn-toggle-project-filters").click()
                expect(page.locator("#project-search")).to_be_focused()
                page.locator("#project-search").fill("website")
                expect(page.locator("#project-list .proj")).to_have_count(1)
                page.locator('#tag-filter [data-tag="personal"]').click()
                expect(page.locator('#tag-filter [data-tag="personal"]')).to_have_attribute("aria-pressed", "true")
                expect(page.locator("#project-list")).to_contain_text("No matching projects")
                page.locator("#project-search").fill("")
                expect(page.locator("#project-list .proj")).to_have_count(1)
                page.locator('#tag-filter [data-tag=""]').click()
                expect(page.locator("#project-list .proj")).to_have_count(4)
                page.locator('#tag-filter [data-tag="personal"]').click()
                page.locator("#btn-toggle-project-filters").click()  # closing clears filters
                expect(page.locator("#project-filters")).to_be_hidden()
                expect(page.locator("#project-list .proj")).to_have_count(4)
                page.locator("#threads .thread").first.click()
                reader_menu = page.locator("#notes-reader-menu")
                reader_menu.locator("summary").focus()
                page.keyboard.press("Enter")
                expect(reader_menu.locator(".thread-utility-panel")).to_be_visible()
                page.screenshot(path=str(screenshots / "thread-actions-dark-desktop.png"), animations="disabled")
                page.keyboard.press("Escape")
                expect(reader_menu.locator(".thread-utility-panel")).to_be_hidden()
                expect(reader_menu.locator("summary")).to_be_focused()
                page.keyboard.press("Escape")
                open_screen("now")
                expect(page.locator("#now-open-count")).to_have_text("5")
                expect(page.locator("#now-done-count")).to_have_text("2")
                if not page.locator("#focus-mode-row").is_visible():
                    # The Focus mode switch belongs to a step you're working on.
                    open_screen("work")
                    page.locator("#threads .thread").first.click()
                    page.locator("#btn-notes-focus").click()
                    page.locator("#btn-start").click()
                expect(page.locator("#btn-focus-mode")).to_have_attribute("aria-checked", "false")
                page.locator("#btn-focus-mode").click()
                expect(page.locator("#btn-focus-mode")).to_have_attribute("aria-checked", "true")
                expect(page.locator("#btn-focus-mode")).to_be_focused()
                expect(page.locator(".now-overview")).to_be_hidden()
                # My work stays usable in focus mode, under one slim bar.
                open_screen("work")
                expect(page.locator("#drift-banner")).to_contain_text("Focus mode is on.")
                expect(page.locator("#threads .thread").first).to_be_visible()
                page.locator("#btn-return-focus").click()
                expect(page.locator("#now-view")).to_be_visible()
                page.locator("#btn-focus-mode").click()
                expect(page.locator(".now-overview")).to_be_visible()
                open_screen("work")
                page.locator("#rail-menu > summary").click()
                page.locator("#btn-organise-projects").click()
                expect(page.locator("#organise-dialog")).to_be_visible()
                expect(page.locator("#organise-list")).not_to_contain_text("Loading suggestions")
                assert page.locator("#organise-list [data-organise-index]").count(), "Expected seeded organiser suggestions"
                page.screenshot(path=str(screenshots / "organise-dark-desktop.png"), animations="disabled")
                page.keyboard.press("Escape")
                open_screen("settings")
                page.locator('[data-accent="#4f46c8"]').click()
                expect(page.locator('[data-accent="#4f46c8"]')).to_have_attribute("aria-pressed", "true")
                page.locator("#accent-colour").fill("#ffff00")
                expect(page.locator("#accent-value")).to_have_text("#FFFF00")
                page.reload()
                open_screen("settings")
                expect(page.locator("#accent-colour")).to_have_value("#ffff00")
                dark_accent = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent')")
                page.get_by_role("radio", name="Light theme", exact=True).click()
                light_accent = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent')")
                assert light_accent != dark_accent, "Custom accent must adapt to its theme"
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
                page.screenshot(path=str(screenshots / "accent-custom-light-mobile.png"), full_page=True, animations="disabled")
                page.locator('[data-accent=""]').click()
                expect(page.locator("#accent-value")).to_have_text("Default palette")
                assert page.evaluate("document.documentElement.style.getPropertyValue('--accent')") == ""
                assert not errors, f"Browser JavaScript errors: {errors}"
                browser.close()
                print(f"PASS: 24 screen/theme/viewport combinations, keyboard actions, organiser and custom accents; screenshots: {screenshots}")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
