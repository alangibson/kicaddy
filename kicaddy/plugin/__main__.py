"""Standalone entry point for the Kicaddy search dialog.

Run without KiCad:

    python -m kicaddy.plugin [--db PATH]

Requires wxPython (pip install wxPython).
"""
from __future__ import annotations

import argparse
import sys

import wx

from . import config
from .search_dialog import SearchDialog


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="python -m kicaddy.plugin",
        description="Kicaddy — regex search over KiCad symbol and footprint index",
    )
    ap.add_argument("--db", metavar="PATH", help="Path to kicaddy.db (overrides saved config)")
    args = ap.parse_args()

    if args.db:
        config.set_db_path(args.db)

    app = wx.App(False)
    dlg = SearchDialog(None)
    dlg.ShowModal()
    dlg.Destroy()
    sys.exit(0)


if __name__ == "__main__":
    main()
