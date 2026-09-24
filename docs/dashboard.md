# A calmer dashboard

On desktop, use the compact **Appearance** button in the app header to cycle System → Light → Dark (the button shows the current mode). The same choices are available under **Settings → Preferences**; on mobile, use Settings. The preference is saved in this browser and follows operating-system changes when set to System. If browser storage is blocked, the dashboard still works and preferences last for the current page visit.

The home screen is **Now**: one chosen task, its next step, and one clear **Start** button. Your choice is remembered in this browser. **Start** (or **Pause here** while working) and **Done** stay visible; **More actions** holds **Choose another** and **Copy agent prompt**. With no task selected, choose one from your work or use **Help me choose** for a suggestion. **My work** is the browsing view for projects and threads; choosing **Focus on this** returns to Now. **Progress** contains activity and optional rewards, so the starting screen stays quiet. Finished threads remain available under **My work → Finished**.

On My work, each thread card shows a short **scan line** under the title when Focus, Resume, Goal, Next, or a safe progress snippet saved on that thread is available (heuristic by default; optional local LLM rewrite when AI scan-lines are enabled in **Settings → Preferences** or via `ADHD_HUB_AI_*` — see [environment variables](environment-variables.md)). In AI settings, **Test & Load Models** fills the Model dropdown from the provider once a base URL is set. Full detail stays in Notes. Each row keeps **Focus on this** and **Read notes** visible. **More options** holds source links, refresh, **Rewrite scan line** (AI when enabled; heuristic fallback otherwise), and copy-link controls; source conflicts and refresh alerts remain visible without opening it. Only meaningful states, such as **In focus** or **Finished**, get a badge. **Read notes** opens the Notes & context reader for that thread’s saved continuity (Goal, Focus, Next, Blocked, Resume, notes, and forge activity). See [Notes & context](notes.md).

Open Hub pages listen for authenticated live updates (SSE) and refresh relevant data shortly after Hub-side changes; if the live connection drops, ordinary Refresh / API use still works. Under **Settings → Forge**, **Sync health** shows last successful or failed forge reconciliation, concise errors, Needs review conflicts, recent change history from the activity ledger, and a Retry sync path beside Forge jobs.

Use **Save a thought** for a quick capture without leaving the current task. When you need to stop, choose **Pause here**, enter the smallest useful next step, and save it. That step appears when you return.

The **Where you left off** area renders saved Markdown (headings, lists, emphasis, and tables) for easier scanning. Raw HTML is escaped and remote images are shown as text descriptions.

Search narrows the loaded thread list in My work. **Pick up later** shows older open work without an overdue warning.

Select a project to show its title. The pencil button beside the title opens project editing in a focused dialog. Projects can carry light **tags** (comma-separated in project settings) and the rail can filter by tag. Use **Organise** to review heuristic tag suggestions and apply only what you confirm. Each project shows open-step count and a calm last-touch cue. Add an HTTP(S) repository URL to show an **Open repo** button beside the title; repository URLs containing credentials are rejected.

## Optional small wins

In **Settings**, turn **Enable rewards** on or off and choose a daily goal of one, three, or five finished threads. Rewards start off by default. These preferences are saved per browser.

- Each currently finished thread contributes 10 XP. Every five finished threads adds a level.
- XP is calculated from actual hub records, including completions made by assistants; refreshing or repeating a completion does not add another thread's XP. Completion retries preserve the original date and do not append duplicate status notes.
- Daily counts and the activity chart use the hub's configured timezone. Taking a break does not reset your level.
- Completing a thread shows one short, quiet acknowledgment. There are no sound effects, confetti, or streak penalties, and reduced-motion preferences are respected.
- Rewards reflect the current data: reopening/deleting completed work or restoring a backup can change totals. They are not a separate permanent reward ledger.

The daily goal is an optional cue, not a deadline. It can be changed or switched off at any time.

## Browser verification

The smoke script uses a temporary hub, a temporary database, and sample projects. It does not change your running hub.

```bash
uv run --with playwright playwright install chromium
uv run --with playwright python scripts/browser_smoke.py
uv run --with playwright python scripts/ui_polish_smoke.py
```

The UI polish check exercises the four screens in both themes at desktop, tablet, and phone widths, checks navigation and keyboard disclosures, and captures screenshots.

Set `ADHD_HUB_BROWSER_EXECUTABLE` to use an existing Chromium binary. Screenshots default to `/tmp/adhd-hub-preview`; override with `ADHD_HUB_SCREENSHOT_DIR`.

Switching projects clears the previous project’s actions while the new one loads. Late responses cannot overwrite a newer selection; failed loads show a retry message.

## Settings and sharing

Settings is a full application destination with categories for **Preferences**, **Account**, **Agents & install**, **Windows / MCP**, **OpenClaw**, **Forge**, and **Data**. Desktop uses the left category navigation; mobile opens a simple Settings index and each category has a Back to settings action. Appearance and rewards save automatically in this browser; timezone uses **Save**. Password controls are under Account. Forge setup (Default profile vs project repos, import policies, PATs) is documented in [Forge permissions](forge-permissions.md).

With rewards enabled, Progress shows the hub's current rank, upcoming rank, and six completion badges. Use **Share progress** to preview the exact export, then download a PNG or copy the text. Compatible devices also offer a share sheet. Nothing is posted automatically. The preview excludes task titles, project names, notes, and connection details. Ranks represent this hub's records; there is no public leaderboard yet.

See the [brand guide](brand-guide.md) for palette, assets, buttons, milestone thresholds, and tone of voice.

The Settings footer links to the public GitHub repository and shows the running server’s version from `/api/health`. Share text includes the public repository link, and PNG cards print its URL in the footer. Your private hub address is never used for that attribution.

Project tags are preserved when you rename a project slug.
The organiser adds only the selected tags and preserves project settings. Projects archived after suggestions were loaded, or selections exceeding the eight-tag limit, are skipped so you can review them again.

### Workspace overview and controls

Now includes open-step, weekly completion, and project counts below the chosen step. Focus mode hides the overview to keep a single task in view. Counts use the same live overview as Progress.

My work has project search (name, slug, or tag) combined with the tag filter, plus a visible result count and empty state. Project rows show open-step counts; the selected project exposes its tags. **Suggest tags** opens the existing editable preview before applying suggestions.

Thread **Actions** opens a compact panel without expanding the row. Only one panel stays open, Escape closes it and returns focus, and tabbing away closes it. Focus and Read notes remain directly available; source conflicts stay visible. AI scan-line rewriting and source refresh remain in Actions.

Light uses porcelain surfaces and indigo controls; dark uses charcoal surfaces and periwinkle controls. Theme cycling and AI Test / Load Models settings remain available.

Appearance also offers named accent presets and a custom colour picker. The selection saves in this browser; Default restores the two built-in palettes. Custom shades adapt to maintain readable text and selected states in light and dark mode. Status and warning colours keep their semantic roles.
