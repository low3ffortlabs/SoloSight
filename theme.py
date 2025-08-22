# theme.py
# Simple theme config for SoloSight. Edit these values for UI customization.

APP_NAME = "SoloSight"
BACKGROUND = "#151515"
FOREGROUND = "#EDEDED"
ACCENT = "#FF7A00"   # orange accent
PANEL = "#1f1f1f"
LABEL_FONT = "Segoe UI"
BASE_FONT_SIZE = 10

# Icon sizes (in px)
ICON_SMALL = 16
ICON_MEDIUM = 28
ICON_LARGE = 48

# Global QSS for regular buttons
BUTTON_STYLE = f"""
QPushButton {{
    border: 4px solid {ACCENT};
    border-radius: 8px;
    min-width: 64px;
    min-height: 64px;
    padding: 8px;
    background: transparent;
    color: {ACCENT};
}}
QPushButton:checked {{
    background: {ACCENT};
    color: {BACKGROUND};
}}
QPushButton:hover {{
    background: rgba(255, 122, 0, 0.2);  /* semi-transparent hover */
    color: {ACCENT};
}}
"""

# Global QSS for icon-only buttons (camera edit/fullscreen)
ICON_BUTTON_STYLE = f"""
QPushButton {{
    border: 2px solid {ACCENT};
    border-radius: 8px;
    padding: 6px;
    background: transparent;
    color: {ACCENT};
}}
QPushButton:hover {{
    background: rgba(255, 122, 0, 0.2);  /* semi-transparent hover, icon stays visible */
}}
"""

# Recording chunk settings (in minutes)
RECORD_CHUNK_MINUTES = 5    # default chunk length (5-10)
RECORD_MAX_MINUTES = 60     # 1 hour max per session
