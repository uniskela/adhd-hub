from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

UI_DIR = Path(__file__).resolve().parent
JS_DIR = UI_DIR / "js"

# Allowlisted ES modules under /ui/js/
UI_JS_MODULES = {
    "state.js",
    "dom.js",
    "api.js",
    "auth.js",
    "theme.js",
    "screens.js",
    "now.js",
    "work.js",
    "progress.js",
    "settings.js",
    "load.js",
    "boot.js",
}
UI_JS_ASSETS = {module: (JS_DIR / module).resolve() for module in UI_JS_MODULES}


def build_ui_router() -> APIRouter:
    router = APIRouter()

    @router.get("/ui")
    def ui_root():
        # Trailing slash so the PWA service worker scope `/ui/` covers the document.
        return RedirectResponse(url="/ui/", status_code=301)

    @router.get("/ui/", response_class=HTMLResponse)
    def ui_home():
        return FileResponse(UI_DIR / "index.html")

    @router.get("/ui/app.css")
    def ui_css():
        return FileResponse(UI_DIR / "app.css", media_type="text/css")

    @router.get("/ui/app.js")
    def ui_js_legacy():
        # Monolith replaced by ES modules; keep old URL working.
        return RedirectResponse(url="/ui/js/boot.js", status_code=307)

    @router.get("/ui/js/{name}")
    def ui_js_module(name: str):
        path = UI_JS_ASSETS.get(name)
        if path is None:
            raise HTTPException(404, "Asset not found")
        if not path.is_file():
            raise HTTPException(404, "Asset not found")
        return FileResponse(path, media_type="text/javascript")

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
        brand_dir = (UI_DIR / "brand").resolve()
        allowed = {
            "icon.svg": (brand_dir / "icon.svg", "image/svg+xml"),
            "logo.svg": (brand_dir / "logo.svg", "image/svg+xml"),
            "logo-dark.svg": (brand_dir / "logo-dark.svg", "image/svg+xml"),
            "icon-192.png": (brand_dir / "icon-192.png", "image/png"),
            "icon-512.png": (brand_dir / "icon-512.png", "image/png"),
        }
        asset = allowed.get(name)
        if asset is None:
            raise HTTPException(404, "Asset not found")
        asset_path, media_type = asset
        if not asset_path.is_file():
            raise HTTPException(404, "Asset not found")
        return FileResponse(asset_path, media_type=media_type)

    return router
