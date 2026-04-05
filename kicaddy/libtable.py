from __future__ import annotations

import re
from pathlib import Path

import kicad_sym

from kicaddy.paths import paths as _kicad_paths


def _expand_vars(uri: str) -> str:
    combined = {**_kicad_paths.as_dict()}
    return re.sub(r"\$\{([^}]+)\}", lambda m: combined.get(m.group(1), m.group(0)), uri)


def parse_lib_table(table_path: Path) -> tuple[str, list[Path]]:
    """Parse a KiCad lib-table file and return (table_type, [expanded_paths]).

    table_type is the root node name, e.g. 'sym_lib_table' or 'fp_lib_table'.
    """
    data = kicad_sym.load(str(table_path))
    table_type = data[0] if data else ""
    paths: list[Path] = []
    for node in data[1:]:
        if not isinstance(node, list) or node[0] != "lib":
            continue
        uri = ""
        for item in node[1:]:
            if isinstance(item, list) and item[0] == "uri":
                uri = item[1]
                break
        if uri:
            paths.append(Path(_expand_vars(uri)))
    return table_type, paths


def get_sym_files(table_path: Path) -> list[Path]:
    """Return .kicad_sym file paths from a sym-lib-table."""
    _, paths = parse_lib_table(table_path)
    return [p for p in paths if p.suffix == ".kicad_sym"]


def get_fp_dirs(table_path: Path) -> list[Path]:
    """Return .pretty directory paths from a fp-lib-table."""
    _, paths = parse_lib_table(table_path)
    return [p for p in paths if p.suffix == ".pretty"]
