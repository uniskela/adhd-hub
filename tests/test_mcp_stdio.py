from __future__ import annotations

from adhd_hub import cli


def test_cli_exposes_mcp_stdio_command() -> None:
    args = cli.build_parser().parse_args(["mcp-stdio"])

    assert args.command == "mcp-stdio"
    assert args.func is cli.cmd_mcp_stdio
