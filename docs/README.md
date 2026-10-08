# Documentation layout

| Audience | Canonical source | Published |
| --- | --- | --- |
| Users and operators | `public/` | Zensical and the documentation importer |
| Implementers and maintainers | `internal/contracts/`, `internal/plans/`, `internal/superpowers/` | Repository only |
| Coding agents working on Hub | `agents/` | Repository only |

Zensical builds only `docs/public`. Navigation paths are relative to that directory; assets, styles and images live there too. `manifest.json` remains the public import contract at this path. Its `source` fields are repository paths and its `slug` fields preserve published URLs. Add user guides to both navigation and the manifest.

The single [public roadmap](public/plans/improvement-roadmap.md) remains at the published `plans/improvement-roadmap/` URL. Issue [#15](https://github.com/uniskela/adhd-hub/issues/15) remains the canonical planning tracker. Execution plans and historical design records belong in `internal/`, not in a second public roadmap.

Historical public paths contain only short, search-excluded signposts to the repository archive and current roadmap. Never copy implementation plans or internal agent instructions back into those pages. Keep user instructions in public guides and implementation details in contracts; link across the boundary with repository URLs from public pages.

Root `AGENTS.md`, `skills/` and `adapters/` remain canonical. `docs/agents` explains contributor workflows; it does not replace, duplicate or ship those assets. See [agent guidance](agents/README.md).

“Internal” is a publication boundary, not confidentiality: these files remain visible in this public GitHub repository. Do not put secrets or private operational details in any documentation tree.
