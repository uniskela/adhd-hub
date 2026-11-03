# Mobile share capture (Wave 8) — design

Parent: [#55](https://github.com/uniskela/adhd-hub/issues/55) · Continuity: [#337](https://github.com/uniskela/adhd-hub/issues/337)

## Goal

Ship **Web Share Target → Save a thought** so a phone can share text/links into the Hub as a quick thought (optionally an open inbox thread). Offline queue is **out of scope** for this slice.

## Non-goals

- IndexedDB / offline flush queue
- Dedicated `/ui/capture` page
- File/image share payloads
- Energy/context modes

## Approach

Reuse existing `captureStep` / `#capture-dialog`. Add `share_target` (GET) to `manifest.webmanifest`. On boot after auth, if share query params are present, prefills the textarea, opens the dialog, and cleans the URL.

## Behaviour

### Manifest

```json
"share_target": {
  "action": "/ui/",
  "method": "GET",
  "enctype": "application/x-www-form-urlencoded",
  "params": { "title": "title", "text": "text", "url": "url" }
}
```

Installed PWA only (browser share sheet → Progress Hub).

### Prefill

Compose summary from non-empty `title`, `text`, `url` (dedupe if text already contains url). Cap at textarea `maxlength` (500). Open `#capture-dialog` with `#capture-as-thread` left as default (checked). `history.replaceState` removes share params (and keep unrelated params like `thread` handled separately).

### Auth

If not signed in, keep share params until after successful login, then open capture (same boot path as `?thread=`).

### SW

Bump shell cache id so the new manifest is precached.

## Verify

- Manifest JSON includes `share_target`
- Unit/static test for compose + param strip helper (or boot string asserts)
- `uv run pytest` / ruff
