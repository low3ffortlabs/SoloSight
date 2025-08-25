import os
import sys
import traceback
import webbrowser
import version

import cv2
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QApplication, QLineEdit, QDialog, QFileDialog, QFrame, QGroupBox,
    QFormLayout, QCheckBox, QDialogButtonBox
)
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtCore import QTimer, Qt, QSize

from icon_loader import icon
from settings_manager import load_settings, save_settings
from camera_manager import CameraWidget, find_available_cameras
import theme


def overlay_text(frame, text, x=10, y=20):
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (255, 255, 255), 1, cv2.LINE_AA)


class ResizableFullScreenDialog(QDialog):
    def __init__(self, label_text, update_func, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle(label_text)
        self.resize(800, 600)
        self.setMinimumSize(100, 100)

        self.full_label = QLabel()
        self.full_label.setAlignment(Qt.AlignCenter)
        self.full_label.setMinimumSize(100, 100)

        layout = QVBoxLayout()
        layout.addWidget(self.full_label)
        self.setLayout(layout)

        self.update_func = update_func

    def resizeEvent(self, event):
        self.update_func()
        return super().resizeEvent(event)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(theme.APP_NAME)
        self.setStyleSheet(f"background:{theme.BACKGROUND}; color:{theme.FOREGROUND};")
        self.setMinimumSize(640, 480)
        self.resize(800, 600)
        font = QFont(theme.LABEL_FONT, theme.BASE_FONT_SIZE)
        self.setFont(font)

        self.settings = load_settings()

        # Back-compat: support either list-based or dict-based labels in settings
        self.camera_labels_list = self.settings.get("camera_labels", [])
        self.camera_labels_map = self.settings.get("camera_labels_map", {})  # { "index": "label" }

        self.save_path = self.settings.get("save_path", "recordings")
        self.chunk_minutes = self.settings.get("record_chunk_minutes", theme.RECORD_CHUNK_MINUTES)
        self.max_minutes = self.settings.get("max_record_minutes", theme.RECORD_MAX_MINUTES)
        self.enabled_map = self.settings.get("enabled_cameras", {})  # { "index": bool }

        # Cache cameras once (so opening Settings is instant)
        self.all_cameras = find_available_cameras(8)  # list of dicts: {"index": int, "name": str}

        # If labels were previously saved as a list, map them onto current cameras (by order)
        if self.camera_labels_list and not self.camera_labels_map:
            for i, cam in enumerate(self.all_cameras):
                if i < len(self.camera_labels_list):
                    lbl = self.camera_labels_list[i]
                    if lbl:
                        self.camera_labels_map[str(cam["index"])] = lbl

        main_layout = QVBoxLayout()
        header = QHBoxLayout()
        title = QLabel(theme.APP_NAME)
        title.setStyleSheet(f"font-size:16pt; font-weight:bold; color:{theme.ACCENT};")
        header.addWidget(title)
        header.addStretch()
        self.status_label = QLabel("Ready")
        header.addWidget(self.status_label)
        main_layout.addLayout(header)

        self.grid = QGridLayout()
        self.grid_frame = QFrame()
        self.grid_frame.setLayout(self.grid)
        main_layout.addWidget(self.grid_frame)

        ctrl = QHBoxLayout()
        self.btn_record = QPushButton()
        self.btn_record.setIcon(icon("record", theme.ICON_MEDIUM))
        self.btn_record.setIconSize(QSize(theme.ICON_MEDIUM, theme.ICON_MEDIUM))
        self.btn_record.setStyleSheet(theme.ICON_BUTTON_STYLE)
        self.btn_record.setToolTip("Start/Stop Recording")
        self.btn_record.setCheckable(True)
        self.btn_record.clicked.connect(self.on_record_toggle)
        ctrl.addWidget(self.btn_record)

        self.btn_refresh = QPushButton()
        self.btn_refresh.setIcon(icon("refresh", theme.ICON_MEDIUM))
        self.btn_refresh.setIconSize(QSize(theme.ICON_MEDIUM, theme.ICON_MEDIUM))
        self.btn_refresh.setStyleSheet(theme.ICON_BUTTON_STYLE)
        self.btn_refresh.setToolTip("Refresh Cameras")
        self.btn_refresh.clicked.connect(self.refresh_cameras)
        ctrl.addWidget(self.btn_refresh)

        self.btn_settings = QPushButton()
        self.btn_settings.setIcon(icon("settings", theme.ICON_MEDIUM))
        self.btn_settings.setIconSize(QSize(theme.ICON_MEDIUM, theme.ICON_MEDIUM))
        self.btn_settings.setStyleSheet(theme.ICON_BUTTON_STYLE)
        self.btn_settings.setToolTip("Settings")
        self.btn_settings.clicked.connect(self.open_settings)
        ctrl.addWidget(self.btn_settings)

        self.btn_instructions = QPushButton()
        self.btn_instructions.setIcon(icon("instructions", theme.ICON_MEDIUM))
        self.btn_instructions.setIconSize(QSize(theme.ICON_MEDIUM, theme.ICON_MEDIUM))
        self.btn_instructions.setStyleSheet(theme.ICON_BUTTON_STYLE)
        self.btn_instructions.setToolTip("Instructions")
        self.btn_instructions.clicked.connect(self.open_instructions)
        ctrl.addWidget(self.btn_instructions)

        main_layout.addLayout(ctrl)
        self.setLayout(main_layout)

        self.camera_widgets = []
        self.record_indicator = QLabel()
        self.record_indicator.setFixedSize(14, 14)
        self.record_indicator.setStyleSheet("background-color: red; border-radius: 7px;")
        self.record_indicator.setVisible(False)
        header.addWidget(self.record_indicator)
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.blink_record_indicator)
        self.blink_state = False

        self.detect_and_build()

    # ---------- Helpers ----------
    def get_label_for(self, cam_index: int) -> str:
        """Return the user label if set, otherwise a default."""
        key = str(cam_index)
        if key in self.camera_labels_map and self.camera_labels_map[key]:
            return self.camera_labels_map[key]
        # Fallback to cached camera 'name' if available
        for cam in self.all_cameras:
            if cam["index"] == cam_index:
                return cam.get("name") or f"Cam {cam_index}"
        return f"Cam {cam_index}"

    def sync_labels_from_widgets(self):
        """Read labels from visible widgets and persist them to settings."""
        updated = False
        for cw in self.camera_widgets:
            key = str(cw.cam_index)
            if self.camera_labels_map.get(key) != cw.label_text:
                self.camera_labels_map[key] = cw.label_text
                updated = True
        if updated:
            # Keep the legacy list in sync (ordered by current camera order)
            self.camera_labels_list = [
                self.get_label_for(cam["index"]) for cam in self.all_cameras
            ]
            self.settings["camera_labels"] = self.camera_labels_list
            self.settings["camera_labels_map"] = self.camera_labels_map
            save_settings(self.settings)

    # ---------- UI building ----------
    def detect_and_build(self):
        # Clear old widgets
        for w in self.camera_widgets:
            try:
                w.close()
                w.setParent(None)
            except Exception:
                pass
        self.camera_widgets.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Use cached list for building. Only refresh_cameras() rescans.
        all_cameras = self.all_cameras
        if not all_cameras:
            self.status_label.setText("No cameras found")
            return
        self.status_label.setText(f"Found {len(all_cameras)} cameras")

        display_count = 0
        cols = 2
        for cam in all_cameras:
            cam_index = cam["index"]
            enabled = self.enabled_map.get(str(cam_index), False)
            if not enabled:
                continue  # skip disabled cameras

            label_text = self.get_label_for(cam_index)
            cw = CameraWidget(cam_index, label_text, self.settings, parent=self)

            opened = cw.open()
            if not opened:
                cw.debug.setText("Failed to open")
            self.camera_widgets.append(cw)
            row = display_count // cols
            col = display_count % cols
            self.grid.addWidget(cw, row, col)
            display_count += 1

        if display_count == 0:
            self.status_label.setText("No cameras enabled. Go to Settings to enable.")

        # Persist any label changes that might have been done via edit icon
        self.sync_labels_from_widgets()

    def on_record_toggle(self, checked):
        if checked:
            self.status_label.setText("Recording...")
            self.record_indicator.setVisible(True)
            self.blink_timer.start(500)
            for cw in self.camera_widgets:
                cw.start_recording(self.save_path, self.chunk_minutes, self.max_minutes)
        else:
            self.status_label.setText("Ready")
            self.record_indicator.setVisible(False)
            self.blink_timer.stop()
            for cw in self.camera_widgets:
                cw.stop_recording()
        # Save labels just in case user renamed while recording
        self.sync_labels_from_widgets()

    def blink_record_indicator(self):
        self.blink_state = not self.blink_state
        self.record_indicator.setVisible(self.blink_state)

    def refresh_cameras(self):
        # Before rescanning, capture any label changes from current widgets
        self.sync_labels_from_widgets()
        # Rescan hardware and rebuild
        self.all_cameras = find_available_cameras(8)
        self.detect_and_build()

    def open_settings(self):
        # Use cached list to avoid lag
        dlg = SettingsDialog(self, cameras=[c["index"] for c in self.all_cameras])
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_values()
            self.apply_settings(data)

    def apply_settings(self, data: dict):
        # Persist any label edits made on widgets before applying other settings
        self.sync_labels_from_widgets()

        self.save_path = data.get("save_path", self.save_path)
        self.chunk_minutes = data.get("record_chunk_minutes", self.chunk_minutes)
        self.max_minutes = data.get("max_record_minutes", self.max_minutes)
        self.enabled_map = data.get("enabled_cameras", self.enabled_map)

        # Save to settings
        self.settings["save_path"] = self.save_path
        self.settings["record_chunk_minutes"] = self.chunk_minutes
        self.settings["max_record_minutes"] = self.max_minutes
        self.settings["enabled_cameras"] = self.enabled_map
        # Keep labels up to date
        self.settings["camera_labels_map"] = self.camera_labels_map
        self.settings["camera_labels"] = [
            self.get_label_for(cam["index"]) for cam in self.all_cameras
        ]
        save_settings(self.settings)

        self.detect_and_build()

    def open_instructions(self):
        webbrowser.open("https://github.com/solosightapp/solosight/blob/main/instructions")

    def closeEvent(self, event):
        # Make sure latest labels are saved on close
        self.sync_labels_from_widgets()
        super().closeEvent(event)


class SettingsDialog(QDialog):
    """
    Settings dialog that:
    - DOES NOT edit camera labels (labels are edited per-feed via the edit icon).
    - DOES NOT include 'disable internal webcam' option.
    - Uses cached camera list from MainWindow so opening is instant.
    - Shows enable/disable checkboxes with the same labels the user set via edit icons.
    """
    def __init__(self, parent=None, cameras=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background-color: {theme.BACKGROUND}; color: {theme.FOREGROUND};")

        self.parent = parent
        self.cameras = cameras or []  # list of camera indices

        layout = QVBoxLayout()
        form = QFormLayout()

        # Recording folder
        self.edit_path = QLineEdit(parent.save_path)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_folder)
        h = QHBoxLayout()
        h.addWidget(self.edit_path)
        h.addWidget(btn_browse)
        form.addRow("Recording folder", h)

        # Chunk & max minutes
        self.edit_chunk = QLineEdit(str(parent.chunk_minutes))
        form.addRow("Chunk minutes (5-10)", self.edit_chunk)
        self.edit_max = QLineEdit(str(parent.max_minutes))
        form.addRow("Max session minutes (<=60)", self.edit_max)

        layout.addLayout(form)

        # Detected cameras with enable/disable checkboxes (labels come from parent's label map)
        self.camera_checkboxes = []
        cams_box = QGroupBox("Detected Cameras")
        cams_layout = QVBoxLayout()

        enabled_map = dict(parent.enabled_map)

        if not self.cameras:
            cams_layout.addWidget(QLabel("No cameras detected."))
        else:
            for cam_index in self.cameras:
                label = parent.get_label_for(cam_index)
                cb = QCheckBox(f"Enable {label}")
                cb.setChecked(enabled_map.get(str(cam_index), False))
                cb.setProperty("cam_index", cam_index)
                self.camera_checkboxes.append(cb)
                cams_layout.addWidget(cb)

        cams_box.setLayout(cams_layout)
        layout.addWidget(cams_box)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Version label
        lbl_version = QLabel(f"Version: {version.VERSION}")
        lbl_version.setStyleSheet("color: white; font-size: 12pt;")
        lbl_version.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_version)

        self.setLayout(layout)

    def browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select folder", os.getcwd())
        if d:
            self.edit_path.setText(d)

    def get_values(self):
        # Chunk and max minutes
        try:
            chunk = max(1, int(self.edit_chunk.text()))
        except Exception:
            chunk = 5
        try:
            mx = min(60, int(self.edit_max.text()))
        except Exception:
            mx = 60

        # Collect checkbox states
        enabled_map = {}
        for cb in self.camera_checkboxes:
            cam_index = cb.property("cam_index")
            enabled_map[str(cam_index)] = cb.isChecked()

        return {
            "save_path": self.edit_path.text().strip() or "recordings",
            "record_chunk_minutes": chunk,
            "max_record_minutes": mx,
            "enabled_cameras": enabled_map
        }


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(f"""
QToolTip {{
    color: {theme.FOREGROUND};
    background-color: {theme.PANEL};
    border: 1px solid {theme.ACCENT};
    padding: 4px;
    border-radius: 4px;
    font-family: {theme.LABEL_FONT};
    font-size: {theme.BASE_FONT_SIZE + 1}px;
}}
""")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit")
        sys.exit(1)
