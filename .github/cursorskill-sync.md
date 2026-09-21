# Sync Hub skills → Cursor Marketplace plugin

The `Sync Cursor skill plugin` workflow copies Hub skills and the Cursor rule into
[`uniskela/adhd-hub-cursorskill`](https://github.com/uniskela/adhd-hub-cursorskill),
applies Marketplace link/setup rewrites, runs the plugin validator, and **opens a
pull request** on the plugin repo. It never pushes to `adhd-hub-cursorskill` `main`.

Operator-facing docs: [`docs/cursor-plugin-skill-sync.md`](../docs/cursor-plugin-skill-sync.md).

## Required credentials (pick one)

### Option A — fine-grained PAT (simplest)

Create a fine-grained personal access token (or machine-user token) with access
**only** to `uniskela/adhd-hub-cursorskill`:

| Permission | Access |
|------------|--------|
| Contents | Read and write |
| Pull requests | Read and write |
| Metadata | Read-only (default) |

Store it as an Actions **secret** on `uniskela/adhd-hub`:

| Name | Where |
|------|--------|
| `CURSORSKILL_SYNC_TOKEN` | Repository secret |

Do not put the token in workflow YAML, docs, PRs, or chat.

### Option B — GitHub App (preferred for least privilege)

Create a GitHub App installed only on `uniskela/adhd-hub-cursorskill` with:

- Repository permissions: **Contents** (read/write), **Pull requests** (read/write)

Configure on `uniskela/adhd-hub`:

| Name | Type |
|------|------|
| `CURSORSKILL_SYNC_APP_CLIENT_ID` | Actions **variable** (App client id) |
| `CURSORSKILL_SYNC_APP_PRIVATE_KEY` | Actions **secret** (App private key PEM) |

When both App credentials and `CURSORSKILL_SYNC_TOKEN` are present, the workflow
uses the App token.

## First-time checklist

1. Add Option A or Option B credentials above.
2. Merge the workflow + `scripts/sync_cursorskill_plugin.py` to Hub `main`.
3. Run **Actions → Sync Cursor skill plugin → Run workflow** (`workflow_dispatch`).
4. Review the draft/open PR on `adhd-hub-cursorskill` (diff + validator).
5. Merge the plugin PR only after the tree matches the path map and
   `node scripts/validate-template.mjs` is green.
6. (Optional) Protect `adhd-hub-cursorskill` `main` so merges require review.

Missing credentials fail the job closed with a pointer to this file.
