from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

UI_DIR = Path(__file__).resolve().parent


def build_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get("/ui", response_class=HTMLResponse)
    @router.get("/ui/", response_class=HTMLResponse)
    def ui_home():
        return FileResponse(UI_DIR / "index.html")

    @router.get("/ui/app.css")
    def ui_css():
        return FileResponse(UI_DIR / "app.css", media_type="text/css")

    @router.get("/ui/app.js")
    def ui_js():
        return FileResponse(
            UI_DIR / "app.js", media_type="application/javascript"
        )

    return router
