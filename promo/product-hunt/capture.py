#!/usr/bin/env python3
"""Capture the Progress Hub launch film from its deterministic HTML composition.

Every frame is rendered by calling ``promo.seek(t)`` in headless Chromium, so the
output never depends on playback timing.

    python3 promo/product-hunt/capture.py still 4.2            # one frame → out/still-4.200.png
    python3 promo/product-hunt/capture.py stills               # the four key stills → stills/
    python3 promo/product-hunt/capture.py frames               # every frame → out/frames/00000.png …
    python3 promo/product-hunt/capture.py video                # out/progress-hub-launch.mp4 (H.264, 60 fps)
    python3 promo/product-hunt/capture.py video --sfx          # …with the synthesized UI-sound stem muxed in
    python3 promo/product-hunt/capture.py qa                   # checkpoints, contact sheet and automated checks → qa/

Requires: ``pip install playwright && playwright install chromium`` (or run via
``uv run --with playwright …``), plus ffmpeg for ``video``. Pillow for the QA sheet.
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import http.server
import json
import math
import shutil
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = HERE / "out"
W, H = 1920, 1080

KEY_STILLS = {
    "01-scattered-context": 2.45,
    "02-where-you-left-off": 4.95,
    "03-agent-continuity": 9.62,
    "04-product-hunt-card": 16.4,
}


@contextlib.contextmanager
def serve_repo():
    """Serve the repository root on a free localhost port (fonts load from src/)."""
    handler = functools.partial(_QuietHandler, directory=str(REPO))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/promo/product-hunt/index.html?capture=1"
    finally:
        httpd.shutdown()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - silence request log
        pass


@contextlib.contextmanager
def film_page():
    from playwright.sync_api import sync_playwright

    with serve_repo() as url, sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_load_state("load")
        if errors:
            raise SystemExit("composition failed to load:\n" + "\n".join(errors))
        page.wait_for_function("window.promo && window.promo.ready === true", timeout=30_000)
        try:
            yield page
        finally:
            browser.close()


def shot(page, t: float) -> bytes:
    page.evaluate("t => window.promo.seek(t)", t)
    return page.screenshot(type="png", clip={"x": 0, "y": 0, "width": W, "height": H})


def info(page) -> dict:
    return page.evaluate("({duration: promo.duration, fps: promo.fps, frames: promo.frames, beats: promo.beats})")


# ---------------------------------------------------------------- commands

def cmd_still(args):
    OUT.mkdir(exist_ok=True)
    with film_page() as page:
        for t in args.t:
            path = Path(args.out) if args.out and len(args.t) == 1 else OUT / f"still-{t:.3f}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(shot(page, t))
            print(path)


def cmd_stills(args):
    dest = HERE / "stills"
    dest.mkdir(exist_ok=True)
    with film_page() as page:
        for name, t in KEY_STILLS.items():
            (dest / f"{name}.png").write_bytes(shot(page, t))
            print(dest / f"{name}.png", f"t={t}")


def cmd_frames(args):
    dest = Path(args.out) if args.out else OUT / "frames"
    dest.mkdir(parents=True, exist_ok=True)
    with film_page() as page:
        meta = info(page)
        fps = args.fps or meta["fps"]
        n = round(meta["duration"] * fps)
        for i in range(n):
            (dest / f"{i:05d}.png").write_bytes(shot(page, i / fps))
            if i % 60 == 0:
                print(f"frame {i}/{n}", flush=True)
    print(f"{n} frames → {dest}")


def cmd_video(args):
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")
    OUT.mkdir(exist_ok=True)
    target = Path(args.out) if args.out else OUT / "progress-hub-launch.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    with film_page() as page:
        meta = info(page)
        fps = args.fps or meta["fps"]
        n = round(meta["duration"] * fps)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-"]
        if args.sfx:
            stem = OUT / "sfx.wav"
            subprocess.run([sys.executable, str(HERE / "sfx.py"), str(stem)], check=True)
            cmd += ["-i", str(stem), "-c:a", "aac", "-b:a", "192k", "-shortest"]
        cmd += ["-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-r", str(fps), str(target)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for i in range(n):
            proc.stdin.write(shot(page, i / fps))
            if i % 60 == 0:
                print(f"frame {i}/{n}", flush=True)
        proc.stdin.close()
        if proc.wait() != 0:
            sys.exit("ffmpeg failed")
    print(target)


def cmd_qa(args):
    from PIL import Image, ImageDraw, ImageFont

    dest = HERE / "qa"
    dest.mkdir(exist_ok=True)
    report: dict = {"checkpoints": [], "checks": {}}
    with film_page() as page:
        meta = info(page)
        D, fps = meta["duration"], meta["fps"]
        points = [("0%", 0.0), ("25%", D * 0.25), ("50%", D * 0.5), ("75%", D * 0.75), ("100%", D)]
        points += [(b["label"], b["t"]) for b in meta["beats"]]
        thumbs = []
        for label, t in points:
            name = f"{t:06.3f}-{label.replace(' ', '-').replace('?', '').replace('%', 'pct').lower()}.png"
            png = shot(page, t)
            (dest / name).write_bytes(png)
            report["checkpoints"].append({"label": label, "t": round(t, 3), "file": f"qa/{name}"})
            thumbs.append((label, t, dest / name))

        # Determinism: same timestamp, reached from different prior states, must be identical.
        probe = [0.7, 4.2, 9.3, 12.3, 15.8]
        a = [hashlib.sha256(shot(page, t)).hexdigest() for t in probe]
        b = [hashlib.sha256(shot(page, t)).hexdigest() for t in reversed(probe)][::-1]
        report["checks"]["deterministic_seek"] = a == b

        # Loop: first and last frame must match.
        f0, fT = shot(page, 0.0), shot(page, D)
        report["checks"]["loop_first_equals_last"] = hashlib.sha256(f0).digest() == hashlib.sha256(fT).digest()

        # Dot continuity at 240 Hz sampling: largest per-sample jump and speed.
        n = int(D * 240)
        pts = page.evaluate("n => Array.from({length: n + 1}, (_, i) => promo.dotAt(i * promo.duration / n))", n)
        jumps = [math.dist(pts[i], pts[i + 1]) for i in range(n)]
        worst = max(range(n), key=lambda i: jumps[i])
        report["checks"]["dot_max_step_px_at_240hz"] = round(jumps[worst], 2)
        report["checks"]["dot_max_step_time"] = round(worst * D / n, 3)
        report["checks"]["dot_max_step_px_per_frame_60fps"] = round(jumps[worst] * 4, 1)
        fastest, taken = [], []
        for i in sorted(range(n), key=lambda i: -jumps[i]):
            if all(abs(i - j) > 40 for j in taken):
                taken.append(i)
                fastest.append({"t": round(i * D / n, 3), "px_per_frame_60fps": round(jumps[i] * 4, 1)})
            if len(fastest) == 5:
                break
        report["checks"]["dot_fastest_moments"] = fastest
        report["checks"]["dot_wrap_gap_px"] = round(math.dist(pts[0], pts[-1]), 3)
        # Inside the frame?
        report["checks"]["dot_always_in_frame"] = all(10 <= x <= W - 10 and 10 <= y <= H - 10 for x, y in pts)

        # Typography overlap: caption/question/end-card word boxes against each other at each checkpoint.
        overlaps = []
        for label, t in points:
            hits = page.evaluate(
                """t => { promo.seek(t);
                const vis = el => { const s = getComputedStyle(el); return s.visibility !== 'hidden' && parseFloat(s.opacity) > 0.05 && el.closest('.caption') && getComputedStyle(el.closest('.caption')).visibility !== 'hidden' && parseFloat(getComputedStyle(el.closest('.caption')).opacity) > 0.05; };
                const boxes = [...document.querySelectorAll('#stage .caption .w')].filter(vis).map(e => ({t: e.textContent, r: e.getBoundingClientRect(), c: e.closest('.caption')}));
                const out = [];
                for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
                  if (boxes[i].c === boxes[j].c) continue;
                  const a = boxes[i].r, b = boxes[j].r;
                  if (a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) out.push(boxes[i].t + ' × ' + boxes[j].t);
                }
                return out; }""",
                t,
            )
            if hits:
                overlaps.append({"t": t, "label": label, "hits": hits})
        report["checks"]["caption_overlaps"] = overlaps

        # The dot must never pass over visible display type (captions, question, end card).
        crossings = page.evaluate(
            """n => { const out = [];
            for (let i = 0; i <= n; i++) {
              const t = i * promo.duration / n; promo.seek(t);
              const [x, y] = promo.dotAt(t);
              for (const w of document.querySelectorAll('#stage .caption .w')) {
                const c = w.closest('.caption'); const cs = getComputedStyle(c);
                if (cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.3 || parseFloat(getComputedStyle(w).opacity) < 0.3) continue;
                const r = w.getBoundingClientRect(), pad = 10, inset = r.height * 0.18;
                if (x + pad > r.left && x - pad < r.right && y + pad > r.top + inset && y - pad < r.bottom - inset) { out.push(+t.toFixed(3) + ' ' + w.textContent); break; }
              }
            } return out; }""",
            int(D * fps),
        )
        report["checks"]["dot_over_caption"] = crossings

    # Contact sheet
    cols, tw, th, pad, cap = 4, 480, 270, 16, 34
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + cap + pad) + pad), (233, 231, 226))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(str(REPO / "src/adhd_hub/ui/brand/figtree-latin.woff2"), 18)
    except OSError:
        font = ImageFont.load_default()
    for i, (label, t, path) in enumerate(thumbs):
        x = pad + (i % cols) * (tw + pad)
        y = pad + (i // cols) * (th + cap + pad)
        sheet.paste(Image.open(path).convert("RGB").resize((tw, th), Image.LANCZOS), (x, y))
        draw.text((x, y + th + 7), f"{t:6.3f}s  {label}", fill=(31, 35, 40), font=font)
    sheet.save(dest / "contact-sheet.png")
    (dest / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["checks"], indent=2))
    print(dest / "contact-sheet.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("still", help="render one or more timestamps")
    s.add_argument("t", type=float, nargs="+")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_still)
    sub.add_parser("stills", help="render the four key stills into stills/").set_defaults(fn=cmd_stills)
    f = sub.add_parser("frames", help="render every frame as PNG")
    f.add_argument("--out")
    f.add_argument("--fps", type=int)
    f.set_defaults(fn=cmd_frames)
    v = sub.add_parser("video", help="render an H.264 MP4 via ffmpeg")
    v.add_argument("--out")
    v.add_argument("--fps", type=int)
    v.add_argument("--crf", type=int, default=14)
    v.add_argument("--sfx", action="store_true", help="mux the synthesized UI-sound stem")
    v.set_defaults(fn=cmd_video)
    sub.add_parser("qa", help="checkpoint frames, contact sheet and automated checks").set_defaults(fn=cmd_qa)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
