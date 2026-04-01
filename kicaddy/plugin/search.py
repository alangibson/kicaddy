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
    s.mpn                                                              AS extra1,
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
    f.tags                                                             AS extra1,
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
