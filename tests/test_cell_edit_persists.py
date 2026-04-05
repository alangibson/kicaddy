"""Regression test: edits in the Parts tab must not silently disappear.

Root cause: _on_parts_cell_changed tried to read the new value via
self._parts_grid.GetCellValue(row, col), which routes through table.GetValue
and returns the *stale* value from _results (table.SetValue is a no-op).
The old==new check then always passed and the edit was silently dropped.

Additionally, wx.grid.GridEvent.GetString() is not reliably populated for
EVT_GRID_CELL_CHANGED across all wxPython versions.

Fix: capture the proposed value in EVT_GRID_CELL_CHANGING (where GetString()
is guaranteed) via self._pending_cell_value, then consume it in
EVT_GRID_CELL_CHANGED.
"""
import types
from unittest.mock import MagicMock, patch

from kicaddy.plugin.search import PartResult
from kicaddy.plugin.search_dialog import SearchDialog


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
        symbol_id=42,
        symbol_raw_name="MySym",
        library_path="/fake/TestLib.kicad_sym",
    )
    return PartResult(**{**defaults, **overrides})


def _make_dialog(result: PartResult) -> types.SimpleNamespace:
    """Build a minimal stand-in with the attributes _on_parts_cell_* need.

    wx.Dialog is a C++ extension type and cannot be instantiated without a
    running wx.App, so we use a plain namespace and call the unbound methods
    directly (SearchDialog._on_parts_cell_changing(dialog, event)).
    """
    dialog = types.SimpleNamespace()
    dialog._pending_cell_value = ""

    mock_grid = MagicMock()
    mock_grid._table._results = [result]
    dialog._parts_grid = mock_grid

    mock_db_input = MagicMock()
    mock_db_input.GetValue.return_value = "/fake/kicaddy.db"
    dialog._db_path_input = mock_db_input

    # Bind real helper methods so the handlers can call self._resolve_library_path etc.
    dialog._resolve_library_path = SearchDialog._resolve_library_path.__get__(dialog)
    dialog._set_status = MagicMock()
    return dialog


def _fire_changing(dialog, row: int, col: int, new_value: str) -> None:
    """Simulate EVT_GRID_CELL_CHANGING with GetString() returning new_value."""
    event = MagicMock()
    event.GetRow.return_value = row
    event.GetCol.return_value = col
    event.GetString.return_value = new_value
    with patch("os.access", return_value=True):
        SearchDialog._on_parts_cell_changing(dialog, event)


def _fire_changed(dialog, row: int, col: int) -> None:
    """Simulate EVT_GRID_CELL_CHANGED (GetString not relied upon)."""
    event = MagicMock()
    event.GetRow.return_value = row
    event.GetCol.return_value = col
    event.GetString.return_value = ""  # empty — as seen on some wxPython builds
    with patch("kicaddy.plugin.search_dialog.update_part_supplier_field"), \
         patch("kicaddy.plugin.search_dialog.write_symbol_property"):
        SearchDialog._on_parts_cell_changed(dialog, event)


def test_edit_updates_result_in_memory():
    """After editing Digikey# the in-memory PartResult must reflect the new value."""
    result = _make_result(digikey_pn="DK-001")
    dialog = _make_dialog(result)

    _fire_changing(dialog, row=0, col=5, new_value="DK-NEW")
    _fire_changed(dialog, row=0, col=5)

    assert result.digikey_pn == "DK-NEW"


def test_edit_calls_db_and_file_update():
    """A valid edit must persist to both the database and the .kicad_sym file."""
    result = _make_result(mouser_pn="MS-001")
    dialog = _make_dialog(result)

    _fire_changing(dialog, row=0, col=6, new_value="MS-NEW")

    with patch("kicaddy.plugin.search_dialog.update_part_supplier_field") as mock_db, \
         patch("kicaddy.plugin.search_dialog.write_symbol_property") as mock_file:
        event = MagicMock()
        event.GetRow.return_value = 0
        event.GetCol.return_value = 6
        event.GetString.return_value = ""
        SearchDialog._on_parts_cell_changed(dialog, event)

    mock_db.assert_called_once()
    mock_file.assert_called_once()


def test_empty_edit_does_not_overwrite():
    """Clearing a cell (empty string) must not overwrite the existing value."""
    result = _make_result(digikey_pn="DK-001")
    dialog = _make_dialog(result)

    _fire_changing(dialog, row=0, col=5, new_value="")
    _fire_changed(dialog, row=0, col=5)

    assert result.digikey_pn == "DK-001"


def test_unchanged_value_does_not_trigger_save():
    """Re-committing the same value must not write to DB or file."""
    result = _make_result(digikey_pn="DK-001")
    dialog = _make_dialog(result)

    _fire_changing(dialog, row=0, col=5, new_value="DK-001")

    with patch("kicaddy.plugin.search_dialog.update_part_supplier_field") as mock_db, \
         patch("kicaddy.plugin.search_dialog.write_symbol_property") as mock_file:
        event = MagicMock()
        event.GetRow.return_value = 0
        event.GetCol.return_value = 5
        event.GetString.return_value = ""
        SearchDialog._on_parts_cell_changed(dialog, event)

    mock_db.assert_not_called()
    mock_file.assert_not_called()
