"""Smoke-test the built Zensical docs at desktop and mobile sizes."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    site = root / "site"
    if not (site / "index.html").exists():
        raise SystemExit("Build docs first: uv run zensical build --clean")
    shots = Path(os.environ.get("ADHD_HUB_DOCS_SCREENSHOT_DIR", "/tmp/adhd-hub-docs-preview"))
    shots.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=site)
    try:
        time.sleep(0.7)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            page.goto(f"http://127.0.0.1:{port}/")
            expect(page.locator("article h1")).to_contain_text("ADHD Progress Hub")
            expect(page.get_by_text("Work → Save continuity → Leave → Come back → Resume", exact=False)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            measure = page.locator(".md-content__inner").evaluate("el => el.getBoundingClientRect().width")
            assert 500 <= measure <= 900, measure
            page.screenshot(path=str(shots / "docs-home-desktop.png"), full_page=True, animations="disabled")
            page.goto(f"http://127.0.0.1:{port}/dashboard/")
            expect(page.locator("article h1")).to_contain_text("A calmer dashboard")
            page.screenshot(path=str(shots / "docs-dashboard-desktop.png"), full_page=True, animations="disabled")
            page.set_viewport_size({"width": 390, "height": 844})
            page.goto(f"http://127.0.0.1:{port}/")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(shots / "docs-home-mobile.png"), full_page=True, animations="disabled")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
