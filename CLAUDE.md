# kicaddy

Crawls directories of KiCad s-expression symbol libraries (`.kicad_sym`) and
footprint libraries (`.pretty`) and indexes them into a SQLite database.

## Module Layout

```
kicaddy/
    models.py    # Library, Symbol, SymbolProperty, Footprint, Part dataclasses + LibraryType enum
    db.py        # SQLite schema, get_connection, create_schema, upsert_library,
                 #   insert_symbol, insert_symbol_properties,
                 #   insert_footprint, link_symbols_to_footprints,
                 #   insert_parts_from_links
    parser.py    # parse_library_file() — uses kicad-sym to extract Library + Symbols
                 # parse_footprint_library_dir() — extracts Library + Footprints from .pretty dir
    crawler.py   # find_kicad_sym_files(), find_kicad_pretty_dirs(),
                 #   crawl_and_index(), CrawlStats
    index.py     # CLI entry point (argparse) — run with: python -m kicaddy.index
```

## Key Design Notes

- **Parsing**: uses [`kicad-sym`](https://pypi.org/project/kicad-sym/) — purpose-built
  for `.kicad_sym` files, zero dependencies. `kicad_sym.load()` is a generic
  s-expression parser and works on `.kicad_mod` footprint files too.
  `kicad_sym.properties(sym)` returns all properties as `dict[str, str]` in one call
  (symbol files only; not applicable to footprints).
- **Standard vs extra properties**: keys in `STANDARD_PROPERTY_KEYS` (`models.py`) map
  to dedicated `symbol` columns; everything else goes into `symbol_property`.
- **`extends`**: extracted from the `(extends "...")` s-expression node, not a property.
- **Idempotent re-indexing**: `upsert_library` uses `ON CONFLICT DO UPDATE`; replacing
  a library row cascades-deletes its child rows, which are then re-inserted fresh.
- **Batch commits**: inserts are committed every 500 items to avoid per-row fsync cost.
- **`LibraryType`**: `StrEnum` — serializes directly to/from its string value in SQLite.
- **Footprint libraries**: each `.pretty` directory is one `library` row
  (`library_type='footprint'`); each `.kicad_mod` inside becomes one `footprint` row.
- **Symbol→Footprint linking**: `crawl_and_index()` runs a SQL UPDATE after all data
  is indexed, matching `symbol.footprint` (e.g. `"Resistor_SMD:R_0402_1005Metric"`)
  against `footprint.kicad_footprint_id` to populate `symbol.footprint_id`.
- **Atomic Parts**: when a symbol has a matched footprint (`symbol.footprint_id IS NOT NULL`),
  they form an "atomic part" — the symbol defines the electrical function, the footprint
  defines the physical form. The `part` table captures this as a minimal join record
  (`symbol_id`, `footprint_id`), populated by `insert_parts_from_links()` after the
  symbol→footprint linking pass.
- **Migration**: `create_schema` issues `ALTER TABLE` statements wrapped in try/except
  so existing databases are upgraded transparently.
- **Crawl phases**: (1) index symbol libraries, (2) index footprint libraries,
  (3) link symbols to footprints, (4) populate part table.

## Documentation

- Always keep `README.md` up to date when making changes that affect usage,
  CLI commands, or module layout.
