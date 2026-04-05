from __future__ import annotations

import os
import threading
import wx
import wx.grid
import wx.svg

from . import config
from .search import PartResult, SearchResult, run_search, search_parts, update_part_supplier_field
from kicaddy.sym_writer import write_symbol_property

# Grid column definitions per tab: list of (header, width)
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


class _ResultTableBase(wx.grid.GridTableBase):
    """GridTableBase backed by a list of result objects."""

    def __init__(self, columns: list[tuple[str, int]], field_fn, editable_cols=frozenset()) -> None:
        super().__init__()
        self._columns = columns
        self._field_fn = field_fn
        self._editable_cols = editable_cols
        self._results: list = []
        self._ro_attr = wx.grid.GridCellAttr()
        self._ro_attr.SetReadOnly(True)

    def set_results(self, results: list) -> None:
        old = len(self._results)
        self._results = results
        new = len(results)
        grid = self.GetView()
        if grid is None:
            return
        grid.BeginBatch()
        if old > new:
            grid.ProcessTableMessage(wx.grid.GridTableMessage(
                self, wx.grid.GRIDTABLE_NOTIFY_ROWS_DELETED, new, old - new))
        elif new > old:
            grid.ProcessTableMessage(wx.grid.GridTableMessage(
                self, wx.grid.GRIDTABLE_NOTIFY_ROWS_APPENDED, new - old))
        grid.EndBatch()
        grid.ForceRefresh()

    def GetNumberRows(self) -> int:
        return len(self._results)

    def GetNumberCols(self) -> int:
        return len(self._columns)

    def GetColLabelValue(self, col: int) -> str:  # noqa: N802
        return self._columns[col][0]

    def IsEmptyCell(self, row: int, col: int) -> bool:  # noqa: N802
        return False

    def GetValue(self, row: int, col: int) -> str:  # noqa: N802
        if row >= len(self._results):
            return ""
        return self._field_fn(self._results[row], col)

    def SetValue(self, row: int, col: int, value: str) -> None:  # noqa: N802
        pass  # commit handled in dialog via EVT_GRID_CELL_CHANGED

    def GetAttr(self, row: int, col: int, kind) -> wx.grid.GridCellAttr | None:  # noqa: N802
        if col not in self._editable_cols:
            self._ro_attr.IncRef()
            return self._ro_attr
        return None


class _ResultGrid(wx.grid.Grid):
    """wx.grid.Grid wrapper backed by _ResultTableBase."""

    def __init__(
        self,
        parent: wx.Window,
        columns: list[tuple[str, int]],
        field_fn,
        editable_cols=frozenset(),
    ) -> None:
        super().__init__(parent)
        self._table = _ResultTableBase(columns, field_fn, editable_cols)
        self.SetTable(self._table, takeOwnership=False)
        self.SetRowLabelSize(0)
        self.DisableDragRowSize()
        self.SetSelectionMode(wx.grid.Grid.SelectRows)
        for idx, (_header, width) in enumerate(columns):
            self.SetColSize(idx, width)

    def set_results(self, results: list) -> None:
        self._table.set_results(results)


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
        self._pending_cell_value = ""
        self._build_ui()
        saved = config.get_db_path()
        if saved:
            self._db_path_input.SetValue(saved)
        for p in config.get_lib_tables():
            self._lib_tables_list.Append(p)
        self._pattern_input.SetFocus()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(self._make_search_row(), flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, border=6)
        root.Add(self._make_notebook(), proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)
        root.Add(self._make_status_row(), flag=wx.EXPAND | wx.ALL, border=6)
        self.SetSizerAndFit(root)
        self.SetSize((1300, 600))

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

        # Parts tab: splitter with grid on left, 3D preview on right
        parts_splitter = wx.SplitterWindow(self._notebook, style=wx.SP_LIVE_UPDATE)
        self._parts_grid = _ResultGrid(parts_splitter, _PART_COLUMNS, _part_field, _EDITABLE_PART_COLS)
        self._preview_panel = _PreviewPanel(parts_splitter)
        parts_splitter.SplitVertically(self._parts_grid, self._preview_panel, sashPosition=1010)
        parts_splitter.SetMinimumPaneSize(200)

        self._symbols_grid = _ResultGrid(self._notebook, _SYMBOL_COLUMNS, _symbol_field)
        self._footprints_grid = _ResultGrid(self._notebook, _FOOTPRINT_COLUMNS, _footprint_field)

        self._notebook.AddPage(parts_splitter, "Parts (0)")
        self._notebook.AddPage(self._symbols_grid, "Symbols (0)")
        self._notebook.AddPage(self._footprints_grid, "Footprints (0)")

        self._notebook.AddPage(self._make_config_tab(), "Configuration")

        self._parts_grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self._on_part_selected)
        self._parts_grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_DCLICK, self._on_item_activated)
        self._parts_grid.Bind(wx.grid.EVT_GRID_CELL_CHANGING, self._on_parts_cell_changing)
        self._parts_grid.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self._on_parts_cell_changed)
        for g in (self._symbols_grid, self._footprints_grid):
            g.Bind(wx.grid.EVT_GRID_CELL_LEFT_DCLICK, self._on_item_activated)

        return self._notebook

    def _make_config_tab(self) -> wx.Panel:
        from kicaddy.paths import paths as _kicad_paths

        panel = wx.Panel(self._notebook)
        outer = wx.BoxSizer(wx.VERTICAL)

        # Top row: two columns side by side
        columns = wx.BoxSizer(wx.HORIZONTAL)

        # --- Left column: lib tables ---
        left = wx.BoxSizer(wx.VERTICAL)
        left.Add(wx.StaticText(panel, label="Library Table Files:"), flag=wx.BOTTOM, border=4)
        self._lib_tables_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        left.Add(self._lib_tables_list, proportion=1, flag=wx.EXPAND | wx.BOTTOM, border=4)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(panel, label="Add\u2026")
        remove_btn = wx.Button(panel, label="Remove")
        add_btn.Bind(wx.EVT_BUTTON, self._on_lib_add)
        remove_btn.Bind(wx.EVT_BUTTON, self._on_lib_remove)
        btn_sizer.Add(add_btn, flag=wx.RIGHT, border=6)
        btn_sizer.Add(remove_btn)
        left.Add(btn_sizer)

        # --- Right column: path variables ---
        right = wx.BoxSizer(wx.VERTICAL)
        right.Add(wx.StaticText(panel, label="KiCad Path Variables:"), flag=wx.BOTTOM, border=4)
        path_vars = wx.ListCtrl(
            panel,
            style=wx.LC_REPORT | wx.LC_HRULES | wx.LC_VRULES | wx.BORDER_SIMPLE,
        )
        path_vars.InsertColumn(0, "Variable", width=220)
        path_vars.InsertColumn(1, "Value", width=340)
        for name, value in sorted(_kicad_paths.as_dict().items()):
            idx = path_vars.InsertItem(path_vars.GetItemCount(), name)
            path_vars.SetItem(idx, 1, value)
        right.Add(path_vars, proportion=1, flag=wx.EXPAND)

        columns.Add(left, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=10)
        columns.Add(right, proportion=1, flag=wx.EXPAND)
        outer.Add(columns, proportion=1, flag=wx.EXPAND | wx.ALL, border=6)

        # Bottom: database path + browse + re-index
        outer.Add(wx.StaticLine(panel), flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)
        db_sizer = wx.BoxSizer(wx.HORIZONTAL)
        db_label = wx.StaticText(panel, label="Database:")
        self._db_path_input = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        browse_btn = wx.Button(panel, label="Browse\u2026")
        browse_btn.Bind(wx.EVT_BUTTON, self._on_browse)
        self._reindex_btn = wx.Button(panel, label="Re-index")
        self._reindex_btn.Bind(wx.EVT_BUTTON, self._on_reindex)
        db_sizer.Add(db_label, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        db_sizer.Add(self._db_path_input, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        db_sizer.Add(browse_btn, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
        db_sizer.Add(self._reindex_btn, flag=wx.ALIGN_CENTER_VERTICAL)
        outer.Add(db_sizer, flag=wx.EXPAND | wx.ALL, border=6)

        panel.SetSizer(outer)
        return panel

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

        self._parts_grid.set_results(parts)
        self._preview_panel.show_message("Select a part to preview 3D model")
        self._symbols_grid.set_results(symbols)
        self._footprints_grid.set_results(footprints)

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

    def _on_part_selected(self, event: wx.grid.GridEvent) -> None:
        row = event.GetRow()
        results = self._parts_grid._table._results
        if row >= len(results):
            event.Skip()
            return
        svg = results[row].svg_path
        if svg and os.path.isfile(svg):
            with open(svg) as f:
                self._preview_panel.show_svg(f.read())
        else:
            self._preview_panel.show_message("No 3D model available")
        event.Skip()

    def _on_item_activated(self, event: wx.grid.GridEvent) -> None:
        row = event.GetRow()
        src = event.GetEventObject()
        if src is self._parts_grid:
            results = self._parts_grid._table._results
            if row >= len(results):
                return
            text = results[row].symbol_name
        elif src is self._symbols_grid:
            results = self._symbols_grid._table._results
            if row >= len(results):
                return
            text = results[row].name
        else:
            results = self._footprints_grid._table._results
            if row >= len(results):
                return
            text = results[row].name
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            self._set_status(f"Copied to clipboard: {text}", error=False)

    def _on_parts_cell_changing(self, event: wx.grid.GridEvent) -> None:
        row = event.GetRow()
        results = self._parts_grid._table._results
        if row >= len(results):
            event.Veto()
            return
        result = results[row]
        abs_lib_path = self._resolve_library_path(result.library_path)
        if not os.access(abs_lib_path, os.W_OK):
            self._set_status(
                f"Read-only library: {abs_lib_path} — cannot edit.",
                error=True,
            )
            event.Veto()
            return
        self._pending_cell_value = event.GetString()
        event.Skip()

    def _on_parts_cell_changed(self, event: wx.grid.GridEvent) -> None:
        row, col = event.GetRow(), event.GetCol()
        if col not in _EDITABLE_PART_COLS:
            return
        results = self._parts_grid._table._results
        if row >= len(results):
            return
        result = results[row]
        new_value = self._pending_cell_value.strip()
        if not new_value or new_value == _part_field(result, col):
            return
        field_name = _COL_TO_FIELD[col]
        db_path = self._db_path_input.GetValue().strip()
        abs_lib_path = self._resolve_library_path(result.library_path)

        try:
            update_part_supplier_field(db_path, result.symbol_id, field_name, new_value)
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return

        try:
            write_symbol_property(abs_lib_path, result.symbol_raw_name, field_name, new_value)
        except Exception as exc:
            self._set_status(f"DB saved, but file write failed: {exc}", error=True)
            return

        setattr(result, field_name, new_value)
        self._set_status(
            f"Saved {field_name} = {new_value!r} for {result.symbol_name}.",
            error=False,
        )

    def _on_close(self, _event: wx.Event) -> None:
        self.EndModal(wx.ID_CANCEL)

    def _on_lib_add(self, _event: wx.Event) -> None:
        with wx.FileDialog(
            self,
            "Select a KiCad library table file",
            wildcard="Library table files (*-lib-table)|*-lib-table|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                if self._lib_tables_list.FindString(path) == wx.NOT_FOUND:
                    self._lib_tables_list.Append(path)
                    config.set_lib_tables(list(self._lib_tables_list.GetItems()))

    def _on_lib_remove(self, _event: wx.Event) -> None:
        sel = self._lib_tables_list.GetSelection()
        if sel != wx.NOT_FOUND:
            self._lib_tables_list.Delete(sel)
            config.set_lib_tables(list(self._lib_tables_list.GetItems()))

    def _on_reindex(self, _event: wx.Event) -> None:
        from kicaddy import db
        from kicaddy.crawler import crawl_from_lib_tables

        db_path = self._db_path_input.GetValue().strip()
        if not db_path:
            self._set_status("No database path set.", error=True)
            return

        table_paths = list(self._lib_tables_list.GetItems())
        if not table_paths:
            self._set_status("No library tables configured.", error=True)
            return

        self._reindex_btn.Disable()
        self._set_status("Indexing\u2026", error=False)

        def _run() -> None:
            try:
                conn = db.get_connection(db_path)
                db.create_schema(conn)
                stats = crawl_from_lib_tables(table_paths, conn)
                conn.close()
                msg = (
                    f"Done. symbols={stats.symbols_indexed} "
                    f"footprints={stats.footprints_indexed} "
                    f"parts={stats.parts_created}"
                )
            except Exception as exc:
                msg = f"Error: {exc}"
            wx.CallAfter(self._reindex_done, msg)

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_library_path(self, library_path: str) -> str:
        """Resolve a possibly-relative library_path against the DB file's directory."""
        if os.path.isabs(library_path):
            return library_path
        db_dir = os.path.dirname(self._db_path_input.GetValue().strip())
        return os.path.normpath(os.path.join(db_dir, library_path))

    def _reindex_done(self, msg: str) -> None:
        error = msg.startswith("Error")
        self._set_status(msg, error=error)
        self._reindex_btn.Enable()

    def _set_status(self, message: str, *, error: bool) -> None:
        self._status_label.SetForegroundColour(
            wx.RED if error else wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        )
        self._status_label.SetValue(message)
        self._status_label.Refresh()
