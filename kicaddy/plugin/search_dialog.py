from __future__ import annotations

import os
import wx
import wx.svg

from . import config
from .search import PartResult, SearchResult, run_search, search_parts, update_part_supplier_field
from kicaddy.sym_writer import write_symbol_property

# ListCtrl column definitions per tab: list of (header, width)
_PART_COLUMNS = [
    ("Symbol Library", 140),
    ("Symbol",         200),
    ("Footprint",      200),
    ("Description",    200),
    ("MPN",            110),
    ("Digikey#",        90),
    ("Mouser#",         90),
    ("TME#",            80),
    ("LCSC#",           80),
]

_SYMBOL_COLUMNS = [
    ("Library",     160),
    ("Name",        220),
    ("Description", 260),
    ("MPN",         120),
    ("Footprint",   180),
]

_FOOTPRINT_COLUMNS = [
    ("Library",     160),
    ("Name",        220),
    ("Description", 260),
    ("Layer",       120),
]

# Columns (by index) in the Parts tab that support inline editing
_EDITABLE_PART_COLS = frozenset({4, 5, 6, 7, 8})

# Map column index → symbol table field name
_COL_TO_FIELD: dict[int, str] = {
    4: "mpn",
    5: "digikey_pn",
    6: "mouser_pn",
    7: "tme_pn",
    8: "lcsc_pn",
}


def _part_field(r: PartResult, col: int) -> str:
    return (
        r.symbol_library,
        r.symbol_name,
        r.footprint,
        r.description,
        r.mpn,
        r.digikey_pn,
        r.mouser_pn,
        r.tme_pn,
        r.lcsc_pn,
    )[col]


def _symbol_field(r: SearchResult, col: int) -> str:
    return (r.library, r.name, r.description, r.extra1, r.extra2)[col]


def _footprint_field(r: SearchResult, col: int) -> str:
    return (r.library, r.name, r.description, r.extra2)[col]


class _ResultList(wx.ListCtrl):
    """Virtual ListCtrl backed by a list of result objects."""

    def __init__(self, parent: wx.Window, columns: list[tuple[str, int]], field_fn) -> None:
        super().__init__(
            parent,
            style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_HRULES | wx.LC_VRULES,
        )
        for idx, (header, width) in enumerate(columns):
            self.InsertColumn(idx, header, width=width)
        self._field_fn = field_fn
        self._results: list = []

    def set_results(self, results: list) -> None:
        self._results = results
        self.SetItemCount(len(results))
        self.Refresh()

    # -- wx.ListCtrl virtual overrides --

    def OnGetItemText(self, item: int, col: int) -> str:  # noqa: N802
        if item >= len(self._results):
            return ""
        return self._field_fn(self._results[item], col)

    def OnGetItemAttr(self, item: int):  # noqa: N802
        return None

    def OnGetItemColumnImage(self, item: int, col: int) -> int:  # noqa: N802
        return -1


class _PreviewPanel(wx.Panel):
    """Right-hand panel in the Parts tab that shows a 3D model preview."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent)
        self._bitmap = wx.StaticBitmap(self)
        self._label = wx.StaticText(self, label="Select a part to preview 3D model")
        self._label.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddStretchSpacer()
        sizer.Add(self._bitmap, flag=wx.ALIGN_CENTER | wx.ALL, border=4)
        sizer.Add(self._label, flag=wx.ALIGN_CENTER | wx.ALL, border=4)
        sizer.AddStretchSpacer()
        self.SetSizer(sizer)

    def show_svg(self, svg_str: str) -> None:
        pw, ph = self.GetSize()
        size = max(min(pw, ph) - 16, 100)
        svg_img = wx.svg.SVGimage.CreateFromBytes(svg_str.encode())
        bmp = svg_img.ConvertToScaledBitmap(wx.Size(size, size), self)
        self._bitmap.SetBitmap(bmp)
        self._label.SetLabel("")
        self.Layout()

    def show_message(self, msg: str) -> None:
        self._bitmap.SetBitmap(wx.NullBitmap)
        self._label.SetLabel(msg)
        self.Layout()


class SearchDialog(wx.Dialog):
    """Main Kicaddy search dialog."""

    def __init__(self, parent: wx.Window | None) -> None:
        super().__init__(
            parent,
            title="Kicaddy — Symbol & Footprint Search",
            size=(1300, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._cell_editor: wx.TextCtrl | None = None
        self._build_ui()
        saved = config.get_db_path()
        if saved:
            self._db_path_input.SetValue(saved)
        self._pattern_input.SetFocus()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self._make_db_row(), flag=wx.EXPAND | wx.ALL, border=6)
        root.Add(self._make_search_row(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=6)
        root.Add(self._make_notebook(), proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)
        root.Add(self._make_status_row(), flag=wx.EXPAND | wx.ALL, border=6)
        self.SetSizerAndFit(root)
        self.SetSize((1300, 600))

    def _make_db_row(self) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, label="Database:")
        self._db_path_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        browse_btn = wx.Button(self, label="Browse…")
        browse_btn.Bind(wx.EVT_BUTTON, self._on_browse)
        sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        sizer.Add(self._db_path_input, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        sizer.Add(browse_btn, flag=wx.ALIGN_CENTER_VERTICAL)
        return sizer

    def _make_search_row(self) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        label = wx.StaticText(self, label="Search:")
        self._pattern_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self._pattern_input.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        search_btn = wx.Button(self, label="Search")
        search_btn.Bind(wx.EVT_BUTTON, self._on_search)
        search_btn.SetDefault()
        sizer.Add(label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        sizer.Add(self._pattern_input, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        sizer.Add(search_btn, flag=wx.ALIGN_CENTER_VERTICAL)
        return sizer

    def _make_notebook(self) -> wx.Notebook:
        self._notebook = wx.Notebook(self)

        # Parts tab: splitter with list on left, 3D preview on right
        parts_splitter = wx.SplitterWindow(self._notebook, style=wx.SP_LIVE_UPDATE)
        self._parts_list = _ResultList(parts_splitter, _PART_COLUMNS, _part_field)
        self._preview_panel = _PreviewPanel(parts_splitter)
        parts_splitter.SplitVertically(self._parts_list, self._preview_panel, sashPosition=1010)
        parts_splitter.SetMinimumPaneSize(200)

        self._symbols_list = _ResultList(self._notebook, _SYMBOL_COLUMNS, _symbol_field)
        self._footprints_list = _ResultList(self._notebook, _FOOTPRINT_COLUMNS, _footprint_field)

        self._notebook.AddPage(parts_splitter, "Parts (0)")
        self._notebook.AddPage(self._symbols_list, "Symbols (0)")
        self._notebook.AddPage(self._footprints_list, "Footprints (0)")

        self._parts_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_part_selected)
        self._parts_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        self._parts_list.Bind(wx.EVT_LEFT_DOWN, self._on_parts_left_down)
        for lst in (self._symbols_list, self._footprints_list):
            lst.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)

        return self._notebook

    def _make_status_row(self) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._status_label = wx.TextCtrl(
            self,
            value="Enter a regex pattern and press Search.",
            style=wx.TE_READONLY | wx.BORDER_NONE,
        )
        self._status_label.SetBackgroundColour(self.GetBackgroundColour())
        close_btn = wx.Button(self, label="Close")
        close_btn.Bind(wx.EVT_BUTTON, self._on_close)
        sizer.Add(self._status_label, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(close_btn, flag=wx.ALIGN_CENTER_VERTICAL)
        return sizer

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_browse(self, _event: wx.Event) -> None:
        with wx.FileDialog(
            self,
            "Select kicaddy database",
            wildcard="SQLite databases (*.db)|*.db|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                self._db_path_input.SetValue(path)
                config.set_db_path(path)

    def _on_search(self, _event: wx.Event) -> None:
        pattern = self._pattern_input.GetValue().strip()
        if not pattern:
            self._set_status("Enter a regex pattern and press Search.", error=False)
            return

        db_path = self._db_path_input.GetValue().strip()
        if not db_path:
            self._set_status("No database path set. Use Browse… to select kicaddy.db.", error=True)
            return

        try:
            parts = search_parts(db_path, pattern)
            all_results = run_search(db_path, pattern)
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return

        symbols = [r for r in all_results if r.result_type == "symbol"]
        footprints = [r for r in all_results if r.result_type == "footprint"]

        self._parts_list.set_results(parts)
        self._preview_panel.show_message("Select a part to preview 3D model")
        self._symbols_list.set_results(symbols)
        self._footprints_list.set_results(footprints)

        np, ns, nf = len(parts), len(symbols), len(footprints)
        self._notebook.SetPageText(0, f"Parts ({np})")
        self._notebook.SetPageText(1, f"Symbols ({ns})")
        self._notebook.SetPageText(2, f"Footprints ({nf})")

        total = np + ns + nf
        limit_note = " (limit reached on one or more tabs)" if any(n == 500 for n in (np, ns, nf)) else ""
        self._set_status(
            f"{total} result{'s' if total != 1 else ''}{limit_note} "
            f"({np} part{'s' if np != 1 else ''}, "
            f"{ns} symbol{'s' if ns != 1 else ''}, "
            f"{nf} footprint{'s' if nf != 1 else ''}).",
            error=False,
        )

    def _on_part_selected(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        results = self._parts_list._results
        if idx >= len(results):
            return
        svg = results[idx].svg_path
        if svg and os.path.isfile(svg):
            with open(svg) as f:
                self._preview_panel.show_svg(f.read())
        else:
            self._preview_panel.show_message("No 3D model available")

    def _on_item_activated(self, event: wx.ListEvent) -> None:
        src = event.GetEventObject()
        if src is self._parts_list:
            results = self._parts_list._results
            idx = event.GetIndex()
            if idx >= len(results):
                return
            text = results[idx].symbol_name
        else:
            lst = src  # _ResultList
            results = lst._results
            idx = event.GetIndex()
            if idx >= len(results):
                return
            text = results[idx].name
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            self._set_status(f"Copied to clipboard: {text}", error=False)

    def _on_parts_left_down(self, event: wx.MouseEvent) -> None:
        event.Skip()  # allow normal row selection to proceed

        x, y = event.GetPosition()
        item, _flags = self._parts_list.HitTest(wx.Point(x, y))
        if item < 0:
            return

        # Determine which column was clicked by accumulating widths
        col_hit = -1
        cumulative = 0
        for col_idx in range(len(_PART_COLUMNS)):
            cumulative += self._parts_list.GetColumnWidth(col_idx)
            if x < cumulative:
                col_hit = col_idx
                break

        if col_hit not in _EDITABLE_PART_COLS:
            return

        results = self._parts_list._results
        if item >= len(results):
            return
        result = results[item]

        # Check writability of the symbol's library file every time
        abs_lib_path = self._resolve_library_path(result.library_path)
        if not os.access(abs_lib_path, os.W_OK):
            self._set_status(
                f"Read-only library: {abs_lib_path} — cannot edit.",
                error=True,
            )
            return

        self._open_cell_editor(item, col_hit, result)

    def _on_close(self, _event: wx.Event) -> None:
        self.EndModal(wx.ID_CANCEL)

    # ------------------------------------------------------------------
    # Inline cell editor
    # ------------------------------------------------------------------

    def _open_cell_editor(self, item: int, col: int, result: PartResult) -> None:
        """Position a floating TextCtrl over the clicked cell."""
        # Destroy any existing editor first
        if self._cell_editor is not None:
            self._cell_editor.Destroy()
            self._cell_editor = None

        row_rect = self._parts_list.GetItemRect(item)

        # Calculate column left edge by accumulating widths
        col_x = 0
        for c in range(col):
            col_x += self._parts_list.GetColumnWidth(c)
        col_w = self._parts_list.GetColumnWidth(col)

        # Convert list-client coordinates to dialog coordinates
        cell_screen = self._parts_list.ClientToScreen(wx.Point(col_x, row_rect.y))
        cell_pos = self.ScreenToClient(cell_screen)

        current_value = _part_field(result, col)
        editor = wx.TextCtrl(
            self,
            value=current_value,
            pos=cell_pos,
            size=wx.Size(col_w, row_rect.height),
            style=wx.TE_PROCESS_ENTER | wx.BORDER_SIMPLE,
        )
        editor.SetFocus()
        editor.SelectAll()

        # Attach edit context as attributes for use in commit handler
        editor._edit_item = item
        editor._edit_col = col
        editor._edit_result = result
        editor._edit_field = _COL_TO_FIELD[col]

        editor.Bind(wx.EVT_TEXT_ENTER, self._on_cell_editor_commit)
        editor.Bind(wx.EVT_KILL_FOCUS, self._on_cell_editor_commit)
        editor.Bind(wx.EVT_KEY_DOWN, self._on_cell_editor_key)

        self._cell_editor = editor

    def _on_cell_editor_key(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            if self._cell_editor is not None:
                self._cell_editor.Destroy()
                self._cell_editor = None
            return
        event.Skip()

    def _on_cell_editor_commit(self, event: wx.Event) -> None:
        # Guard against re-entrancy: EVT_KILL_FOCUS fires again when Destroy() is called
        editor = self._cell_editor
        if editor is None:
            return
        self._cell_editor = None  # clear before Destroy to prevent re-entry

        new_value = editor.GetValue().strip()
        item       = editor._edit_item
        col        = editor._edit_col
        result     = editor._edit_result
        field_name = editor._edit_field
        editor.Destroy()

        db_path = self._db_path_input.GetValue().strip()
        abs_lib_path = self._resolve_library_path(result.library_path)

        # Write to database
        try:
            update_part_supplier_field(db_path, result.symbol_id, field_name, new_value)
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return

        # Write to .kicad_sym file (backs up to .bak first)
        try:
            write_symbol_property(abs_lib_path, result.symbol_raw_name, field_name, new_value)
        except Exception as exc:
            self._set_status(f"DB saved, but file write failed: {exc}", error=True)
            return

        # Update in-memory result so the list reflects the change immediately
        setattr(result, field_name, new_value)
        self._parts_list.RefreshItem(item)
        self._set_status(
            f"Saved {field_name} = {new_value!r} for {result.symbol_name}.",
            error=False,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_library_path(self, library_path: str) -> str:
        """Resolve a possibly-relative library_path against the DB file's directory."""
        if os.path.isabs(library_path):
            return library_path
        db_dir = os.path.dirname(self._db_path_input.GetValue().strip())
        return os.path.normpath(os.path.join(db_dir, library_path))

    def _set_status(self, message: str, *, error: bool) -> None:
        self._status_label.SetForegroundColour(
            wx.RED if error else wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        )
        self._status_label.SetValue(message)
        self._status_label.Refresh()
