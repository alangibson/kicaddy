"""Tests for column-index correctness in the Parts tab.

Regression for the bug where clicking an editable cell displayed the value from
the adjacent column.  Root cause: column hit-testing accumulated raw widths
against client-space x without accounting for horizontal scroll, so the wrong
column index was resolved.  The fix uses GetSubItemRect which returns
client-space rects directly.

The tests here verify the pure-Python column-mapping helpers that determine
which value to display and which DB field to write — if the mappings are
wrong the editor will silently corrupt the wrong field.
"""
from kicaddy.plugin.search import PartResult
from kicaddy.plugin.search_dialog import (
    _COL_TO_FIELD,
    _EDITABLE_PART_COLS,
    _PART_COLUMNS,
    _part_field,
)


def _make_result(**overrides) -> PartResult:
    defaults = dict(
        symbol_library="MyLib",
        symbol_name="MySym",
        footprint="MyLib:MyFP",
        description="A test part",
        mpn="MPN-001",
        digikey_pn="DK-001",
        mouser_pn="MS-001",
        tme_pn="TME-001",
        lcsc_pn="LCSC-001",
    )
    return PartResult(**{**defaults, **overrides})


def test_part_field_returns_correct_value_per_column():
    r = _make_result(permissions="ro")
    assert _part_field(r, 0) == "E"        # button column: ro library shows "E"
    assert _part_field(r, 1) == "MyLib"
    assert _part_field(r, 2) == "MySym"
    assert _part_field(r, 3) == "MyLib:MyFP"
    assert _part_field(r, 4) == "A test part"
    assert _part_field(r, 5) == "MPN-001"
    assert _part_field(r, 6) == "DK-001"
    assert _part_field(r, 7) == "MS-001"
    assert _part_field(r, 8) == "TME-001"
    assert _part_field(r, 9) == "LCSC-001"


def test_part_field_button_col_hidden_for_rw_library():
    r = _make_result(permissions="rw")
    assert _part_field(r, 0) == ""         # rw library: no button


def test_part_field_column_count_matches_part_columns():
    """_part_field must cover every column declared in _PART_COLUMNS."""
    r = _make_result()
    for col_idx in range(len(_PART_COLUMNS)):
        # Should not raise IndexError
        _part_field(r, col_idx)


def test_col_to_field_keys_match_editable_cols():
    """`_COL_TO_FIELD` must cover exactly the editable column set."""
    assert set(_COL_TO_FIELD.keys()) == _EDITABLE_PART_COLS


def test_col_to_field_maps_to_correct_attribute():
    r = _make_result()
    for col_idx, field_name in _COL_TO_FIELD.items():
        assert _part_field(r, col_idx) == getattr(r, field_name), (
            f"Column {col_idx} → _part_field returned {_part_field(r, col_idx)!r} "
            f"but _COL_TO_FIELD says field is {field_name!r} = {getattr(r, field_name)!r}"
        )
