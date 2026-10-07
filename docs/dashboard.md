# A calmer dashboard

![My work with Notes & context](images/my-work-notes-hero.png)

*Desktop My work with the Notes & context reader.* See the [README screenshots](../README.md#screenshots) for Now, Progress, and Settings (gallery shots use dummy data).

## Getting around

The dashboard has four main areas:

| Area | Use it for |
| --- | --- |
| **Now** | One current step, resuming, pausing, and Focus mode |
| **My work** | Browse projects and unfinished/finished threads |
| **Progress** | Activity, counts, and optional rewards |
| **Settings** | Appearance, connections, sync, AI helpers, and data |

On desktop, the compact **Appearance** button cycles System → Light → Dark. The same choices live under **Settings → Appearance**; on mobile, use Settings. The browser remembers the preference when storage is available.

## Now: one step at a time

The **Now** screen keeps one chosen step in front of you.

The main card can show:

- **Your next step**, **You’re on it**, or **Welcome back**;
- the project and last-touch time;
- **Where you left off** when a resume step is saved.

Before starting:

- **Start this step** or **Resume** begins the work;
- **Choose something else** picks another thread;
- **Help me choose** ranks quiet/stale open work with a useful resume cue first.

While working:

- **Mark step done** completes it;
- **Pause and leave a note** saves the next pickup action;
- **Focus mode** can hide extra information and optionally run a 15, 25, or 45 minute timer.

The **⋯** menu contains secondary actions such as **Choose another step**, **Open in My work**, **Copy agent prompt**, and **Mark step done** when you are not mid-step.

After completion, the toast offers **Undo**. A failed undo can be retried; once undo has succeeded, a later **Retry** refreshes the UI only and does not send the undo twice.

Below the card, the dashboard links to open steps, this week’s finished steps, and projects. **Gentle checks** show due reminders and older work that may need a keep/snooze decision. Finished threads remain under **My work → Finished**.

## My work: browse and review

Desktop **My work** uses two columns: projects on the left and steps on the right.

Each step row keeps only the useful scan information visible:

- title;
- **Left off:** resume step, or scan line when no resume step exists;
- project name while viewing **All projects**;
- relative last-touch time;
- a badge only for **In focus** or a source issue that needs review.

Click a row to open its notes beside the list.

### Search, create, and review

**Search your work** matches titles, resume steps, goals, scan lines, projects, and progress snippets. The **New** menu contains **New project** and **Leave a reminder**.

When an action needs a yes/no decision, a single **Needs you** line appears above the list. Open **Review** to handle:

- agent project-change approvals;
- forge import offers;
- due reminders.

When nothing needs attention, the line disappears. Focus mode keeps the list usable and adds **Back to Now**.

## AI helpers and scan lines

Scan lines are heuristic by default. Optional LLM rewriting is available under **Settings → AI helpers** or through `ADHD_HUB_AI_*` settings (see [environment variables](environment-variables.md)).

 Status-history audits such as ``[status→open] Undone from …`` after Undo Done never become the scan line or the copy-agent **Progress** snippet — empty is fine when no continuity cue exists; an older eligible human note is preferred when one exists. The scan line spans the full card width and wraps up to two lines (ellipsis when longer). In AI settings, pick a Base URL preset (or custom URL — unknown saved URLs reopen as Custom… with the field filled); Save / Test & Load use the URL field as source of truth. **Test and load models** replaces the Model dropdown with that provider’s chat-capable models (Gemini OpenAI-compat ids drop a leading `models/` / `google/` prefix; embeddings, image/TTS variants, and Gemini flash ids deprecated for new users are hidden — prefer `gemini-3.6-flash`). Default AI timeout is 15s (raise up to 30s for local/proxy models). Stub or truncated AI replies fall back to the heuristic line with a calm toast. On Rewrite failure, the toast shows the outbound model id and a scrubbed provider snippet rather than always blaming a `models/` prefix; timeouts suggest raising Timeout in AI settings. Opt-in **Rewrite scan lines on their own** (default off) rewrites new/changed threads once per content hash and skips the provider when the hash matches; **Summarise notes on their own** (default off) does the same for the Notes reader card on open. **Rewrite scan line** for one step lives in the reader’s **⋯** menu, and **Rewrite all scan lines** lives in the project title’s **⋯** menu; both appear only when **Use AI helpers** is on, so a no-op cannot look like a successful batch. Rewrite all confirms first, covers open steps only, and runs one batch at a time per project (client and server reject a second run with a calm busy state / HTTP 409). Its toast stays sticky for the batch and does not show a fake `0/N`; completion reports `(completed/total)` only when at least one line updated. Tab focus or a live refresh mid-batch keeps the item disabled as **Rewriting…**.


## Live updates and PWA

Open Hub pages listen for authenticated live updates (SSE) and refresh relevant data shortly after Hub-side changes. If the live connection drops, ordinary Refresh and API use still work.

The installable PWA caches the **UI shell only**.  When a newer shell service worker is waiting, a calm sticky toast offers **Refresh** (activates the update and reloads this tab); it does not interrupt mid-task on its own. Under **Settings → Issue sync**, **Last sync** shows last successful or failed forge reconciliation, concise errors, Needs review conflicts, recent change history from the activity ledger (under **Recent changes**), and **Sync now** / **Retry sync** beside any background jobs.

Use **Save a thought** for a quick capture without leaving the current task. When you need to stop, choose **Pause and leave a note**, write the smallest useful next step right on the card, and choose **Save and pause** (**Keep working** or Escape cancels). That step appears under **Where you left off** when you return.

The **Where you left off** area renders saved Markdown (headings, lists, emphasis, and tables) for easier scanning. Raw HTML is escaped and remote images are shown as text descriptions.

**Open**, **Later**, and **Finished** sit in one segmented control beside the project title, each with its count as soon as My work loads. **Later** shows older open work without an overdue warning. The soft **Still relevant?** check now lives only on Now (“Is this still on your list?”), so it is asked in one place. Nothing auto-dismisses.

Select a project to show its title. The pencil beside it opens project editing, the external-link icon opens the repository when a URL is configured, and **⋯** holds **Rewrite all scan lines** when AI is on. On phones the project name becomes the project switcher (ellipsis when long) beside the same icons. Menus (**New**, the project **⋯**, the projects list **⋯**, and the reader **⋯**) close on Escape with focus back on their button, and flip upward when there is not enough room below, including above the phone bottom bar. Projects can nest under other projects (Notion-style tree in the left rail; chevron expands, row click selects). Selecting a parent filters My work to that project plus all nested descendants; rail open counts aggregate the same way. **Rewrite all scan lines** on a parent rewrites open threads across that scope. Drag the six-dot grip to nest or reorder — on desktop the grip appears on row hover; on phones and touch devices it stays visible with a larger hit target and uses a pointer drag path (not HTML5-only). Keyboard users can Tab to a grip and press Up or Down to move that project one place among its siblings; focus stays on the grip and a calm toast confirms the move. Inbox is not draggable. Tags stay orthogonal (comma-separated labels and tag chips). Use **Suggest tags** (in the projects list **⋯** menu) to review heuristic tag suggestions and apply only what you confirm. Each project shows its name and open-step count; hover for when it was last touched and its tags. Add an HTTP(S) repository URL to expose the repository action; repository URLs containing credentials are rejected. Choose **This project has no repository** when creating a project to skip a repo URL and use the project as a folder for other projects only — forge sync no-ops for those.

Project settings opens with the basics (name, description, tags, repository). **More options** folds the short name (slug), parent project, issue sync connection, folder on your computer and the issue sync overrides (owner, repository name, wiki path, board id). **Rename short name…** and **Delete project…** sit on their own row at the bottom. Every dialog shares one pattern: a title row with a Close (X) button, labelled fields stacked one per row, and the main action first with a quiet Cancel beside it. Escape or Close always cancels. Notifications (toasts) stack in the corner with a coloured dot for their kind, an optional action such as **Undo**, and a full-size dismiss button.

## Optional small wins

In **Settings → Appearance**, turn **Gentle rewards** on or off and choose a daily goal of one, three, or five finished threads. Rewards start off by default. These preferences are saved per browser.

- Each currently finished thread contributes 10 XP. Every five finished threads adds a level.
- XP is calculated from actual hub records, including completions made by assistants; refreshing or repeating a completion does not add another thread's XP. Completion retries preserve the original date and do not append duplicate status notes.
- Daily counts and the activity chart use the hub's configured timezone. Taking a break does not reset your level.
- Completing a thread shows one short, quiet acknowledgment in the shared toast stack (alongside the Done/**Undo** toast when both appear). There are no sound effects, confetti, or streak penalties, and reduced-motion preferences are respected. **Undo** dismisses the rewards cue so it does not overlap the Restored toast.
- Rewards reflect the current data: reopening/deleting completed work or restoring a backup can change totals. They are not a separate permanent reward ledger.

The daily goal is an optional cue, not a deadline. It can be changed or switched off at any time.

## Browser verification

The smoke script uses a temporary hub, a temporary database, and sample projects. It does not change your running hub.

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python scripts/browser_smoke.py
uv run --with playwright python scripts/ui_polish_smoke.py
# Optional: refresh README/docs product shots under docs/images/
ADHD_HUB_SCREENSHOT_DIR=docs/images uv run --with playwright python scripts/capture_readme_screenshots.py
```

The UI polish check exercises the four screens in both themes at desktop, tablet, and phone widths, checks navigation and keyboard disclosures, and captures screenshots. `capture_readme_screenshots.py` seeds a temporary hub with dummy projects and writes the light-theme desktop shots used in the README.

Set `ADHD_HUB_BROWSER_EXECUTABLE` to use an existing Chromium binary. Screenshots default to `/tmp/adhd-hub-preview`; override with `ADHD_HUB_SCREENSHOT_DIR`.

Switching projects clears the previous project’s actions while the new one loads. Late responses cannot overwrite a newer selection; failed loads show a retry message.

## Settings and sharing

Settings groups its sections as **You** (**Appearance**, **Account**), **Connections** (**Coding agents**, **Remote access**, **Phone alerts**, **Issue sync**, **AI helpers**) and **Data** (**Your data**). Each section is a card of rows with the label on the left and the control on the right; rarely used fields sit under **Advanced**. Desktop uses the left section list; on phones Settings opens on that list and each section has an **All settings** link back. Appearance (theme, accent colour, gentle rewards, daily goal and time zone) saves as you change it. Sections that hold keys or tokens (Phone alerts, Issue sync, AI helpers) and the coding-agent defaults keep their own Save button. Issue sync connections fold to one line each until opened. AI helpers are off by default, and lists always lead with where you left off. Forge setup (default connection vs project repos, import policies, PATs) is documented in [Forge permissions](forge-permissions.md).

Progress opens with one **Last 14 days** card: amber bars for steps added and teal bars for steps finished, a line with the totals, and your open and this-week counts. Hover or focus a day to see its numbers, or choose **Show as a table** for the same data as rows. With rewards enabled, a rank card shows your rank, level and XP, how many finished steps remain until the next rank, and **Today’s gentle goal**; beside it, **Milestones** lists the six completion badges as **Earned** or **Not yet**. With rewards off, one line says so and **Turn them on in Settings** takes you straight to the switch. **Share progress** (top right, rewards on) previews the exact export, then you can download a PNG or copy the text. Compatible devices also offer a share sheet. Nothing is posted automatically. The preview excludes task titles, project names, notes, and connection details. Ranks represent this hub's records; there is no public leaderboard yet.

See the [brand guide](brand-guide.md) for palette, assets, buttons, milestone thresholds, and tone of voice.

The Settings footer links to the public GitHub repository and shows the running server’s version from `/api/health`. Share text includes the public repository link, and PNG cards print its URL in the footer. Your private hub address is never used for that attribution.

Project tags and parent links are preserved when you rename a project slug. Archiving a parent clears children’s parent links so they become top-level again.
The organiser adds only the selected tags and preserves project settings (including parent). Projects archived after suggestions were loaded, or selections exceeding the eight-tag limit, are skipped so you can review them again.

### Workspace overview and controls

Now includes open-step, weekly completion, and project counts below the chosen step. Focus mode hides the overview to keep a single task in view. Counts use the same live overview as Progress.

Project search and tags stay tucked behind the filter button at the top of the projects list. It reveals **Find a project** (name, slug, or tag), tag chips, and a result count; closing it clears both, so no hidden filter is left behind. The Projects rail shows a collapsible parent/child tree with **unlimited nesting** (expand state remembered in this browser). On desktop, drag a project onto another to nest it, or into the gap between rows to reorder siblings; `parent_slug` and `sort_order` persist. On small screens the rail opens as a full-screen left drawer (backdrop, Escape, focus trap). Drag the six-dot grip to nest or reorder — while dragging, the list auto-scrolls near the top/bottom edges so off-screen targets stay reachable. After a drop (or a cancelled drag), the drawer stays open so organising can continue: a move refreshes the tree via `loadAll` without closing the drawer, and only an intentional project pick (or All projects / close / backdrop) dismisses it. Ghost clicks and backdrop taps from the same pointer release are ignored briefly. **Suggest tags** and the drag tip live in the list’s **⋯** menu so switching projects remains the primary browse action. Nested rows remain inside the viewport rather than requiring horizontal scrolling. Project rows show open-step counts; zero-open projects are visually quieter without being hidden. **Archived projects (n)** stays collapsed at the bottom. The edit form Parent select remains available as a touch-friendly fallback for hierarchy changes.

The reader keeps one primary action, **Focus on this** (or **Return to focus**), beside **Mark done** and a **⋯** menu. The menu names where the step came from and holds **Open issue #**, **Refresh from source issue**, **Copy link**, and, when AI is on, **Summarise notes with AI** and **Rewrite scan line**. A source issue that has changed or conflicts shows as a short notice above the notes, with **Review changes**. A live refresh keeps the reader on the same step while it is still listed.

Light uses warm paper surfaces and teal controls; dark uses charcoal surfaces and mint controls. Text is set in the bundled Figtree font. Theme cycling and AI Test / Load Models settings remain available.

Appearance also offers named accent presets (Indigo keeps the previous look) and a custom colour picker. The selection saves in this browser; Default restores the two built-in palettes. Custom shades adapt to maintain readable text and selected states in light and dark mode. Status and warning colours keep their semantic roles.
