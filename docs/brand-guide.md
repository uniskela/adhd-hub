# Progress Hub brand guide

**Small steps. Your pace.**

Progress Hub gives unfinished work a place to wait. The identity should feel grounded, clear, and welcoming when someone returns after a break. The product’s full name is **ADHD Progress Hub**; use **Progress Hub** in the interface and wordmark.

## Logo and icon

![Progress Hub logo](assets/logo.svg)

The **Next step** mark combines a soft upward bend with a gold dot. The bend represents picking up a thread; the dot is a thought kept for later. Its open shape leaves room to continue. The symbol is deliberately simple enough for a favicon.

- [App icon / favicon](assets/icon.svg): square SVG with a teal tile, ivory path, and gold dot.
- [Light-surface wordmark](assets/logo.svg).
- [Dark-surface wordmark](assets/logo-dark.svg).
- [Visual brand sheet](assets/brand-sheet.html): open locally in a browser, or print to PDF.

Use the icon at 32 px or larger in the app and 16 px for the favicon. Use the wordmark at 180 px or wider. Keep clear space of at least one-quarter of the icon width around standalone marks. Preserve the aspect ratio, colour relationships, and rounded corners. Do not add gradients, bevels, glow, or animation. The SVG wordmarks use live system-font text for editability; glyphs can vary slightly by operating system. For fixed print artwork, outline the type in a vector editor.

## Colour system

| Role | Light | Dark | Use |
| --- | --- | --- | --- |
| Canvas | `#F7F6F1` | `#0D1210` | Page background |
| Header / navigation | White `#FFFFFF` | `#101613` | Primary chrome |
| Primary surface | White `#FFFFFF` | `#151D19` | Intentional grouped content |
| Elevated surface | White `#FFFFFF` | `#1B2520` | Dialogs and popovers |
| Text | `#20332C` | `#E7EEEA` | Headings and body |
| Secondary text | `#617069` | `#98A89F` | Supporting text |
| Primary action | Teal `#176B60` | Mint `#7ACDB6` | Action, focus and selection |
| Selected subtle background | `#EFF1EC` | `#172A24` | Selected rows/tabs |
| Divider | `#D7DDD8` | `#2A3731` | Thin boundaries |
| Achievement accent | `#B18430` | `#DDBB68` | Milestones only |
| Destructive action | `#AB3546` | `#F08C99` | Delete and irreversible actions |
| Destructive action | Berry `#AB3546` | Rose `#FFACB8` | Delete and irreversible actions |

Gold `#EFC978` is a small accent, not body text on white. Use colour with labels and state text: earned badges say **Earned**, tabs expose selection, and destructive buttons name the action. Primary labels and normal body/secondary text should meet WCAG AA contrast in both modes; focus outlines should remain visible. The interface follows the system theme unless the user chooses otherwise.

## Type, spacing, and buttons

Use the local system sans-serif stack; no font download is required. Body: 15 px / 1.6. Headings: 1.2 line height. Section headings: about 18–20 px. Main headings: 29–41 px, responsive. Labels: about 14 px. Keep long notes near 65 characters per line. All-caps eyebrows are short landmarks, never paragraphs or instructions.

Use spacing steps of 4, 8, 12, 16, 24, and 32 px. Prefer whitespace, alignment, then dividers before introducing extra containers. Ordinary grouped surfaces and controls use roughly 8–10 px corners. The Now focus surface and dialogs may use slightly larger soft corners when that distinction helps. Normal page regions stay flat; reserve shadows for dialogs, popovers, and real elevation.

- **Primary:** teal/mint fill, solid readable label; one primary action per immediate group. Verb first: Start, Resume, Save, Download PNG.
- **Secondary:** quiet outline with text. Use for alternatives such as Choose another, Copy text, or Settings.
- **Destructive:** berry/rose with an explicit action label and confirmation where data will be lost.
- **Close:** a visible 44 × 44 px × button with an accessible label. Settings keeps it visible while content scrolls.
- **Focus:** 3 px accent outline with space around it. Never remove keyboard focus styling.
- **Motion:** brief colour transitions only; honour reduced-motion preferences. No animated XP counters, confetti, audio, or pulsing reminders.

Controls target at least 44 px height. Settings tabs support Left/Right, Home/End, and Tab; Escape closes the dialog. On mobile, keep all four tab names visible and scroll content inside the dialog.

## Voice and attention

Write like a calm collaborator: brief, concrete, and useful. Prefer **Next step saved. You can stop here.** and **Choose one task. Everything else can wait.** Avoid guilt, urgency, lost streaks, or competitive comparisons. Do not promise that one design suits every person with ADHD; allow personal appearance and reward preferences.

The **Now** screen answers: what am I doing, how do I start, and where can I leave it? Keep ranks, badges, charts, and settings on their own screens. Render notes as Markdown and keep long project context expandable.

## Ranks, badges, and sharing

Rewards are opt-in. Each currently finished thread contributes 10 XP. Every five finished threads advances a level. Ranks are personal milestones for the **hub**, not placements among people. The app does not currently have individual reward profiles.

| Finished steps | XP | Rank | Badge earned |
| --- | --- | --- | --- |
| 0 | 0 | Seedling | — |
| 1 | 10 | Seedling | First step |
| 5 | 50 | Sprout | Finding rhythm |
| 15 | 150 | Grower | Taking root |
| 30 | 300 | Pathfinder | Branching out |
| 60 | 600 | Wayfinder | Making space |
| 100 | 1,000 | Trailblazer | 100 little wins |

There are no deadlines or streak requirements. Breaks do not reduce totals. Reopening, deleting, or restoring data can change ranks and badges because they reflect current records; these are not a permanent award ledger. Duplicate completion requests do not award extra XP.

Share cards use the light brand palette for predictable exports. Users preview a card, download a PNG, copy text, or open their device’s share sheet if supported. Exports contain only rank, level, XP, finished count, earned badge names, and the public repository URL (`github.com/uniskela/adhd-hub`). They omit task/project names, notes, tokens, account details, and server URLs. No public profile or hosted link is created.

## Future leaderboard direction

The reward payload has stable rank/badge IDs and a version for future integration. A leaderboard remains a separate feature: it would need opt-in individual profiles, clear scope, a trusted completion ledger, abuse handling, consent to publication, and withdrawal/deletion controls. Decide how imported work and reopened tasks count before comparing people. Preserve private, noncompetitive use as the default. See [reward roadmap](rewards-roadmap.md).
