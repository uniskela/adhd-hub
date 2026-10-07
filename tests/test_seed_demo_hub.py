from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seed_demo_hub import demo_payload  # noqa: E402


def test_demo_payload_is_generic_readme_set():
    data = demo_payload()
    slugs = {p["slug"] for p in data["projects"]}
    assert slugs == {"sample-demo-site", "sample-home-admin", "sample-learning"}
    titles = {t["summary"] for t in data["threads"]}
    assert "Polish the landing page" in titles
    assert "Book a dentist visit" in titles
    assert data["stale_summary"] == "Book a dentist visit"
    assert data["progress_note"]["project_slug"] == "sample-demo-site"
    blob = repr(data).lower()
    assert "pike" not in blob
    assert "@" not in blob
