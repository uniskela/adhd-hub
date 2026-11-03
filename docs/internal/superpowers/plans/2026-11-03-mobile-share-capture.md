# Mobile share capture — plan

Design: `docs/internal/superpowers/specs/2026-11-03-mobile-share-capture-design.md`

1. Add `share_target` (GET, `action: /ui/?share=1`) to `manifest.webmanifest`.
2. Export compose + `openShareCaptureIfRequested` from `now.js`; call from `boot.js` after auth (alongside `?thread=`).
3. Bump `sw.js` CACHE id.
4. Extend `tests/test_pwa.py` (+ small JS/string asserts for compose if needed).
5. Docs: `dashboard.md` PWA section; roadmap stamp if appropriate.
6. PR `feat(ui): …` / Wave 8 share target.
