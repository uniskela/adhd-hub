# Browser verification for coding agents

Run these checks from the repository root after UI changes.

The smoke script uses a temporary hub, a temporary database, and sample projects. It does not change your running hub.

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python scripts/browser_smoke.py
uv run --with playwright python scripts/ui_polish_smoke.py
# Optional: refresh README/docs product shots under docs/public/images/
ADHD_HUB_SCREENSHOT_DIR=docs/public/images uv run --with playwright python scripts/capture_readme_screenshots.py
```

The UI polish check exercises the four screens in both themes at desktop, tablet, and phone widths, checks navigation and keyboard disclosures, and captures screenshots. `capture_readme_screenshots.py` seeds a temporary hub with dummy projects and writes the light-theme desktop shots used in the README.

Set `ADHD_HUB_BROWSER_EXECUTABLE` to use an existing Chromium binary. Screenshots default to `/tmp/adhd-hub-preview`; override with `ADHD_HUB_SCREENSHOT_DIR`.
