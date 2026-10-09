# Product Hunt launch film

A 17.5-second, 1920 × 1080, 60 fps looping promo for ADHD Progress Hub, built as a deterministic HTML composition. Isolated from the app: nothing here is imported by `src/`.

| File | What it is |
| --- | --- |
| `storyboard.md` | Beat map with timestamps, copy, motion, the product capability each scene shows, claim sources, still review and QA results |
| `index.html`, `promo.css`, `promo.js` | The composition and a small preview player |
| `capture.py` | Stills, frame sequences, MP4 export and automated QA (headless Chromium) |
| `sfx.py` | Optional quiet UI-sound stem on the 120 BPM beat map |
| `stills/` | The four key frames |
| `qa/` | Checkpoint frames, `contact-sheet.png`, `report.json` |
| `out/` | Render output (git-ignored) |

The film uses Figtree from `src/adhd_hub/ui/brand/` and the official logo geometry from `docs/public/assets/`, so it must be served from the repository root.

## Preview

```bash
# from the repository root
python3 -m http.server --bind 127.0.0.1 8000   # loopback only: this serves the whole repo
```

Open <http://localhost:8000/promo/product-hunt/index.html>.

| Control | Does |
| --- | --- |
| Space / **Play** | Play or pause (loops) |
| ← → | Step one frame (Shift: half a second) |
| **b** / **Next beat** | Jump to the next sync beat |
| Scrubber | Seek anywhere |

URL options: `?t=12.5` opens at a timestamp, `?play` starts playing, `?capture=1` renders the bare 1920 × 1080 stage with no controls.

## Seek to any timestamp

Every frame is a pure function of time. In the browser console:

```js
promo.seek(12.5)     // draw the frame at 12.5 s
promo.duration       // 17.5
promo.fps            // 60
promo.frames         // 1050
promo.beats          // [{ t: 0.45, label: "Fragments arrive" }, …]
promo.dotAt(9.2)     // [x, y] of the gold dot at 9.2 s
```

`seek()` never reads layout and keeps no state between calls, so seeking backwards, forwards or at random always gives the same picture. Playback in the preview just maps wall-clock time to `seek(t)`.

## Capture

Needs Python 3.10+, Playwright with Chromium, and ffmpeg for video:

```bash
pip install playwright pillow numpy && playwright install chromium
# or prefix commands with: uv run --with playwright --with pillow --with numpy
```

```bash
python3 promo/product-hunt/capture.py still 4.2 12.5      # → out/still-4.200.png, out/still-12.500.png
python3 promo/product-hunt/capture.py stills              # → stills/01…04
python3 promo/product-hunt/capture.py frames              # → out/frames/00000.png … 01049.png
python3 promo/product-hunt/capture.py video               # → out/progress-hub-launch.mp4 (H.264, yuv420p, CRF 14)
python3 promo/product-hunt/capture.py video --sfx         # same, with the UI-sound stem as AAC
python3 promo/product-hunt/capture.py qa                  # → qa/
```

`capture.py` starts its own localhost server on a free port, so nothing else needs to be running. A full video render takes about 90 seconds.

To build the video yourself from frames (for a different codec or a music bed):

```bash
ffmpeg -framerate 60 -i promo/product-hunt/out/frames/%05d.png \
  -i music.wav -c:v libx264 -crf 14 -pix_fmt yuv420p -c:a aac -shortest launch.mp4
```

### Product Hunt notes

- Product Hunt has taken gallery video as a YouTube link; check their current launch guide, then upload `out/progress-hub-launch.mp4` wherever it asks. The file loops cleanly if the host loops it.
- For a GIF thumbnail: `ffmpeg -i promo/product-hunt/out/progress-hub-launch.mp4 -vf "fps=30,scale=1270:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" promo/product-hunt/out/launch.gif`
- `stills/04-product-hunt-card.png` works as a gallery image or social card.

## Sound

The film is designed to read muted. `sfx.py` writes a quiet stem (soft clicks, card settles, a spring tick, two small confirmations) at the beats listed in `storyboard.md`. No music is bundled: lay a licensed 120 BPM track under it with the downbeat at 0.0 s.

## QA

`capture.py qa` renders 0 %, 25 %, 50 %, 75 %, 100 % and every beat, then checks:

- determinism (same frame from different seek orders)
- loop seam (first frame byte-identical to last)
- dot continuity (sampled at 240 Hz; largest jump and fastest moments)
- dot stays in frame
- caption collisions between separate captions

Results are in `qa/report.json`; the visual pass is in `storyboard.md`.

## Editing

- Timing lives in `promo.js`, one block per scene in `render()`, plus `dotAt()` for the dot. Any element the dot drives reads the same motion function as the dot (`shell2Rect`, `shellARect`, `tFixState`, `maskDark`, `maskLight`), so they cannot drift apart.
- UI is rebuilt from `src/adhd_hub/ui/app.css` values in real CSS pixels and scaled by its group (×1.5 for the Now card, ×1.2 for My work). If the app's UI changes, update `promo.css` and the copy in `build()`.
- Keep the logo as the verbatim SVG. Reveal it with opacity only.
- After changes, run `capture.py qa` and `capture.py stills`, and look at `qa/contact-sheet.png`.
