# A calmer dashboard

Choose **Appearance → System, Light, or Dark** at the top of the page. The preference is saved in this browser, works on the sign-in page, and follows operating-system changes when set to System. If browser storage is blocked, the dashboard still works and preferences last for the current page visit.

The home screen is **Now**: one chosen task, its next step, and one clear **Start** button. Your choice is remembered in this browser. With no task selected, choose one from your work or use **Help me choose** for a suggestion. **My work** is the browsing view for projects and threads; choosing **Work on this** returns to Now. **Progress** contains activity and optional rewards, so the starting screen stays quiet. Finished threads remain available under **My work → Finished**.

Use **Save a thought** for a quick capture without leaving the current task. When you need to stop, choose **Pause here**, enter the smallest useful next step, and save it. That step appears when you return.

The **Where you left off** area renders saved Markdown (headings, lists, emphasis, and tables) for easier scanning. Raw HTML is escaped and remote images are shown as text descriptions.

Search narrows the loaded thread list in My work. **Pick up later** shows older open work without an overdue warning.

Select a project to show its title. The pencil button beside the title opens project editing in a focused dialog. Add an HTTP(S) repository URL to show an **Open repo** button beside the title; repository URLs containing credentials are rejected.

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
```

Set `ADHD_HUB_BROWSER_EXECUTABLE` to use an existing Chromium binary. Screenshots default to `/tmp/adhd-hub-preview`; override with `ADHD_HUB_SCREENSHOT_DIR`.

Switching projects clears the previous project’s actions while the new one loads. Late responses cannot overwrite a newer selection; failed loads show a retry message.

## Settings and sharing

Settings has a fixed **Close settings** button and four sections: **Preferences**, **Account**, **Connections**, and **Data**. Arrow keys, Home, and End move between tabs; Escape closes the dialog. Appearance and rewards save automatically in this browser; timezone uses **Save**. Password controls are under Account. Assistant setup, encrypted OpenClaw connection settings, alert controls, and optional forge configuration live under Connections.

With rewards enabled, Progress shows the hub's current rank, upcoming rank, and six completion badges. Use **Share progress** to preview the exact export, then download a PNG or copy the text. Compatible devices also offer a share sheet. Nothing is posted automatically. The preview excludes task titles, project names, notes, and connection details. Ranks represent this hub's records; there is no public leaderboard yet.

See the [brand guide](brand-guide.md) for palette, assets, buttons, milestone thresholds, and tone of voice.

The Settings footer links to the public GitHub repository and shows the running server’s version from `/api/health`. Share text includes the public repository link, and PNG cards print its URL in the footer. Your private hub address is never used for that attribution.
