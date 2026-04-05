from __future__ import annotations

import os
import threading
import wx
import wx.svg

from . import config
from .search import PartResult, SearchResult, run_search, search_parts

# ListCtrl column definitions per tab: list of (header, width)
_PART_COLUMNS = [
    ("Symbol Library", 140),
    ("Symbol",         200),
    ("Footprint",      220),
    ("Description",    220),
    ("MPN",            120),
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


def _part_field(r: PartResult, col: int) -> str:
    return (r.symbol_library, r.symbol_name, r.footprint, r.description, r.mpn)[col]


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
            size=(1050, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
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
        self.SetSize((1050, 600))

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
        parts_splitter.SplitVertically(self._parts_list, self._preview_panel, sashPosition=780)
        parts_splitter.SetMinimumPaneSize(200)

        self._symbols_list = _ResultList(self._notebook, _SYMBOL_COLUMNS, _symbol_field)
        self._footprints_list = _ResultList(self._notebook, _FOOTPRINT_COLUMNS, _footprint_field)

        self._notebook.AddPage(parts_splitter, "Parts (0)")
        self._notebook.AddPage(self._symbols_list, "Symbols (0)")
        self._notebook.AddPage(self._footprints_list, "Footprints (0)")

        self._notebook.AddPage(self._make_config_tab(), "Configuration")

        self._parts_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_part_selected)
        self._parts_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        for lst in (self._symbols_list, self._footprints_list):
            lst.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)

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
