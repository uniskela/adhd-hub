"""One-time OpenClaw pairing (device-code style) — no Hub auth token in OpenClaw.

Flow (single-owner Hub):
1. Operator starts a pair in the Hub UI (authenticated) → short user code.
2. OpenClaw submits webhook/agent URLs + its hook bearer token with that code
   (no ADHD_HUB_AUTH_TOKEN), or reports a safe structured provisioning failure.
3. Operator approves the submitted endpoints in the Hub UI → saved encrypted.

This is not OAuth; OpenClaw hooks have no callback contract. Pairing avoids
pasting long-lived Hub tokens into OpenClaw while keeping a human gate.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from adhd_hub.connect_auth import generate_user_code, normalize_user_code
from adhd_hub.openclaw_config import OpenClawConfig

PAIR_SECONDS = 15 * 60
PAIR_FAILURE_CODES = frozenset({"hooks_token_secretref_unsupported"})
PairStatus = Literal["none", "waiting", "submitted", "failed", "expired"]


@dataclass
class PairState:
    status: PairStatus
    user_code: str = ""
    expires_at: float = 0.0
    webhook_url: str = ""
    agent_url: str = ""
    token_present: bool = False
    submitted_at: float | None = None
    error_code: str = ""
    hub_origin: str = ""

    def public_dict(self) -> dict[str, Any]:
        remaining = max(0, int(self.expires_at - time.time())) if self.expires_at else 0
        out: dict[str, Any] = {
            "status": self.status,
            "user_code": self.user_code if self.status in {"waiting", "submitted"} else "",
            "expires_in": remaining if self.status in {"waiting", "submitted"} else 0,
            "webhook_url": self.webhook_url if self.status == "submitted" else "",
            "agent_url": self.agent_url if self.status == "submitted" else "",
            "token_present": self.token_present if self.status == "submitted" else False,
            "submitted_at": self.submitted_at if self.status == "submitted" else None,
        }
        if self.status == "failed":
            out["error_code"] = self.error_code
        if self.status in {"waiting", "submitted"} and self.hub_origin:
            out["prompt"] = openclaw_pair_prompt(
                hub_origin=self.hub_origin,
                user_code=self.user_code,
            )
        return out


def pair_path(data_dir: Path) -> Path:
    return data_dir / "openclaw_pair.json"


class OpenClawPairStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = pair_path(data_dir)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _save_raw(self, data: dict[str, Any] | None) -> None:
        if not data:
            if self._path.is_file():
                self._path.unlink(missing_ok=True)
            return
        self._path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def clear(self) -> None:
        self._save_raw(None)

    def status(self) -> PairState:
        raw = self._load_raw()
        if not raw:
            return PairState(status="none")
        expires_at = float(raw.get("expires_at") or 0)
        if expires_at and expires_at <= time.time():
            self.clear()
            return PairState(status="expired")
        phase = str(raw.get("phase") or "waiting")
        if phase == "submitted":
            return PairState(
                status="submitted",
                user_code=str(raw.get("user_code") or ""),
                expires_at=expires_at,
                webhook_url=str(raw.get("webhook_url") or ""),
                agent_url=str(raw.get("agent_url") or ""),
                token_present=bool(raw.get("token")),
                submitted_at=float(raw["submitted_at"]) if raw.get("submitted_at") else None,
                hub_origin=str(raw.get("hub_origin") or ""),
            )
        if phase == "failed":
            return PairState(
                status="failed",
                expires_at=expires_at,
                error_code=str(raw.get("error_code") or ""),
            )
        return PairState(
            status="waiting",
            user_code=str(raw.get("user_code") or ""),
            expires_at=expires_at,
            hub_origin=str(raw.get("hub_origin") or ""),
        )

    def start(self, *, hub_origin: str = "") -> PairState:
        current = self.status()
        if current.status == "submitted":
            raise ValueError(
                "pair_submitted_pending_approval — Approve or Cancel before starting a new pair"
            )
        code = generate_user_code()
        now = time.time()
        self._save_raw(
            {
                "phase": "waiting",
                "user_code": code,
                "expires_at": now + PAIR_SECONDS,
                "created_at": now,
                "hub_origin": str(hub_origin or "").rstrip("/"),
            }
        )
        return self.status()

    def fail(self, *, user_code: str, error_code: str) -> PairState:
        normalized = normalize_user_code(user_code)
        if not normalized:
            raise ValueError("invalid_user_code")
        raw = self._load_raw()
        if not raw:
            raise ValueError("no_active_pair")
        expires_at = float(raw.get("expires_at") or 0)
        if expires_at <= time.time():
            self.clear()
            raise ValueError("pair_expired")
        if normalize_user_code(str(raw.get("user_code") or "")) != normalized:
            raise ValueError("user_code_mismatch")
        if str(raw.get("phase") or "") != "waiting":
            raise ValueError("pair_not_waiting")
        if error_code not in PAIR_FAILURE_CODES:
            raise ValueError("invalid_pair_error_code")
        self._save_raw(
            {
                "phase": "failed",
                "user_code": normalized,
                "expires_at": expires_at,
                "created_at": raw.get("created_at", time.time()),
                "error_code": error_code,
            }
        )
        return self.status()

    def submit(
        self,
        *,
        user_code: str,
        webhook_url: str,
        agent_url: str = "",
        token: str,
        alerts_enabled: bool = True,
        stale_nudge_cron: str | None = None,
        stale_days: int | None = None,
        remind_cooldown_days: int | None = None,
        digest_max_nudge: int | None = None,
    ) -> PairState:
        normalized = normalize_user_code(user_code)
        if not normalized:
            raise ValueError("invalid_user_code")
        raw = self._load_raw()
        if not raw:
            raise ValueError("no_active_pair")
        expires_at = float(raw.get("expires_at") or 0)
        if expires_at <= time.time():
            self.clear()
            raise ValueError("pair_expired")
        if normalize_user_code(str(raw.get("user_code") or "")) != normalized:
            raise ValueError("user_code_mismatch")
        if str(raw.get("phase") or "") != "waiting":
            raise ValueError("pair_not_waiting")
        if not token.strip():
            raise ValueError("token_required")
        schedule_from_submit = any(
            v is not None
            for v in (stale_nudge_cron, stale_days, remind_cooldown_days, digest_max_nudge)
        )
        preview = OpenClawConfig(
            alerts_enabled=alerts_enabled,
            webhook_url=webhook_url,
            agent_url=agent_url,
            token=token.strip(),
            stale_nudge_cron=stale_nudge_cron or "0 9 * * *",
            stale_days=stale_days if stale_days is not None else 3,
            remind_cooldown_days=(
                remind_cooldown_days if remind_cooldown_days is not None else 3
            ),
            digest_max_nudge=digest_max_nudge if digest_max_nudge is not None else 2,
        )
        now = time.time()
        self._save_raw(
            {
                "phase": "submitted",
                "user_code": normalized,
                "expires_at": expires_at,
                "created_at": raw.get("created_at", now),
                "submitted_at": now,
                "webhook_url": preview.webhook_url,
                "agent_url": preview.agent_url,
                "token": preview.token,
                "alerts_enabled": preview.alerts_enabled,
                "stale_nudge_cron": preview.stale_nudge_cron,
                "stale_days": preview.stale_days,
                "remind_cooldown_days": preview.remind_cooldown_days,
                "digest_max_nudge": preview.digest_max_nudge,
                "_schedule_from_submit": schedule_from_submit,
                "hub_origin": str(raw.get("hub_origin") or ""),
            }
        )
        return self.status()

    def approve_config(self, *, current: OpenClawConfig | None = None) -> OpenClawConfig:
        raw = self._load_raw()
        state = self.status()
        if state.status != "submitted":
            raise ValueError("nothing_to_approve")
        base = current or OpenClawConfig()
        if raw.get("_schedule_from_submit"):
            schedule = {
                "stale_nudge_cron": str(raw.get("stale_nudge_cron") or base.stale_nudge_cron),
                "stale_days": int(raw.get("stale_days") or base.stale_days),
                "remind_cooldown_days": int(
                    raw.get("remind_cooldown_days") or base.remind_cooldown_days
                ),
                "digest_max_nudge": int(raw.get("digest_max_nudge") or base.digest_max_nudge),
            }
        else:
            schedule = {
                "stale_nudge_cron": base.stale_nudge_cron,
                "stale_days": base.stale_days,
                "remind_cooldown_days": base.remind_cooldown_days,
                "digest_max_nudge": base.digest_max_nudge,
            }
        config = OpenClawConfig(
            alerts_enabled=bool(raw.get("alerts_enabled", base.alerts_enabled)),
            webhook_url=str(raw.get("webhook_url") or ""),
            agent_url=str(raw.get("agent_url") or ""),
            token=str(raw.get("token") or ""),
            **schedule,
        )
        self.clear()
        return config

    def cancel(self) -> None:
        self.clear()


def openclaw_pair_prompt(*, hub_origin: str, user_code: str) -> str:
    hub = hub_origin.rstrip("/")
    code = (user_code or "").strip() or "<PAIRING_CODE_FROM_HUB>"
    return "\n".join(
        [
            "Set up ADHD Progress Hub ↔ OpenClaw on my private LAN or Tailscale.",
            "",
            f"Pairing code from the Hub UI: {code}",
            "",
            "Do this end-to-end:",
            "1. Install Hub skills for OpenClaw (non-interactive):",
            "   npx skills add uniskela/adhd-hub -g -y -a openclaw",
            "2. Ensure the OpenClaw gateway exposes /hooks/wake and optional /hooks/agent",
            "   on a LAN/Tailscale URL (not the public internet).",
            "3. Provision a dedicated hook bearer token without exposing it. Configure",
            "   hooks.token through a protected runtime SecretRef, or inject it through the",
            "   gateway service environment if that is the supported secure path for this",
            "   OpenClaw version. Never print, echo, reveal, or paste the token into chat,",
            "   command arguments, config files, or tool output.",
            "4. If hooks.token cannot be securely provisioned by reference/runtime injection,",
            "   report this structured failure to the Hub and stop — do not fall back to",
            "   exposing the token:",
            f"   POST {hub}/api/openclaw/pair/submit",
            "   JSON body:",
            "   {",
            f'     "user_code": "{code}",',
            '     "error_code": "hooks_token_secretref_unsupported"',
            "   }",
            "5. If secure provisioning succeeds, submit the pair from a secret-injected",
            "   request. The Hub needs the actual hook token to authenticate outbound nudges,",
            "   but the request mechanism must inject it without displaying it:",
            f"   POST {hub}/api/openclaw/pair/submit",
            "   JSON body shape:",
            "   {",
            f'     "user_code": "{code}",',
            '     "webhook_url": "http(s)://<openclaw-host>:18789/hooks/wake",',
            '     "agent_url": "http(s)://<openclaw-host>:18789/hooks/agent",',
            '     "token": "<secret-injected-at-request-time>",',
            '     "alerts_enabled": true',
            "   }",
            "6. Recommended Hub alert defaults unless I say otherwise:",
            '   cron "0 9 * * *", stale after 3 days, cooldown 3 days, digest limit 2.',
            "7. Tell me when submit succeeds so I can Approve in Hub Settings → Connections,",
            "   then help interpret Save & send test if needed.",
            "",
            f"Hub UI: {hub}/ui",
            "Never put ADHD_HUB_AUTH_TOKEN into OpenClaw config, skills, or chat logs.",
            "Summaries only — no raw transcripts.",
        ]
    )
