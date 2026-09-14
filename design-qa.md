# Notes reader design QA

final result: passed

## Reviewed states

- Desktop docked reader at 1440 × 1080: the project rail, thread list, and reading pane remain visible without overlap.
- Desktop expanded reader at 1440 × 1080: the reader uses a wider centered reading column while preserving comfortable line length and its layout controls.
- Desktop viewport boundary: the reader measures the space below its actual top edge so its bottom remains visible above the browser viewport edge.
- Mobile reader at 390 × 844: the reader becomes a full-screen surface; safe-area padding, list indentation, wrapping, and local code/table scrolling prevent left-edge clipping and page overflow.
- Keyboard behavior: Escape closes the reader and returns focus to the Notes & context button that opened it.
- Accessibility: the trigger exposes `aria-controls` and `aria-expanded`; layout buttons expose pressed state; the reader has a labelled heading and focusable scroll region.

## Evidence

- Browser smoke coverage exercises open, dock, expand, close, focus restoration, mobile viewport overflow guards, and sanitized Markdown rendering.
- Desktop screenshots: `ui-qa/notes-reader-docked.png` and `ui-qa/notes-reader-expanded.png` (local test output, not committed).
- Source screenshot comparison: the previous detached right-side popup is now an integrated reading column with a subject header and explicit layout controls while retaining the existing calm visual language.
