"""Write supplier PN and MPN properties back into .kicad_sym files.

Uses the kicad_sym library to load, modify, and save the s-expression tree.
A .bak copy of the original file is created before each write.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import kicad_sym

# Canonical property key written to the file when no existing alias is present
_FIELD_CANONICAL_KEY: dict[str, str] = {
    "mpn":        "MPN",
    "digikey_pn": "Digikey_PN",
    "mouser_pn":  "Mouser_PN",
    "tme_pn":     "TME_PN",
    "lcsc_pn":    "LCSC_PN",
}

# All recognised alias keys per field (mirrors parser.py key tuples)
_FIELD_ALIAS_KEYS: dict[str, tuple[str, ...]] = {
    "mpn": (
        "MPN", "mpn", "Part Number", "PartNumber", "Part_Number", "PART_NUMBER",
    ),
    "digikey_pn": (
        "digikey", "digi-key", "digi_key",
        "digikey#", "digikey_#", "digikey-#",
        "digi-key#", "digi-key_#", "digi-key-#",
        "digikeypn",    "digikey_pn",    "digikey-pn",
        "digikeypn#",   "digikey_pn#",   "digikey-pn#",
        "digi-key_pn",  "digi-key-pn",
        "digi-key_pn#", "digi-key-pn#",
        "digikeyvpn",   "digikey_vpn",   "digikey-vpn",
        "digikeyvpn#",  "digikey_vpn#",  "digikey-vpn#",
        "digikeyvp",    "digikey_vp",    "digikey-vp",
        "digikeyvp#",   "digikey_vp#",   "digikey-vp#",
        "digikeyvendor",  "digikey_vendor",  "digikey-vendor",
        "digikeyvendor#", "digikey_vendor#", "digikey-vendor#",
        "digikeynum",   "digikey_num",   "digikey-num",
        "digikeynum#",  "digikey_num#",  "digikey-num#",
        "DigiKey_PN", "Digi-Key_PN",
    ),
    "mouser_pn": (
        "mouser",
        "mouser#", "mouser_#", "mouser-#",
        "mouserpn",    "mouser_pn",    "mouser-pn",
        "mouserpn#",   "mouser_pn#",   "mouser-pn#",
        "mouservpn",   "mouser_vpn",   "mouser-vpn",
        "mouservpn#",  "mouser_vpn#",  "mouser-vpn#",
        "mouservp",    "mouser_vp",    "mouser-vp",
        "mouservp#",   "mouser_vp#",   "mouser-vp#",
        "mouservendor",  "mouser_vendor",  "mouser-vendor",
        "mouservendor#", "mouser_vendor#", "mouser-vendor#",
        "mousernum",   "mouser_num",   "mouser-num",
        "mousernum#",  "mouser_num#",  "mouser-num#",
        "Mouser_PN", "Mouser PN",
    ),
    "tme_pn": (
        "tme",
        "tme#", "tme_#", "tme-#",
        "tmepn",   "tme_pn",   "tme-pn",
        "tmepn#",  "tme_pn#",  "tme-pn#",
        "tmevpn",  "tme_vpn",  "tme-vpn",
        "tmevpn#", "tme_vpn#", "tme-vpn#",
        "tmevp",   "tme_vp",   "tme-vp",
        "tmevp#",  "tme_vp#",  "tme-vp#",
        "tmenum",  "tme_num",  "tme-num",
        "tmenum#", "tme_num#", "tme-num#",
        "TME_PN",
    ),
    "lcsc_pn": (
        "lcsc",
        "lcsc#", "lcsc_#", "lcsc-#",
        "lcscpn",   "lcsc_pn",   "lcsc-pn",
        "lcscpn#",  "lcsc_pn#",  "lcsc-pn#",
        "lcscvpn",  "lcsc_vpn",  "lcsc-vpn",
        "lcscvpn#", "lcsc_vpn#", "lcsc-vpn#",
        "lcscvp",   "lcsc_vp",   "lcsc-vp",
        "lcscvp#",  "lcsc_vp#",  "lcsc-vp#",
        "lcscnum",  "lcsc_num",  "lcsc-num",
        "lcscnum#", "lcsc_num#", "lcsc-num#",
        "LCSC_PN", "LCSC Part", "LCSC Part Number",
    ),
}


def write_symbol_property(
    file_path: str | Path,
    symbol_name: str,
    field_name: str,
    value: str,
) -> None:
    """Write a supplier PN or MPN property into a .kicad_sym file in-place.

    Steps:
    1. Validates ``field_name``.
    2. Backs up the file to ``<file_path>.bak``.
    3. Loads the s-expression tree with kicad_sym.
    4. Locates the symbol by ``symbol_name`` (raw name, not kicad_library_id).
    5. If ``value`` is non-empty: creates or updates the property (reusing
       an existing alias key if present, otherwise using the canonical key).
       New properties are created as hidden so they don't clutter the schematic.
    6. If ``value`` is empty/whitespace: deletes the property under all alias keys.
    7. Saves the modified tree back to the file.

    Raises:
        ValueError: unknown field_name.
        KeyError: symbol_name not found in the library file.
        OSError: backup or file-write failure.
    """
    if field_name not in _FIELD_CANONICAL_KEY:
        raise ValueError(f"Unknown supplier field: {field_name!r}")

    path = Path(file_path)
    shutil.copy2(path, str(path) + ".bak")

    lib_tree = kicad_sym.load(path)
    sym_node = kicad_sym.get_symbol(lib_tree, symbol_name)  # raises KeyError if missing

    existing_props = kicad_sym.properties(sym_node)
    aliases = _FIELD_ALIAS_KEYS[field_name]
    canonical = _FIELD_CANONICAL_KEY[field_name]
    value = value.strip()

    if value:
        # Reuse whichever alias key is already in the file (case-insensitive), else use canonical
        existing_lower = {k.lower(): k for k in existing_props}
        write_key = next(
            (existing_lower[a.lower()] for a in aliases if a.lower() in existing_lower),
            canonical,
        )
        kicad_sym.set_property(sym_node, write_key, value, hidden=True)
    else:
        # Remove all alias keys (case-insensitive) so no empty stub remains
        existing_lower = {k.lower(): k for k in existing_props}
        for a in aliases:
            actual_key = existing_lower.get(a.lower())
            if actual_key is not None:
                kicad_sym.del_property(sym_node, actual_key)

    kicad_sym.save(path, lib_tree)
