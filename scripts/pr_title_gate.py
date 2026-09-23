"""Fail PRs whose title would skip Release Please after a multi-commit squash.

GitHub squash-merge with COMMIT_OR_PR_TITLE uses the PR title as the merge
subject. Body bullets and branch commit subjects do not count. This gate
matches ``scripts/release_gate.py`` release-surface paths and releasable
subject rules so a human-readable PR title cannot silently skip a release.

Release Please's own release PRs are exempt: they intentionally use
``chore(…): release …`` titles while bumping release surfaces. Detection
prefers head-branch / author signals over title matching.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# Authors used by googleapis/release-please-action / release-please[bot].
# Prefer combining with branch detection: GHA-token PRs may show as
# ``app/github-actions`` rather than release-please itself.
_RELEASE_PLEASE_AUTHORS = frozenset(
    {
        "release-please[bot]",
        "app/release-please",
        "release-please",
    }
)

# Default release-please-action branch prefix (manifest/component suites append
# more segments after ``release-please--branches--``).
_RELEASE_PLEASE_BRANCH_PREFIX = "release-please--branches--"


def _load_release_gate():
    path = Path(__file__).with_name("release_gate.py")
    spec = importlib.util.spec_from_file_location("release_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_release_please_pr(
    *,
    author: str | None = None,
    head_ref: str | None = None,
) -> bool:
    """True when this PR is a Release Please release PR (skip title gate).

    Prefer head-branch prefix (stable across token identities) and known
    release-please bot logins. Do not rely on title alone.
    """
    ref = (head_ref or "").strip()
    if ref.startswith(_RELEASE_PLEASE_BRANCH_PREFIX):
        return True

    login = (author or "").strip().lower()
    if not login:
        return False
    if login in {a.lower() for a in _RELEASE_PLEASE_AUTHORS}:
        return True
    # e.g. release-please-manifest[bot] if naming drifts
    return "release-please" in login and (
        login.endswith("[bot]") or login.startswith("app/")
    )


def check_pr_title(
    title: str,
    paths: list[str],
    *,
    author: str | None = None,
    head_ref: str | None = None,
) -> tuple[bool, str]:
    """Return whether a PR title is allowed for the given changed paths."""
    if is_release_please_pr(author=author, head_ref=head_ref):
        return (
            True,
            "ok: release-please PR exempt from conventional title gate",
        )

    gate = _load_release_gate()
    subject = title.strip()
    touches_release = any(gate.is_release_surface(path) for path in paths)

    if not touches_release:
        return (
            True,
            "ok: no release-surface paths; docs/chore/ci titles are allowed",
        )

    if gate.subject_can_release(subject):
        return True, "ok: releasable conventional title for release-surface changes"

    return (
        False,
        (
            "PR title must be a Release Please subject when the diff touches "
            "release surfaces (src/, pyproject.toml, uv.lock, Dockerfile, "
            "docker-compose.yml). Use feat:/fix:/perf:/revert: or type!: "
            "(optional scope). Squash merges use the PR title as the subject; "
            f"body bullets do not count. Got: {subject!r}"
        ),
    )


def _paths_from_git(base: str, head: str) -> list[str]:
    gate = _load_release_gate()
    return gate.git_lines("diff", "--name-only", f"{base}...{head}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Pull request title")
    parser.add_argument(
        "--base",
        help="Base SHA for git diff (with --head)",
    )
    parser.add_argument(
        "--head",
        help="Head SHA for git diff (with --base)",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Changed paths (skip git when provided)",
    )
    parser.add_argument(
        "--author",
        default="",
        help="PR author login (e.g. release-please[bot]); used for RP exempt",
    )
    parser.add_argument(
        "--head-ref",
        default="",
        help="PR head branch name; release-please--branches--* skips the gate",
    )
    args = parser.parse_args(argv)

    if args.paths is not None and (args.base or args.head):
        print("use either --paths or --base/--head, not both", file=sys.stderr)
        return 2
    if args.paths is None:
        if not args.base or not args.head:
            print("provide --paths or both --base and --head", file=sys.stderr)
            return 2
        paths = _paths_from_git(args.base, args.head)
    else:
        paths = list(args.paths)

    ok, message = check_pr_title(
        args.title,
        paths,
        author=args.author or None,
        head_ref=args.head_ref or None,
    )
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
