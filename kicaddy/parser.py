from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import kicad_sym

from kicaddy.models import Footprint, Library, LibraryType, STANDARD_PROPERTY_KEYS, Symbol, SymbolProperty, ThreeDModel

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


def parse_footprint_library_dir(
    dir_path: Path,
    library_path: str,
) -> tuple[Library, list[Footprint]]:
    """
    Parse a .pretty footprint library directory and return (Library, list[Footprint]).

    Each .kicad_mod file in the directory becomes one Footprint.
    Footprint.library_id is left as 0 — the caller must set it after persisting
    the Library row.

    Logs a warning and skips individual files that cannot be parsed.
    """
    library = Library(
        library_path=library_path,
        library_type=LibraryType.FOOTPRINT,
        version=0,
        generator="",
        generator_version="",
    )

    library_name = Path(library_path).stem
    footprints: list[Footprint] = []
    for mod_file in sorted(dir_path.glob("*.kicad_mod")):
        try:
            file_path = f"{library_path}/{mod_file.name}"
            fp = _parse_footprint_file(mod_file, library_id=0, library_name=library_name, file_path=file_path)
            footprints.append(fp)
        except Exception as exc:
            logger.warning("Failed to parse footprint %s: %s", mod_file, exc)

    return library, footprints


def _parse_footprint_file(
    mod_file: Path,
    library_id: int,
    library_name: str,
    file_path: str = "",
) -> Footprint:
    """Parse a single .kicad_mod file and return a Footprint."""
    tree = kicad_sym.load(mod_file)

    name = mod_file.stem

    descr_node = kicad_sym.child(tree, "descr")
    description = str(descr_node[1]) if descr_node else ""

    tags_node = kicad_sym.child(tree, "tags")
    tags = str(tags_node[1]) if tags_node else ""

    layer_node = kicad_sym.child(tree, "layer")
    layer = str(layer_node[1]) if layer_node else ""

    threedmodel: ThreeDModel | None = None
    model_node = kicad_sym.child(tree, "model")
    if model_node:
        threedmodel = ThreeDModel(model_path=str(model_node[1]))

    return Footprint(
        library_id=library_id,
        name=name,
        description=description,
        tags=tags,
        layer=layer,
        kicad_footprint_id=f"{library_name}:{name}",
        file_path=file_path,
        threedmodel=threedmodel,
    )
