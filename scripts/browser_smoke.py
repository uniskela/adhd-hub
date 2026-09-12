"""Exercise the dashboard against a temporary hub (requires Playwright + Chromium).

Run: uv run --with playwright python scripts/browser_smoke.py
Optional: ADHD_HUB_BROWSER_EXECUTABLE=/path/to/chromium
Screenshots: ADHD_HUB_SCREENSHOT_DIR=/tmp/adhd-hub-preview (default)
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    screenshots = Path(os.environ.get("ADHD_HUB_SCREENSHOT_DIR", "/tmp/adhd-hub-preview"))
    screenshots.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    token = secrets.token_urlsafe(32)
    password = "a little progress every day"

    def seed(path, payload):
        request = Request(
            base + "/api" + path,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    with tempfile.TemporaryDirectory(prefix="adhd-hub-browser-") as data:
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
                raise RuntimeError("Temporary test server did not start")
            for slug, title, project_repo in [
                ("my-website", "Personal website", "https://github.com/example/my-website"),
                ("learning", "Learning corner", None),
                ("home", "Little life admin", None),
            ]:
                seed("/projects", {"slug": slug, "title": title, "repo_url": project_repo})
            for summary, slug, status in [
                ("Collect a few homepage ideas", "my-website", "done"),
                ("Make a place for project notes", "learning", "done"),
                ("Write down one thing I learned", "learning", "open"),
                ("Find the appointment email", "home", "open"),
                ("Pick a photo for the about page", "my-website", "open"),
                ("Write the first sentence of my homepage", "my-website", "open"),
            ]:
                seed(
                    "/threads",
                    {
                        "summary": summary,
                        "project_slug": slug,
                        "status": status,
                        "source_tool": "web",
                    },
                )
            seed(
                "/progress",
                {
                    "project_slug": "my-website",
                    "content": "## Next visit\n\n- **Choose a photo**\n- Write the intro\n\n<script>alert(1)</script>",
                    "title": "Website notes",
                },
            )
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=os.environ.get("ADHD_HUB_BROWSER_EXECUTABLE"),
                    args=["--no-sandbox"],
                )
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1080}, reduced_motion="reduce"
                )
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/ui")
                expect(page.locator("#login-gate")).to_be_visible()
                expect(page.locator("#app-shell")).to_be_hidden()
                page.evaluate("localStorage.setItem(\"adhd_hub_theme\", \"light\")"); page.reload()
                page.screenshot(path=str(screenshots / "login-light.png"), full_page=True)
                page.evaluate("localStorage.setItem(\"adhd_hub_theme\", \"dark\")"); page.reload()
                page.reload()
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                page.screenshot(path=str(screenshots / "login-dark.png"), full_page=True)
                page.evaluate("localStorage.setItem(\"adhd_hub_theme\", \"system\")"); page.reload()
                page.emulate_media(color_scheme="light")
                expect(page.locator("html")).to_have_attribute("data-theme", "light")
                page.emulate_media(color_scheme="dark")
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                page.locator("#login-token").fill("wrong")
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator("#login-error")).to_contain_text("not accepted")
                page.locator("#login-token").fill(token)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator("#app-shell")).to_be_visible()
                expect(page.locator(".appearance-bar")).to_have_count(0)
                expect(page.locator(".app-header")).to_be_visible()
                expect(page.locator(".mobile-nav")).to_have_count(1)
                expect(page.locator("#login-gate")).to_be_hidden()
                expect(page.locator("#now-view")).to_be_visible()
                expect(page.locator("#work-view")).to_be_hidden()
                expect(page.locator("#progress-view")).to_be_hidden()
                page.get_by_role("button", name="Settings", exact=True).click()
                page.get_by_role("tab", name="Account", exact=True).click()
                page.get_by_role("button", name="Create password", exact=True).click()
                page.locator("#password-current").fill(token)
                page.locator("#password-new").fill(password)
                page.locator("#password-confirm").fill("these words do not match")
                page.get_by_role("button", name="Save password", exact=True).click()
                expect(page.locator("#password-error")).to_contain_text("don’t match")
                page.locator("#password-confirm").fill(password)
                page.get_by_role("button", name="Save password", exact=True).click()
                expect(page.locator("#password-dialog")).to_be_hidden()
                expect(page.locator("#password-banner")).to_be_hidden()
                page.get_by_role("button", name="Settings", exact=True).click()
                page.get_by_role("tab", name="Account", exact=True).click()
                page.get_by_role("button", name="Log out", exact=True).click()
                expect(page.locator("#login-label")).to_have_text("Password")
                page.locator("#login-token").fill(password)
                page.get_by_role("button", name="Show password", exact=True).click()
                expect(page.locator("#login-token")).to_have_attribute("type", "text")
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator("#app-shell")).to_be_visible()
                assert page.evaluate('localStorage.getItem("adhd_hub_token")') is None
                assert "adhd_hub_session" not in page.evaluate("document.cookie")
                page.reload()
                expect(page.locator("#app-shell")).to_be_visible()
                page.get_by_role("button", name="Choose a task", exact=True).click()
                expect(page.locator("#work-view")).to_be_visible()
                page.locator('#project-list [data-slug="my-website"]').click()
                expect(page.locator("#work-title")).to_have_text("Personal website")
                page.locator("#threads [data-choose]").first.click()
                expect(page.locator("#now-view")).to_be_visible()
                notes = page.locator("#next-card .progress-details")
                assert notes.evaluate("el => !el.open")
                notes.locator("summary").click()
                expect(notes.locator(".markdown-body")).to_contain_text("Personal website")
                expect(page.locator("#next-card script")).to_have_count(0)
                page.get_by_role("button", name="Start", exact=True).click()
                page.get_by_role("button", name="Pause here", exact=True).click()
                page.locator("#pause-step").fill("Open the **photo folder**")
                page.get_by_role("button", name="Save & pause", exact=True).click()
                expect(page.locator("#pause-dialog")).to_be_hidden()
                expect(page.locator("#next-card .resume-step strong")).to_have_text("photo folder")
                page.reload()
                expect(page.get_by_role("button", name="Resume", exact=True)).to_be_visible()
                page.get_by_role("button", name="Save a thought", exact=True).click()
                page.locator("#capture-summary").fill("Open the draft and add one sentence")
                page.get_by_role("button", name="Save thought", exact=True).click()
                expect(page.locator("#capture-dialog")).to_be_hidden()
                expect(page.locator("#now-view")).to_be_visible()
                page.get_by_role("button", name="My work", exact=True).click()
                page.get_by_role("button", name="All projects", exact=True).click()
                expect(page.locator("#threads")).to_contain_text("Open the draft")
                page.locator("#thread-search").fill("no matches")
                expect(page.locator("#threads")).to_contain_text("No matches")
                page.locator("#thread-search").fill("")
                page.get_by_role("button", name="Now", exact=True).click()
                page.get_by_role("button", name="Settings", exact=True).click()
                page.locator("#rewards-enabled").check()
                page.locator("#daily-goal").select_option("3")
                page.get_by_role("button", name="Save", exact=True).click()
                expect(page.locator("#settings-msg")).to_contain_text("Settings saved")
                page.get_by_role("button", name="Now", exact=True).click()
                page.locator("#next-card").get_by_role("button", name="Done", exact=True).click()
                expect(page.get_by_role("button", name="Choose a task", exact=True)).to_be_visible()
                page.get_by_role("button", name="Progress", exact=True).click()
                expect(page.locator("#reward-level")).to_contain_text("30 XP")
                expect(page.locator("#daily-progress")).to_have_attribute("value", "3")
                expect(page.locator("#rank-name")).to_have_text("Seedling")
                expect(page.locator("#badges .earned")).to_have_count(1)
                page.get_by_role("button", name="Share progress", exact=True).click()
                expect(page.locator("#share-dialog")).to_be_visible()
                assert "30 XP" in page.locator("#share-text").input_value()
                assert "https://github.com/uniskela/adhd-hub" in page.locator("#share-text").input_value()
                assert base not in page.locator("#share-text").input_value()
                assert "my-website" not in page.locator("#share-text").input_value()
                assert "Write the first sentence" not in page.locator("#share-text").input_value()
                with page.expect_download() as download:
                    page.get_by_role("button", name="Download PNG", exact=True).click()
                download.value.save_as(str(screenshots / "progress-card.png"))
                assert (screenshots / "progress-card.png").read_bytes().startswith(b"\x89PNG")
                page.get_by_role("button", name="Copy text", exact=True).click()
                expect(page.locator("#share-msg")).to_contain_text(
                    re.compile(r"copied|Select and copy")
                )
                page.keyboard.press("Escape")
                expect(
                    page.get_by_role("button", name="Share progress", exact=True)
                ).to_be_focused()
                page.screenshot(path=str(screenshots / "progress-dark.png"), full_page=True)
                page.get_by_role("button", name="Settings", exact=True).click()
                expect(page.get_by_role("tab", name="Preferences", exact=True)).to_have_attribute(
                    "aria-selected", "true"
                )
                page.get_by_role("tab", name="Preferences", exact=True).focus()
                page.keyboard.press("ArrowRight")
                expect(page.get_by_role("tab", name="Account", exact=True)).to_be_focused()
                page.keyboard.press("End")
                expect(page.locator("#settings-data")).to_be_visible()
                page.keyboard.press("Home")
                expect(page.locator("#settings-preferences")).to_be_visible()
                with urlopen(base + "/api/health", timeout=10) as response:
                    installed_version = json.load(response)["version"]
                expect(page.locator("#app-version")).to_have_text("v" + installed_version)
                expect(page.locator("#repo-link")).to_have_attribute("href", "https://github.com/uniskela/adhd-hub")
                page.locator("#settings-preferences [data-theme-value=\"light\"]").click()
                expect(page.locator("html")).to_have_attribute("data-theme", "light")
                page.screenshot(path=str(screenshots / "settings-light.png"), full_page=True)
                page.locator("#settings-preferences [data-theme-value=\"dark\"]").click()
                page.get_by_role("tab", name="Agents & install", exact=True).click()
                expect(page.locator("#install-cmd")).to_be_visible()
                expect(page.get_by_role("button", name="Allow this CLI", exact=True)).to_be_visible()
                page.get_by_role("tab", name="Windows / MCP", exact=True).click()
                expect(page.locator("#mcp-url")).to_be_visible()
                page.get_by_role("tab", name="OpenClaw", exact=True).click()
                page.locator("#oc_webhook_url").fill("http://openclaw:18789/hooks/wake")
                page.locator("#oc_token").fill("browser-smoke-secret")
                page.get_by_role("button", name="Save OpenClaw", exact=True).click()
                expect(page.locator("#openclaw-msg")).to_contain_text("saved")
                expect(page.locator("#oc_token")).to_have_value("")
                expect(page.locator("#oc_token_status")).to_contain_text("saved")
                page.screenshot(path=str(screenshots / "settings-connections.png"), full_page=True)
                page.get_by_role("button", name="Now", exact=True).click()
                expect(page.locator("#now-view")).to_be_visible()

                page.get_by_role("button", name="Settings", exact=True).click()
                page.locator("#rewards-enabled").uncheck()
                page.get_by_role("button", name="Now", exact=True).click()
                page.reload()
                page.get_by_role("button", name="Progress", exact=True).click()
                expect(page.locator("#rewards-panel")).to_be_hidden()
                page.get_by_role("button", name="Now", exact=True).click()
                page.get_by_role("button", name="Help me choose", exact=True).click()
                page.get_by_role("button", name="Choose this", exact=True).click()
                page.evaluate("localStorage.setItem(\"adhd_hub_theme\", \"light\")"); page.reload()
                page.screenshot(
                    path=str(screenshots / "dashboard-light.png"),
                    full_page=True,
                    animations="disabled",
                )
                page.evaluate("localStorage.setItem(\"adhd_hub_theme\", \"dark\")"); page.reload()
                page.screenshot(
                    path=str(screenshots / "dashboard-dark.png"),
                    full_page=True,
                    animations="disabled",
                )
                page.screenshot(
                    path=str(screenshots / "dashboard-dark-preview.png"), animations="disabled"
                )
                page.get_by_role("button", name="My work", exact=True).click()
                # Project editing lives beside the title and opens as a focused dialog.
                page.locator('#project-list [data-slug="my-website"]').click()
                expect(page.locator("#btn-edit-project")).to_be_visible()
                expect(page.locator("#btn-open-project-repo")).to_have_attribute(
                    "href", "https://github.com/example/my-website"
                )
                page.locator("#btn-edit-project").click()
                expect(page.locator("#project-dialog")).to_be_visible()
                expect(page.locator("#p_title")).to_be_visible()
                expect(page.locator("#p_repo_url")).to_have_value(
                    "https://github.com/example/my-website"
                )
                page.screenshot(path=str(screenshots / "project-edit-dialog.png"))
                page.locator("#btn-close-project").click()
                page.get_by_role("button", name="All projects", exact=True).click()
                expect(page.locator("#threads .thread-project").first).to_be_visible()
                expect(page.locator("#threads .thread-status").first).to_have_text("Ready")
                expect(page.get_by_role("button", name="Choose this step").first).to_be_visible()
                page.screenshot(path=str(screenshots / "my-work-dense-list.png"), full_page=True)
                # Deliver project A after B; B must remain selected and editable.
                held = []

                def hold_project(route):
                    held.append((route, route.fetch()))

                page.route("**/api/projects/my-website", hold_project)
                page.locator('#project-list [data-slug="my-website"]').click()
                expect(page.locator("#work-title")).to_have_text("Loading project…")
                expect(page.locator("#btn-edit-project")).to_be_hidden()
                page.locator('#project-list [data-slug="learning"]').click()
                expect(page.locator("#work-title")).to_have_text("Learning corner")
                assert held
                with page.expect_response("**/api/projects/my-website") as delivered:
                    held[0][0].fulfill(response=held[0][1])
                delivered.value.body()
                page.evaluate(
                    "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
                )
                expect(page.locator("#work-title")).to_have_text("Learning corner")
                page.locator("#btn-edit-project").click()
                expect(page.locator("#p_slug")).to_have_value("learning")
                page.locator("#btn-close-project").click()
                page.unroute("**/api/projects/my-website", hold_project)
                page.route(
                    "**/api/projects/my-website",
                    lambda route: route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"detail":"Temporary test failure"}',
                    ),
                )
                page.locator('#project-list [data-slug="my-website"]').click()
                expect(page.locator("#work-title")).to_have_text("Project unavailable")
                expect(page.locator("#btn-edit-project")).to_be_hidden()
                page.unroute("**/api/projects/my-website")
                page.get_by_role("button", name="All projects", exact=True).click()
                page.get_by_role("button", name="Now", exact=True).click()
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(
                    path=str(screenshots / "dashboard-mobile.png"),
                    full_page=True,
                    animations="disabled",
                )
                page.get_by_role("button", name="Settings", exact=True).click()
                for name in [
                    "Preferences",
                    "Account",
                    "Agents & install",
                    "Windows / MCP",
                    "OpenClaw",
                    "Forge",
                    "Data",
                ]:
                    page.get_by_role("tab", name=name, exact=True).click()
                    assert page.locator("#settings-view").evaluate(
                        "el => el.scrollWidth <= el.clientWidth"
                    )
                    expect(page.locator("#btn-settings-index-back")).to_be_in_viewport()
                    page.locator("#btn-settings-index-back").click()
                page.get_by_role("tab", name="Preferences", exact=True).click()
                page.locator("#rewards-enabled").check()
                page.screenshot(path=str(screenshots / "settings-mobile.png"), full_page=True)
                page.get_by_role("button", name="Now", exact=True).click()
                page.get_by_role("button", name="Progress", exact=True).click()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(screenshots / "progress-mobile.png"), full_page=True)
                page.get_by_role("button", name="Settings", exact=True).click()
                page.get_by_role("tab", name="Account", exact=True).click()
                page.get_by_role("button", name="Log out", exact=True).click()
                page.reload()
                expect(page.locator("#login-gate")).to_be_visible()
                # Denied storage must not prevent password sign-in or theme changes.
                isolated = browser.new_context(color_scheme="dark")
                blocked = isolated.new_page()
                blocked.on("pageerror", lambda error: errors.append(str(error)))
                blocked.add_init_script("""Object.defineProperty(window, 'localStorage', {
                    get() { throw new DOMException('Storage denied', 'SecurityError'); }
                });""")
                blocked.goto(base + "/ui")
                expect(blocked.locator("#login-gate")).to_be_visible()
                expect(blocked.locator("html")).to_have_attribute("data-theme", "dark")
                blocked.locator("#login-token").fill(password)
                blocked.get_by_role("button", name="Sign in", exact=True).click()
                expect(blocked.locator("#app-shell")).to_be_visible()
                expect(blocked.locator("#now-view")).to_be_visible()
                blocked.locator("#appearance-menu").get_by_text("Appearance", exact=True).click(); blocked.locator("#appearance-menu [data-theme-value=\"light\"]").click()
                expect(blocked.locator("html")).to_have_attribute("data-theme", "light")
                blocked.get_by_role("button", name="Settings", exact=True).click()
                blocked.locator("#rewards-enabled").uncheck()
                blocked.keyboard.press("Escape")
                expect(blocked.locator("#rewards-panel")).to_be_hidden()
                isolated.close()
                assert not errors, errors
                browser.close()
                print(
                    "PASS: password setup/login, themes/system preference, rewards, Now/My work/Progress, Markdown, pause/resume, capture, search, mobile, settings tabs/keyboard/close, ranks/badges, PNG download, private share text, logout, delayed requests, denied storage; no JS errors"
                )
                print(f"Screenshots: {screenshots}")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
