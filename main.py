from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from kicaddy import db
from kicaddy.crawler import crawl_and_index


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kicaddy",
        description="Index KiCad symbol libraries into a SQLite database.",
    )
    p.add_argument(
        "directories",
        nargs="+",
        metavar="DIR",
        help="One or more directories to crawl recursively for .kicad_sym files.",
    )
    p.add_argument(
        "--db",
        default="kicaddy.db",
        metavar="PATH",
        help="Path to the SQLite database file (default: kicaddy.db).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return p


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )

    directories: list[Path] = []
    for raw in args.directories:
        p = Path(raw)
        if not p.is_dir():
            print(f"error: not a directory: {raw}", file=sys.stderr)
            sys.exit(1)
        directories.append(p)

    try:
        conn = db.get_connection(args.db)
        db.create_schema(conn)
        stats = crawl_and_index(directories, conn)
        conn.close()
    except Exception as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        sys.exit(2)

    print(
        f"Done. "
        f"files={stats.files_found} (failed={stats.files_failed})  "
        f"symbols={stats.symbols_indexed} (failed={stats.symbols_failed})  "
        f"footprint_libs={stats.footprint_libs_found} (failed={stats.footprint_libs_failed})  "
        f"footprints={stats.footprints_indexed} (failed={stats.footprints_failed})"
    )


if __name__ == "__main__":
    main()
