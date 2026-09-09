import importlib.util
from pathlib import Path


def _load_gate():
    path = Path(__file__).parents[1] / "scripts" / "release_gate.py"
    spec = importlib.util.spec_from_file_location("release_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_gate_classifies_subjects_and_paths():
    gate = _load_gate()

    assert gate.subject_can_release("fix(auth): trust the public origin")
    assert gate.subject_can_release("refactor(api)!: remove a route")
    assert not gate.subject_can_release("docs: explain the API")
    assert not gate.subject_can_release("chore: update CI")
    assert gate.RELEASE_MERGE_SUBJECT.match("chore(main): release 0.3.4")

    assert gate.is_release_surface("src/adhd_hub/app.py")
    assert gate.is_release_surface("pyproject.toml")
    assert gate.is_release_surface("docker-compose.yml")
    assert not gate.is_release_surface("docs/dashboard.md")
    assert not gate.is_release_surface(".github/workflows/pages.yml")
    assert not gate.is_release_surface("skills/adhd-hub-session/SKILL.md")
