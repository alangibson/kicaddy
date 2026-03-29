from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from kicaddy import db, parser
from kicaddy.models import LibraryType

logger = logging.getLogger(__name__)


@dataclass
class CrawlStats:
    files_found: int = 0
    files_failed: int = 0
    symbols_indexed: int = 0
    symbols_failed: int = 0


def find_kicad_sym_files(directories: list[Path]) -> Iterator[tuple[Path, str]]:
    """
    Recursively walk each directory and yield (absolute_path, relative_path)
    for every .kicad_sym file found.

    relative_path is relative to the directory argument that contains the file.
    Duplicate files reached via multiple directory arguments are skipped.
    """
    seen: set[Path] = set()
    for root in directories:
        for abs_path in sorted(root.rglob("*.kicad_sym")):
            resolved = abs_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            rel_path = abs_path.relative_to(root)
            yield abs_path, str(rel_path)


def crawl_and_index(
    directories: list[Path],
    conn: sqlite3.Connection,
    *,
    batch_size: int = 500,
) -> CrawlStats:
    """
    Full pipeline: discover .kicad_sym files, parse symbols, persist to DB.

    Commits in batches of batch_size symbols. Returns summary stats.
    """
    stats = CrawlStats()
    pending_commits = 0

    conn.execute("BEGIN")

    for abs_path, rel_path in find_kicad_sym_files(directories):
        stats.files_found += 1
        logger.info("Indexing %s", rel_path)

        library, symbols = parser.parse_library_file(
            abs_path, rel_path, LibraryType.SYMBOL
        )

        try:
            library_id = db.upsert_library(conn, library)
        except Exception as exc:
            logger.warning("Failed to upsert library %s: %s", rel_path, exc)
            stats.files_failed += 1
            continue

        for symbol in symbols:
            symbol.library_id = library_id
            try:
                symbol_id = db.insert_symbol(conn, symbol)
                db.insert_symbol_properties(conn, symbol_id, symbol.extra_properties)
                stats.symbols_indexed += 1
                pending_commits += 1
            except Exception as exc:
                logger.warning(
                    "Failed to index symbol %r from %s: %s",
                    symbol.name,
                    rel_path,
                    exc,
                )
                stats.symbols_failed += 1

            if pending_commits >= batch_size:
                conn.commit()
                conn.execute("BEGIN")
                pending_commits = 0

    conn.commit()
    return stats
