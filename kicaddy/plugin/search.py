from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


@dataclass
class SearchResult:
    result_type: str   # "symbol" or "footprint"
    library: str       # library_name (symbol) or library prefix from kicad_footprint_id (footprint)
    name: str          # kicad_library_id if set, else symbol.name; footprint.name
    description: str
    extra1: str        # MPN for symbols; Tags for footprints
    extra2: str        # Footprint string for symbols; Layer for footprints


@dataclass
class PartResult:
    symbol_library: str
    symbol_name: str    # kicad_library_id if set, else symbol.name
    footprint: str      # kicad_footprint_id
    description: str
    mpn: str
    model_path: str = ""  # resolved absolute path to STEP file, empty if none
    symbol_id: int = 0          # symbol.id — needed for in-place DB edits
    symbol_raw_name: str = ""   # symbol.name — raw name inside the .kicad_sym file
    library_path: str = ""      # library.library_path — for writability check
    digikey_pn: str = ""
    mouser_pn: str = ""
    tme_pn: str = ""
    lcsc_pn: str = ""


# Search all text columns in symbol + symbol_property, and footprint + footprint_property.
# Each branch uses the same pattern for every ? placeholder.
# Symbol branch: 15 column checks + 2 for EXISTS on symbol_property  = 17 params
# Footprint branch: 6 column checks + 2 for EXISTS on footprint_property = 8 params
_SEARCH_SQL = """
SELECT
    'symbol'                                                           AS result_type,
    s.library_name                                                     AS library,
    CASE WHEN s.kicad_library_id != '' THEN s.kicad_library_id
         ELSE s.name END                                               AS name,
    s.description,
    ''                                                                 AS extra1,
    s.footprint                                                        AS extra2
FROM symbol s
WHERE s.name             REGEXP ?
   OR s.extends          REGEXP ?
   OR s.kicad_library_id REGEXP ?
   OR s.reference        REGEXP ?
   OR s.value            REGEXP ?
   OR s.footprint        REGEXP ?
   OR s.datasheet        REGEXP ?
   OR s.description      REGEXP ?
   OR s.keywords         REGEXP ?
   OR s.mpn              REGEXP ?
   OR s.manufacturer     REGEXP ?
   OR s.package          REGEXP ?
   OR s.mounting         REGEXP ?
   OR s.category         REGEXP ?
   OR s.library_name     REGEXP ?
   OR EXISTS (
       SELECT 1 FROM symbol_property sp
       WHERE sp.symbol_id = s.id
         AND (sp.key REGEXP ? OR sp.value REGEXP ?)
   )

UNION ALL

SELECT
    'footprint'                                                        AS result_type,
    CASE WHEN INSTR(f.kicad_footprint_id, ':') > 0
         THEN SUBSTR(f.kicad_footprint_id, 1, INSTR(f.kicad_footprint_id, ':') - 1)
         ELSE '' END                                                   AS library,
    f.name,
    f.description,
    ''                                                                 AS extra1,
    f.layer                                                            AS extra2
FROM footprint f
WHERE f.name               REGEXP ?
   OR f.description        REGEXP ?
   OR f.tags               REGEXP ?
   OR f.layer              REGEXP ?
   OR f.kicad_footprint_id REGEXP ?
   OR f.file_path          REGEXP ?
   OR EXISTS (
       SELECT 1 FROM footprint_property fp
       WHERE fp.footprint_id = f.id
         AND (fp.key REGEXP ? OR fp.value REGEXP ?)
   )

ORDER BY result_type, library, name
LIMIT 500
"""


_SYMBOL_IDS_SQL = """
SELECT s.id FROM symbol s
WHERE s.name             REGEXP ?
   OR s.extends          REGEXP ?
   OR s.kicad_library_id REGEXP ?
   OR s.reference        REGEXP ?
   OR s.value            REGEXP ?
   OR s.footprint        REGEXP ?
   OR s.datasheet        REGEXP ?
   OR s.description      REGEXP ?
   OR s.keywords         REGEXP ?
   OR s.mpn              REGEXP ?
   OR s.manufacturer     REGEXP ?
   OR s.package          REGEXP ?
   OR s.mounting         REGEXP ?
   OR s.category         REGEXP ?
   OR s.library_name     REGEXP ?
   OR EXISTS (
       SELECT 1 FROM symbol_property sp
       WHERE sp.symbol_id = s.id
         AND (sp.key REGEXP ? OR sp.value REGEXP ?)
   )
"""

_FOOTPRINT_IDS_SQL = """
SELECT f.id FROM footprint f
WHERE f.name               REGEXP ?
   OR f.description        REGEXP ?
   OR f.tags               REGEXP ?
   OR f.layer              REGEXP ?
   OR f.kicad_footprint_id REGEXP ?
   OR f.file_path          REGEXP ?
   OR EXISTS (
       SELECT 1 FROM footprint_property fp
       WHERE fp.footprint_id = f.id
         AND (fp.key REGEXP ? OR fp.value REGEXP ?)
   )
"""

_PARTS_BY_IDS_SQL = """
SELECT DISTINCT
    s.library_name                                                      AS symbol_library,
    CASE WHEN s.kicad_library_id != '' THEN s.kicad_library_id
         ELSE s.name END                                                AS symbol_name,
    f.kicad_footprint_id                                                AS footprint,
    s.description,
    COALESCE(s.mpn, '')                                                 AS mpn,
    COALESCE(sol.model_path, '')                                        AS model_path,
    s.id                                                                AS symbol_id,
    s.name                                                              AS symbol_raw_name,
    l.library_path                                                      AS library_path,
    COALESCE(s.digikey_pn, '')                                          AS digikey_pn,
    COALESCE(s.mouser_pn,  '')                                          AS mouser_pn,
    COALESCE(s.tme_pn,     '')                                          AS tme_pn,
    COALESCE(s.lcsc_pn,    '')                                          AS lcsc_pn
FROM part p
JOIN symbol s    ON s.id = p.symbol_id
JOIN footprint f ON f.id = p.footprint_id
JOIN library l   ON l.id = s.library_id
LEFT JOIN solid sol ON sol.footprint_id = f.id
WHERE {where}
ORDER BY symbol_library, symbol_name
LIMIT 500
"""


def _make_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.create_function(
        "REGEXP", 2,
        lambda pattern, value: bool(re.search(pattern, value or "", re.IGNORECASE)),
    )
    return conn


def run_search(db_path: str, pattern: str) -> list[SearchResult]:
    """Search the kicaddy database with a regular expression.

    Applies the pattern to all text fields in symbol, symbol_property,
    footprint, and footprint_property tables.

    Raises ValueError on an invalid regex pattern or database error.
    Returns up to 500 SearchResult objects, ordered by type → library → name.
    """
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from exc

    try:
        conn = _make_connection(db_path)
    except Exception as exc:
        raise ValueError(f"Cannot open database: {exc}") from exc

    # 17 params for the symbol branch + 8 for the footprint branch
    params = (pattern,) * 25
    try:
        rows = conn.execute(_SEARCH_SQL, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"Database query failed: {exc}") from exc
    finally:
        conn.close()

    return [
        SearchResult(
            result_type=row[0],
            library=row[1] or "",
            name=row[2] or "",
            description=row[3] or "",
            extra1=row[4] or "",
            extra2=row[5] or "",
        )
        for row in rows
    ]


def search_parts(db_path: str, pattern: str) -> list[PartResult]:
    """Return parts linked to any symbol or footprint matching pattern.

    Fetches matching symbol IDs and footprint IDs separately, then looks up
    part rows that reference either set.

    Raises ValueError on an invalid regex pattern or database error.
    Returns up to 500 PartResult objects, ordered by symbol_library, symbol_name.
    """
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regular expression: {exc}") from exc

    try:
        conn = _make_connection(db_path)
    except Exception as exc:
        raise ValueError(f"Cannot open database: {exc}") from exc

    try:
        symbol_ids = [r[0] for r in conn.execute(_SYMBOL_IDS_SQL, (pattern,) * 17).fetchall()]
        footprint_ids = [r[0] for r in conn.execute(_FOOTPRINT_IDS_SQL, (pattern,) * 8).fetchall()]

        if not symbol_ids and not footprint_ids:
            return []

        conditions = []
        params: list = []
        if symbol_ids:
            conditions.append(f"p.symbol_id IN ({','.join('?' * len(symbol_ids))})")
            params.extend(symbol_ids)
        if footprint_ids:
            conditions.append(f"p.footprint_id IN ({','.join('?' * len(footprint_ids))})")
            params.extend(footprint_ids)

        sql = _PARTS_BY_IDS_SQL.format(where=" OR ".join(conditions))
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise ValueError(f"Database query failed: {exc}") from exc
    finally:
        conn.close()

    return [
        PartResult(
            symbol_library=row[0] or "",
            symbol_name=row[1] or "",
            footprint=row[2] or "",
            description=row[3] or "",
            mpn=row[4] or "",
            model_path=row[5] or "",
            symbol_id=row[6] or 0,
            symbol_raw_name=row[7] or "",
            library_path=row[8] or "",
            digikey_pn=row[9] or "",
            mouser_pn=row[10] or "",
            tme_pn=row[11] or "",
            lcsc_pn=row[12] or "",
        )
        for row in rows
    ]


def update_part_supplier_field(
    db_path: str,
    symbol_id: int,
    field_name: str,
    value: str,
) -> None:
    """Persist a supplier PN or MPN edit to the database.

    Raises ValueError on database error or unknown field name.
    """
    from kicaddy import db as _db

    try:
        conn = _db.get_connection(db_path)
    except Exception as exc:
        raise ValueError(f"Cannot open database: {exc}") from exc
    try:
        _db.update_symbol_supplier_field(conn, symbol_id, field_name, value)
    except Exception as exc:
        raise ValueError(f"Failed to save: {exc}") from exc
    finally:
        conn.close()
