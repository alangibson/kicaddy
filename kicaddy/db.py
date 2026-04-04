from __future__ import annotations

import sqlite3

from kicaddy.models import Footprint, FootprintProperty, Library, Part, Solid, Symbol, SymbolProperty

_DDL = """
CREATE TABLE IF NOT EXISTS library (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    library_path      TEXT     NOT NULL UNIQUE,
    library_type      TEXT     NOT NULL DEFAULT 'symbol',
    version           INTEGER  NOT NULL DEFAULT 0,
    generator         TEXT     NOT NULL DEFAULT '',
    generator_version TEXT     NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS footprint (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id         INTEGER NOT NULL REFERENCES library(id) ON DELETE CASCADE,
    name               TEXT    NOT NULL DEFAULT '',
    description        TEXT    NOT NULL DEFAULT '',
    tags               TEXT    NOT NULL DEFAULT '',
    layer              TEXT    NOT NULL DEFAULT '',
    kicad_footprint_id TEXT    NOT NULL DEFAULT '',
    file_path          TEXT    NOT NULL DEFAULT '',
    UNIQUE (library_id, name)
);

CREATE TABLE IF NOT EXISTS solid (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    footprint_id INTEGER NOT NULL UNIQUE REFERENCES footprint(id) ON DELETE CASCADE,
    model_path   TEXT    NOT NULL DEFAULT '',
    svg_path     TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_solid_footprint_id
    ON solid(footprint_id);

CREATE TABLE IF NOT EXISTS symbol (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id       INTEGER NOT NULL REFERENCES library(id) ON DELETE CASCADE,
    footprint_id     INTEGER REFERENCES footprint(id),
    name             TEXT    NOT NULL,
    extends          TEXT,
    kicad_library_id TEXT    NOT NULL,
    unit_id          TEXT,
    reference        TEXT    NOT NULL,
    value            TEXT    NOT NULL,
    footprint        TEXT    NOT NULL DEFAULT '',
    datasheet        TEXT    NOT NULL DEFAULT '',
    description      TEXT    NOT NULL DEFAULT '',
    keywords         TEXT    NOT NULL DEFAULT '',
    mpn              TEXT,
    manufacturer     TEXT,
    package          TEXT,
    digikey_pn       TEXT,
    mouser_pn        TEXT,
    tme_pn           TEXT,
    lcsc_pn          TEXT,
    mounting         TEXT,
    category         TEXT,
    library_name     TEXT    NOT NULL DEFAULT '',
    UNIQUE (library_id, name)
);

CREATE TABLE IF NOT EXISTS symbol_property (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id INTEGER NOT NULL REFERENCES symbol(id) ON DELETE CASCADE,
    key       TEXT    NOT NULL,
    value     TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS footprint_property (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    footprint_id INTEGER NOT NULL REFERENCES footprint(id) ON DELETE CASCADE,
    key          TEXT    NOT NULL,
    value        TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_footprint_property_footprint_id
    ON footprint_property(footprint_id);

CREATE INDEX IF NOT EXISTS idx_footprint_library_id
    ON footprint(library_id);

CREATE INDEX IF NOT EXISTS idx_footprint_kicad_id
    ON footprint(kicad_footprint_id);

CREATE INDEX IF NOT EXISTS idx_symbol_library_id
    ON symbol(library_id);

CREATE INDEX IF NOT EXISTS idx_symbol_property_symbol_id
    ON symbol_property(symbol_id);

CREATE TABLE IF NOT EXISTS part (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id    INTEGER NOT NULL REFERENCES symbol(id) ON DELETE CASCADE,
    footprint_id INTEGER NOT NULL REFERENCES footprint(id) ON DELETE CASCADE,
    mpn          TEXT    NOT NULL DEFAULT '',
    UNIQUE (symbol_id, footprint_id)
);

CREATE INDEX IF NOT EXISTS idx_part_symbol_id
    ON part(symbol_id);

CREATE INDEX IF NOT EXISTS idx_part_footprint_id
    ON part(footprint_id);
"""


_MIGRATIONS = [
    "ALTER TABLE symbol ADD COLUMN digikey_pn TEXT",
    "ALTER TABLE symbol ADD COLUMN mouser_pn   TEXT",
    "ALTER TABLE symbol ADD COLUMN tme_pn      TEXT",
    "ALTER TABLE symbol ADD COLUMN lcsc_pn     TEXT",
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Run forward-only schema migrations. Silently skips already-applied ones."""
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with WAL journal mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Execute all CREATE TABLE / CREATE INDEX DDL statements."""
    conn.executescript(_DDL)
    conn.commit()
    _apply_migrations(conn)


def upsert_library(conn: sqlite3.Connection, lib: Library) -> int:
    """
    Insert or replace a Library row. Returns the row id.
    Replacing the row cascades-deletes all child symbol and symbol_property rows.
    Populates lib.id in-place.
    """
    cur = conn.execute(
        """
        INSERT INTO library (library_path, library_type, version, generator, generator_version)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(library_path) DO UPDATE SET
            library_type      = excluded.library_type,
            version           = excluded.version,
            generator         = excluded.generator,
            generator_version = excluded.generator_version
        RETURNING id
        """,
        (
            lib.library_path,
            str(lib.library_type),
            lib.version,
            lib.generator,
            lib.generator_version,
        ),
    )
    row = cur.fetchone()
    lib.id = row[0]
    return lib.id


def _delete_symbols_for_library(conn: sqlite3.Connection, library_id: int) -> None:
    """Remove all symbol rows for a library (symbol_property cascades automatically)."""
    conn.execute("DELETE FROM symbol WHERE library_id = ?", (library_id,))


def insert_symbol(conn: sqlite3.Connection, symbol: Symbol) -> int:
    """
    Insert or replace a Symbol row. Returns the row id.
    Populates symbol.id in-place.
    """
    cur = conn.execute(
        """
        INSERT INTO symbol
            (library_id, name, extends, kicad_library_id, unit_id,
             reference, value, footprint, datasheet, description, keywords,
             mpn, manufacturer, package, digikey_pn, mouser_pn, tme_pn, lcsc_pn,
             mounting, category, library_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(library_id, name) DO UPDATE SET
            extends          = excluded.extends,
            kicad_library_id = excluded.kicad_library_id,
            unit_id          = excluded.unit_id,
            reference        = excluded.reference,
            value            = excluded.value,
            footprint        = excluded.footprint,
            datasheet        = excluded.datasheet,
            description      = excluded.description,
            keywords         = excluded.keywords,
            mpn              = excluded.mpn,
            manufacturer     = excluded.manufacturer,
            package          = excluded.package,
            digikey_pn       = CASE WHEN excluded.digikey_pn IS NOT NULL
                                    THEN excluded.digikey_pn
                                    ELSE symbol.digikey_pn END,
            mouser_pn        = CASE WHEN excluded.mouser_pn IS NOT NULL
                                    THEN excluded.mouser_pn
                                    ELSE symbol.mouser_pn END,
            tme_pn           = CASE WHEN excluded.tme_pn IS NOT NULL
                                    THEN excluded.tme_pn
                                    ELSE symbol.tme_pn END,
            lcsc_pn          = CASE WHEN excluded.lcsc_pn IS NOT NULL
                                    THEN excluded.lcsc_pn
                                    ELSE symbol.lcsc_pn END,
            mounting         = excluded.mounting,
            category         = excluded.category,
            library_name     = excluded.library_name
        RETURNING id
        """,
        (
            symbol.library_id,
            symbol.name,
            symbol.extends,
            symbol.kicad_library_id,
            symbol.unit_id,
            symbol.reference,
            symbol.value,
            symbol.footprint,
            symbol.datasheet,
            symbol.description,
            symbol.keywords,
            symbol.mpn,
            symbol.manufacturer,
            symbol.package,
            symbol.digikey_pn,
            symbol.mouser_pn,
            symbol.tme_pn,
            symbol.lcsc_pn,
            symbol.mounting,
            symbol.category,
            symbol.library_name,
        ),
    )
    row = cur.fetchone()
    symbol.id = row[0]
    return symbol.id


def insert_symbol_properties(
    conn: sqlite3.Connection,
    symbol_id: int,
    properties: list[SymbolProperty],
) -> None:
    """
    Replace all extra properties for a symbol.
    Deletes existing rows then bulk-inserts the new ones.
    """
    conn.execute("DELETE FROM symbol_property WHERE symbol_id = ?", (symbol_id,))
    if properties:
        conn.executemany(
            "INSERT INTO symbol_property (symbol_id, key, value) VALUES (?, ?, ?)",
            [(symbol_id, p.key, p.value) for p in properties],
        )


def insert_footprint_properties(
    conn: sqlite3.Connection,
    footprint_id: int,
    properties: list[FootprintProperty],
) -> None:
    """
    Replace all extra properties for a footprint.
    Deletes existing rows then bulk-inserts the new ones.
    """
    conn.execute("DELETE FROM footprint_property WHERE footprint_id = ?", (footprint_id,))
    if properties:
        conn.executemany(
            "INSERT INTO footprint_property (footprint_id, key, value) VALUES (?, ?, ?)",
            [(footprint_id, p.key, p.value) for p in properties],
        )


def insert_footprint(conn: sqlite3.Connection, footprint: Footprint) -> int:
    """
    Insert or replace a Footprint row. Returns the row id.
    Populates footprint.id in-place.
    """
    cur = conn.execute(
        """
        INSERT INTO footprint
            (library_id, name, description, tags, layer, kicad_footprint_id, file_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(library_id, name) DO UPDATE SET
            description        = excluded.description,
            tags               = excluded.tags,
            layer              = excluded.layer,
            kicad_footprint_id = excluded.kicad_footprint_id,
            file_path          = excluded.file_path
        RETURNING id
        """,
        (
            footprint.library_id,
            footprint.name,
            footprint.description,
            footprint.tags,
            footprint.layer,
            footprint.kicad_footprint_id,
            footprint.file_path,
        ),
    )
    row = cur.fetchone()
    footprint.id = row[0]
    return footprint.id


def insert_solid(conn: sqlite3.Connection, model: Solid) -> int:
    """
    Insert or replace a Solid row. Returns the row id.
    Populates model.id in-place.
    """
    cur = conn.execute(
        """
        INSERT INTO solid (footprint_id, model_path, svg_path)
        VALUES (?, ?, ?)
        ON CONFLICT(footprint_id) DO UPDATE SET
            model_path = excluded.model_path,
            svg_path   = excluded.svg_path
        RETURNING id
        """,
        (model.footprint_id, model.model_path, model.svg_path),
    )
    row = cur.fetchone()
    model.id = row[0]
    return model.id


def link_symbols_to_footprints(conn: sqlite3.Connection) -> None:
    """
    Populate symbol.footprint_id by matching symbol.footprint (e.g.
    "Resistor_SMD:R_0402_1005Metric") against footprint.kicad_footprint_id.
    """
    conn.execute(
        """
        UPDATE symbol
        SET footprint_id = (
            SELECT f.id FROM footprint f
            WHERE f.kicad_footprint_id = symbol.footprint
        )
        WHERE symbol.footprint != ''
        """
    )


def update_symbol_supplier_field(
    conn: sqlite3.Connection,
    symbol_id: int,
    field_name: str,
    value: str,
) -> None:
    """Update a single supplier/MPN field on a symbol row.

    field_name must be one of: 'mpn', 'digikey_pn', 'mouser_pn', 'tme_pn', 'lcsc_pn'.
    Stores empty string as NULL.
    Raises ValueError for unknown field names.
    """
    allowed = frozenset({"mpn", "digikey_pn", "mouser_pn", "tme_pn", "lcsc_pn"})
    if field_name not in allowed:
        raise ValueError(f"Unknown supplier field: {field_name!r}")
    stored_value = value.strip() or None
    conn.execute(
        f"UPDATE symbol SET {field_name} = ? WHERE id = ?",  # noqa: S608 — field_name validated above
        (stored_value, symbol_id),
    )
    conn.commit()


def insert_parts_from_links(conn: sqlite3.Connection) -> int:
    """
    Populate the part table from existing symbol→footprint links.
    Only symbols with both a matched footprint and a non-empty MPN produce a part.
    Must be called after link_symbols_to_footprints().
    Uses INSERT OR IGNORE for idempotency.
    """
    cur = conn.execute(
        """
        INSERT INTO part (symbol_id, footprint_id, mpn)
        SELECT id, footprint_id, mpn
        FROM symbol
        WHERE footprint_id IS NOT NULL
          AND mpn IS NOT NULL
        """
    )
    return cur.rowcount
