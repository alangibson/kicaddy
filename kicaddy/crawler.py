from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from kicaddy import db, parser, render
from kicaddy.models import LibraryType

logger = logging.getLogger(__name__)


@dataclass
class CrawlStats:
    files_found: int = 0
    files_failed: int = 0
    symbols_indexed: int = 0
    symbols_failed: int = 0
    footprint_libs_found: int = 0
    footprint_libs_failed: int = 0
    footprints_indexed: int = 0
    footprints_failed: int = 0
    parts_created: int = 0


def find_kicad_pretty_dirs(directories: list[Path]) -> Iterator[tuple[Path, str]]:
    """
    Recursively walk each directory and yield (absolute_path, relative_path)
    for every .pretty footprint library directory found.

    relative_path is relative to the directory argument that contains it.
    Duplicates reached via multiple directory arguments are skipped.
    """
    seen: set[Path] = set()
    for root in directories:
        for abs_path in sorted(root.rglob("*.pretty")):
            if not abs_path.is_dir():
                continue
            resolved = abs_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            rel_path = abs_path.relative_to(root)
            yield abs_path, str(rel_path)


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

    # Phase 2: index footprint libraries (.pretty dirs → footprint rows)
    conn.execute("BEGIN")
    pending_commits = 0

    for abs_path, rel_path in find_kicad_pretty_dirs(directories):
        stats.footprint_libs_found += 1
        logger.info("Indexing footprint library %s", rel_path)

        library, footprints = parser.parse_footprint_library_dir(abs_path, rel_path)

        try:
            library_id = db.upsert_library(conn, library)
        except Exception as exc:
            logger.warning("Failed to upsert footprint library %s: %s", rel_path, exc)
            stats.footprint_libs_failed += 1
            continue

        for footprint in footprints:
            footprint.library_id = library_id
            try:
                db.insert_footprint(conn, footprint)
                db.insert_footprint_properties(conn, footprint.id, footprint.extra_properties)
                if footprint.solid is not None:
                    footprint.solid.footprint_id = footprint.id
                    model_path = footprint.solid.model_path
                    footprint.solid.svg_path = render.render_step_to_svg(model_path) or ""
                    db.insert_solid(conn, footprint.solid)
                stats.footprints_indexed += 1
                pending_commits += 1
            except Exception as exc:
                logger.warning(
                    "Failed to index footprint %r from %s: %s",
                    footprint.name,
                    rel_path,
                    exc,
                )
                stats.footprints_failed += 1

            if pending_commits >= batch_size:
                conn.commit()
                conn.execute("BEGIN")
                pending_commits = 0

    conn.commit()

    # Phase 3: link symbol.footprint_id → footprint.id, then populate part table
    db.link_symbols_to_footprints(conn)
    stats.parts_created = db.insert_parts_from_links(conn)
    conn.commit()

    return stats
