from __future__ import annotations

import wx

from . import config
from .search import SearchResult, run_search

# ListCtrl column definitions: (header, width)
_COLUMNS = [
    ("Type",              70),
    ("Library",          160),
    ("Name",             220),
    ("Description",      260),
    ("MPN / Tags",       120),
    ("Footprint / Layer", 180),
]


class _ResultList(wx.ListCtrl):
    """Virtual ListCtrl backed by a list of SearchResult objects."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(
            parent,
            style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_HRULES | wx.LC_VRULES,
        )
        for idx, (header, width) in enumerate(_COLUMNS):
            self.InsertColumn(idx, header, width=width)
        self._results: list[SearchResult] = []

    def set_results(self, results: list[SearchResult]) -> None:
        self._results = results
        self.SetItemCount(len(results))
        self.Refresh()

    # -- wx.ListCtrl virtual overrides --

    def OnGetItemText(self, item: int, col: int) -> str:
        if item >= len(self._results):
            return ""
        r = self._results[item]
        return (r.result_type, r.library, r.name, r.description, r.extra1, r.extra2)[col]

    def OnGetItemAttr(self, item: int):  # noqa: N802
        return None

    def OnGetItemColumnImage(self, item: int, col: int) -> int:  # noqa: N802
        return -1


class SearchDialog(wx.Dialog):
    """Main Kicaddy search dialog."""

    def __init__(self, parent: wx.Window | None) -> None:
        super().__init__(
            parent,
            title="Kicaddy — Symbol & Footprint Search",
            size=(1050, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._results: list[SearchResult] = []
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
        root.Add(self._make_list(), proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=6)
        root.Add(self._make_status_row(), flag=wx.EXPAND | wx.ALL, border=6)
        self.SetSizerAndFit(root)
        self.SetSize((1050, 600))

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

    def _make_list(self) -> wx.Window:
        self._list = _ResultList(self)
        self._list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        return self._list

    def _make_status_row(self) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._status_label = wx.StaticText(self, label="Enter a regex pattern and press Search.")
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
            results = run_search(db_path, pattern)
        except ValueError as exc:
            self._set_status(str(exc), error=True)
            return

        self._results = results
        self._list.set_results(results)
        count = len(results)
        suffix = " (limit reached)" if count == 500 else ""
        self._set_status(f"{count} result{'s' if count != 1 else ''}{suffix}.", error=False)

    def _on_item_activated(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        if idx >= len(self._results):
            return
        r = self._results[idx]
        # Copy the canonical KiCad ID to the clipboard for easy pasting.
        text = r.name  # kicad_library_id for symbols, footprint name for footprints
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()
            self._set_status(f"Copied to clipboard: {text}", error=False)

    def _on_close(self, _event: wx.Event) -> None:
        self.EndModal(wx.ID_CANCEL)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, message: str, *, error: bool) -> None:
        self._status_label.SetForegroundColour(
            wx.RED if error else wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        )
        self._status_label.SetLabel(message)
        self._status_label.GetParent().Layout()
