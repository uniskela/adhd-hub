"""Conservative meaningful-work heuristics (deterministic, no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tools that mutate the workspace (Cursor / Claude Code tool names).
MUTATION_TOOLS = frozenset(
    {
        "write",
        "edit",  # Claude Code primary file mutation tool
        "multiedit",
        "streplace",
        "applypatch",
        "delete",
        "deleted",
        "editnotebook",
        "shell",  # may mutate; refined by command heuristics
    }
)

READ_ONLY_TOOLS = frozenset(
    {
        "read",
        "grep",
        "glob",
        "readdir",
        "listdir",
        "semanticsearch",
        "webfetch",
        "websearch",
        "await",
        "awaitshell",
    }
)

# Shell commands that are usually read-only.
_READONLY_SHELL = re.compile(
    r"^(?:"
    r"ls|ll|dir|pwd|cd|echo|cat|head|tail|less|more|rg|grep|find|which|type|"
    r"git\s+(?:status|diff|log|show|branch|rev-parse|describe|blame|remote)|"
    r"gh\s+(?:pr\s+view|issue\s+view|api\s+graphql)|"
    r"python\s+-c\s+['\"]print|"
    r"uv\s+run\s+pytest\b|"
    r"pytest\b|"
    r"ruff\s+check\b|"
    r"npm\s+(?:test|run\s+test)\b"
    r")\b",
    re.IGNORECASE,
)

# Shell commands that strongly imply meaningful work.
_MEANINGFUL_SHELL = re.compile(
    r"(?:"
    r"\bgit\s+(?:commit|push|merge|rebase|cherry-pick|am)\b|"
    r"\bgh\s+pr\s+create\b|"
    r"\bgh\s+issue\s+create\b|"
    r"\bnpm\s+install\b|"
    r"\bpip\s+install\b|"
    r"\buv\s+add\b|"
    r"\balembic\b|"
    r"\bprisma\s+migrate\b|"
    r"\bdocker\s+(?:build|compose)\b|"
    r"\brm\s+-rf\b|"
    r"\bmkdir\b|"
    r"\bmv\b|"
    r"\bcp\b"
    r")",
    re.IGNORECASE,
)

# Paths that count as meaningful project files when edited.
_TRIVIAL_PATH = re.compile(
    r"(?i)("
    r"\.mdc?$|"
    r"LICENSE|"
    r"\.gitignore$|"
    r"\.editorconfig$|"
    r"\.prettierrc|"
    r"\.cursorignore$"
    r")"
)

_TRIVIAL_EDIT_MAX_CHARS = 80

_CODE_PATH = re.compile(
    r"(?i)\.("
    r"py|pyi|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|swift|c|cc|cpp|h|hpp|"
    r"rb|php|cs|scala|toml|yaml|yml|json|sql|sh|bash|zsh|css|scss|html|"
    r"vue|svelte|mdx"
    r")$"
)


@dataclass(frozen=True)
class ToolAssessment:
    """Result of classifying a tool invocation."""

    is_mutation: bool
    is_meaningful: bool
    is_read_only: bool
    reason: str


def normalize_tool_name(tool_name: str | None) -> str:
    if not tool_name:
        return ""
    name = tool_name.strip()
    # Cursor matchers sometimes use MCP:tool_name
    if name.upper().startswith("MCP:"):
        return name
    # Strip namespace prefixes like "functions.Write"
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name


def _is_code_path(path: str | None) -> bool:
    if not path:
        return False
    norm = path.replace("\\", "/")
    if "/src/" in f"/{norm}" or norm.startswith("src/"):
        return True
    return bool(_CODE_PATH.search(norm.split("/")[-1]))


def assess_tool(
    tool_name: str | None,
    *,
    tool_input: dict | str | None = None,
    command: str | None = None,
) -> ToolAssessment:
    """Classify a tool use for meaningful-work detection."""
    raw = (tool_name or "").strip()
    name = normalize_tool_name(raw)
    lower = name.lower()

    if lower.startswith("mcp:") or raw.upper().startswith("MCP:"):
        # MCP tools are not workspace mutations by themselves
        return ToolAssessment(False, False, True, "mcp_tool")

    if lower in READ_ONLY_TOOLS or lower in {"readfile", "searchfiles"}:
        return ToolAssessment(False, False, True, "read_only")

    cmd = command
    if cmd is None and isinstance(tool_input, dict):
        maybe = tool_input.get("command")
        cmd = maybe if isinstance(maybe, str) else None

    if lower in {"shell", "bash", "run_terminal_cmd", "runcommand"}:
        text = (cmd or "").strip()
        if not text:
            return ToolAssessment(True, False, False, "empty_shell")
        if _MEANINGFUL_SHELL.search(text):
            return ToolAssessment(True, True, False, "meaningful_shell")
        if _READONLY_SHELL.match(text):
            return ToolAssessment(False, False, True, "readonly_shell")
        # Unknown shell: treat as mutation but not automatically meaningful
        return ToolAssessment(True, False, False, "shell_unknown")

    if lower in MUTATION_TOOLS - {"shell"}:
        path = _path_from_input(tool_input)
        if path and _TRIVIAL_PATH.search(path) and not _is_code_path(path):
            return ToolAssessment(True, False, False, "trivial_path_edit")
        if _is_code_path(path):
            # Source files are meaningful even for short writes (new modules).
            # Tiny single-line StrReplace on code may still be non-meaningful.
            if lower == "streplace" and _looks_tiny_edit(tool_input):
                return ToolAssessment(True, False, False, "tiny_edit")
            return ToolAssessment(True, True, False, "code_mutation")
        if _looks_tiny_edit(tool_input):
            return ToolAssessment(True, False, False, "tiny_edit")
        return ToolAssessment(True, True, False, "code_mutation")

    if lower in {"task", "todowrite", "createplan"}:
        return ToolAssessment(False, False, True, "planning")

    # Default: unknown tools are not treated as meaningful mutations
    return ToolAssessment(False, False, False, "unknown")


def assess_file_edit(
    file_path: str | None,
    *,
    edits: list | None = None,
) -> ToolAssessment:
    """Classify an afterFileEdit payload."""
    path = file_path or ""
    if _is_code_path(path):
        return ToolAssessment(True, True, False, "file_edit")
    if _TRIVIAL_PATH.search(path):
        # Docs-only / config-ish — still counts as edit toward threshold slowly
        return ToolAssessment(True, False, False, "trivial_path_edit")
    total = 0
    for edit in edits or []:
        if not isinstance(edit, dict):
            continue
        old = edit.get("old_string") or edit.get("old_line") or ""
        new = edit.get("new_string") or edit.get("new_line") or ""
        if isinstance(old, str) and isinstance(new, str):
            total += abs(len(new) - len(old)) + min(len(new), 20)
    if total and total < _TRIVIAL_EDIT_MAX_CHARS and len(edits or []) <= 1:
        return ToolAssessment(True, False, False, "tiny_edit")
    return ToolAssessment(True, True, False, "file_edit")


def _path_from_input(tool_input: dict | str | None) -> str | None:
    if isinstance(tool_input, dict):
        for key in ("path", "file_path", "filePath", "target_file"):
            val = tool_input.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _looks_tiny_edit(tool_input: dict | str | None) -> bool:
    if not isinstance(tool_input, dict):
        return False
    old = tool_input.get("old_string") or tool_input.get("old_str") or ""
    new = tool_input.get("new_string") or tool_input.get("new_str") or ""
    if (
        isinstance(old, str)
        and isinstance(new, str)
        and abs(len(new) - len(old)) <= _TRIVIAL_EDIT_MAX_CHARS
        and len(new) < 200
        and "\n" not in old
        and "\n" not in new
    ):
        return True
    contents = tool_input.get("contents") or tool_input.get("content")
    return isinstance(contents, str) and len(contents) < _TRIVIAL_EDIT_MAX_CHARS
