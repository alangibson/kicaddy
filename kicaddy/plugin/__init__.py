# KiCad 9 action plugin registration.
# This file is imported by KiCad's plugin loader. The try/except ensures it is
# safely importable outside of KiCad (e.g. during unit tests or standalone use).
try:
    import pcbnew  # noqa: F401 — available only inside KiCad
    from .kicaddy_plugin import KicaddyPlugin
    KicaddyPlugin().register()
except Exception:
    pass
