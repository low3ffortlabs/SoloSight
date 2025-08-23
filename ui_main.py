import os
import sys
import time
import traceback
import webbrowser
import version

import cv2
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QApplication, QLineEdit, QDialog, QFileDialog, QFrame, QScrollArea,
    QGroupBox, QFormLayout, QMessageBox, QCheckBox, QInputDialog
)
from PyQt5.QtGui import QImage, QPixmap, QFont, QIcon
from PyQt5.QtCore import QTimer, Qt, QSize

from icon_loader import icon
from settings_manager import load_settings, save_settings
from camera_manager import find_available_cameras
from recorder import CameraRecorder
import theme


def overlay_text(frame, text, x=10, y=20):
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)


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


class CameraWidget(QWidget):
    def __init__(self, cam_index, label_text, settings, parent=None):
        super().__init__(parent)
        self.cam_index = cam_index
        self.label_text = label_text
        self.settings = settings
        self.cap = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.grab_frame)
        self.recording = False
        self.recorder = None

        # UI components
        self.label = QLabel(self.label_text)
        self.label.setStyleSheet(
            f"color: {theme.FOREGROUND}; font-family: {theme.LABEL_FONT}; font-size: {theme.BASE_FONT_SIZE + 8}px;"
        )
        self.video = QLabel()
        self.video.setFixedSize(480, 360)
        self.video.setStyleSheet("background: black;")

        self.btn_full = QPushButton()
        self.btn_full.setIcon(icon("fullscreen", theme.ICON_MEDIUM))
        self.btn_full.setIconSize(QSize(theme.ICON_MEDIUM, theme.ICON_MEDIUM))
        self.btn_full.setStyleSheet(theme.ICON_BUTTON_STYLE)
        self.btn_full.setToolTip("Fullscreen")
        self.btn_full.setFixedSize(48, 48)
        self.btn_full.clicked.connect(self.toggle_fullscreen)

        self.btn_edit = QPushButton()
        self.btn_edit.setIcon(icon("edit", theme.ICON_MEDIUM))
        self.btn_edit.setIconSize(QSize(theme.ICON_MEDIUM, theme.ICON_MEDIUM))
        self.btn_edit.setStyleSheet(theme.ICON_BUTTON_STYLE)
        self.btn_edit.setToolTip("Edit Camera Label")
        self.btn_edit.setFixedSize(48, 48)
        self.btn_edit.clicked.connect(self.edit_label)

        top_row = QHBoxLayout()
        top_row.addWidget(self.label)
        top_row.addStretch()
        top_row.addWidget(self.btn_edit)
        top_row.addWidget(self.btn_full)

        layout = QVBoxLayout()
        layout.addLayout(top_row)
        layout.addWidget(self.video)
        self.debug = QLabel("")
        self.debug.setStyleSheet(f"color:{theme.FOREGROUND}; font-size:8pt;")
        layout.addWidget(self.debug)
        self.setLayout(layout)
        self.in_fullscreen = False

    def open(self):
        try:
            self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        except Exception:
            self.cap = cv2.VideoCapture(self.cam_index)
        if not self.cap.isOpened():
            return False
        self.timer.start(30)
        return True

    def close(self):
        self.timer.stop()
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def grab_frame(self):
        if not self.cap or not self.cap.isOpened():
            self.debug.setText("No feed")
            return
        ret, frame = self.cap.read()
        if not ret:
            self.debug.setText("Frame grab failed")
            return

        h, w = frame.shape[:2]
        fps_text = f"{int(self.cap.get(cv2.CAP_PROP_FPS) or 30)}FPS"
        cam_name = self.label_text
        overlay_text(frame, f"{cam_name} | {w}x{h} | {fps_text}", 8, 18)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, rgb.shape[1], rgb.shape[0], QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(self.video.width(), self.video.height(), Qt.KeepAspectRatio)
        self.video.setPixmap(pix)
        if self.recording and self.recorder:
            self.recorder.write_frame(frame)

    def toggle_fullscreen(self):
        if not self.in_fullscreen:
            self.full_win = ResizableFullScreenDialog(self.label_text, self._update_full, self)
            self.full_label = self.full_win.full_label
            self.full_win.show()

            self.full_timer = QTimer()
            self.full_timer.timeout.connect(self._update_full)
            self.full_timer.start(30)
            self.in_fullscreen = True
        else:
            try:
                self.full_timer.stop()
                self.full_win.close()
            except Exception:
                pass
            self.in_fullscreen = False

    def _update_full(self):
        if not self.cap:
            return
        ret, frame = self.cap.read()
        if not ret:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, rgb.shape[1], rgb.shape[0], QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(self.full_label.width(), self.full_label.height(), Qt.KeepAspectRatio)
        self.full_label.setPixmap(pix)
        if self.recording and self.recorder:
            self.recorder.write_frame(frame)

    def edit_label(self):
        text, ok = QInputDialog.getText(self, "Edit Camera Label", "Label:", QLineEdit.Normal, self.label_text)
        if ok and text:
            self.label_text = text
            self.label.setText(text)

    def start_recording(self, save_dir, chunk_minutes, max_minutes):
        if self.recording:
            return
        self.recorder = CameraRecorder(save_dir, self.cam_index, chunk_minutes=chunk_minutes, max_minutes=max_minutes)
        self.recorder.start()
        self.recording = True

    def stop_recording(self):
        if not self.recording:
            return
        if self.recorder:
            self.recorder.stop()
        self.recording = False


class MainWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(theme.APP_NAME)
        self.setStyleSheet(f"background:{theme.BACKGROUND}; color:{theme.FOREGROUND};")
        font = QFont(theme.LABEL_FONT, theme.BASE_FONT_SIZE)
        self.setFont(font)

        self.settings = load_settings()
        self.camera_labels = self.settings.get("camera_labels", [])
        self.save_path = self.settings.get("save_path", "recordings")
        self.chunk_minutes = self.settings.get("record_chunk_minutes", theme.RECORD_CHUNK_MINUTES)
        self.max_minutes = self.settings.get("max_record_minutes", theme.RECORD_MAX_MINUTES)
        self.disable_internal_cam = self.settings.get("disable_internal_cam", False)

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
        self.detect_and_build()

        self.record_indicator = QLabel()
        self.record_indicator.setFixedSize(14, 14)
        self.record_indicator.setStyleSheet("background-color: red; border-radius: 7px;")
        self.record_indicator.setVisible(False)
        header.addWidget(self.record_indicator)
        self.blink_timer = QTimer()
        self.blink_timer.timeout.connect(self.blink_record_indicator)
        self.blink_state = False

    def detect_and_build(self):
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

        cam_indices = find_available_cameras(8)
        if not cam_indices:
            self.status_label.setText("No cameras found")
            return
        self.status_label.setText(f"Found {len(cam_indices)} cameras")

        for idx, cidx in enumerate(cam_indices):
            label_text = self.get_label(idx, cidx)
            cw = CameraWidget(cidx, label_text, self.settings, parent=self)

            if self.disable_internal_cam and cidx == 0:
                cw.debug.setText("Disabled (internal webcam)")
            else:
                opened = cw.open()
                if not opened:
                    cw.debug.setText("Failed to open")

            self.camera_widgets.append(cw)
            cols = 2
            row = idx // cols
            col = idx % cols
            self.grid.addWidget(cw, row, col)

    def get_label(self, slot_idx, cam_index):
        if slot_idx < len(self.camera_labels) and self.camera_labels[slot_idx]:
            return self.camera_labels[slot_idx]
        return f"Cam {cam_index}"

    def refresh_cameras(self):
        self.detect_and_build()

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

    def blink_record_indicator(self):
        self.blink_state = not self.blink_state
        self.record_indicator.setVisible(self.blink_state)

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec_():
            data = dlg.get_values()
            self.camera_labels = data.get("camera_labels", self.camera_labels)
            self.save_path = data.get("save_path", self.save_path)
            self.chunk_minutes = data.get("record_chunk_minutes", self.chunk_minutes)
            self.max_minutes = data.get("max_record_minutes", self.max_minutes)
            self.disable_internal_cam = data.get("disable_internal_cam", self.disable_internal_cam)

            self.settings["camera_labels"] = self.camera_labels
            self.settings["save_path"] = self.save_path
            self.settings["record_chunk_minutes"] = self.chunk_minutes
            self.settings["max_record_minutes"] = self.max_minutes
            self.settings["disable_internal_cam"] = self.disable_internal_cam
            save_settings(self.settings)

            self.refresh_cameras()

    def open_instructions(self):
        url = "https://github.com/solosightapp/solosight/blob/main/instructions"
        webbrowser.open(url)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        # White background + black text for dialogs
        self.setStyleSheet(f"background-color: {theme.BACKGROUND}; color: {theme.FOREGROUND};")
        layout = QVBoxLayout()
        form = QFormLayout()

        cam_labels = ",".join(parent.camera_labels) if parent.camera_labels else ""
        self.edit_labels = QLineEdit(cam_labels)
        form.addRow("Camera labels (comma-separated)", self.edit_labels)

        self.edit_path = QLineEdit(parent.save_path)
        btn_browse = QPushButton("Browse")
        btn_browse.clicked.connect(self.browse_folder)
        h = QHBoxLayout()
        h.addWidget(self.edit_path)
        h.addWidget(btn_browse)
        form.addRow("Recording folder", h)

        self.edit_chunk = QLineEdit(str(parent.chunk_minutes))
        form.addRow("Chunk minutes (5-10)", self.edit_chunk)

        self.edit_max = QLineEdit(str(parent.max_minutes))
        form.addRow("Max session minutes (<=60)", self.edit_max)

        self.chk_disable_internal = QCheckBox("Disable internal webcam on startup")
        self.chk_disable_internal.setChecked(parent.disable_internal_cam)
        form.addRow(self.chk_disable_internal)

        layout.addLayout(form)

        btns = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

        # --- Add version label at the very bottom ---
        self.lbl_version = QLabel(f"Version: {version.VERSION}")
        self.lbl_version.setStyleSheet("color: white; font-size: 12pt;")
        self.lbl_version.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_version)

        self.setLayout(layout)

    def browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select folder", os.getcwd())
        if d:
            self.edit_path.setText(d)

    def get_values(self):
        labels = [s.strip() for s in self.edit_labels.text().split(",") if s.strip()]
        try:
            chunk = max(1, int(self.edit_chunk.text()))
        except:
            chunk = 5
        try:
            mx = min(60, int(self.edit_max.text()))
        except:
            mx = 60
        disable_internal = self.chk_disable_internal.isChecked()
        return {
            "camera_labels": labels,
            "save_path": self.edit_path.text().strip() or "recordings",
            "record_chunk_minutes": chunk,
            "max_record_minutes": mx,
            "disable_internal_cam": disable_internal,
        }

class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to SoloSight!")
        self.setStyleSheet(f"background:{theme.BACKGROUND}; color:{theme.FOREGROUND};")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        msg = QLabel(
            "Welcome to SoloSight! Before you begin, it is recommended that you read the instructions "
            "and that you select the recording destination in 'Settings'."
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        self.chk_dont_show = QCheckBox("Do not show this message again")
        self.chk_dont_show.setChecked(False)

        self.btn_instructions = QPushButton("Instructions")
        self.btn_instructions.setIcon(icon("instructions", theme.ICON_MEDIUM))
        self.btn_instructions.setIconSize(QSize(theme.ICON_MEDIUM, theme.ICON_MEDIUM))
        self.btn_instructions.setStyleSheet(theme.ICON_BUTTON_STYLE)
        self.btn_instructions.clicked.connect(lambda: parent.open_instructions())

        bottom = QHBoxLayout()
        bottom.addWidget(self.chk_dont_show)
        bottom.addStretch()
        bottom.addWidget(self.btn_instructions)
        layout.addLayout(bottom)

        self.setLayout(layout)

def main():
    app = QApplication(sys.argv)

    # Optional: set global tooltip font
    tooltip_font = QFont("Segoe UI", 10)
    app.setFont(tooltip_font)
    app.setStyleSheet(f"""
QToolTip {{
    color: {theme.FOREGROUND};        /* text color */
    background-color: {theme.PANEL};  /* dark background */
    border: 1px solid {theme.ACCENT};
    padding: 4px;
    border-radius: 4px;
    font-family: {theme.LABEL_FONT};
    font-size: {theme.BASE_FONT_SIZE + 1}px;
}}
""")

    win = MainWindow()
    settings = win.settings

    # --- Welcome dialog logic ---
    if settings.get("show_welcome_dialog", True):
        dlg = WelcomeDialog(win)

        # Add an OK button to the bottom layout dynamically
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(dlg.accept)
        bottom_layout = dlg.layout().itemAt(dlg.layout().count() - 1)
        if isinstance(bottom_layout, QHBoxLayout):
            bottom_layout.addWidget(btn_ok)

        if dlg.exec_() == QDialog.Accepted or dlg.chk_dont_show.isChecked():
            settings["show_welcome_dialog"] = not dlg.chk_dont_show.isChecked()
            save_settings(settings)

    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("Press Enter to exit")
        sys.exit(1)
