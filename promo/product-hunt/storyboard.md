# ADHD Progress Hub · Product Hunt launch film — storyboard

**Runtime:** 17.5 s, seamless loop · **Frame:** 1920 × 1080, 16:9, 60 fps (1050 frames)
**Grid:** 120 BPM, so one beat = 0.5 s and one bar = 2 s. Every landmark below sits on a beat or a half-beat.
**Theme:** light warm paper throughout, with one dark interlude for the coding-agent scene (the real dark palette).
**Viewer takeaway (muted):** *"This remembers my unfinished work and helps me pick it back up."*

## The one idea: the gold dot

The dot is the brand's "thought saved for later" (brand guide: *"The gold dot is a thought saved for later"*). It is the only object on screen in frame 0 and frame 1050, and it never cuts:

| Scene | What the dot is doing |
| --- | --- |
| 1 | Hops between environments, dropping a fragment of work at each one |
| 2 | Comes to rest under "Where was I?", then the Now card blooms out of it; it docks beside **Where you left off** and presses **Resume** |
| 3 | Rides the card as it unfolds into **My work**, steps down the rows and stops on *Fix deployment* |
| 4 | Opens the dark agent scene (the mask grows from the dot), then carries the thread along each agent connection, through the Hub |
| 5 | Opens the light scene again, presses **Pause and leave a note**, then **Save and pause**, and docks beside the new **Where you left off** — the same spot it docked in scene 2 |
| 6 | Traces the "Next step" bend, lands exactly on the logo's own dot, and the static wordmark appears around it. It then lifts off and drifts back to frame-centre, which is frame 0 |

## Sources for every product claim

| Claim / visual on screen | Where it comes from in the repo |
| --- | --- |
| "Welcome back", "Where you left off", **Resume**, **Choose something else**, "last touched …" | `src/adhd_hub/ui/js/now.js` (`focusStageLabel`, `renderFocus`), `docs/public/images/now-desktop.png` |
| "You're on it", **Mark step done**, **Pause and leave a note** | `now.js` working state |
| "Leave a note for later", "What's the next tiny step?", **Save and pause**, **Keep working** | `now.js` pause form |
| Toast "Next step saved. You can stop here." | `now.js` line ~242, brand guide voice section |
| Start cue "Start with the smallest part. You can leave a note for later whenever you stop." | `now.js` (shown when a step has no saved resume step) |
| My work: heading, subtitle, Projects rail, All projects, Open / Later / Finished counts, rows with **Left off:**, project line, relative time, **In focus** badge, chosen-row teal inset edge, selected-row tint | `docs/public/dashboard.md`, `docs/public/images/my-work-desktop.png`, `js/work.js`, `app.css` (`.thread-*`) |
| "check overlap", "resume context", "save progress" | MCP tools `check_overlap`, `session_digest`, `upsert_progress` / `pause_thread` (README tool table, `AGENTS.md`) |
| Cursor, Codex, Claude Code | Shipped adapters: `adapters/cursor-*`, `adapters/codex.md`, `adapters/claude-code.md` |
| Self-hosted, open source, MCP | README (Docker/uv install, MIT licence, Streamable HTTP + stdio MCP) |
| Dark scene colours | `app.css` `:root[data-theme="dark"]`, brand guide colour table |
| Logo, icon, "Next step" bend | `docs/public/assets/logo.svg`, `icon.svg` (geometry copied verbatim, never animated) |

Not shown because it is roadmap or out of scope: merge/dedupe suggestions, mobile capture, energy modes, leaderboards, any autonomous Hub "agent". The Hub is drawn as a store the agents talk to, never as an actor.

All task data is dummy, in the style of the README gallery.

## Beat map

Times are seconds. "Beat" = sound-sync landmark from the brief.

### 1 · The problem — 0.00 → 2.75

| Time | Event |
| --- | --- |
| 0.00 | Warm paper, only the gold dot at frame centre (identical to the last frame). |
| 0.05–0.40 | Five environment labels rise in, staggered: **Cursor**, **Dev LXC**, **Laptop**, **Claude**, **Codex**. Typographic only, secondary-text grey, 30 px. |
| **0.45** ① | Dot springs to Cursor → chip *Refactor auth* pops out of it. |
| 0.80 / 1.15 / 1.50 / 1.85 | Dot hops round the ring: Dev LXC (*Finish migration*) → Laptop → Claude (*Fix deployment*) → Codex (*Test API*). Each hop is a shallow arc on a sine travel ease with ~1 % landing overshoot; peak speed stays near 70 px/frame. Brisk, not frantic. |
| 1.60–2.40 | Everything drifts 6 % outward from centre and dims to ~45 %. Context is visibly scattering. |
| 1.90–**2.00** ② | **Where was I?** (120 px, word by word, landing on the beat). The dot swings round the right of the headline and settles under it at 2.27. |
| 2.00–2.70 | Hold. Nothing moves except the settle. |

*Communicates:* work and thoughts are spread across tools and machines.

### 2 · The Hub catches the thread — 2.70 → 5.50

| Time | Event |
| --- | --- |
| 2.70–2.90 | Question lifts out. Labels fade. Three chips sink toward centre (they will reappear as rows in scene 3). |
| 2.85–3.40 | The *Refactor auth* chip sheds its border and glides up to become the card title. |
| **3.00** ③ | The real Now card blooms out of the dot (spring, 16 px radius × 1.5). |
| 3.30–3.45 | Eyebrow **Welcome back**, meta *Auth service · last touched 4 days ago*, ⋯ button. |
| 3.60–3.95 | Dot slides to the card's left margin. |
| **4.00** ④ | **Where you left off** panel opens beside the dot: *Finish the auth callback test.* |
| **4.50** | **Resume** springs in, then **Choose something else** and the Project notes fold. |
| 4.75–5.00 | Dot moves onto **Resume**; press on 5.00. |

*Communicates:* one place answers "what was I doing and what's next" — the first aha.

### 3 · One place for unfinished work — 5.50 → 8.00

| Time | Event |
| --- | --- |
| 5.45–5.60 | Card contents fade except the title. |
| 5.50–5.95 | Card shell morphs into the My work step card; title glides into row 1. Dot rides to the row margin. |
| **6.00** ⑤ | Rows 2–4 unfold downward. Around them: **My work** heading and subtitle, Projects rail (All projects · Auth service 2 · Homelab 1 · Deploy pipeline 1), **Open 4 · Later 0 · Finished 3**. Row 1 has **In focus** and the teal inset edge because we just pressed Resume. |
| 6.00–6.35 | Caption **Your unfinished work. One place.** |
| 6.45 / 6.80 / 7.15 | Dot steps down the rows and stops on *Fix deployment*, which takes the selected tint. |
| 7.70–7.95 | Caption out. |

*Communicates:* every half-finished thing, each with a "Left off" cue, in one calm list.

### 4 · Works with your coding agents — 8.00 → 10.50 (dark)

| Time | Event |
| --- | --- |
| 8.00–8.45 | The *Fix deployment* row lifts; a dark canvas circle grows from the dot past all four corners. |
| 8.10–8.55 | The row becomes a compact Hub card (dark surface): Progress Hub icon + name, *Fix deployment*, *Deploy pipeline · last touched 2 days ago*, *Left off: New base image builds locally.* |
| **8.50** ⑥ | **Cursor**, **Codex**, **Claude Code** land around the Hub; hairline connections draw in. Caption **Your agents can remember too.** |
| 8.60–8.85 | Dot runs Hub → Cursor. Label **check overlap**; under Cursor: *Already in progress*. |
| 8.95–9.40 | Dot runs Cursor → through the Hub → Codex. Label **resume context**. |
| 9.50–9.95 | Dot runs Codex → through the Hub → Claude Code. Label **save progress**. |
| 10.00–10.25 | Dot returns into the Hub; meta changes to *last touched just now*. |

Each connection turns mint as the dot travels it, so information and dot share one path.

*Communicates:* agents check for duplicate work, pick up context and save progress through MCP. The Hub is the shared memory, not an agent.

### 5 · Stop without losing your place — 10.30 → 13.60

| Time | Event |
| --- | --- |
| 10.30–10.70 | Warm paper circle grows from the dot; the Hub card morphs into the Now card: **You're on it** · *Fix deployment* · start cue · **Mark step done** / **Pause and leave a note**. |
| 10.88–11.20 | Dot moves onto **Pause and leave a note**, press at 11.20. |
| 11.25–11.55 | Card grows into the real pause form: **Leave a note for later**, *What's the next tiny step?*, focused field, **Save and pause** / **Keep working**. |
| 11.24–11.55 | Dot drops to the field's margin: the thought being written. |
| 11.42–11.92 | Typed: *Verify the Docker health check.* (caret computed from time). |
| 11.72–11.98 | Dot moves onto **Save and pause**. |
| **12.00** ⑦ | Dot presses **Save and pause**. |
| 12.05–12.60 | **The key move.** The focused field contracts onto the sentence; the sentence lifts and settles as the resume text; the tinted panel blooms back out from the sentence; eyebrow becomes **Welcome back**; buttons become **Resume** / **Choose something else**. The dot swings out past the card's left edge (never over the text) and docks beside the panel exactly as in scene 2. |
| 12.25 | Toast: *Next step saved. You can stop here.* |
| **12.50** ⑧ | **Where you left off** label lands. |
| 12.60–13.60 | Caption **Stop now. Pick it up later.** |

The sentence the viewer watched being typed is the same object that becomes the resume cue, so "stopping creates the way back" is shown, not told. The two docking positions rhyme on purpose.

### 6 · Brand payoff — 13.60 → 17.50

| Time | Event |
| --- | --- |
| 13.60–13.90 | UI and caption fade back to paper. Dot keeps moving. |
| 13.70–14.10 | Dot glides to where the logo's bend will start. |
| 14.10–14.45 | Dot traces the bend (right, curve, up) leaving a teal stroke the exact width of the logo path. Drawn as a separate path; the logo asset is untouched. |
| 14.45–14.60 | Dot hops back to the exact spot of the logo's own dot. |
| **14.50–14.80** ⑨ | Static wordmark fades in around it (opacity only — no scale, no movement, no redraw). The film dot sits on the logo's dot pixel-for-pixel. |
| 15.00 | **Small steps. Your pace.** |
| 15.25 | **ADHD Progress Hub** · *Self-hosted continuity for unfinished work.* |
| 15.40 | *Open source · MCP · Cursor · Codex · Claude Code* |
| 15.60 | **Now on Product Hunt** |
| 15.60–16.90 | Hold for reading. |
| 16.90–17.20 | Everything fades except the dot. |
| 16.90–17.50 | Dot drifts to frame centre and comes to rest = frame 0. |

## Sound

Design for a restrained electronic track at **120 BPM** (bar = 2 s). The film reads fully muted; captions carry the story.

| # | Time | Sync moment | Optional UI sound |
| --- | --- | --- | --- |
| 1 | 0.45 → 1.85 | Fragments arrive (5 hops) | very soft tick per hop |
| 2 | 2.00 | "Where was I?" | none — let the track drop out briefly |
| 3 | 3.00 | Hub catches the dot | card settle |
| 4 | 4.00 | Resume cue appears | soft click |
| 5 | 6.00 | My work unfolds | card settle |
| 6 | 8.50 | Agents connect | quiet spring tick |
| 7 | 12.00 | Save and pause | soft click |
| 8 | 12.50 | Where you left off returns | small confirmation |
| 9 | 14.50 | Logo lands | small confirmation |

`sfx.py` renders these cues as a quiet synthesized stem (`out/sfx.wav`). Music is not bundled; drop a licensed 120 BPM track on the grid.

## Design decisions

- **Real UI, rebuilt.** Cards are reconstructed from `app.css` values (16 px card radius, 32 px padding, 24 px gaps, 10 px controls, Figtree, token colours) and scaled ×1.5 (Now) and ×1.2 (My work) so text survives Product Hunt's downscaled player. Copy is verbatim from the UI source.
- **The UI itself never "animates" in the film the way the app wouldn't.** Morphs happen between scenes. Within the product surface the only motion is what a person causes: a press, typing, a state change, a toast.
- **One dark interlude.** Agents are developer-side, so scene 4 uses the real dark theme. Both theme changes are circles that grow from the dot and pass every frame corner before the scene underneath is removed. The travelling card exists in a light and a dark copy; the top copy is clipped by the same circle, so the card changes theme exactly where the mask edge crosses it — no grey crossfade.
- **No logos for third-party tools** — names only, in the UI's own pill style.
- **Captions** are one line, 60 px, centred, word-by-word in and out, never overlapping another caption's window.
- **Typing** shows *Verify the Docker health check.* rather than the brief's *Next: …* because the real field is already labelled "What's the next tiny step?".

## Key-still review (would a stranger get it?)

Reviewed `stills/01–04` as if seeing Progress Hub for the first time, before building the motion.

| Still | Reads as | Changes made |
| --- | --- | --- |
| 01 Scattered context | Work spread across tools and machines; "Where was I?" names the feeling. Clear without sound. | None to the frame. In motion the Cursor → Codex hop crossed the whole frame at ~212 px/frame, which read as frantic, so the ring order changed and hops got a gentler ease. |
| 02 Where you left off | A calm card that answers the question: the task, the exact next step, one button. The first aha. | The dot sat on the end of "Resume"; it now presses inside the button's right padding. |
| 03 Agent continuity | Three named coding agents wired to one Progress Hub card; plain-language labels say what each connection does; "Already in progress" shows the duplicate-work check. | Caption moved down to tighten the group. "save progress" now appears during the trip to Claude Code so it is on screen long enough to read. |
| 04 Product Hunt card | Logo, the brand line, the full product name, what it is, what it works with, where to find it. | Scene-4 connection lines leaked into this frame (a child `visibility` overriding a hidden parent). Fixed. |

## Final QA (from `capture.py qa`, see `qa/report.json` and `qa/contact-sheet.png`)

Checkpoints: 0 %, 25 %, 50 %, 75 %, 100 % and every beat above.

| Check | Result |
| --- | --- |
| Same timestamp renders the same frame, whatever was rendered before | Pass (`deterministic_seek`) |
| First frame equals last frame (seamless loop) | Pass, byte-identical PNGs; dot wrap gap 0 px |
| Dot continuity | No jumps; fastest moment ≈ 70 px/frame during a scene-1 hop |
| Dot never crosses display type | Pass at every frame (`dot_over_caption`) |
| Dot stays inside the frame | Pass |
| Caption collisions | None at any checkpoint; in/out windows never overlap |
| Clipping | None found; masks clear all four corners (dark R 1640 px vs 1533 px needed, light R 1480 px vs 1391 px) |
| Colours | Only app.css light/dark tokens and gold `#EFC978` (dot and logo only); no gradients, glow or blur |
| Smallest copy | The **In focus** badge, 12 px × 1.2 = 14.4 px at 1080p (row project names and times 15.6 px); every caption is 60 px or larger, so the story survives a downscaled player |
| Product claims | Every claim maps to the source table above; roadmap items excluded |
| Logo | Rendered only from the verbatim SVG, opacity-only reveal, never scaled or moved |

Known, accepted: in scene 4 the dot passes *under* the Hub card for ~0.1 s on each crossing (it is "inside the Hub"); every exit is at the port opposite its entry, so it never reappears somewhere unrelated.
