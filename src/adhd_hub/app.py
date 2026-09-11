from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from adhd_hub import __version__
from adhd_hub.api import build_router
from adhd_hub.auth import auth_dependency, build_auth_router
from adhd_hub.config import Settings, load_settings
from adhd_hub.connect import render_install_ps1, render_install_sh
from adhd_hub.connect_auth import ConnectStore, bearer_authorized, build_connect_router
from adhd_hub.mcp_app import build_mcp
from adhd_hub.package_dist import find_cli_wheel
from adhd_hub.scheduler import start_scheduler
from adhd_hub.service import HubService
from adhd_hub.sessions import BrowserSessions
from adhd_hub.ui import build_ui_router

log = logging.getLogger(__name__)


class MCPPathRewriteMiddleware:
    """Rewrite POST /mcp → /mcp/ in-process (no 307). Starlette Mount needs the slash."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            if "raw_path" in scope:
                scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


class BearerGateMiddleware(BaseHTTPMiddleware):
    """Require bearer token for /mcp when auth_token is not the default."""

    def __init__(self, app: ASGIApp, settings: Settings, connect_store: ConnectStore) -> None:
        super().__init__(app)
        self.settings = settings
        self.connect_store = connect_store

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(("/mcp", "/messages")):
            expected = self.settings.auth_token
            if expected and expected != "change-me":
                auth = request.headers.get("authorization", "")
                scheme, _, value = auth.partition(" ")
                if scheme.lower() != "bearer" or not bearer_authorized(
                    self.settings, self.connect_store, value
                ):
                    return JSONResponse(
                        {"detail": "Unauthorized"},
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )
        response = await call_next(request)
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    if settings.auth_token in {"", "change-me"} and settings.host not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise ValueError(
            "Set ADHD_HUB_AUTH_TOKEN to a strong token before binding to a network interface"
        )
    settings.ensure_dirs()
    service = HubService(settings)
    mcp = build_mcp(service)

    # Build MCP ASGI app early so session_manager exists for lifespan
    mcp_asgi = mcp.streamable_http_app(
        streamable_http_path="/",
        host=settings.host,
        json_response=True,
        stateless_http=True,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        scheduler = start_scheduler(service)
        try:
            async with mcp.session_manager.run():
                log.info("ADHD Hub ready on %s:%s", settings.host, settings.port)
                yield
        finally:
            scheduler.shutdown(wait=False)

    app = FastAPI(
        title="ADHD Progress Hub",
        version=__version__,
        lifespan=lifespan,
        # POST /mcp must not 307 to /mcp/ — Cursor drops tools on redirect.
        redirect_slashes=False,
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/auth/"):
            # FastAPI's default errors include the submitted input (even passwords).
            return JSONResponse(
                {
                    "detail": [
                        {
                            "loc": error["loc"],
                            "type": error["type"],
                            "msg": "Invalid credential field",
                        }
                        for error in exc.errors()
                    ]
                },
                status_code=422,
                headers={"Cache-Control": "no-store"},
            )
        return await request_validation_exception_handler(request, exc)

    app.state.settings = settings
    app.state.service = service
    app.state.mcp = mcp

    sessions = BrowserSessions(settings.data_dir / "browser_sessions.sqlite3")
    connect_store = ConnectStore(settings.data_dir / "connect.sqlite3")
    app.state.sessions = sessions
    app.state.connect_store = connect_store
    app.include_router(build_auth_router(settings, sessions))
    app.include_router(build_connect_router(settings, sessions, connect_store))
    auth_dep = auth_dependency(settings, sessions, connect_store)
    app.include_router(build_router(service, auth_dep), prefix="/api")
    app.include_router(build_ui_router())
    app.add_middleware(
        BearerGateMiddleware, settings=settings, connect_store=connect_store
    )
    app.add_middleware(MCPPathRewriteMiddleware)

    # Only an explicitly configured public URL may make cross-origin requests.
    # The browser sends the bearer token in a header, so no credentialed-cookie
    # CORS mode or wildcard origin is needed.
    public_url = settings.resolve_public_url()
    if public_url:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[public_url],
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Hub-Request", "X-Backup-Passphrase"],
        )

    # Trailing-slash mount is what Starlette expects for the sub-app root.
    app.mount("/mcp/", mcp_asgi)

    @app.get("/")
    def root():
        return {
            "name": "adhd-hub",
            "docs": "/docs",
            "ui": "/ui/",
            "health": "/api/health",
            "mcp": "/mcp",
            "install": "/install.sh",
            "install_sh": "/install.sh",
            "install_ps1": "/install.ps1",
            "install_wheel": "/install/adhd-hub.whl",
            "install_wheel_url": "/install/cli-wheel.url",
            "hint": (
                "Open /ui/ for the dashboard. MCP at /mcp with Authorization Bearer token. "
                "Connect a CLI without exporting the server token: "
                "macOS/Linux: curl -fsSL <hub>/install.sh | sh -s -- . "
                "Windows: irm <hub>/install.ps1 | iex"
            ),
        }

    def _install_hub_base(request: Request) -> str:
        configured = settings.resolve_public_url()
        if configured:
            return configured
        return str(request.base_url).rstrip("/")

    def _wheel_or_404():
        wheel = find_cli_wheel()
        if wheel is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "CLI wheel not packaged with this Hub. "
                    "Rebuild the Docker image, or: uv tool install "
                    "git+https://github.com/uniskela/adhd-hub.git"
                ),
            )
        return wheel

    @app.get("/install.sh", response_class=PlainTextResponse)
    def install_sh(request: Request):
        """Public POSIX bootstrap — never embeds auth tokens."""
        prefs = service.prefs()
        script = render_install_sh(
            _install_hub_base(request),
            default_agents=prefs.connect_agents_csv(),
            with_i_have_adhd=prefs.companion_enabled("i-have-adhd"),
            with_graphify=prefs.companion_enabled("graphify"),
            with_rtk=prefs.companion_enabled("rtk"),
        )
        return PlainTextResponse(script, media_type="text/x-shellscript")

    @app.get("/install.ps1", response_class=PlainTextResponse)
    def install_ps1(request: Request):
        """Public Windows PowerShell bootstrap — never embeds auth tokens."""
        prefs = service.prefs()
        script = render_install_ps1(
            _install_hub_base(request),
            default_agents=prefs.connect_agents_csv(),
            with_i_have_adhd=prefs.companion_enabled("i-have-adhd"),
            with_graphify=prefs.companion_enabled("graphify"),
            with_rtk=prefs.companion_enabled("rtk"),
        )
        return PlainTextResponse(script, media_type="text/plain")

    @app.get("/install/cli-wheel.url", response_class=PlainTextResponse)
    def install_cli_wheel_url(request: Request):
        """Plain-text absolute URL to a PEP 427-named wheel (for uvx --from)."""
        wheel = _wheel_or_404()
        base = _install_hub_base(request)
        return PlainTextResponse(f"{base}/install/wheels/{wheel.name}\n")

    @app.api_route("/install/adhd-hub.whl", methods=["GET", "HEAD"])
    def install_wheel_alias(request: Request):
        """Stable alias → redirect to a PEP 427-valid wheel filename for uvx."""
        wheel = _wheel_or_404()
        return RedirectResponse(
            url=f"/install/wheels/{wheel.name}",
            status_code=302,
        )

    @app.api_route("/install/wheels/{name}", methods=["GET", "HEAD"])
    def install_wheel_named(name: str, request: Request):
        """Serve the Hub CLI wheel under its real PEP 427 filename."""
        wheel = _wheel_or_404()
        if name != wheel.name:
            raise HTTPException(status_code=404, detail="Unknown wheel name")
        if request.method == "HEAD":
            return Response(
                status_code=200,
                media_type="application/zip",
                headers={
                    "content-length": str(wheel.stat().st_size),
                    "content-disposition": f'attachment; filename="{wheel.name}"',
                },
            )
        return FileResponse(
            wheel,
            media_type="application/zip",
            filename=wheel.name,
        )

    return app
