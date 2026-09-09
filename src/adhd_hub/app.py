from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from adhd_hub import __version__
from adhd_hub.api import build_router
from adhd_hub.auth import BrowserSessions, auth_dependency, build_auth_router, token_matches
from adhd_hub.config import Settings, load_settings
from adhd_hub.mcp_app import build_mcp
from adhd_hub.scheduler import start_scheduler
from adhd_hub.service import HubService
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

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(("/mcp", "/messages")):
            expected = self.settings.auth_token
            if expected and expected != "change-me":
                auth = request.headers.get("authorization", "")
                scheme, _, value = auth.partition(" ")
                if scheme.lower() != "bearer" or not token_matches(self.settings, value):
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

    sessions = BrowserSessions()
    app.include_router(build_auth_router(settings, sessions))
    auth_dep = auth_dependency(settings, sessions)
    app.include_router(build_router(service, auth_dep), prefix="/api")
    app.include_router(build_ui_router())
    app.add_middleware(BearerGateMiddleware, settings=settings)
    app.add_middleware(MCPPathRewriteMiddleware)

    # Trailing-slash mount is what Starlette expects for the sub-app root.
    app.mount("/mcp/", mcp_asgi)

    @app.get("/")
    def root():
        return {
            "name": "adhd-hub",
            "docs": "/docs",
            "ui": "/ui",
            "health": "/api/health",
            "mcp": "/mcp",
            "hint": "Open /ui for the dashboard. MCP at /mcp with Authorization Bearer token.",
        }

    return app
