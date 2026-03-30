# kicaddy

Crawls directories of KiCad s-expression symbol libraries (`.kicad_sym`) and
footprint libraries (`.pretty`) and indexes them into a SQLite database.

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
    models.py    # Library, Symbol, SymbolProperty, Footprint, Solid dataclasses + LibraryType enum
    db.py        # SQLite schema, get_connection, create_schema, upsert_library,
                 #   insert_symbol, insert_symbol_properties,
                 #   insert_footprint, insert_solid, link_symbols_to_footprints
    parser.py    # parse_library_file() — uses kicad-sym to extract Library + Symbols
                 # parse_footprint_library_dir() — extracts Library + Footprints from .pretty dir
    crawler.py   # find_kicad_sym_files(), find_kicad_pretty_dirs(),
                 #   crawl_and_index(), CrawlStats
main.py          # CLI entry point (argparse)
```

## Database Schema

### `library`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `library_path` | TEXT UNIQUE | relative path to `.kicad_sym` file or `.pretty` dir |
| `library_type` | TEXT | `"symbol"` or `"footprint"` (LibraryType enum) |
| `version` | INTEGER | e.g. `20241209`; `0` for footprint libraries |
| `generator` | TEXT | e.g. `"kicad_symbol_editor"`; `""` for footprint libraries |
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
| `footprint` | TEXT | raw footprint string, e.g. `"Resistor_SMD:R_0402_1005Metric"` |
| `datasheet` | TEXT | |
| `description` | TEXT | from `ki_description` |
| `keywords` | TEXT | from `ki_keywords` |
| `footprint_id` | INTEGER FK | → `footprint.id` (nullable; populated by linking pass) |

### `symbol_property`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `symbol_id` | INTEGER FK | → `symbol.id` ON DELETE CASCADE |
| `key` | TEXT | |
| `value` | TEXT | |

### `footprint`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `library_id` | INTEGER FK | → `library.id` ON DELETE CASCADE |
| `name` | TEXT | stem of `.kicad_mod` filename |
| `description` | TEXT | from `(descr "...")` |
| `tags` | TEXT | from `(tags "...")` |
| `layer` | TEXT | primary layer, from `(layer "...")` |
| `kicad_footprint_id` | TEXT | `"LibraryName:FootprintName"` (used for linking) |
| `file_path` | TEXT | relative path of the `.kicad_mod` file |

### `solid`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `footprint_id` | INTEGER FK | → `footprint.id` ON DELETE CASCADE (UNIQUE — 1:1) |
| `model_path` | TEXT | path as stored in the `.kicad_mod` `(model ...)` node |

## Packaging

`pyproject.toml` uses `build-backend = "setuptools.build_meta"` — the standard
modern setuptools backend. Do not use `setuptools.backends.legacy:build`; that
path does not exist in current setuptools and raises `BackendUnavailable`.

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
- **3D models**: `Solid` (1:1 with `footprint`) is populated from the `(model "...")` node
  in each `.kicad_mod`. Only present when the footprint declares a model; `Footprint.solid`
  is `None` otherwise.
- **Symbol→Footprint linking**: `crawl_and_index()` runs a SQL UPDATE after all data
  is indexed, matching `symbol.footprint` (e.g. `"Resistor_SMD:R_0402_1005Metric"`)
  against `footprint.kicad_footprint_id` to populate `symbol.footprint_id`.
- **Migration**: `create_schema` issues `ALTER TABLE` statements wrapped in try/except
  so existing databases are upgraded transparently.
- **Crawl phases**: (1) index symbol libraries, (2) index footprint libraries + solids,
  (3) link symbols to footprints.
