"""Hub preferences (timezone, etc.) stored under data/prefs.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class HubPrefs(BaseModel):
    # IANA name, e.g. Australia/Sydney. Empty/"UTC" = Coordinated Universal Time.
    timezone: str = "UTC"

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump()


def prefs_path(data_dir: Path) -> Path:
    return data_dir / "prefs.json"


def load_prefs(data_dir: Path, *, default_timezone: str = "UTC") -> HubPrefs:
    path = prefs_path(data_dir)
    base = HubPrefs(timezone=default_timezone or "UTC")
    if not path.is_file():
        return base
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    merged = base.model_dump()
    merged.update({k: v for k, v in raw.items() if v is not None})
    return HubPrefs.model_validate(merged)


def save_prefs(data_dir: Path, prefs: HubPrefs) -> Path:
    path = prefs_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs.model_dump(), indent=2) + "\n", encoding="utf-8")
    return path
