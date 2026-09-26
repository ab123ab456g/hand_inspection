import json
import sys
from pathlib import Path

import cv2
from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QPlainTextEdit, QProgressBar, QStatusBar, QVBoxLayout, QWidget
)

from backend.manager import create_backend
from camera.camera_manager import CameraManager
from services.result_storage import ResultStorage

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "settings.json"

LABELS = {
    "normal": "正常",
    "trauma": "外傷",
    "suspected_fracture": "疑似骨折",
}


class PredictWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, backend, image_a, image_b, metadata):
        super().__init__()
        self.backend = backend
        self.image_a = image_a
        self.image_b = image_b
        self.metadata = metadata

    def run(self):
        try:
            result = self.backend.predict(self.image_a, self.image_b, self.metadata)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class CameraScanWorker(QObject):
    finished = Signal(list, list)
    failed = Signal(str)

    @Slot()
    def run(self):
        try:
            available, diagnostics = CameraManager.scan(max_index=7)
            self.finished.emit(available, diagnostics)
        except Exception as exc:
            self.failed.emit(str(exc))


class ImagePanel(QGroupBox):
    def __init__(self, title):
        super().__init__(title)
        self.preview = QLabel("尚未載入")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 315)
        self.preview.setStyleSheet("QLabel{background:#111;color:#aaa;border:1px solid #444;}")
        layout = QVBoxLayout(self)
        layout.addWidget(self.preview)

    def show_path(self, path):
        pix = QPixmap(str(path))
        if pix.isNull():
            self.preview.setText("無法預覽圖片")
            return
        self.preview.setPixmap(pix.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def show_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(image)
        self.preview.setPixmap(pix.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def clear(self, text="尚未載入"):
        self.preview.clear()
        self.preview.setText(text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("雙攝影機手部影像辨識系統 v0.1.6")
        self.resize(1180, 900)

        self.settings = self.load_settings()
        self.camera = CameraManager()
        self.storage = ResultStorage(BASE_DIR / "runs")
        self.photo_a = None
        self.photo_b = None
        self.frame_a = None
        self.frame_b = None
        self.predict_thread = None
        self.predict_worker = None
        self.camera_scan_thread = None
        self.camera_scan_worker = None
        self.pending_image_a = None
        self.pending_image_b = None
        self.pending_metadata = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_camera_frames)

        self.build_ui()
        self.apply_settings()
        self.refresh_mode_ui()
        self.statusBar().showMessage("Ready")

    def load_settings(self):
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        data = {
            "input_mode": self.input_mode.currentText(),
            "backend": self.backend_mode.currentText(),
            "openai_uri": self.openai_uri.text().strip(),
            "model": self.model.text().strip(),
            "custom_uri": self.custom_uri.text().strip(),
            "simulation_table": self.sim_table.text().strip(),
            "camera_a": self.camera_a.currentData(),
            "camera_b": self.camera_b.currentData(),
            "auto_save": self.auto_save.isChecked(),
        }
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.statusBar().showMessage("設定已儲存", 3000)

    def build_ui(self):
        root = QWidget()
        main = QVBoxLayout(root)

        top = QHBoxLayout()
        top.addWidget(QLabel("輸入來源："))
        self.input_mode = QComboBox()
        self.input_mode.addItems(["Photo", "Camera"])
        self.input_mode.currentTextChanged.connect(self.refresh_mode_ui)
        top.addWidget(self.input_mode)
        top.addStretch()
        self.save_cfg_btn = QPushButton("儲存設定")
        self.save_cfg_btn.clicked.connect(self.save_settings)
        top.addWidget(self.save_cfg_btn)
        main.addLayout(top)

        image_grid = QGridLayout()
        image_grid.setHorizontalSpacing(12)
        image_grid.setColumnStretch(0, 1)
        image_grid.setColumnStretch(1, 1)
        self.panel_a = ImagePanel("Image / Camera A")
        self.panel_b = ImagePanel("Image / Camera B")
        image_grid.addWidget(self.panel_a, 0, 0)
        image_grid.addWidget(self.panel_b, 0, 1)
        main.addLayout(image_grid)

        input_controls = QGroupBox("輸入控制")
        input_layout = QGridLayout(input_controls)
        input_layout.setHorizontalSpacing(12)
        input_layout.setColumnStretch(0, 1)
        input_layout.setColumnStretch(1, 1)
        self.choose_a_btn = QPushButton("選擇照片 A")
        self.choose_b_btn = QPushButton("選擇照片 B")
        self.choose_a_btn.setMinimumHeight(38)
        self.choose_b_btn.setMinimumHeight(38)
        self.choose_a_btn.clicked.connect(lambda: self.choose_photo("a"))
        self.choose_b_btn.clicked.connect(lambda: self.choose_photo("b"))
        input_layout.addWidget(self.choose_a_btn, 0, 0)
        input_layout.addWidget(self.choose_b_btn, 0, 1)

        self.camera_a = QComboBox()
        self.camera_b = QComboBox()
        self.scan_btn = QPushButton("掃描攝影機")
        self.start_cam_btn = QPushButton("開始攝影")
        self.stop_cam_btn = QPushButton("停止攝影")
        self.scan_btn.clicked.connect(self.scan_cameras)
        self.start_cam_btn.clicked.connect(self.start_camera)
        self.stop_cam_btn.clicked.connect(self.stop_camera)
        input_layout.addWidget(QLabel("Camera A"), 1, 0)
        input_layout.addWidget(self.camera_a, 1, 1)
        input_layout.addWidget(QLabel("Camera B"), 2, 0)
        input_layout.addWidget(self.camera_b, 2, 1)
        cam_buttons = QHBoxLayout()
        cam_buttons.addWidget(self.scan_btn)
        cam_buttons.addWidget(self.start_cam_btn)
        cam_buttons.addWidget(self.stop_cam_btn)
        input_layout.addLayout(cam_buttons, 3, 0, 1, 2)

        self.camera_scan_result = QPlainTextEdit()
        self.camera_scan_result.setReadOnly(True)
        self.camera_scan_result.setMaximumHeight(150)
        self.camera_scan_result.setPlaceholderText("按『掃描攝影機』後，這裡會顯示 index / backend 測試結果。")
        input_layout.addWidget(QLabel("掃描結果"), 4, 0)
        input_layout.addWidget(self.camera_scan_result, 4, 1)
        main.addWidget(input_controls)
        self.input_controls = input_controls

        backend_box = QGroupBox("辨識模式")
        backend_layout = QFormLayout(backend_box)
        self.backend_mode = QComboBox()
        self.backend_mode.addItems(["OpenAI API", "Custom API", "Random Mock", "Simulation Table"])
        self.backend_mode.currentTextChanged.connect(self.refresh_mode_ui)
        backend_layout.addRow("辨識模式：", self.backend_mode)

        self.openai_uri = QLineEdit("https://api.openai.com/v1/responses")
        self.custom_uri = QLineEdit("http://127.0.0.1:8000/predict")
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("僅保留於程式記憶體，不寫入 settings.json")
        self.model = QLineEdit("gpt-5.6-luna")
        self.sim_table = QLineEdit(str(BASE_DIR / "simulation" / "simulation_data.csv"))
        self.sim_browse = QPushButton("選擇資料表")
        self.sim_browse.clicked.connect(self.choose_simulation_table)

        self.openai_uri_label = QLabel("OpenAI URI：")
        self.custom_uri_label = QLabel("Custom URI：")
        self.token_label = QLabel("Token：")
        self.model_label = QLabel("Model：")
        self.sim_label = QLabel("Simulation Table：")
        backend_layout.addRow(self.openai_uri_label, self.openai_uri)
        backend_layout.addRow(self.custom_uri_label, self.custom_uri)
        backend_layout.addRow(self.token_label, self.token)
        backend_layout.addRow(self.model_label, self.model)
        sim_row = QHBoxLayout()
        sim_row.addWidget(self.sim_table)
        sim_row.addWidget(self.sim_browse)
        backend_layout.addRow(self.sim_label, sim_row)

        self.mode_notice = QLabel()
        self.mode_notice.setWordWrap(True)
        self.mode_notice.setStyleSheet("QLabel{padding:8px;background:#2c2c2c;border-radius:4px;}")
        backend_layout.addRow("狀態：", self.mode_notice)
        main.addWidget(backend_box)

        action_row = QHBoxLayout()
        self.analyze_btn = QPushButton("開始辨識")
        self.analyze_btn.setMinimumHeight(42)
        self.analyze_btn.clicked.connect(self.start_prediction)
        self.auto_save = QCheckBox("自動保存辨識結果")
        self.auto_save.setChecked(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        action_row.addWidget(self.analyze_btn)
        action_row.addWidget(self.auto_save)
        action_row.addWidget(self.progress)
        main.addLayout(action_row)

        result_box = QGroupBox("辨識結果")
        result_layout = QGridLayout(result_box)
        self.result_class = QLabel("-")
        self.result_class.setStyleSheet("font-size:28px;font-weight:700;")
        self.result_conf = QLabel("-")
        self.result_review = QLabel("-")
        self.result_findings = QPlainTextEdit()
        self.result_findings.setReadOnly(True)
        self.result_reason = QPlainTextEdit()
        self.result_reason.setReadOnly(True)
        result_layout.addWidget(QLabel("分類："), 0, 0)
        result_layout.addWidget(self.result_class, 0, 1)
        result_layout.addWidget(QLabel("Confidence："), 1, 0)
        result_layout.addWidget(self.result_conf, 1, 1)
        result_layout.addWidget(QLabel("建議進一步檢查："), 2, 0)
        result_layout.addWidget(self.result_review, 2, 1)
        result_layout.addWidget(QLabel("可見特徵："), 3, 0)
        result_layout.addWidget(self.result_findings, 3, 1)
        result_layout.addWidget(QLabel("說明："), 4, 0)
        result_layout.addWidget(self.result_reason, 4, 1)
        main.addWidget(result_box)

        medical_note = QLabel("注意：一般 RGB 影像無法確診骨折；『疑似骨折』僅代表可見外觀存在疑似變形、異常角度或嚴重腫脹等特徵。")
        medical_note.setWordWrap(True)
        medical_note.setStyleSheet("QLabel{padding:8px;background:#533;color:white;border-radius:4px;}")
        main.addWidget(medical_note)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())

    def apply_settings(self):
        self.input_mode.setCurrentText(self.settings.get("input_mode", "Photo"))
        self.backend_mode.setCurrentText(self.settings.get("backend", "Random Mock"))
        self.openai_uri.setText(self.settings.get("openai_uri", "https://api.openai.com/v1/responses"))
        self.custom_uri.setText(self.settings.get("custom_uri", "http://127.0.0.1:8000/predict"))
        self.model.setText(self.settings.get("model", "gpt-5.6-luna"))
        sim = self.settings.get("simulation_table", "simulation/simulation_data.csv")
        sim_path = Path(sim)
        if not sim_path.is_absolute():
            sim_path = BASE_DIR / sim_path
        self.sim_table.setText(str(sim_path))
        self.auto_save.setChecked(bool(self.settings.get("auto_save", True)))
        saved_a = self.settings.get("camera_a")
        saved_b = self.settings.get("camera_b")
        if isinstance(saved_a, dict) and saved_a.get("label"):
            self.camera_a.addItem(saved_a["label"], saved_a)
        if isinstance(saved_b, dict) and saved_b.get("label"):
            self.camera_b.addItem(saved_b["label"], saved_b)

    def refresh_mode_ui(self):
        input_mode = self.input_mode.currentText()
        backend = self.backend_mode.currentText()
        photo = input_mode == "Photo"

        for w in (self.choose_a_btn, self.choose_b_btn):
            w.setEnabled(photo)
        for w in (self.camera_a, self.camera_b, self.scan_btn, self.start_cam_btn, self.stop_cam_btn):
            w.setEnabled(not photo)

        is_openai = backend == "OpenAI API"
        is_custom = backend == "Custom API"
        is_sim = backend == "Simulation Table"

        for w in (self.openai_uri, self.openai_uri_label):
            w.setVisible(is_openai)
        for w in (self.custom_uri, self.custom_uri_label):
            w.setVisible(is_custom)
        for w in (self.token, self.token_label, self.model, self.model_label):
            w.setVisible(is_openai or is_custom)
        for w in (self.sim_table, self.sim_browse, self.sim_label):
            w.setVisible(is_sim)

        blocked = input_mode == "Camera" and is_sim
        self.analyze_btn.setEnabled(not blocked)
        if backend == "Random Mock":
            self.mode_notice.setText("Random Mock：不分析圖片內容，按下辨識後直接隨機回傳三種結果之一。")
        elif is_sim:
            self.mode_notice.setText("Simulation Table：依兩張照片的檔名解析 Case ID，再查 CSV/JSON 回傳固定結果。" if photo else "Simulation Table 第一版僅支援 Photo 模式。請切換輸入來源為 Photo。")
        elif is_openai:
            self.mode_notice.setText("OpenAI API：一次送出兩張影像，預設 Responses API + gpt-5.6-luna。Token 不會寫入設定檔。")
        else:
            self.mode_notice.setText("Custom API：使用 multipart/form-data 傳送 image_a、image_b、model；Token 以 Bearer 方式傳送。")

    def choose_photo(self, which):
        path, _ = QFileDialog.getOpenFileName(self, "選擇圖片", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        if which == "a":
            self.photo_a = path
            self.panel_a.show_path(path)
        else:
            self.photo_b = path
            self.panel_b.show_path(path)
        self.statusBar().showMessage(f"已載入 {Path(path).name}", 3000)

    def choose_simulation_table(self):
        path, _ = QFileDialog.getOpenFileName(self, "選擇 Simulation Table", "", "Simulation (*.csv *.json)")
        if path:
            self.sim_table.setText(path)

    def scan_cameras(self):
        if self.camera_scan_thread is not None:
            return

        self.scan_btn.setEnabled(False)
        self.start_cam_btn.setEnabled(False)
        self.camera_scan_result.setPlainText("正在平行掃描 Camera index 0~7；同一 index 依序測試 backend...")
        self.statusBar().showMessage("正在掃描攝影機...")

        self.camera_scan_thread = QThread(self)
        self.camera_scan_worker = CameraScanWorker()
        self.camera_scan_worker.moveToThread(self.camera_scan_thread)
        self.camera_scan_thread.started.connect(self.camera_scan_worker.run)
        self.camera_scan_worker.finished.connect(self.on_camera_scan_done)
        self.camera_scan_worker.failed.connect(self.on_camera_scan_failed)
        self.camera_scan_worker.finished.connect(self.camera_scan_thread.quit)
        self.camera_scan_worker.failed.connect(self.camera_scan_thread.quit)
        self.camera_scan_thread.finished.connect(self.camera_scan_worker.deleteLater)
        self.camera_scan_thread.finished.connect(self.camera_scan_thread.deleteLater)
        self.camera_scan_thread.finished.connect(self.on_camera_scan_thread_finished)
        self.camera_scan_thread.start()

    @Slot(list, list)
    def on_camera_scan_done(self, available, diagnostics):
        self.camera_a.clear()
        self.camera_b.clear()

        for config in available:
            self.camera_a.addItem(config["label"], config)
            self.camera_b.addItem(config["label"], config)

        # Prefer two different physical camera indices for A/B.
        if available:
            self.camera_a.setCurrentIndex(0)
            first_index = int(available[0]["index"])
            for i, config in enumerate(available):
                if int(config["index"]) != first_index:
                    self.camera_b.setCurrentIndex(i)
                    break

        lines = []
        for row in diagnostics:
            mark = "✓" if row["opened"] and row["read"] else "✗"
            lines.append(
                f"{mark} index={row['index']}  backend={row['backend_name']:<5}  "
                f"opened={row['opened']}  read={row['read']}"
            )
        self.camera_scan_result.setPlainText("\n".join(lines))

        if available:
            self.statusBar().showMessage(
                f"掃描完成：找到 {len(available)} 個可用 index/backend 組合", 7000
            )
        else:
            self.statusBar().showMessage("掃描完成：未找到可讀取影像的攝影機", 7000)

    @Slot(str)
    def on_camera_scan_failed(self, message):
        self.camera_scan_result.setPlainText(f"掃描失敗：{message}")
        self.statusBar().showMessage("Camera scan failed", 5000)

    @Slot()
    def on_camera_scan_thread_finished(self):
        self.camera_scan_thread = None
        self.camera_scan_worker = None
        self.refresh_mode_ui()

    def start_camera(self):
        config_a = self.camera_a.currentData()
        config_b = self.camera_b.currentData()

        if not isinstance(config_a, dict) or not isinstance(config_b, dict):
            QMessageBox.warning(self, "Camera", "請先按『掃描攝影機』並選擇 Camera A / B。")
            return

        if int(config_a["index"]) == int(config_b["index"]):
            QMessageBox.warning(self, "Camera", "Camera A 與 Camera B 必須選擇不同的 Camera index。")
            return

        try:
            self.camera.start(config_a, config_b)
            self.timer.start(33)
            self.statusBar().showMessage(
                f"Camera connected：{config_a['label']} / {config_b['label']}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Camera Error", str(exc))

    def stop_camera(self):
        self.timer.stop()
        self.camera.stop()
        self.statusBar().showMessage("Camera stopped", 3000)

    def update_camera_frames(self):
        ok, a, b = self.camera.read()
        if not ok:
            self.statusBar().showMessage("Camera read failed")
            return
        self.frame_a = a.copy(); self.frame_b = b.copy()
        self.panel_a.show_frame(a); self.panel_b.show_frame(b)

    def current_images(self):
        if self.input_mode.currentText() == "Photo":
            if not self.photo_a or not self.photo_b:
                raise ValueError("請先選擇照片 A 與照片 B")
            return self.photo_a, self.photo_b, {
                "filename_a": Path(self.photo_a).name,
                "filename_b": Path(self.photo_b).name,
                "input_mode": "Photo",
            }
        if self.frame_a is None or self.frame_b is None:
            raise ValueError("請先啟動兩台攝影機，並確認已有即時畫面")
        return self.frame_a.copy(), self.frame_b.copy(), {
            "filename_a": "camera_a.jpg",
            "filename_b": "camera_b.jpg",
            "input_mode": "Camera",
        }

    def backend_settings(self):
        mode = self.backend_mode.currentText()
        if mode == "OpenAI API":
            uri = self.openai_uri.text().strip()
        elif mode == "Custom API":
            uri = self.custom_uri.text().strip()
        else:
            uri = ""
        return {
            "uri": uri,
            "token": self.token.text().strip(),
            "model": self.model.text().strip(),
            "simulation_table": self.sim_table.text().strip(),
        }

    def start_prediction(self):
        try:
            image_a, image_b, metadata = self.current_images()
            mode = self.backend_mode.currentText()
            if self.input_mode.currentText() == "Camera" and mode == "Simulation Table":
                raise ValueError("Simulation Table 第一版僅支援 Photo 模式")
            backend = create_backend(mode, self.backend_settings())
        except Exception as exc:
            QMessageBox.warning(self, "無法開始辨識", str(exc))
            return

        self.analyze_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.statusBar().showMessage("Analyzing...")

        # Keep request context on the MainWindow.  Do not capture GUI callbacks
        # in a lambda connected to a worker-thread signal: a plain Python lambda
        # may execute in the emitter thread and must never touch Qt widgets.
        self.pending_image_a = image_a
        self.pending_image_b = image_b
        self.pending_metadata = metadata

        self.predict_thread = QThread(self)
        self.predict_worker = PredictWorker(backend, image_a, image_b, metadata)
        self.predict_worker.moveToThread(self.predict_thread)
        self.predict_thread.started.connect(self.predict_worker.run)
        self.predict_worker.finished.connect(self.on_prediction_done)
        self.predict_worker.failed.connect(self.on_prediction_failed)
        self.predict_worker.finished.connect(self.predict_thread.quit)
        self.predict_worker.failed.connect(self.predict_thread.quit)
        self.predict_thread.finished.connect(self.predict_worker.deleteLater)
        self.predict_thread.finished.connect(self.predict_thread.deleteLater)
        self.predict_thread.start()

    @Slot(dict)
    def on_prediction_done(self, result):
        # This slot belongs to MainWindow and therefore runs on the GUI thread.
        image_a = self.pending_image_a
        image_b = self.pending_image_b
        metadata = self.pending_metadata or {}
        label = result.get("class", "")
        confidence = float(result.get("confidence", 0) or 0)
        findings = result.get("visible_findings", []) or []
        reason = result.get("reason", "")
        review = bool(result.get("need_medical_review", False))

        self.result_class.setText(LABELS.get(label, label or "未知"))
        self.result_conf.setText(f"{confidence * 100:.1f}%")
        self.result_findings.setPlainText("\n".join(f"• {x}" for x in findings) if findings else "無")
        self.result_reason.setPlainText(reason)
        self.result_review.setText("是" if review else "否")

        if self.backend_mode.currentText() == "Random Mock":
            self.result_class.setStyleSheet("font-size:28px;font-weight:700;color:#f0ad4e;")
        else:
            self.result_class.setStyleSheet("font-size:28px;font-weight:700;")

        if self.auto_save.isChecked():
            try:
                out = self.storage.save(image_a, image_b, result, metadata)
                self.statusBar().showMessage(f"Completed；已保存至 {out.name}", 7000)
            except Exception as exc:
                self.statusBar().showMessage(f"Completed；保存失敗：{exc}", 7000)
        else:
            self.statusBar().showMessage("Completed", 5000)
        self.finish_prediction_ui()

    @Slot(str)
    def on_prediction_failed(self, message):
        QMessageBox.critical(self, "辨識失敗", message)
        self.statusBar().showMessage("Prediction failed", 5000)
        self.finish_prediction_ui()

    def finish_prediction_ui(self):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.pending_image_a = None
        self.pending_image_b = None
        self.pending_metadata = None
        self.refresh_mode_ui()

    def closeEvent(self, event):
        self.timer.stop()
        self.camera.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
