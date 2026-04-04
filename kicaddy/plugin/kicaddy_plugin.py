from __future__ import annotations

import pcbnew

from .search_dialog import SearchDialog


class KicaddyPlugin(pcbnew.ActionPlugin):
    def defaults(self) -> None:
        self.name = "Kicaddy"
        self.category = "Search"
        self.description = "Regex search over KiCad symbol and footprint index"
        self.show_toolbar_button = True

    def Run(self) -> None:  # noqa: N802
        parent = pcbnew.GetCurrentFrame()
        dlg = SearchDialog(parent)
        dlg.ShowModal()
        dlg.Destroy()
