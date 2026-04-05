"""Tests that library_path is stored as an absolute path so writability checks work.

Regression test for the bug where clicking an editable cell showed
"Read-only library" even for writable files in the user's home directory.

Root cause: crawler.py passed a relative path as library_path, but
search_dialog._resolve_library_path resolved it against the DB directory
(not the crawl root), producing a wrong path that failed os.access().

Fix: crawler.py now passes str(abs_path) so library_path is always absolute.
"""
import os
import sqlite3
from pathlib import Path

import pytest

from kicaddy import db as kdb
from kicaddy.crawler import crawl_and_index


_MINIMAL_KICAD_SYM = """\
(kicad_symbol_lib
  (version 20231120)
  (generator "test")
  (generator_version "0.0")
  (symbol "TestPart"
    (in_bom yes)
    (on_board yes)
    (property "Reference" "U"
      (at 0 0 0)
    )
    (property "Value" "TestPart"
      (at 0 0 0)
    )
    (property "Footprint" ""
      (at 0 0 0)
    )
    (property "Datasheet" ""
      (at 0 0 0)
    )
  )
)
"""


@pytest.fixture()
def sym_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with one .kicad_sym file."""
    lib_file = tmp_path / "TestLib.kicad_sym"
    lib_file.write_text(_MINIMAL_KICAD_SYM)
    return tmp_path


@pytest.fixture()
def indexed_db(sym_dir: Path, tmp_path: Path) -> tuple[Path, Path]:
    """Crawl sym_dir and return (db_path, sym_dir)."""
    db_path = tmp_path / "kicaddy.db"
    conn = kdb.get_connection(str(db_path))
    kdb.create_schema(conn)
    crawl_and_index([sym_dir], conn)
    conn.close()
    return db_path, sym_dir


def test_library_path_is_absolute(indexed_db):
    """library.library_path must be an absolute path after crawling."""
    db_path, _ = indexed_db
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT library_path FROM library").fetchall()
    conn.close()

    assert rows, "No library rows found"
    for (library_path,) in rows:
        assert os.path.isabs(library_path), (
            f"library_path is not absolute: {library_path!r}\n"
            "This causes false 'read-only library' errors in the Parts tab."
        )


def test_library_path_points_to_writable_file(indexed_db):
    """The stored library_path must resolve to the actual writable .kicad_sym file."""
    db_path, sym_dir = indexed_db
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute("SELECT library_path FROM library").fetchall()
    conn.close()

    assert rows
    for (library_path,) in rows:
        assert os.path.isfile(library_path), (
            f"library_path does not point to an existing file: {library_path!r}"
        )
        assert os.access(library_path, os.W_OK), (
            f"library_path is not writable: {library_path!r}\n"
            "Inline cell editing would be blocked with 'Read-only library' error."
        )
