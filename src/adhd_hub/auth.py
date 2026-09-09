from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from adhd_hub.config import Settings
from adhd_hub.passwords import PasswordStore

_bearer = HTTPBearer(auto_error=False)
COOKIE_NAME = "adhd_hub_session"
SESSION_SECONDS = 12 * 60 * 60


def token_matches(settings: Settings, value: str) -> bool:
    return secrets.compare_digest(value.encode(), settings.auth_token.encode())


def require_auth(
    settings: Settings,
    credentials: HTTPAuthorizationCredentials | None,
) -> None:
    # Default-token development mode is restricted to a loopback bind at startup.
    if (
        settings.auth_token in {"", "change-me"}
        and credentials is None
        and not PasswordStore(settings.data_dir).configured
    ):
        return
    if credentials is None or not token_matches(settings, credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@dataclass
class BrowserSessions:
    """Short-lived opaque sessions; restart and logout invalidate browser access."""

    tokens: dict[str, float] = field(default_factory=dict)

    def create(self) -> str:
        now = time.monotonic()
        self.tokens = {key: expiry for key, expiry in self.tokens.items() if expiry > now}
        if len(self.tokens) >= 1024:
            del self.tokens[next(iter(self.tokens))]
        token = secrets.token_urlsafe(32)
        self.tokens[token] = now + SESSION_SECONDS
        return token

    def valid(self, token: str | None) -> bool:
        return self.tokens.get(token or "", 0) > time.monotonic()


def require_browser_request(request: Request) -> None:
    # A cross-origin form cannot set this header; no permissive CORS is installed.
    if request.headers.get("x-hub-request") != "1":
        raise HTTPException(403, "Missing browser request header")
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Cross-origin request rejected")


def auth_dependency(settings: Settings, sessions: BrowserSessions):
    async def _dep(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Security(_bearer),  # noqa: B008
    ) -> None:
        if credentials is None and sessions.valid(request.cookies.get(COOKIE_NAME)):
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                require_browser_request(request)
            return
        require_auth(settings, credentials)

    return _dep


@dataclass
class LoginThrottle:
    attempts: dict[str, list[float]] = field(default_factory=dict)

    def check(self, key: str) -> None:
        now = time.monotonic()
        self.attempts = {
            key: [stamp for stamp in stamps if stamp > now - 60]
            for key, stamps in self.attempts.items()
            if stamps[-1] > now - 60
        }
        stamps = self.attempts.get(key, [])
        if len(stamps) >= 5:
            retry = max(1, int(61 - (now - stamps[0])))
            raise HTTPException(
                429,
                "Too many attempts. Try again in a minute.",
                headers={"Retry-After": str(retry)},
            )
        if key not in self.attempts and len(self.attempts) >= 2048:
            raise HTTPException(
                429, "Sign-in is busy. Try again in a minute.", headers={"Retry-After": "60"}
            )
        self.attempts[key] = [*stamps, now]


class LoginRequest(BaseModel):
    token: str | None = Field(default=None, min_length=1, max_length=4096)
    password: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def one_credential(self):
        if (self.token is None) == (self.password is None):
            raise ValueError("Supply a password or an access token")
        return self


class PasswordRequest(BaseModel):
    current_secret: str = Field(min_length=1, max_length=4096)
    current_method: Literal["password", "token"] = "password"
    password: str = Field(min_length=12, max_length=1024)


def build_auth_router(settings: Settings, sessions: BrowserSessions) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["Browser login"])
    passwords = PasswordStore(settings.data_dir)
    throttle = LoginThrottle()
    credential_lock = asyncio.Lock()

    def client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def set_session(request: Request, response: Response) -> None:
        sessions.tokens.pop(request.cookies.get(COOKIE_NAME, ""), None)
        response.set_cookie(
            COOKIE_NAME,
            sessions.create(),
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=SESSION_SECONDS,
            path="/api",
        )
        response.headers["Cache-Control"] = "no-store"

    async def verify_password(value: str) -> bool:
        try:
            return await run_in_threadpool(passwords.verify, value)
        except (OSError, ValueError):
            raise HTTPException(
                503, "Password sign-in is unavailable. Use your access token to reset it."
            ) from None

    @router.get("/status")
    async def auth_status():
        return {
            "password_configured": passwords.configured,
            "development_mode": settings.auth_token in {"", "change-me"},
            "session_hours": SESSION_SECONDS // 3600,
        }

    @router.post("/login")
    async def login(payload: LoginRequest, request: Request, response: Response):
        require_browser_request(request)
        key = client_key(request)
        throttle.check(key)
        async with credential_lock:
            valid = (
                token_matches(settings, payload.token)
                if payload.token is not None
                else await verify_password(payload.password)
            )
            if not valid:
                raise HTTPException(401, "That sign-in was not accepted. Please try again.")
            throttle.attempts.pop(key, None)
            set_session(request, response)
        return {"authenticated": True, "expires_in": SESSION_SECONDS}

    @router.put("/password")
    async def save_password(payload: PasswordRequest, request: Request, response: Response):
        require_browser_request(request)
        key = client_key(request)
        throttle.check(key)
        if settings.auth_token in {"", "change-me"}:
            raise HTTPException(
                409, "Set a private ADHD_HUB_AUTH_TOKEN on the server before creating a password."
            )
        async with credential_lock:
            valid = (
                token_matches(settings, payload.current_secret)
                if payload.current_method == "token"
                else await verify_password(payload.current_secret)
            )
            if not valid:
                raise HTTPException(401, "Current password or recovery token was not accepted.")
            if token_matches(settings, payload.password):
                raise HTTPException(
                    400, "Choose a dashboard password different from your access token."
                )
            await run_in_threadpool(passwords.save, payload.password)
            throttle.attempts.pop(key, None)
            sessions.tokens.clear()
            set_session(request, response)
        return {"password_configured": True, "other_sessions_revoked": True}

    @router.post("/logout", status_code=204)
    async def logout(request: Request, response: Response):
        require_browser_request(request)
        sessions.tokens.pop(request.cookies.get(COOKIE_NAME, ""), None)
        response.delete_cookie(COOKIE_NAME, path="/api")
        response.headers["Cache-Control"] = "no-store"

    return router
