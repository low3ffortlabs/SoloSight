# icon_loader.py
import os
import sys
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSize
import theme

def resource_path(relative_path: str) -> str:
    """Return the absolute path to a resource, works in dev and PyInstaller."""
    try:
        # PyInstaller stores temp files in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def icon(name: str, size: int = None) -> QIcon:
    """
    Load an SVG icon from the /icons folder.
    Example: icon("refresh"), icon("settings", theme.ICON_LARGE)
    """
    if size is None:
        size = theme.ICON_MEDIUM

    path = resource_path(f"icons/{name}.svg")
    qicon = QIcon(path)
    return qicon
