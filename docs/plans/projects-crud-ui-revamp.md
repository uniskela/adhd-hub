# Projects CRUD, forge folder sync, ADHD UI revamp

Approved execution plan (2026-09-08). See also Cursor plan `projects_crud_ui_revamp_030b7d97`.

## Delivered

1. **Project CRUD** — `rename_project` / `delete_project` (store + wiki + REST + MCP). Delete safe by default (`delete_progress` / `delete_remote` opt-in).
2. **Forge root layout** — primary memory uses empty `wiki_path` → `projects/<slug>/PROGRESS.md`. Contents DELETE + PUT-before-DELETE move. Labels `adhd-hub` + `project:<slug>`. Per-project `forge_project_id`. PROGRESS `## Forge` section + issue body progress URL.
3. **UI** — project-first `/ui` with Next-up focus, Settings drawer, rename/delete dialogs (`app.css` / `app.js`).
4. **Docs** — README, forge-permissions, skills, scaffold README layout.
