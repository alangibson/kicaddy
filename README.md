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
python -m kicaddy.index <DIR> [DIR ...] [--db PATH] [--log-level LEVEL]
```

**Arguments**

| Argument | Default | Description |
|---|---|---|
| `DIR` | _(required)_ | One or more directories to crawl recursively |
| `--db PATH` | `kicaddy.db` | SQLite database file to write |
| `--log-level` | `INFO` | Verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**Example**

```bash
python -m kicaddy.index ~/kicad/symbols /my/custom-libs --db index.db
```

## Kicaddy Plugin

A wxPython search dialog that applies regular expressions to all text fields in
`symbol`, `symbol_property`, `footprint`, and `footprint_property` tables.

### Standalone (for testing — no KiCad required)

```bash
pip install wxPython        # if not already installed
python -m kicaddy.plugin --db path/to/kicaddy.db
```

Omit `--db` to use the path saved from a previous session (stored in
`kicaddy/plugin/kicaddy.ini`) or set the `KICADDY_DB` environment variable.

Once the dialog is open:
- Type a Python regular expression in the **Search** box and press **Enter** or click **Search**.
- Results are shown across all symbol and footprint text fields.
- **Double-click** a result to copy its KiCad ID (`Device:R`, `Resistor_SMD:R_0402_1005Metric`, …) to the clipboard.
- Use **Browse…** to change the database file; the new path is saved automatically.

### KiCad 9 (action plugin)

Symlink (or copy) the plugin directory into KiCad's scripting plugins path, then
refresh plugins or restart KiCad:

```bash
ln -s "$PWD/kicaddy/plugin" \
      ~/.local/share/kicad/9.0/scripting/plugins/kicaddy
```

The plugin appears under **Tools → External Plugins → Kicaddy** in the PCB editor.
