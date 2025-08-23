import os
import sys
from PyQt5.QtGui import QIcon
import theme

# Project-relative icons folder
ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")

def resource_path(relative_path: str) -> str:
    """Return absolute path to resource; works in dev and PyInstaller."""
    try:
        # PyInstaller stores temp files in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

def icon(name: str, size: int = None) -> QIcon:
    """
    Load an SVG icon from the /icons folder inside the project.
    If size is provided, returns the icon as-is (size handled in QPushButton setIconSize).
    """
    path = os.path.join(ICON_DIR, f"{name}.svg")
    if not os.path.exists(path):
        print(f"Icon not found: {path}")
        return QIcon()
    qicon = QIcon(path)
    return qicon

