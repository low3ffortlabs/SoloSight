# settings_manager.py
import json
import os

SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "camera_labels": [],             # if empty, labels will be auto-filled "Cam 0", etc
    "enabled_cameras": {},           # map of camera_index->bool (all disabled by default)
    "save_path": "recordings",
    "record_chunk_minutes": 5,
    "max_record_minutes": 60,
    "window_geometry": None,
    "show_welcome_dialog": True
}


def _ensure_structure(data: dict) -> dict:
    """
    Ensure the loaded settings have all expected keys and sensible defaults.
    In particular, enabled_cameras should be a dictionary (index->bool).
    """
    out = dict(DEFAULT_SETTINGS)  # start with defaults
    if not isinstance(data, dict):
        return out

    # copy known keys if present
    for k in DEFAULT_SETTINGS.keys():
        if k in data:
            out[k] = data[k]

    # Normalize enabled_cameras to a dict (was previously a list in some older versions)
    ec = out.get("enabled_cameras", {})
    if isinstance(ec, list):
        # convert list to dict where index->value
        new_ec = {}
        for i, v in enumerate(ec):
            try:
                new_ec[str(i)] = bool(v)
            except Exception:
                new_ec[str(i)] = False
        out["enabled_cameras"] = new_ec
    elif not isinstance(ec, dict):
        out["enabled_cameras"] = {}

    # ensure camera_labels is a list
    if not isinstance(out.get("camera_labels"), list):
        out["camera_labels"] = []

    return out


def load_settings() -> dict:
    """
    Load settings from SETTINGS_FILE. If file missing or corrupted,
    return a fresh copy of DEFAULT_SETTINGS (not the same object).
    """
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data = _ensure_structure(data)
            return data
        except Exception:
            # If loading/parsing fails, fall back to defaults but don't overwrite file here
            return dict(DEFAULT_SETTINGS)
    # no file -> defaults
    return dict(DEFAULT_SETTINGS)


def save_settings(data: dict) -> None:
    """
    Save settings to disk. Will attempt to ensure structure before saving.
    """
    try:
        safe = _ensure_structure(data)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=2, sort_keys=False)
    except Exception as e:
        # Keep this friendly for debugging; don't raise to avoid crashing UI.
        print("Failed to save settings:", e)
