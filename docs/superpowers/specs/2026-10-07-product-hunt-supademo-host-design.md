# Product Hunt Supademo — hosted dummy Hub UI

**Date:** 2026-10-07  
**Status:** Approved (conversation)  
**Goal:** Host a Tailscale-reachable ADHD Hub web UI seeded with generic dummy data for a Product Hunt Supademo walkthrough.

## Constraints

- Generic demo content only (no personal, customer, or private infrastructure details in seed data).
- Hosting path: private Tailscale Serve on this VPS (`unidev` / `dev-vps`), not public Cloudflare.
- Auth: shortest clean recording path — pre-authenticate so the walkthrough can open on **Now**.
- Do not change the Product Hunt launch film under `promo/product-hunt/`.

## Approach

**uv serve + existing Tailscale Serve on 8787 + one-shot seed** (not Docker for this demo).

| Piece | Choice |
| --- | --- |
| Process | `uv run adhd-hub serve --host 127.0.0.1 --port 8787` |
| Data | Workspace-local `.demo-data/` (gitignored), dedicated instance |
| Preview | `serve 8787` → `https://dev-vps.pygora-gacrux.ts.net:8787/ui/` (tailnet only) |
| Seed | Thin script reusing the README gallery dummy set from `scripts/capture_readme_screenshots.py` |
| Auth | Sign in once with `ADHD_HUB_AUTH_TOKEN`; leave browser storage so recording starts on Now |

## Seed content (generic)

Projects (same spirit as README shots):

| Slug | Title | Tags |
| --- | --- | --- |
| `demo-site` | Demo website | Creative |
| `home-admin` | Home admin | Personal |
| `learning` | Learning notes | Learning |

Open threads with focus / next / resume cues suitable for Supademo steps:

1. **Polish the landing page** (`demo-site`) — focus: Tighten the hero copy; resume: Draft one clearer headline  
2. **Book a dentist visit** (`home-admin`) — focus: Find a nearby clinic; resume: Check opening hours (optionally backdated so Quiet check-in appears)  
3. **Review design notes** (`learning`) — focus: Skim last week's notes; resume: Write one takeaway  

One finished thread for list variety: **Collect homepage ideas** (`demo-site`, done).

One progress note on the landing-page thread (generic screenshot-style wording only).

Landing state for recording: light theme, rewards on, chosen thread = landing-page step, focus state `paused` so **Where you left off** shows.

## Components

1. **`scripts/seed_demo_hub.py`**  
   - Assumes Hub already listening; waits for `/api/health`, then `POST /api/sample-data/load` (same pack as Settings).  
   - Re-seed = `POST /api/sample-data/remove` then load again (pack-only; do not wipe `.demo-data/`). Repeat load is a no-op when the pack is already owned.

2. **`.demo-data/`**  
   - `ADHD_HUB_DATA_DIR`; add to `.gitignore`.

3. **Runbook**  
   - Docstring on `seed_demo_hub.py` only (no Product Hunt film README changes).  
   - Env: strong `ADHD_HUB_AUTH_TOKEN`, `ADHD_HUB_FORGE_PROVIDER=none`, empty OpenClaw URL.  
   - Operator/agent steps: start serve → run seed → `serve 8787` → open Tailscale `/ui/`.

4. **Pre-auth for recording**  
   - One Playwright login with the token (same localStorage keys as `capture_readme_screenshots.py`: light theme, rewards on, chosen thread, `paused`).  
   - No dashboard password required for the first recording pass.

## Out of scope

- Public tunnel / Product Hunt-facing live demo URL  
- Docker Compose demo stack  
- Changing product UI or MCP tools  
- Non-generic / branded customer scenarios  
- Committing real tokens or `.demo-data/`

## Verification

1. `/api/health` OK on loopback 8787.  
2. Tailscale URL loads `/ui/` from a tailnet browser.  
3. After seed + pre-auth: Now shows resume cue for the landing-page thread; My work lists the three projects and open/finished mix.  
4. Seed text contains only generic phrases (spot-check titles and resume steps).

## Success

Operator can record a Supademo against the Tailscale UI URL with a populated, calm dummy Hub and no personal content on screen.
