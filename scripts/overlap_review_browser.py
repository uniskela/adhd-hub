"""Browser check for Possible overlap. Mocks the merge API so the UI can run first.

Run: uv run --with playwright python scripts/overlap_review_browser.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    token = "overlap-review-token"
    posts: list[tuple[str, str]] = []
    mode = {"suggestions": "hits", "approve": "stale"}

    def seed(path: str, payload: dict) -> dict:
        request = Request(
            base + "/api" + path,
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    with tempfile.TemporaryDirectory(prefix="adhd-hub-overlap-") as data:
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
            open_thread = seed(
                "/threads",
                {
                    "summary": "Ship DNS cutover",
                    "project_slug": "dns",
                    "goal": "Ship DNS cutover",
                    "focus": "Review source checklist",
                    "next_steps": ["source step 1", "source step 2", "source step 3"],
                    "resume_step": "Open source cutover log",
                    "source_tool": "cursor",
                },
            )
            other = {
                **open_thread,
                "id": "target",
                "focus": "Review target checklist",
                "next_steps": ["target step 1", "target step 2", "target step 3"],
                "resume_step": "Open target cutover log",
                "source_tool": "codex",
            }
            blocked = {
                **other,
                "id": "docs",
                "summary": "Document DNS cutover",
                "goal": "Document DNS cutover",
            }
            suggestions = {
                "thread_id": open_thread["id"],
                "query": "Ship DNS cutover",
                "hits": [
                    {
                        "thread": other,
                        "score": 1.15,
                        "reason": "token_overlap=0.30; goal_in_query; title_in_query",
                        "outcome": "same_outcome",
                        "evidence": ["goal_exact_match", "same_project"],
                        "merge_allowed": True,
                        "merge_blocked_reason": None,
                    },
                    {
                        "thread": blocked,
                        "score": 0.4,
                        "reason": "token_overlap=0.40",
                        "outcome": "related",
                        "evidence": ["distinct_known_goal", "same_project"],
                        "merge_allowed": False,
                        "merge_blocked_reason": "distinct_outcomes",
                    },
                ],
                "alternatives": ["review_separately", "link_in_progress_note"],
            }

            def fulfill(route, status: int, payload: dict) -> None:
                route.fulfill(
                    status=status,
                    content_type="application/json",
                    body=json.dumps(payload),
                )

            def handle(route) -> None:
                path = urlparse(route.request.url).path
                method = route.request.method
                if method == "GET" and path.endswith("/duplicates"):
                    if mode["suggestions"] == "error":
                        fulfill(route, 500, {"detail": "unavailable"})
                        return
                    body = dict(suggestions)
                    if mode["suggestions"] == "empty":
                        body["hits"] = []
                    fulfill(route, 200, body)
                    return
                if method == "GET" and path.endswith("/threads/target"):
                    fulfill(route, 200, {**other, "progress_html": "<p>Target notes stay here.</p>"})
                    return
                if method == "POST" and path.endswith("/merge"):
                    posts.append(("merge", route.request.post_data or ""))
                    fulfill(
                        route,
                        200,
                        {
                            "pending": True,
                            "merge_allowed": True,
                            "action": {
                                "id": "merge-action",
                                "kind": "merge_threads",
                                "payload": {"source": other, "target": open_thread},
                            },
                            "message": "Awaiting human approval via pending-actions. No thread changed.",
                        },
                    )
                    return
                if method == "POST" and path.endswith("/approve"):
                    posts.append(("approve", route.request.post_data or ""))
                    if mode["approve"] == "stale":
                        fulfill(route, 409, {"detail": "merge_preview_stale: review and request a new merge"})
                        return
                    fulfill(
                        route,
                        200,
                        {
                            "approved": True,
                            "result": {
                                "source_thread_id": "target",
                                "target_thread_id": open_thread["id"],
                                "history_preserved": True,
                                "remote_changed": False,
                            },
                        },
                    )
                    return
                if method == "POST" and path.endswith("/reject"):
                    posts.append(("reject", route.request.post_data or ""))
                    fulfill(route, 200, {"rejected": True})
                    return
                if method == "GET" and path.endswith("/merge-history"):
                    fulfill(
                        route,
                        200,
                        {
                            "thread_id": open_thread["id"],
                            "items": [
                                {
                                    "thread": {**other, "status": "dismissed", "merged_into": open_thread["id"]},
                                    "notes": [{"content": "source cutover decision", "thread_id": "target"}],
                                    "events": [],
                                }
                            ],
                            "limit_per_thread": 50,
                        },
                    )
                    return
                route.fallback()

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=os.environ.get("ADHD_HUB_BROWSER_EXECUTABLE") or None,
                    args=["--no-sandbox"],
                )
                page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
                page.route("**/api/**", handle)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/ui/")
                page.locator("#login-token").fill(token)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.locator("#app-shell")).to_be_visible()
                page.get_by_role("button", name="My work", exact=True).click()
                page.locator("#threads .thread").first.click()
                expect(page.locator("#notes-reader")).to_be_visible()
                expect(page.locator("#btn-overlap-cue")).to_be_visible()
                page.locator("#btn-overlap-cue").click()
                dialog = page.locator("#overlap-dialog")
                expect(dialog).to_be_visible()
                expect(dialog).to_contain_text("Looking does not change either step.")
                expect(dialog).to_contain_text("Finishable goal")
                expect(dialog).to_contain_text("The finishable goals match.")
                expect(dialog).to_contain_text("The goals are different.")
                expect(dialog.get_by_role("button", name="Review a safe merge")).to_have_count(1)
                assert posts == [], posts
                kept = client_status(base, token, open_thread["id"])
                assert kept["status"] == "open"
                assert not kept.get("merged_into")

                dialog.locator("article.overlap-hit", has_text="Document DNS cutover").get_by_role(
                    "button", name="Hide this suggestion"
                ).click()
                expect(dialog).not_to_contain_text("Document DNS cutover")
                assert posts == [], posts

                dialog.get_by_role("button", name="Look at this step").click()
                expect(dialog).to_be_hidden()
                expect(page.locator("#notes-reader-meta")).to_contain_text("Codex")
                expect(page.locator("#notes-reader-body")).to_contain_text("Target notes stay here.")
                assert posts == [], posts

                page.locator("#threads .thread").first.click()
                page.locator("#notes-reader-menu > summary").click()
                page.locator("#btn-notes-overlap").click()
                expect(dialog).to_contain_text("Review a safe merge")
                dialog.get_by_role("button", name="Review a safe merge").click()
                expect(dialog).to_contain_text("Nothing is combined until you confirm.")
                expect(dialog).to_contain_text("The active step keeps its focus")
                expect(dialog).to_contain_text("target step 1")
                expect(dialog).to_contain_text("source step 1")
                assert posts == [], posts
                dialog.get_by_role("button", name="Leave both as they are").click()
                expect(dialog).to_contain_text("Review a safe merge")
                assert posts == [], posts

                dialog.get_by_role("button", name="Review a safe merge").click()
                dialog.get_by_role("button", name="Confirm merge").click()
                expect(dialog).to_contain_text("Nothing was merged.")
                assert [name for name, _body in posts] == ["merge", "approve"], posts
                assert json.loads(posts[0][1]) == {"target_thread_id": open_thread["id"]}
                assert json.loads(posts[1][1]) == {"confirm_merge": True}
                dialog.get_by_role("button", name="Set this preview aside").click()
                expect(dialog).to_contain_text("Both steps are unchanged.")
                assert posts[-1][0] == "reject"

                mode["approve"] = "ok"
                posts.clear()
                dialog.get_by_role("button", name="Try again").click()
                dialog.get_by_role("button", name="Review a safe merge").click()
                dialog.get_by_role("button", name="Confirm merge").click()
                expect(dialog).to_contain_text("Nothing outside this hub was changed.")
                assert [name for name, _body in posts] == ["merge", "approve"], posts
                dialog.get_by_role("button", name="Show retained notes").click()
                expect(dialog).to_contain_text("source cutover decision")

                mode["suggestions"] = "empty"
                dialog.locator("[data-overlap-action='close']").click()
                page.locator("#notes-reader-menu > summary").click()
                page.locator("#btn-notes-overlap").click()
                expect(dialog).to_contain_text("No other open steps look like this one.")

                mode["suggestions"] = "error"
                dialog.get_by_role("button", name="Look again").click()
                expect(dialog).to_contain_text("Nothing was changed.")

                page.set_viewport_size({"width": 390, "height": 844})
                mode["suggestions"] = "hits"
                dialog.get_by_role("button", name="Try again").click()
                expect(dialog).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                stacked = page.locator(".overlap-pair")
                dialog.get_by_role("button", name="Review a safe merge").click()
                expect(stacked).to_be_visible()
                columns = stacked.evaluate("el => getComputedStyle(el).gridTemplateColumns")
                assert " " not in columns.strip(), columns
                motion = dialog.evaluate("el => getComputedStyle(el).animationName")
                assert motion in ("none", ""), motion
                assert not errors, errors
                browser.close()
                print("PASS: overlap review loading, review, dismiss, confirm, stale, empty, error, mobile")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


def client_status(base: str, token: str, thread_id: str) -> dict:
    request = Request(
        base + "/api/threads/" + thread_id,
        headers={"Authorization": "Bearer " + token},
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


if __name__ == "__main__":
    main()
