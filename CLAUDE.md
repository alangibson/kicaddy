# kicaddy

Crawls directories of KiCad s-expression symbol libraries (`.kicad_sym`) and
indexes them into a SQLite database.

## Setup

```bash
pip install -e .          # installs kicad-sym dependency
```

## Usage

```bash
python main.py /path/to/symbols [/more/dirs] --db kicaddy.db --log-level INFO
```

## Module Layout

```
kicaddy/
    models.py    # Library, Symbol, SymbolProperty dataclasses + LibraryType enum
    db.py        # SQLite schema, get_connection, create_schema, upsert_library,
                 #   insert_symbol, insert_symbol_properties
    parser.py    # parse_library_file() — uses kicad-sym to extract Library + Symbols
    crawler.py   # find_kicad_sym_files(), crawl_and_index(), CrawlStats
main.py          # CLI entry point (argparse)
```

## Database Schema

### `library`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `library_path` | TEXT UNIQUE | relative path to `.kicad_sym` file |
| `library_type` | TEXT | `"symbol"` or `"footprint"` (LibraryType enum) |
| `version` | INTEGER | e.g. `20241209` |
| `generator` | TEXT | e.g. `"kicad_symbol_editor"` |
| `generator_version` | TEXT | e.g. `"9.0"` |

### `symbol`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `library_id` | INTEGER FK | → `library.id` ON DELETE CASCADE |
| `name` | TEXT | symbol name within the library |
| `extends` | TEXT | parent symbol name, or `""` |
| `kicad_library_id` | TEXT | KiCad `LIBRARY_ID` property (e.g. `"Device:R"`) |
| `unit_id` | TEXT | KiCad `UNIT_ID` property |
| `reference` | TEXT | |
| `value` | TEXT | |
| `footprint` | TEXT | |
| `datasheet` | TEXT | |
| `description` | TEXT | from `ki_description` |
| `keywords` | TEXT | from `ki_keywords` |

### `symbol_property`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `symbol_id` | INTEGER FK | → `symbol.id` ON DELETE CASCADE |
| `key` | TEXT | |
| `value` | TEXT | |

## Packaging

`pyproject.toml` uses `build-backend = "setuptools.build_meta"` — the standard
modern setuptools backend. Do not use `setuptools.backends.legacy:build`; that
path does not exist in current setuptools and raises `BackendUnavailable`.

## Key Design Notes

- **Parsing**: uses [`kicad-sym`](https://pypi.org/project/kicad-sym/) — purpose-built
  for `.kicad_sym` files, zero dependencies. `kicad_sym.properties(sym)` returns all
  properties as `dict[str, str]` in one call.
- **Standard vs extra properties**: keys in `STANDARD_PROPERTY_KEYS` (`models.py`) map
  to dedicated `symbol` columns; everything else goes into `symbol_property`.
- **`extends`**: extracted from the `(extends "...")` s-expression node, not a property.
- **Idempotent re-indexing**: `upsert_library` uses `ON CONFLICT DO UPDATE`; replacing
  a library row cascades-deletes its symbols and their properties, which are then
  re-inserted fresh.
- **Batch commits**: inserts are committed every 500 symbols to avoid per-row fsync cost.
- **`LibraryType`**: `StrEnum` — serializes directly to/from its string value in SQLite.
  Footprint library support is scaffolded for future use.

## Adding Footprint Library Support

1. Add `find_kicad_mod_files()` to `crawler.py` targeting `.kicad_mod` files.
2. Add a `parse_footprint_library_file()` to `parser.py`.
3. Pass `LibraryType.FOOTPRINT` when calling `upsert_library`.
4. Add a `footprint` table (analogous to `symbol`) with its own FK to `library`.
