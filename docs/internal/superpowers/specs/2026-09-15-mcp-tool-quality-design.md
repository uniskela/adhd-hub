# MCP Tool Quality Design

## Goal

Make ADHD Hub's MCP surface easier for agents to choose correctly without changing tool behavior, and add regression coverage for the stdio transport used by Glama and local subprocess clients.

## Scope

- Keep Streamable HTTP as the recommended persistent/shared transport and `adhd-hub mcp-stdio` as the optional local/proxy transport.
- Improve MCP tool descriptions, especially ambiguous write tools, so each description states purpose, when to use it, important side effects, and the nearest alternative when useful.
- Preserve existing tool names, argument schemas, return values, permissions, and business logic.
- Add stdio integration coverage that initializes the real subprocess server, verifies published server instructions, lists tools, and successfully calls representative read tools (`check_overlap`, `list_reminders`, `get_overview`).
- Add a focused schema-level regression test so terse descriptions cannot silently replace the more actionable guidance later.
- Do not add Glama-specific behavior to production tool logic.

## Non-goals

- Chasing a particular Glama numeric score or encoding Glama's rubric into runtime behavior.
- Changing HTTP authentication, OAuth, tool semantics, or persistence behavior.
- Working around `mcp-proxy` inside ADHD Hub if the proxy drops upstream initialize metadata.

## Verification

- `uv run pytest -q`
- `uv run ruff check src tests`
- `git diff --check`
- Confirm the stdio test exercises real `ClientSession.call_tool` calls rather than only `tools/list`.
