import importlib.util
from pathlib import Path


def _load_pr_title_gate():
    path = Path(__file__).parents[1] / "scripts" / "pr_title_gate.py"
    spec = importlib.util.spec_from_file_location("pr_title_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pr_title_gate_requires_releasable_title_for_release_surfaces():
    gate = _load_pr_title_gate()

    ok, message = gate.check_pr_title(
        "ADHD-friendly Notes & context reader",
        ["src/adhd_hub/service.py"],
    )
    assert not ok
    assert "feat:" in message or "Release Please" in message

    ok, message = gate.check_pr_title(
        "feat(notes): ADHD-friendly Notes & context reader",
        ["src/adhd_hub/service.py"],
    )
    assert ok

    ok, message = gate.check_pr_title(
        "refactor(api)!: remove a route",
        ["src/adhd_hub/api.py"],
    )
    assert ok

    ok, message = gate.check_pr_title(
        "fix(ui): stamp timezone",
        ["pyproject.toml"],
    )
    assert ok


def test_pr_title_gate_allows_docs_titles_off_release_surface():
    gate = _load_pr_title_gate()

    ok, message = gate.check_pr_title(
        "docs: explain release squash titles",
        ["docs/installation.md", "README.md", "AGENTS.md"],
    )
    assert ok
    assert "no release-surface" in message

    ok, message = gate.check_pr_title(
        "Human readable docs-only title",
        [".github/PULL_REQUEST_TEMPLATE.md", "CONTRIBUTING.md"],
    )
    assert ok


def test_pr_title_gate_cli_paths_mode(capsys):
    gate = _load_pr_title_gate()

    assert (
        gate.main(
            [
                "--title",
                "feat(ci): add title gate",
                "--paths",
                "scripts/pr_title_gate.py",
            ]
        )
        == 0
    )

    assert (
        gate.main(
            [
                "--title",
                "Add title gate",
                "--paths",
                "src/adhd_hub/app.py",
            ]
        )
        == 1
    )
    err = capsys.readouterr().out
    assert "Release Please" in err or "feat:" in err


def test_is_release_please_pr_branch_and_author():
    gate = _load_pr_title_gate()

    assert gate.is_release_please_pr(
        head_ref="release-please--branches--main--components--adhd-hub"
    )
    assert gate.is_release_please_pr(author="release-please[bot]")
    assert gate.is_release_please_pr(author="app/release-please")
    assert not gate.is_release_please_pr(
        author="app/github-actions",
        head_ref="cursor/some-feature",
    )
    assert not gate.is_release_please_pr(
        author="human-dev",
        head_ref="feat/notes",
    )


def test_pr_title_gate_skips_release_please_prs():
    gate = _load_pr_title_gate()
    # Same shape as failing #153: chore release title + release-surface paths
    paths = ["src/adhd_hub/service.py", "CHANGELOG.md", "pyproject.toml"]

    ok, message = gate.check_pr_title(
        "chore(main): release 0.15.0",
        paths,
        head_ref="release-please--branches--main--components--adhd-hub",
        author="app/github-actions",
    )
    assert ok
    assert "exempt" in message

    ok, message = gate.check_pr_title(
        "chore(main): release 0.15.0",
        paths,
        author="release-please[bot]",
        head_ref="some-other-branch",
    )
    assert ok
    assert "exempt" in message

    # Human/agent still enforced
    ok, message = gate.check_pr_title(
        "chore(main): release 0.15.0",
        paths,
        author="cursor-agent",
        head_ref="cursor/fake-release",
    )
    assert not ok


def test_pr_title_gate_cli_release_please_exempt(capsys):
    gate = _load_pr_title_gate()

    assert (
        gate.main(
            [
                "--title",
                "chore(main): release 0.15.0",
                "--paths",
                "src/adhd_hub/app.py",
                "--head-ref",
                "release-please--branches--main",
                "--author",
                "app/github-actions",
            ]
        )
        == 0
    )
    assert "exempt" in capsys.readouterr().out


def test_release_branch_does_not_exempt_ordinary_feature_titles():
    gate = _load_pr_title_gate()
    ok, _ = gate.check_pr_title(
        "chore: change application behaviour",
        ["src/adhd_hub/service.py"],
        head_ref="release-please--branches--main--components--adhd-hub",
    )
    assert not ok
