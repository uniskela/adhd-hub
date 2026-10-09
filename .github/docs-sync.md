# Notify the Uniskela documentation site

The `Notify Uniskela documentation` workflow sends an immediate update notification after README/docs changes merge to `main`. It does not publish the website directly: `uniskela/com` imports reviewed content, runs checks, and proposes a draft PR for review.

The destination GitHub repository is `uniskela/com` (repository name `com`); the public website remains `uniskela.com`. Ensure the GitHub App is installed on `uniskela/com`.

Configure Actions variable `DOCS_SYNC_APP_CLIENT_ID` and Actions secret `DOCS_SYNC_APP_PRIVATE_KEY` using the dedicated documentation GitHub App installed only on `uniskela/com` with Contents read/write permission. The workflow creates a short-lived, destination-only installation token and revokes it after use. It never runs on pull requests or forks and does not check out source code.

Merge the receiver into the destination default branch and configure its `DOCS_SYNC_APP_SLUG` before merging/enabling this notifier. Missing source credentials cause a visible workflow failure. Then run this workflow manually on `main` to test, and verify the destination receiver succeeds. The weekly destination sync remains a fallback. For ADHD Hub, new public pages are selected in this repository’s `docs/manifest.json`; the destination reads that source-owned manifest.

Keep `zensical.toml` and `docs/manifest.json` aligned so user guides and related links resolve on [uniskela.com/docs/adhd-hub](https://uniskela.com/docs/adhd-hub/). Source paths change with the repository layout; slugs preserve the published routes:

- `docs/public/remote-mcp-access.md` → `/docs/adhd-hub/remote-mcp-access/` (and versioned `/next/`, `/0.x/` paths)
- `docs/public/cursor-plugin-skill-sync.md` → `/docs/adhd-hub/cursor-plugin-skill-sync/`

Account-wide registration, configuration, and smoke-test instructions are maintained by the site owner in the `uniskela/com` repository at `docs/docs-dispatch-setup.md`. Do not put App private keys in repository files, PRs, or chats.

GitHub may suppress push-triggered workflows when the original push used `GITHUB_TOKEN`; use the manual run or scheduled destination fallback for such updates. Existing GitHub Pages deployments continue unchanged until the separate documentation migration cutover.

The source manifest remains `docs/manifest.json`; source paths now start with `docs/public/`, while slugs and published URLs stay unchanged. The current destination importer reads this source-owned manifest and accepts `docs/public/` paths; previously released tags retain their own manifests and layouts. Internal contracts, plans and agent guidance are excluded from both Zensical and the manifest. Historical URL signposts are built by Zensical but are not selected as imported user guides.
