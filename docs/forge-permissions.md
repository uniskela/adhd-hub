# Forge PAT permissions (GitHub & Gitea)

ADHD Hub talks to your forge with a **Personal Access Token (PAT)** for two optional features:

| Feature | What the token is used for |
|---------|----------------------------|
| **Wiki sync** | Create/update/delete files in the **Hub memory repo** (Contents API) — primary memory: `projects/<slug>/PROGRESS.md` at repo root; otherwise under Wiki path. Project `forge_owner`/`forge_repo` bind the **issue/code** repo and must not receive the wiki tree. |
| **Board sync** | Create/update Issues (labels `adhd-hub` + `project:<slug>`), close when done; optionally attach to a **Project** board |

Use a **dedicated bot/machine user** token when you can. Prefer **least privilege**: only enable the scopes below that match what you turned on in `/ui`.

---

## GitHub

### Fine-grained PAT (recommended)

Create at: GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens**.

1. **Resource owner** — you or the org that owns the target repo.  
2. **Repository access** — only the repo used for wiki/issues (or “All” if you must).  
3. **Permissions:**

| Permission | Access | Needed for |
|------------|--------|------------|
| **Contents** | Read and write | Wiki sync (push `PROGRESS.md` / `INDEX.md`) |
| **Issues** | Read and write | Board sync (create/update/close issues + labels) |
| **Metadata** | Read-only | Always required by GitHub for repo tokens |

If **Board sync → GitHub Projects v2** is enabled (project number set):

| Permission | Access | Needed for |
|------------|--------|------------|
| **Organization projects** *or* **User projects** (depending on where the Project lives) | Read and write | Attach the issue to the Project via GraphQL |

Notes:

- Classic **Projects (classic)** boards are not what Hub uses; it uses **Projects v2**.
- The token must be allowed to use labels that already exist on the repo (Hub sends `adhd-hub`). Create that label once in the repo if needed.
- For org-owned Projects, an org admin may need to approve the fine-grained token.

### Classic PAT (alternative)

Create at: **Personal access tokens → Tokens (classic)**.

| Scope | Needed for |
|-------|------------|
| `repo` | Private repos: wiki Contents + Issues (includes public too) |
| `public_repo` | **Only** if the target repo is public and you refuse `repo` |
| `project` | Projects v2 read/write (board attach). Some accounts show `read:project` / `write:project` — enable write. |

Do **not** enable `admin:*`, `delete_repo`, `workflow`, etc. unless you have another reason.

### GitHub API base URL

Leave **API base URL** as `https://api.github.com` (default). GitHub Enterprise Server: `https://github.example.com/api/v3`.

---

## Gitea

Create at: Gitea → **Settings → Applications → Generate New Token** (wording varies slightly by version).

Pick scopes that cover repository contents and issues. Exact checkbox names differ by Gitea version; map to:

| Capability | Typical Gitea token scope | Needed for |
|------------|---------------------------|------------|
| Read/write repo files | `write:repository` (includes read) | Wiki sync |
| Read/write issues | `write:issue` | Board sync |
| Projects (board attach) | Often covered by `write:repository` / `write:issue`, or a **project** / **organization** write scope if listed | Optional project attach |

Minimal practical sets:

- **Wiki only:** `write:repository`  
- **Wiki + Issues/board:** `write:repository` + `write:issue`  
- **Org project boards:** add whatever your Gitea build labels for project write (e.g. `write:organization` if projects are org-scoped)

If your Gitea only offers coarse “all” / “repository” packages, use the smallest package that includes **repository write** and **issue write**.

### Gitea API base URL

In `/ui` set **API base URL** to:

```text
https://<your-gitea-host>/api/v1
```

Example: `https://gitea.home.example/api/v1`  
Owner/repo are the Gitea owner and repository name (not the full URL).

---

## Checklist before first Sync

1. Token created with the scopes above.  
2. Repo exists (hub can create the `adhd-hub` issue label on first board sync).  
3. For Projects: note the **GitHub project number** or **Gitea project id** and enter it in `/ui` (optional — Issues work without it).  
4. Paste the token in `/ui` (or `ADHD_HUB_FORGE_TOKEN` / `data/forge.json`).  
5. Enable **Wiki sync** and/or **Board sync**. For a dedicated memory repo, also enable **Primary ADHD memory repo** (seeds `README.md` + `AGENTS.md`).  
6. Save, then **Sync now**.

If sync fails with `401`/`403`, the usual causes are missing **Contents** write, missing **Issues** write, or Projects permission on the wrong resource owner (user vs org).

**File tree vs tabs:** wiki sync writes markdown files into the repo. That does **not** turn on Gitea/GitHub’s separate Wiki feature. Look under **Issues** for board-synced threads.
