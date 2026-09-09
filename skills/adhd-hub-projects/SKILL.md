---
name: adhd-hub-projects
description: >-
  ADHD Progress Hub project registry — resolve or upsert projects by workspace
  path (website, chrome extension, homelab, etc.), list projects, and optional
  per-project forge targets. Use when categorising work by project or mapping a cwd.
---

# ADHD Hub — projects

MCP server: **`adhd-hub`** at `/mcp` (Streamable HTTP, bearer authentication). If unavailable, continue the user’s work and report that project registration could not be saved.

## Resolve from cwd

```
resolve_project(workspace_path="<absolute workspace>", create_if_missing=true)
```

If the result is `error: not_found`, do not invent a project id or slug. Resolve with creation enabled only for a known project.

Use the returned `slug` on all later `upsert_progress` / `upsert_thread` calls.

## Register or update

```
upsert_project(
  title="My Website",
  slug="my-website",           # optional; derived from title if omitted
  workspace_path="Z:/Projects/my-website",
  description="Marketing site",
  forge_owner="alex",          # optional override
  forge_repo="my-website",     # optional; default = hub memory repo
  forge_wiki_path="",          # blank = repo root (primary memory)
  forge_project_id=null        # optional Gitea/GitHub board id override
)
```

## Rename / delete

```
rename_project(slug="old", new_slug="new", title=null, reason="…")
delete_project(slug="…", delete_progress=false, delete_remote=false, reason="…")
list_pending_actions()
```

These **do not apply immediately**. They queue a pending action; you Approve/Reject in hub `/ui`. Direct apply still works from the UI after its own confirm dialog.

## List

`list_projects` — includes open/done counts per slug.

## Conventions

- Slugs are lowercase kebab-case (`chrome-ext`, `homelab-dns`).
- Prefer absolute workspace paths so multi-machine resolve works.
- Do not invent forge remotes; only set forge_* when the user asks or config already has them.
- Issues are linked via label `project:<slug>` and links inside `PROGRESS.md` / issue body.
- Give a project a durable purpose in its description; put the temporary, verb-led work in a thread title instead.
- Keep one concrete `Now` action and one `Return cue` at the top of active project progress. Record only decisions that change later work, then link to the fuller context.
- Use the [ADHD-friendly writing guide](../../docs/adhd-friendly-writing.md) for concise progress, plan, decision, and handoff templates.
