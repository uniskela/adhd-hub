# Cursor plugin skill sync

Hub skills under `skills/` and the Cursor rule (`adapters/cursor-rule.mdc`) are the
**source of truth** for the Marketplace client plugin
[`uniskela/adhd-hub-cursorskill`](https://github.com/uniskela/adhd-hub-cursorskill).

When those paths change on Hub `main`, automation copies them into the plugin repository, rewrites Hub-only packaging details, validates the template, and **opens a pull request** on `adhd-hub-cursorskill`.

Automation never pushes directly to the plugin `main` branch.

## Which path applies to you?

| You are… | Do this |
| --- | --- |
| Using the Cursor Marketplace plugin | Install/update the plugin normally; mirrored skills may trail Hub `main` by one reviewed PR. |
| Using project-local `AGENTS.md` | Run `adhd-hub doctor --project .` and `adhd-hub setup . --refresh` after guidance changes. |
| Using CLI-installed global skills | Refresh that installation path separately. |
| Contributing guidance/rule content | Edit the canonical files in the Hub repository, not the mirrored plugin copy. |

## What operators need to know

- Install and configure the plugin from the plugin repo / Marketplace listing.
- Continuity behavior still comes from the same Hub skills and always-apply rule.
- Skill wording may lag Hub `main` by one reviewed plugin PR — that is intentional.
- Per-project `AGENTS.md` injections are **not** updated by Marketplace. After Hub
  guidance changes, run `adhd-hub doctor --project .` and `adhd-hub setup . --refresh`
  on each project (see [project agent setup](project-agent-setup.md#keep-generated-guidance-current)).
- CLI skill installs (`npx skills add` / `setup --install-skills`) are separate from
  Marketplace; refresh whichever path you installed from.

## What contributors should edit where

| Edit | Where |
|------|--------|
| Skill / rule **content** (protocol, versions, guidance) | **This Hub repo** (`skills/…`, `adapters/cursor-rule.mdc`) |
| Packaging, `mcp.json` variables, plugin manifest, logo | **Plugin repo** (`adhd-hub-cursorskill`) |
| Mirrored skill/rule bodies in the plugin | **Do not hand-edit** except packaging emergencies |

If you must hotfix a mirrored file on the plugin side, open a Hub PR with the same
content as soon as possible so the next sync does not revert the fix incorrectly,
and bump `hub_skill_version` / `hub_guidance_version` when the guidance changes.

## Path map

| Hub | Plugin |
|-----|--------|
| `skills/adhd-hub-session/**` | `skills/adhd-hub-session/**` |
| `skills/adhd-hub-projects/SKILL.md` | `skills/adhd-hub-projects/SKILL.md` |
| `skills/env-check/**` | `skills/env-check/**` |
| `adapters/cursor-rule.mdc` (preferred) or `.cursor/rules/adhd-hub.mdc` | `rules/adhd-hub.mdc` |

Not synced: Hub app source, Docker, Graphify companions, OpenClaw adapters,
`adapters/cursor-mcp.json` (wrong variable syntax for Marketplace), secrets.

## Rewrites applied on every sync

- Relative `../../docs/…` links → absolute
  `https://github.com/uniskela/adhd-hub/blob/main/docs/…` URLs
- `adhd-hub-session/reference.md` probe language → Marketplace MCP variables +
  `/api/health` / MCP panel verify (no `uv run python scripts/probe_mcp.py`)
- `env-check` script path language → plugin root / `${CURSOR_PLUGIN_ROOT}`
- README **Upstream sync** table → Hub SHA + `hub_skill_version` /
  `hub_guidance_version` pins
- `skills/env-check/scripts/check_runtime.sh` executable bit preserved

Plugin manifest `version` is **not** auto-bumped on skill sync.

## Triggering a sync

Automatic: push to Hub `main` that touches the path filters above.

Manual: **Actions → Sync Cursor skill plugin → Run workflow**.

Maintainer setup (PAT or GitHub App secrets):
[`.github/cursorskill-sync.md`](https://github.com/uniskela/adhd-hub/blob/main/.github/cursorskill-sync.md).

## Local dry-run

```bash
# From a Hub checkout, with a sibling clone of the plugin:
python3 scripts/sync_cursorskill_plugin.py \
  --plugin-repo ../adhd-hub-cursorskill \
  --hub-sha "$(git rev-parse HEAD)" \
  --dry-run
```

Inspect the plugin working tree, run `node scripts/validate-template.mjs` there,
and discard the changes (or open a plugin PR yourself) — do not push to plugin
`main` from a laptop unless you intend a packaging emergency.
