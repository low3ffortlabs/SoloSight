# camera_manager.py
import cv2
from PyQt5.QtWidgets import QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QDialog
from PyQt5.QtCore import QTimer, Qt, QSize
from PyQt5.QtGui import QImage, QPixmap
from icon_loader import icon
from recorder import CameraRecorder
import theme

def find_available_cameras(max_scan=10):
    """Return a list of dicts: [{'index': 0, 'name': 'Cam 0'}, ...]"""
    cameras = []
    for i in range(max_scan):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap and cap.isOpened():
            ret, _ = cap.read()
            if ret:
                cameras.append({"index": i, "name": f"Cam {i}"})
        cap.release()
    return cameras

def overlay_text(frame, text, x=10, y=20):
    import cv2
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

        # --- Original UI layout ---
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
        self.full_win = None
        self.full_timer = None

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
        if self.in_fullscreen and self.full_win:
            try:
                self.full_timer.stop()
                self.full_win.close()
            except Exception:
                pass
            self.in_fullscreen = False

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
        overlay_text(frame, f"{self.label_text} | {w}x{h} | {fps_text}", 8, 18)
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
            if self.full_timer:
                self.full_timer.stop()
            if self.full_win:
                self.full_win.close()
            self.in_fullscreen = False

    def _update_full(self):
        if not self.cap or not self.cap.isOpened():
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
        from PyQt5.QtWidgets import QInputDialog, QLineEdit
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
