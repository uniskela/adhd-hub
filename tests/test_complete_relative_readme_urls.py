import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).parents[1] / "scripts" / "ci" / "complete-relative-readme-urls.py"
    spec = importlib.util.spec_from_file_location("complete_relative_readme_urls", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rewrite_images_links_anchors_and_absolute():
    mod = _load()
    out = mod.rewrite(
        "![a](docs/x.png)\n[y](foo.md)\n[z](#z)\n[abs](https://example.com/a)",
        "BLOB/",
        "RAW/",
        "README.md",
    )
    assert "RAW/docs/x.png" in out
    assert "BLOB/foo.md" in out
    assert "BLOB/README.md#z" in out
    assert "[abs](https://example.com/a)" in out
