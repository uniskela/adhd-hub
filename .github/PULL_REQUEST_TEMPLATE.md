## Summary

<!-- What changed and why (scannable bullets are fine). -->

## PR title / squash subject (required)

GitHub squash-merge uses **this PR’s title** as the merge commit subject
(`COMMIT_OR_PR_TITLE`). Body bullets and branch commit messages do **not**
count for Release Please.

- Touches release surfaces (`src/`, `pyproject.toml`, `uv.lock`, `Dockerfile`,
  `docker-compose.yml`): title **must** be `feat:` / `fix:` / `perf:` /
  `revert:` (optional scope) or `type!:` for breaking changes.
- Docs / chore / CI-only: `docs:`, `chore:`, `ci:`, `test:`, etc. are fine.

Examples: `feat(notes): scannable Notes reader`, `fix(ui): midnight stamps`,
`docs: explain squash titles`.

## Checklist

- [ ] Title matches the rules above
- [ ] Wiki / docs updated if behavior or setup changed
