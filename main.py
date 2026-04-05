from __future__ import annotations

import argparse
import logging
import sys

from kicaddy import db
from kicaddy.crawler import crawl_from_lib_tables
from kicaddy.plugin.config import get_db_path, get_lib_tables


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kicaddy",
        description="Index KiCad libraries into a SQLite database using configured library tables.",
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="Path to the SQLite database file (default: value from config, or kicaddy.db).",
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

    lib_tables = get_lib_tables()
    if not lib_tables:
        print(
            "error: no library tables configured. Add them via the plugin UI Configuration tab.",
            file=sys.stderr,
        )
        sys.exit(1)

    db_path = args.db or get_db_path() or "kicaddy.db"

    try:
        conn = db.get_connection(db_path)
        db.create_schema(conn)
        stats = crawl_from_lib_tables(lib_tables, conn)
        conn.close()
    except Exception as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        sys.exit(2)

    print(
        f"Done. "
        f"files={stats.files_found} (failed={stats.files_failed})  "
        f"symbols={stats.symbols_indexed} (failed={stats.symbols_failed})  "
        f"footprint_libs={stats.footprint_libs_found} (failed={stats.footprint_libs_failed})  "
        f"footprints={stats.footprints_indexed} (failed={stats.footprints_failed})  "
        f"parts={stats.parts_created}"
    )


if __name__ == "__main__":
    main()
