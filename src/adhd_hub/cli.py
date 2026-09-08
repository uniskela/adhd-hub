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
    from adhd_hub.backup import export_data_dir

    out = Path(args.output)
    out.write_bytes(export_data_dir(settings.data_dir))
    print(out.resolve())
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    settings = load_settings(Path(args.config) if args.config else None)
    from adhd_hub.backup import import_data_dir

    archive = Path(args.archive).read_bytes()
    result = import_data_dir(settings.data_dir, archive, replace=not args.merge)
    print(result)
    return 0


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
    export_p.set_defaults(func=cmd_export)

    import_p = sub.add_parser("import", help="Import a migrate zip into data/")
    import_p.add_argument("archive", help="Path to adhd-hub-backup.zip")
    import_p.add_argument(
        "--merge",
        action="store_true",
        help="Do not delete existing files before copy (default replaces)",
    )
    import_p.set_defaults(func=cmd_import)

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
