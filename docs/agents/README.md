# Guidance for agents contributing to ADHD Hub

Start with the repository root [AGENTS.md](../../AGENTS.md), then [CONTRIBUTING.md](../../CONTRIBUTING.md). Those files govern repository work. Canonical installable guidance lives in [skills/](../../skills/) and [adapters/](../../adapters/); change it there and use the existing sync workflows for downstream copies.

Use [implementation contracts](../internal/contracts/) for payloads and invariants and [internal plans](../internal/plans/) for historical execution context. Current work ordering comes from the single [public roadmap](../public/plans/improvement-roadmap.md) and GitHub issue #15.

- [Browser verification](browser-verification.md): temporary demo data, UI checks and product screenshots.
- [Clock-Off](clock-off.md): respect advisory wind-down guidance and explicit overrides.
- [Return-cue coaching](return-cue-coaching.md): improve a resume instruction using known session context.

Keep operator setup instructions in `docs/public`. Keep maintainer contracts, release plans and agent workflow in their own trees. Build with `uv run zensical build --clean` and run `uv run pytest -q` and `uv run ruff check src tests` before opening a PR.
