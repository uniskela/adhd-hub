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
