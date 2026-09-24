"""Custom colours must keep controls and selected states readable."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_custom_accent_contrast_in_both_themes():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to verify the browser colour helper")
    module = Path(__file__).resolve().parents[1] / "src/adhd_hub/ui/js/accent.js"
    script = """
      const { accentPalette, contrast, normalizeAccent } = await import(process.argv[1]);
      for (const value of [null, "", "red", "#fff", "#gggggg", "var(--ink)"]) {
        if (normalizeAccent(value) !== null || accentPalette(value, false) !== null) {
          throw Error(`Accepted invalid colour ${value}`);
        }
      }
      if (normalizeAccent("#ABCDEF") !== "#abcdef") throw Error("Normalization failed");
      for (let r = 0; r <= 255; r += 51) for (let g = 0; g <= 255; g += 51)
        for (let b = 0; b <= 255; b += 51) for (const dark of [false, true]) {
          const colour = "#" + [r,g,b].map(v => v.toString(16).padStart(2,"0")).join("");
          const p = accentPalette(colour, dark);
          const surfaces = dark ? ["#14141c", "#1e1e29", "#292937"] : ["#f7f7fa", "#ffffff", "#eeeef4"];
          const pairs = [[p.accent, p.ink], [p.hover, p.ink], [p.accent, p.soft],
            ...surfaces.map(surface => [p.accent, surface])];
          if (pairs.some(([a,b]) => contrast(a,b) < 4.5)) {
            throw Error(`Unreadable accent ${colour} dark=${dark}: ${JSON.stringify(p)}`);
          }
        }
    """
    subprocess.run(
        [node, "--input-type=module", "-e", script, module.as_uri()],
        check=True, capture_output=True, text=True, timeout=15,
    )
