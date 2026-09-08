"""Probe Gitea/GitHub forge target without printing secrets."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
forge_path = root / "data" / "forge.json"
if not forge_path.is_file():
    print("NO_FORGE_JSON")
    sys.exit(1)

forge = json.loads(forge_path.read_text(encoding="utf-8"))
owner = forge.get("owner")
repo = forge.get("repo")
base = (forge.get("base_url") or "").rstrip("/")
token = forge.get("token") or ""
print(f"owner={owner} repo={repo}")
print(f"base_url={base}")
print(f"token_set={bool(token)} token_len={len(token)}")

paths = [
    f"/repos/{owner}/{repo}",
    "/user",
    f"/repos/{owner}/{repo}/issues?limit=1",
    f"/repos/{owner}/{repo}/contents/?ref={forge.get('wiki_branch') or 'main'}",
]
for path in paths:
    url = base + path
    req = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=15) as resp:
            body = resp.read().decode()[:180].replace("\n", " ")
            print(f"GET {path} -> {resp.status} {body}")
    except HTTPError as e:
        err_body = e.read().decode()[:180].replace("\n", " ")
        print(f"GET {path} -> {e.code} {err_body}")
    except Exception as e:  # noqa: BLE001
        print(f"GET {path} -> ERR {type(e).__name__}: {e}")
