from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from adhd_hub.config import load_settings

log = logging.getLogger("adhd_hub.cli")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def cmd_serve(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port
    _configure_logging(args.verbose)
    # Import app factory after settings path known
    from adhd_hub.app import create_app

    app = create_app(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    _configure_logging(args.verbose)
    from adhd_hub.indexer.runner import run_indexer

    result = run_indexer(settings, dry_run=args.dry_run, force=args.force)
    print(result)
    return 0


def cmd_rebuild_wiki(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    from adhd_hub.service import HubService

    svc = HubService(settings)
    path = svc.rebuild_wiki_index()
    print(path)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    from adhd_hub.backup import export_data_dir, is_encrypted_backup

    passphrase = args.passphrase or None
    out = Path(args.output)
    data = export_data_dir(settings.data_dir, passphrase=passphrase)
    if passphrase and out.suffix == ".zip":
        out = out.with_suffix(".zip.enc")
    out.write_bytes(data)
    kind = "encrypted" if is_encrypted_backup(data) else "zip"
    print(f"{out.resolve()} ({kind})")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    from adhd_hub.backup import import_data_dir

    archive = Path(args.archive).read_bytes()
    result = import_data_dir(
        settings.data_dir,
        archive,
        replace=not args.merge,
        passphrase=args.passphrase or None,
    )
    print(result)
    return 0


def cmd_forge_wiki_paths(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    from adhd_hub.forge.migrate_wiki_paths import apply_forge_wiki_path_cleanup

    result = apply_forge_wiki_path_cleanup(settings, dry_run=not args.apply)
    print(result)
    if result["count"] == 0:
        print("No legacy adhd-hub/wiki paths found in Hub config.")
    elif result.get("applied"):
        print("Updated Hub config. Move remote forge files separately if needed.")
    else:
        print("Dry-run only. Pass --apply to write changes.")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    from adhd_hub.connect import expected_cursor_rule_text
    from adhd_hub.project_setup import (
        check_project_guidance,
        install_agent_guidance,
        install_skills,
        print_guidance_check,
        uninstall_agent_guidance,
    )

    project = Path(args.path)
    if args.uninstall:
        path, action = uninstall_agent_guidance(project)
        print(f"ADHD Hub project guidance {action}: {path}")
        return 0

    if args.check:
        items = check_project_guidance(
            project,
            expected_cursor_rule=expected_cursor_rule_text(),
            check_skills=True,
        )
        return print_guidance_check(items)

    path, action = install_agent_guidance(project)
    print(f"ADHD Hub project guidance {action}: {path}")
    if args.install_skills:
        code = install_skills(args.skills_source)
        if code:
            print("AGENTS.md was configured, but the global skills install failed.", file=sys.stderr)
            return code
    else:
        print("Skills unchanged. Add --install-skills to install them globally with npx.")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    from adhd_hub.connect import print_report, resolve_hub_url, run_connect
    from adhd_hub.connect_login import resolve_cli_token, run_login

    agents = [part.strip() for part in args.agents.split(",") if part.strip()]
    find_roots = [Path(p) for p in (args.find_roots or [])]
    hub_url = resolve_hub_url(args.hub)
    token = resolve_cli_token(args.token, hub_url)
    if not args.dry_run and not args.no_login and not token:
        try:
            token = run_login(hub_url, open_browser=not args.no_browser)
        except (RuntimeError, ConnectionError, ValueError) as exc:
            print(f"CLI login skipped: {exc}", file=sys.stderr)
            token = None
    report = run_connect(
        project=Path(args.path),
        hub_url=hub_url,
        agents=agents,
        scope=args.scope,
        install_skills_flag=args.skills,
        skills_source=args.skills_source,
        cursor_rule=args.cursor_rule,
        openclaw_skills=args.openclaw_skills,
        register=args.register,
        find_roots=find_roots or None,
        token=token,
        dry_run=args.dry_run,
        with_i_have_adhd=args.with_i_have_adhd,
        with_graphify=args.with_graphify,
        with_rtk=args.with_rtk,
        with_superpowers=args.with_superpowers,
        with_context7=args.with_context7,
        with_agent_browser=args.with_agent_browser,
        with_serena=args.with_serena,
    )
    print_report(report, verbose=args.verbose)
    return 0 if report.ok else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    from adhd_hub.connect import print_report, resolve_hub_url, run_doctor
    from adhd_hub.connect_login import resolve_cli_token

    project_arg = args.project or args.path
    project = Path(project_arg) if project_arg else None
    hub_url = resolve_hub_url(args.hub)
    agents = [part.strip() for part in (args.agents or "").split(",") if part.strip()]
    report = run_doctor(
        hub_url=hub_url,
        project=project,
        token=resolve_cli_token(args.token, hub_url),
        agents=agents or None,
    )
    print_report(report, verbose=args.verbose)
    continuity_drift = any(
        s.status in {"warn", "error"}
        for s in report.steps
        if s.name.startswith("AGENTS.md")
        or s.name == "Cursor rule"
        or s.name.endswith(" skill")
    )
    return 0 if report.ok and not continuity_drift else 1


def cmd_login(args: argparse.Namespace) -> int:
    from adhd_hub.connect import ConnectReport, print_report, resolve_hub_url
    from adhd_hub.connect_login import run_login

    hub_url = resolve_hub_url(args.hub)
    report = ConnectReport(hub_url=hub_url)
    try:
        run_login(hub_url, open_browser=not args.no_browser, report=report)
    except (RuntimeError, ConnectionError, ValueError) as exc:
        report.add("login", "error", str(exc))
        print_report(report, verbose=args.verbose)
        return 1
    print_report(report, verbose=args.verbose)
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    from adhd_hub.connect import resolve_hub_url
    from adhd_hub.connect_login import resolve_cli_token, run_logout

    hub_url = resolve_hub_url(args.hub)
    run_logout(hub_url, resolve_cli_token(args.token, hub_url))
    print(f"Signed the CLI out of {hub_url} (local session file cleared).")
    return 0


def cmd_use_hub(args: argparse.Namespace) -> int:
    from adhd_hub.connect import print_report, resolve_hub_url, run_use_hub
    from adhd_hub.connect_login import resolve_cli_token, run_login

    hub_url = resolve_hub_url(args.hub)
    agents = [part.strip() for part in (args.agents or "").split(",") if part.strip()]
    token = resolve_cli_token(args.token, hub_url)
    if not args.dry_run and not args.no_login and not token:
        try:
            token = run_login(hub_url, open_browser=not args.no_browser)
        except (RuntimeError, ConnectionError, ValueError) as exc:
            print(f"CLI login skipped: {exc}", file=sys.stderr)
            token = None
    report = run_use_hub(
        hub_url=hub_url,
        project=Path(args.project) if args.project else None,
        agents=agents or None,
        scope=args.scope,
        token=token,
        dry_run=args.dry_run,
    )
    print_report(report, verbose=args.verbose)
    return 0 if report.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adhd-hub", description="ADHD Progress Hub")
    p.add_argument("-c", "--config", help="Path to config.toml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run REST + MCP server")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=cmd_serve)

    index = sub.add_parser("index", help="Scan local transcripts and POST summaries to hub")
    index.add_argument("--dry-run", action="store_true")
    index.add_argument("--force", action="store_true")
    index.set_defaults(func=cmd_index)

    wiki = sub.add_parser("rebuild-wiki", help="Rebuild wiki INDEX.md from open threads")
    wiki.set_defaults(func=cmd_rebuild_wiki)

    export_p = sub.add_parser("export", help="Export data/ as a migrate zip")
    export_p.add_argument(
        "-o",
        "--output",
        default="adhd-hub-backup.zip",
        help="Output zip path",
    )
    export_p.add_argument(
        "--passphrase",
        default=None,
        help="Optional passphrase to encrypt the backup (scrypt + Fernet; v1 files still import)",
    )
    export_p.set_defaults(func=cmd_export)

    import_p = sub.add_parser("import", help="Import a migrate zip into data/")
    import_p.add_argument("archive", help="Path to adhd-hub-backup.zip[.enc]")
    import_p.add_argument(
        "--merge",
        action="store_true",
        help="Do not delete existing files before copy (default replaces)",
    )
    import_p.add_argument(
        "--passphrase",
        default=None,
        help="Passphrase for an encrypted backup",
    )
    import_p.set_defaults(func=cmd_import)

    forge_paths = sub.add_parser(
        "forge-wiki-paths",
        help="Migrate legacy forge wiki_path adhd-hub/wiki → repo-root projects/",
    )
    forge_paths.add_argument(
        "--apply",
        action="store_true",
        help="Write config changes (default is dry-run)",
    )
    forge_paths.set_defaults(func=cmd_forge_wiki_paths)

    setup = sub.add_parser(
        "setup",
        help="Add reversible ADHD Hub continuity guidance to a project's AGENTS.md",
    )
    setup.add_argument("path", nargs="?", default=".", help="Project folder (default: .)")
    setup.add_argument(
        "--install-skills",
        action="store_true",
        help="Also run npx skills add <source> -g",
    )
    setup.add_argument(
        "--skills-source",
        default="uniskela/adhd-hub",
        help="skills.sh source or local skills path (default: uniskela/adhd-hub)",
    )
    setup.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove only the managed ADHD Hub block from AGENTS.md",
    )
    setup.add_argument(
        "--check",
        action="store_true",
        help="Report Hub guidance/skill drift without writing files",
    )
    setup.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh Hub-managed AGENTS.md block (default behaviour of setup)",
    )
    setup.set_defaults(func=cmd_setup)

    connect = sub.add_parser(
        "connect",
        help="Wire MCP, AGENTS.md, optional skills/OpenClaw to a running Hub",
    )
    connect.add_argument("path", nargs="?", default=".", help="Project folder (default: .)")
    connect.add_argument(
        "--hub",
        default=None,
        help="Hub base URL (default: ADHD_HUB_PUBLIC_URL, saved default_hub, or http://127.0.0.1:8787)",
    )
    connect.add_argument(
        "--agents",
        default="",
        help=(
            "Comma list of coding agents for MCP wire-up and skills install "
            "(cursor,codex,claude). Use * for skills on every agent. "
            "Empty = no agent MCP/skills targets (set in Hub Settings → Connections "
            "or pass explicitly). Claude maps to skills.sh id claude-code."
        ),
    )
    connect.add_argument(
        "--scope",
        choices=("project", "user"),
        default="project",
        help="Where to write Cursor MCP config (default: project)",
    )
    connect.add_argument(
        "--skills",
        action="store_true",
        help="Install global agent skills via npx skills add",
    )
    connect.add_argument(
        "--skills-source",
        default="uniskela/adhd-hub",
        help="skills.sh source or local skills path",
    )
    connect.add_argument(
        "--cursor-rule",
        action="store_true",
        help="Install .cursor/rules/adhd-hub.mdc in the project",
    )
    connect.add_argument(
        "--openclaw-skills",
        action="store_true",
        help="Also install skills into OpenClaw (-a openclaw)",
    )
    connect.add_argument(
        "--register",
        action="store_true",
        help="Resolve/create the project on the Hub (needs adhd-hub login or ADHD_HUB_AUTH_TOKEN)",
    )
    connect.add_argument(
        "--find-roots",
        nargs="*",
        metavar="DIR",
        help="Scan directories for candidate projects and list them",
    )
    connect.add_argument(
        "--token",
        default=None,
        help="Hub bearer token (default: saved CLI session, then ADHD_HUB_AUTH_TOKEN)",
    )
    connect.add_argument(
        "--no-login",
        action="store_true",
        help="Do not open the browser connect handshake when no session is saved",
    )
    connect.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the connect code instead of opening a browser",
    )
    connect.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned writes without changing files or calling register",
    )
    connect.add_argument(
        "--with-i-have-adhd",
        action="store_true",
        help="Opt-in: install ayghri/i-have-adhd skill for selected --agents",
    )
    connect.add_argument(
        "--with-graphify",
        action="store_true",
        help="Opt-in: install/register Graphify for selected --agents",
    )
    connect.add_argument(
        "--with-rtk",
        action="store_true",
        help="Opt-in: run rtk init for selected --agents (binary must already be on PATH)",
    )
    connect.add_argument(
        "--with-superpowers",
        action="store_true",
        help="Opt-in: best-effort Superpowers setup for selected --agents (mostly manual hints)",
    )
    connect.add_argument(
        "--with-context7",
        action="store_true",
        help="Opt-in: merge Context7 MCP into selected agent configs",
    )
    connect.add_argument(
        "--with-agent-browser",
        action="store_true",
        help="Opt-in: install agent-browser + skill for selected --agents",
    )
    connect.add_argument(
        "--with-serena",
        action="store_true",
        help="Opt-in: install Serena and merge MCP for selected --agents",
    )
    connect.set_defaults(func=cmd_connect)

    doctor = sub.add_parser(
        "doctor",
        help="Report Hub reachability and local MCP / AGENTS / skills status",
    )
    doctor.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Optional project folder to inspect",
    )
    doctor.add_argument(
        "--project",
        default=None,
        help="Project folder to inspect (alias for positional path)",
    )
    doctor.add_argument("--hub", default=None, help="Hub base URL")
    doctor.add_argument(
        "--agents",
        default="",
        help=(
            "Optional comma list used for companion install recipes "
            "(same ids as connect --agents)."
        ),
    )
    doctor.add_argument(
        "--token",
        default=None,
        help="Optional bearer token (default: saved CLI session, then ADHD_HUB_AUTH_TOKEN)",
    )
    doctor.set_defaults(func=cmd_doctor)

    login = sub.add_parser(
        "login",
        help="Connect this CLI to a Hub without putting the server token in your shell",
    )
    login.add_argument("--hub", default=None, help="Hub base URL")
    login.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the one-time code instead of opening a browser",
    )
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser("logout", help="Forget the saved CLI session for a Hub")
    logout.add_argument("--hub", default=None, help="Hub base URL")
    logout.add_argument("--token", default=None, help="Optional bearer to revoke")
    logout.set_defaults(func=cmd_logout)

    use_hub = sub.add_parser(
        "use-hub",
        help="Switch preferred Hub host and retarget local MCP configs",
    )
    use_hub.add_argument(
        "hub",
        help="Hub base URL (e.g. https://adhd-hub.example.com)",
    )
    use_hub.add_argument(
        "--project",
        default=".",
        help="Project folder whose Cursor MCP to retarget (default: .)",
    )
    use_hub.add_argument(
        "--agents",
        default="cursor,codex,claude",
        help="Comma list of agents to retarget (default: cursor,codex,claude)",
    )
    use_hub.add_argument(
        "--scope",
        choices=("project", "user", "both"),
        default="project",
        help="Where to write Cursor MCP config (default: project)",
    )
    use_hub.add_argument(
        "--token",
        default=None,
        help="Hub bearer token (default: saved CLI session, then ADHD_HUB_AUTH_TOKEN)",
    )
    use_hub.add_argument(
        "--no-login",
        action="store_true",
        help="Do not open the browser connect handshake when no session is saved",
    )
    use_hub.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the connect code instead of opening a browser",
    )
    use_hub.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned writes without changing files",
    )
    use_hub.set_defaults(func=cmd_use_hub)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code = args.func(args)
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:
        log.exception("command failed")
        print(f"error: {exc}", file=sys.stderr)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
