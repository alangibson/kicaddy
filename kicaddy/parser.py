from __future__ import annotations

import functools
import json
import logging
import os
import re
from pathlib import Path
from typing import Sequence

import kicad_sym

from kicaddy.models import Footprint, FootprintProperty, Library, LibraryType, Solid, STANDARD_PROPERTY_KEYS, Symbol, SymbolProperty
from kicaddy.paths import paths as _kicad_paths

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _load_kicad_path_vars() -> dict[str, str]:
    """Load user-defined path variables from KiCad's Configure Paths dialog."""
    config = _kicad_paths.KICAD_CONFIG_HOME / "kicad_common.json"
    try:
        data = json.loads(config.read_text())
        vars_list = data.get("environment", {}).get("vars") or []
        return {v["name"]: v["value"] for v in vars_list}
    except Exception:
        return {}


def _expand_model_path(raw: str, mod_file: Path) -> str:
    """Expand ${VAR} refs (KiCad vars override OS env) and resolve to absolute path."""
    # Priority: OS env < built-in KiCad paths < user-defined vars from kicad_common.json
    combined = {**os.environ, **_kicad_paths.as_dict(), **_load_kicad_path_vars()}
    expanded = re.sub(r"\$\{([^}]+)\}", lambda m: combined.get(m.group(1), m.group(0)), raw)
    if not os.path.isabs(expanded):
        expanded = str((mod_file.parent / expanded).resolve())
    return expanded


# ---------------------------------------------------------------------------
# Property key aliases for extracted fields
# ---------------------------------------------------------------------------

_MPN_KEYS = ("MPN", "mpn", "Part Number", "PartNumber", "Part_Number", "PART_NUMBER")
_MANUFACTURER_KEYS = ("Manufacturer", "MFR", "Mfr", "manufacturer", "MANUFACTURER")
_PACKAGE_PROP_KEYS = ("Package", "package", "Package/Case", "Package / Case")

# Library name prefixes / patterns that unambiguously indicate SMD packages
_SMD_FOOTPRINT_LIBS = frozenset({
    "Package_SO", "Package_QFP", "Package_QFN", "Package_BGA",
    "Package_DFN", "Package_TO_SOT_SMD", "Package_LGA", "Package_CSP",
})
# Library name prefixes / patterns that unambiguously indicate THT packages
_THT_FOOTPRINT_LIBS = frozenset({
    "Package_DIP", "Package_TO_SOT_THT", "Package_TO_SOT_Axial",
})
# Footprint name sub-strings (case-insensitive check via lower()) → SMD
_SMD_FP_HINTS = (
    "soic", "sot-", "sot_", "qfn", "qfp", "bga", "dfn-", "dfn_",
    "tssop", "ssop", "vssop", "sc-", "sc_", "wson", "uson", "lga",
    "csp", "fcbga",
)
# Footprint name sub-strings → THT
_THT_FP_HINTS = (
    "dip-", "dip_", "to-220", "to_220", "to-92", "to_92",
    "to-3", "to_3", "to-126", "to_126", "axial", "radial",
    "sip-", "sip_", "_tht",
)


def _first(props: dict[str, str], keys: tuple[str, ...]) -> str | None:
    """Return the value of the first matching key in props, or None."""
    for k in keys:
        if k in props:
            return props[k] or None
    return None


def _infer_mounting(footprint_str: str, library_name: str) -> str | None:
    """
    Infer mounting type ("SMD", "THT", or "") from multiple sources, in priority order:

    1. Footprint library name (part before ':') — explicit _SMD / _THT suffix or
       known package-family library names.
    2. Symbol library name — _SMD / _THT segment anywhere in the name.
    3. Footprint name heuristics (sub-string matching).
    """
    fp_lib = ""
    fp_name = ""
    if ":" in footprint_str:
        fp_lib, fp_name = footprint_str.split(":", 1)

    # 1. Footprint library name
    if fp_lib:
        if "_SMD" in fp_lib or fp_lib in _SMD_FOOTPRINT_LIBS:
            return "SMD"
        if "_THT" in fp_lib or fp_lib in _THT_FOOTPRINT_LIBS:
            return "THT"

    # 2. Symbol library name segments
    if library_name:
        parts = library_name.split("_")
        if "SMD" in parts:
            return "SMD"
        if "THT" in parts:
            return "THT"

    # 3. Footprint name heuristics
    if fp_name:
        fp_lower = fp_name.lower()
        for hint in _SMD_FP_HINTS:
            if hint in fp_lower:
                return "SMD"
        for hint in _THT_FP_HINTS:
            if hint in fp_lower:
                return "THT"

    return None


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
    lib_name = Path(library_path).stem

    symbols: list[Symbol] = []
    for name in kicad_sym.symbol_names(lib_tree):
        try:
            sym_node = kicad_sym.get_symbol(lib_tree, name)
            symbol = _extract_symbol(sym_node, name, library_id=0, library_name=lib_name)
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
    library_name: str = "",
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
    extends: str | None = str(extends_node[1]) if extends_node else None

    props: dict[str, str] = kicad_sym.properties(sym_node)

    extra_properties: list[SymbolProperty] = [
        SymbolProperty(key=k, value=v)
        for k, v in props.items()
        if k not in STANDARD_PROPERTY_KEYS
    ]

    footprint_str = props.get("Footprint", "")

    # Package: prefer explicit property, fall back to footprint name (part after ':')
    package = _first(props, _PACKAGE_PROP_KEYS)
    if not package and ":" in footprint_str:
        package = footprint_str.split(":", 1)[1] or None

    return Symbol(
        library_id=library_id,
        name=name,
        extends=extends,
        kicad_library_id=props.get("LIBRARY_ID", ""),
        unit_id=props.get("UNIT_ID") or None,
        reference=props.get("Reference", ""),
        value=props.get("Value", ""),
        footprint=footprint_str,
        datasheet=props.get("Datasheet", ""),
        description=props.get("ki_description", ""),
        keywords=props.get("ki_keywords", ""),
        mpn=_first(props, _MPN_KEYS),
        manufacturer=_first(props, _MANUFACTURER_KEYS),
        package=package,
        mounting=_infer_mounting(footprint_str, library_name),
        category=library_name.split("_")[0] if library_name else None,
        library_name=library_name,
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

    solid: Solid | None = None
    model_node = kicad_sym.child(tree, "model")
    if model_node:
        solid = Solid(model_path=_expand_model_path(str(model_node[1]), mod_file))

    extra_properties: list[FootprintProperty] = [
        FootprintProperty(key=str(node[1]), value=str(node[2]))
        for node in _node_children(tree, "property")
        if len(node) >= 3
    ]

    return Footprint(
        library_id=library_id,
        name=name,
        description=description,
        tags=tags,
        layer=layer,
        kicad_footprint_id=f"{library_name}:{name}",
        file_path=file_path,
        solid=solid,
        extra_properties=extra_properties,
    )
