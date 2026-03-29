from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import kicad_sym

from kicaddy.models import Library, LibraryType, STANDARD_PROPERTY_KEYS, Symbol, SymbolProperty

logger = logging.getLogger(__name__)


def parse_library_file(
    file_path: Path,
    library_path: str,
    library_type: LibraryType = LibraryType.SYMBOL,
) -> tuple[Library, list[Symbol]]:
    """
    Load a .kicad_sym file and return (Library, list[Symbol]).

    Symbol.library_id is left as 0 — the caller must set it after persisting
    the Library row.

    Logs a warning and returns an empty symbol list if the file cannot be
    parsed. Individual symbol extraction errors are also logged and skipped.
    """
    try:
        lib_tree = kicad_sym.load(file_path)
    except Exception as exc:
        logger.warning("Failed to load %s: %s", file_path, exc)
        return _empty_library(library_path, library_type), []

    library = _extract_library_metadata(lib_tree, library_path, library_type)

    symbols: list[Symbol] = []
    for name in kicad_sym.symbol_names(lib_tree):
        try:
            sym_node = kicad_sym.get_symbol(lib_tree, name)
            symbol = _extract_symbol(sym_node, name, library_id=0)
            symbols.append(symbol)
        except Exception as exc:
            logger.warning("Failed to extract symbol %r from %s: %s", name, file_path, exc)

    return library, symbols


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_library_metadata(
    lib_tree: kicad_sym.Form,
    library_path: str,
    library_type: LibraryType,
) -> Library:
    version_node = kicad_sym.child(lib_tree, "version")
    generator_node = kicad_sym.child(lib_tree, "generator")
    gen_ver_node = kicad_sym.child(lib_tree, "generator_version")

    version: int = int(version_node[1]) if version_node else 0
    generator: str = str(generator_node[1]) if generator_node else ""
    generator_version: str = str(gen_ver_node[1]) if gen_ver_node else ""

    return Library(
        library_path=library_path,
        library_type=library_type,
        version=version,
        generator=generator,
        generator_version=generator_version,
    )


def _empty_library(library_path: str, library_type: LibraryType) -> Library:
    return Library(
        library_path=library_path,
        library_type=library_type,
        version=0,
        generator="",
        generator_version="",
    )


def _extract_symbol(
    sym_node: kicad_sym.Form,
    name: str,
    library_id: int,
) -> Symbol:
    """
    Extract a Symbol from a parsed symbol form.

    Standard property keys are mapped to dedicated Symbol fields.
    All other properties become SymbolProperty instances.
    The 'extends' value comes from the (extends "...") child node,
    not from a property.
    """
    # extends is a structural node, not a property
    extends_node = kicad_sym.child(sym_node, "extends")
    extends: str = str(extends_node[1]) if extends_node else ""

    props: dict[str, str] = kicad_sym.properties(sym_node)

    extra_properties: list[SymbolProperty] = [
        SymbolProperty(key=k, value=v)
        for k, v in props.items()
        if k not in STANDARD_PROPERTY_KEYS
    ]

    return Symbol(
        library_id=library_id,
        name=name,
        extends=extends,
        kicad_library_id=props.get("LIBRARY_ID", ""),
        unit_id=props.get("UNIT_ID", ""),
        reference=props.get("Reference", ""),
        value=props.get("Value", ""),
        footprint=props.get("Footprint", ""),
        datasheet=props.get("Datasheet", ""),
        description=props.get("ki_description", ""),
        keywords=props.get("ki_keywords", ""),
        extra_properties=extra_properties,
    )


def _node_children(
    node: Sequence[kicad_sym.Node],
    tag: str,
) -> list[kicad_sym.Form]:
    """Return all direct child forms whose head matches tag."""
    return [
        child
        for child in node
        if isinstance(child, list) and kicad_sym.head(child) == tag
    ]
