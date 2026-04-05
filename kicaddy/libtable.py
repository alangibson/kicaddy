from __future__ import annotations

import re
from pathlib import Path

import kicad_sym

from kicaddy.paths import paths as _kicad_paths


def _expand_vars(uri: str) -> str:
    combined = {**_kicad_paths.as_dict()}
    return re.sub(r"\$\{([^}]+)\}", lambda m: combined.get(m.group(1), m.group(0)), uri)


def parse_lib_table(table_path: Path) -> tuple[str, list[tuple[str, Path]]]:
    """Parse a KiCad lib-table file and return (table_type, [(name, path), ...]).

    table_type is the root node name, e.g. 'sym_lib_table' or 'fp_lib_table'.
    name is the logical library name from the (name ...) field.
    """
    data = kicad_sym.load(str(table_path))
    table_type = data[0] if data else ""
    entries: list[tuple[str, Path]] = []
    for node in data[1:]:
        if not isinstance(node, list) or node[0] != "lib":
            continue
        lib_name = ""
        uri = ""
        for item in node[1:]:
            if isinstance(item, list) and item[0] == "name":
                lib_name = item[1]
            elif isinstance(item, list) and item[0] == "uri":
                uri = item[1]
        if lib_name and uri:
            entries.append((lib_name, Path(_expand_vars(uri))))
    return table_type, entries


def get_sym_files(table_path: Path) -> list[Path]:
    """Return .kicad_sym file paths from a sym-lib-table."""
    _, entries = parse_lib_table(table_path)
    return [p for _, p in entries if p.suffix == ".kicad_sym"]


def get_fp_dirs(table_path: Path) -> list[Path]:
    """Return .pretty directory paths from a fp-lib-table."""
    _, entries = parse_lib_table(table_path)
    return [p for _, p in entries if p.suffix == ".pretty"]
