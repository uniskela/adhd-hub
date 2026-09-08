# Cursor hooks (sample)

Copy useful hooks from [cursor-hooks.sample.json](cursor-hooks.sample.json) into your Cursor hooks config (see Cursor docs for the current hooks file location / schema — it varies by version).

Goal:

- **sessionStart** → `resolve_project` + `session_digest` + `check_overlap`
- **stop** → `upsert_progress` if work is incomplete

Hooks are a backstop; also install skills:

```bash
npx skills add ./skills -g
# later: npx skills add uniskela/adhd-hub -g
```
