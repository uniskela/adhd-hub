from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

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
        return FileResponse(UI_DIR / "app.js", media_type="application/javascript")

    @router.get("/ui/manifest.webmanifest")
    def ui_manifest():
        return FileResponse(
            UI_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    @router.get("/ui/sw.js")
    def ui_sw():
        # Scope must cover /ui/; Service-Worker-Allowed lets SW live under /ui/.
        return Response(
            (UI_DIR / "sw.js").read_text(encoding="utf-8"),
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/ui/"},
        )

    @router.get("/ui/brand/{name}")
    def brand_asset(name: str):
        allowed = {
            "icon.svg": "image/svg+xml",
            "logo.svg": "image/svg+xml",
            "logo-dark.svg": "image/svg+xml",
            "icon-192.png": "image/png",
            "icon-512.png": "image/png",
        }
        if name not in allowed:
            raise HTTPException(404, "Asset not found")
        return FileResponse(UI_DIR / "brand" / name, media_type=allowed[name])

    return router
