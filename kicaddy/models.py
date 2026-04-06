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
    # Digi-Key aliases
    "digikey", "digi-key", "digi_key",
    "digikey#", "digikey_#", "digikey-#",
    "digi-key#", "digi-key_#", "digi-key-#",
    "digikeypn", "digikey_pn", "digikey-pn",
    "digikeypn#", "digikey_pn#", "digikey-pn#",
    "digi-key_pn", "digi-key-pn", "digi-key_pn#", "digi-key-pn#",
    "digikeyvpn", "digikey_vpn", "digikey-vpn",
    "digikeyvpn#", "digikey_vpn#", "digikey-vpn#",
    "digikeyvp", "digikey_vp", "digikey-vp",
    "digikeyvp#", "digikey_vp#", "digikey-vp#",
    "digikeyvendor", "digikey_vendor", "digikey-vendor",
    "digikeyvendor#", "digikey_vendor#", "digikey-vendor#",
    "digikeynum", "digikey_num", "digikey-num",
    "digikeynum#", "digikey_num#", "digikey-num#",
    "DigiKey_PN", "Digi-Key_PN",
    # Mouser aliases
    "mouser",
    "mouser#", "mouser_#", "mouser-#",
    "mouserpn", "mouser_pn", "mouser-pn",
    "mouserpn#", "mouser_pn#", "mouser-pn#",
    "mouservpn", "mouser_vpn", "mouser-vpn",
    "mouservpn#", "mouser_vpn#", "mouser-vpn#",
    "mouservp", "mouser_vp", "mouser-vp",
    "mouservp#", "mouser_vp#", "mouser-vp#",
    "mouservendor", "mouser_vendor", "mouser-vendor",
    "mouservendor#", "mouser_vendor#", "mouser-vendor#",
    "mousernum", "mouser_num", "mouser-num",
    "mousernum#", "mouser_num#", "mouser-num#",
    "Mouser_PN", "Mouser PN",
    # TME aliases
    "tme",
    "tme#", "tme_#", "tme-#",
    "tmepn", "tme_pn", "tme-pn",
    "tmepn#", "tme_pn#", "tme-pn#",
    "tmevpn", "tme_vpn", "tme-vpn",
    "tmevpn#", "tme_vpn#", "tme-vpn#",
    "tmevp", "tme_vp", "tme-vp",
    "tmevp#", "tme_vp#", "tme-vp#",
    "tmenum", "tme_num", "tme-num",
    "tmenum#", "tme_num#", "tme-num#",
    "TME_PN",
    # LCSC aliases
    "lcsc",
    "lcsc#", "lcsc_#", "lcsc-#",
    "lcscpn", "lcsc_pn", "lcsc-pn",
    "lcscpn#", "lcsc_pn#", "lcsc-pn#",
    "lcscvpn", "lcsc_vpn", "lcsc-vpn",
    "lcscvpn#", "lcsc_vpn#", "lcsc-vpn#",
    "lcscvp", "lcsc_vp", "lcsc-vp",
    "lcscvp#", "lcsc_vp#", "lcsc-vp#",
    "lcscnum", "lcsc_num", "lcsc-num",
    "lcscnum#", "lcsc_num#", "lcsc-num#",
    "LCSC_PN", "LCSC Part", "LCSC Part Number",
})


@dataclass
class Library:
    library_path: str       # absolute path to the .kicad_sym file
    library_type: LibraryType
    version: int            # e.g. 20241209
    generator: str          # e.g. "kicad_symbol_editor"
    generator_version: str  # e.g. "9.0"; empty string if absent
    name: str               # logical name from lib-table (e.g. "Device"), else stem of path
    permissions: str        # "rw" if current user can write, "ro" otherwise
    id: int | None = None


@dataclass
class SymbolProperty:
    key: str
    value: str
    symbol_id: int | None = None
    id: int | None = None


@dataclass
class FootprintProperty:
    key: str
    value: str
    footprint_id: int | None = None
    id: int | None = None


@dataclass
class Solid:
    model_path: str              # fully resolved absolute path to the 3D model file
    svg: str | None = None       # cached SVG content rendered from model_path, NULL until rendered
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
    extra_properties: list[FootprintProperty] = field(default_factory=list)
    id: int | None = None


@dataclass
class Part:
    symbol_id: int    # FK → symbol.id
    footprint_id: int # FK → footprint.id
    id: int | None = None


@dataclass
class Symbol:
    library_id: int             # FK → library.id
    name: str
    extends: str | None         # parent symbol name if this extends another, else None
    kicad_library_id: str       # KiCad "LIBRARY_ID" property, e.g. "Device:R"
    unit_id: str | None         # KiCad "UNIT_ID" property, e.g. "1"
    reference: str
    value: str
    footprint: str
    datasheet: str
    description: str            # from ki_description
    keywords: str               # from ki_keywords
    # Extracted from symbol properties (with alias resolution)
    mpn: str | None = None     # Manufacturer Part Number
    manufacturer: str | None = None  # Manufacturer name
    package: str | None = None  # Package/footprint name (e.g. "SOT-23", "R_0402_1005Metric")
    digikey_pn: str | None = None    # Digi-Key part number
    mouser_pn: str | None = None     # Mouser part number
    tme_pn: str | None = None        # TME part number
    lcsc_pn: str | None = None       # LCSC part number
    # Derived from library file path and footprint string
    mounting: str | None = None  # "SMD", "THT", or None
    category: str | None = None  # First segment of library name (e.g. "Resistor", "MCU")
    library_name: str = ""    # Stem of .kicad_sym file (e.g. "Resistor_SMD")
    extra_properties: list[SymbolProperty] = field(default_factory=list)
    id: int | None = None
