#!/usr/bin/env python3
"""Bump project semver in pyproject.toml and docker-compose.yml.

Usage:
  python scripts/bump_version.py patch|minor|major
  python scripts/bump_version.py 1.2.3
Prints the new version to stdout.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
COMPOSE = ROOT / "docker-compose.yml"
VERSION_RE = re.compile(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"\s*$', re.M)
COMPOSE_IMAGE_RE = re.compile(
    r"^(?P<prefix>\s*image:\s*adhd-hub:)(?P<ver>\d+\.\d+\.\d+)(?P<suffix>\s*(?:#.*)?)$",
    re.M,
)


def parse_version(text: str) -> tuple[int, int, int]:
    m = VERSION_RE.search(text)
    if not m:
        raise SystemExit("version not found in pyproject.toml")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump(parts: tuple[int, int, int], kind: str) -> str:
    major, minor, patch = parts
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if re.fullmatch(r"\d+\.\d+\.\d+", kind):
        return kind
    raise SystemExit(f"unknown bump {kind!r}; use patch|minor|major|X.Y.Z")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    kind = sys.argv[1].strip()
    text = PYPROJECT.read_text(encoding="utf-8")
    new = bump(parse_version(text), kind)
    text = VERSION_RE.sub(f'version = "{new}"', text, count=1)
    PYPROJECT.write_text(text, encoding="utf-8")

    compose = COMPOSE.read_text(encoding="utf-8")
    if not COMPOSE_IMAGE_RE.search(compose):
        raise SystemExit("image: adhd-hub:X.Y.Z not found in docker-compose.yml")
    compose = COMPOSE_IMAGE_RE.sub(rf"\g<prefix>{new}\g<suffix>", compose, count=1)
    COMPOSE.write_text(compose, encoding="utf-8")

    print(new)


if __name__ == "__main__":
    main()
