"""Guard the locked-install policy: uv.lock tracks pyproject.toml across releases."""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _locked_project_packages() -> list[dict]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return [pkg for pkg in lock["package"] if pkg["name"] == _project()["name"]]


def test_lockfile_records_the_current_package_version():
    packages = _locked_project_packages()

    assert len(packages) == 1
    assert packages[0]["source"] == {"editable": "."}
    assert packages[0]["version"] == _project()["version"], (
        "uv.lock is stale: run `uv lock` (release bumps come from Release Please)"
    )


def test_release_please_bumps_the_lockfile_with_the_package_version():
    config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    extra_files = config["packages"]["."]["extra-files"]
    lock_entries = [entry for entry in extra_files if entry.get("path") == "uv.lock"]

    # Without this entry a release PR bumps pyproject.toml only, and the
    # --locked installs below fail on main right after the release merge.
    assert lock_entries == [
        {
            "type": "toml",
            "path": "uv.lock",
            "jsonpath": f"$.package[?(@.name.value=='{_project()['name']}')].version",
        }
    ]


def test_ci_and_image_installs_reject_a_stale_lockfile():
    quality = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    sync_commands = re.findall(r"^\s*run: (uv sync.*)$", quality, flags=re.MULTILINE)
    assert sync_commands
    assert all("--locked" in command for command in sync_commands)
    # UV_LOCKED also covers `uv run`, which would otherwise re-lock implicitly.
    assert re.search(r'^\s*UV_LOCKED: "true"$', quality, flags=re.MULTILINE)
    assert "frozen" not in quality.lower()

    docker_syncs = re.findall(r"uv sync[^\n\\]*", dockerfile)
    assert docker_syncs
    assert all("--locked" in command for command in docker_syncs)
