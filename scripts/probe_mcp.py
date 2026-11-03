"""Probe MCP directly using the same transport checks as agents doctor.

Use injected ADHD_HUB_AUTH_TOKEN; never load a checkout's .env implicitly.
"""

from __future__ import annotations

import json
import os

from adhd_hub.mcp_probe import probe_mcp


def main() -> int:
    result = probe_mcp(
        os.environ.get("ADHD_HUB_MCP_URL", "http://127.0.0.1:8787/mcp"),
        token=os.environ.get("ADHD_HUB_AUTH_TOKEN"),
    )
    print(json.dumps(result))
    return 0 if result["tools_discovered"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
