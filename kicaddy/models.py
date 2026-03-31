from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class LibraryType(StrEnum):
    SYMBOL = "symbol"
    FOOTPRINT = "footprint"


# Properties routed into dedicated Symbol columns rather than symbol_property.
STANDARD_PROPERTY_KEYS: frozenset[str] = frozenset({
    # Core KiCad fields
    "Reference",
    "Value",
    "Footprint",
    "Datasheet",
    "ki_description",
    "ki_keywords",
    "LIBRARY_ID",
    "UNIT_ID",
    # MPN aliases
    "MPN",
    "mpn",
    "Part Number",
    "PartNumber",
    "Part_Number",
    "PART_NUMBER",
    # Manufacturer aliases
    "Manufacturer",
    "MFR",
    "Mfr",
    "manufacturer",
    "MANUFACTURER",
    # Package aliases
    "Package",
    "package",
    "Package/Case",
    "Package / Case",
})


@dataclass
class Library:
    library_path: str       # relative path to the .kicad_sym file
    library_type: LibraryType
    version: int            # e.g. 20241209
    generator: str          # e.g. "kicad_symbol_editor"
    generator_version: str  # e.g. "9.0"; empty string if absent
    id: int | None = None


@dataclass
class SymbolProperty:
    key: str
    value: str
    symbol_id: int | None = None
    id: int | None = None


@dataclass
class Solid:
    model_path: str              # relative path as stored in the .kicad_mod file
    footprint_id: int | None = None
    id: int | None = None


@dataclass
class Footprint:
    library_id: int             # FK → library.id
    name: str                   # stem of .kicad_mod filename
    description: str = ""       # from (descr "...")
    tags: str = ""              # from (tags "...")
    layer: str = ""             # from (layer "...")
    kicad_footprint_id: str = ""  # e.g. "Resistor_SMD:R_0402_1005Metric"
    file_path: str = ""         # relative path of the .kicad_mod file
    solid: Solid | None = None
    id: int | None = None


@dataclass
class Symbol:
    library_id: int             # FK → library.id
    name: str
    extends: str                # parent symbol name if this extends another, else ""
    kicad_library_id: str       # KiCad "LIBRARY_ID" property, e.g. "Device:R"
    unit_id: str                # KiCad "UNIT_ID" property, e.g. "1"
    reference: str
    value: str
    footprint: str
    datasheet: str
    description: str            # from ki_description
    keywords: str               # from ki_keywords
    # Extracted from symbol properties (with alias resolution)
    mpn: str = ""              # Manufacturer Part Number
    manufacturer: str = ""    # Manufacturer name
    package: str = ""         # Package/footprint name (e.g. "SOT-23", "R_0402_1005Metric")
    # Derived from library file path and footprint string
    mounting: str = ""        # "SMD", "THT", or ""
    category: str = ""        # First segment of library name (e.g. "Resistor", "MCU")
    library_name: str = ""    # Stem of .kicad_sym file (e.g. "Resistor_SMD")
    extra_properties: list[SymbolProperty] = field(default_factory=list)
    id: int | None = None
