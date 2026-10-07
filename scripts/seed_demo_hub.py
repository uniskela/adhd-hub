"""Load generic sample data into a running Hub (Product Hunt / Supademo ops).

Prefer Settings → Your data → Load sample data, or ADHD_HUB_SEED_DEMO=1 on boot.
This script calls the same API (no-op if the sample pack is already present).

Runbook (local / unidev):
  export ADHD_HUB_AUTH_TOKEN=<long-random>
  export ADHD_HUB_DATA_DIR="$PWD/.demo-data"
  mkdir -p "$ADHD_HUB_DATA_DIR"
  uv run adhd-hub serve --host 127.0.0.1 --port 8787
  ADHD_HUB_BASE=http://127.0.0.1:8787 uv run python scripts/seed_demo_hub.py
  serve 8787
  # UI: https://<tailscale-serve-host>:8787/ui/
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from adhd_hub.sample_data import sample_payload


def demo_payload():
    """Back-compat alias for tests / callers expecting demo_payload()."""
    return sample_payload()


def wait_health(base: str, tries: int = 50) -> None:
    for _ in range(tries):
        try:
            urlopen(base.rstrip("/") + "/api/health", timeout=1).close()
            return
        except (URLError, OSError):
            time.sleep(0.1)
    raise SystemExit(f"Hub not healthy at {base}")


def main(argv: list[str] | None = None) -> int:
    _ = argv
    token = os.environ.get("ADHD_HUB_AUTH_TOKEN", "").strip()
    if not token or token == "change-me-to-a-long-random-string":
        print("Set ADHD_HUB_AUTH_TOKEN to a non-placeholder value", file=sys.stderr)
        return 2
    base = os.environ.get("ADHD_HUB_BASE", "http://127.0.0.1:8787").rstrip("/")
    wait_health(base)
    req = Request(
        base + "/api/sample-data/load",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    print(
        "seeded ok"
        + (" already_loaded" if body.get("already_loaded") else "")
        + f" message={body.get('message', '')}"
    )
    _ = Path(os.environ.get("ADHD_HUB_DATA_DIR", ".demo-data"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
