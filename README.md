# kicaddy

Crawls directories of KiCad symbol libraries (`.kicad_sym`) and indexes them
into a SQLite database for fast querying.

## Requirements

- Python 3.11+

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
python main.py <DIR> [DIR ...] [--db PATH] [--log-level LEVEL]
```

**Arguments**

| Argument | Default | Description |
|---|---|---|
| `DIR` | _(required)_ | One or more directories to crawl recursively |
| `--db PATH` | `kicaddy.db` | SQLite database file to write |
| `--log-level` | `INFO` | Verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**Example**

```bash
python main.py ~/kicad/symbols /my/custom-libs --db index.db
```

## Database

Three tables are created in the output database.

**`library`** — one row per `.kicad_sym` file

| Column | Description |
|---|---|
| `library_path` | Relative path to the `.kicad_sym` file |
| `library_type` | `symbol` or `footprint` |
| `version` | KiCad version integer, e.g. `20241209` |
| `generator` | Tool that wrote the file, e.g. `kicad_symbol_editor` |
| `generator_version` | Tool version, e.g. `9.0` |

**`symbol`** — one row per symbol

| Column | Description |
|---|---|
| `library_id` | FK → `library.id` |
| `name` | Symbol name |
| `extends` | Parent symbol name if this symbol inherits from another |
| `kicad_library_id` | KiCad `LIBRARY_ID` property, e.g. `Device:R` |
| `unit_id` | KiCad `UNIT_ID` property |
| `reference` | Reference designator prefix, e.g. `R` |
| `value` | Default value |
| `footprint` | Default footprint |
| `datasheet` | Datasheet URL |
| `description` | From `ki_description` |
| `keywords` | From `ki_keywords` |

**`symbol_property`** — user-defined extra properties

| Column | Description |
|---|---|
| `symbol_id` | FK → `symbol.id` |
| `key` | Property name |
| `value` | Property value |

## Example queries

```sql
-- Find all resistors
SELECT s.name, s.description, s.keywords
FROM symbol s
JOIN library l ON l.id = s.library_id
WHERE s.keywords LIKE '%resistor%';

-- List all extra properties for a symbol
SELECT key, value
FROM symbol_property
WHERE symbol_id = (SELECT id FROM symbol WHERE name = 'R' LIMIT 1);

-- Count symbols per library
SELECT l.library_path, COUNT(*) AS symbol_count
FROM symbol s
JOIN library l ON l.id = s.library_id
GROUP BY l.id
ORDER BY symbol_count DESC;
```
