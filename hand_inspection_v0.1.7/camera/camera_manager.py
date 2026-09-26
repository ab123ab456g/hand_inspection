import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2


class CameraManager:
    """Two-camera manager with explicit index/backend selection."""

    def __init__(self):
        self.cap_a = None
        self.cap_b = None
        self.config_a = None
        self.config_b = None

    @staticmethod
    def backend_candidates():
        if sys.platform.startswith("win"):
            return [
                ("DSHOW", cv2.CAP_DSHOW),
                ("MSMF", cv2.CAP_MSMF),
                ("ANY", cv2.CAP_ANY),
            ]
        return [("ANY", cv2.CAP_ANY)]

    @classmethod
    def _scan_index(cls, index):
        """Scan one camera index sequentially across backends.

        Backends for the same index are never opened in parallel, avoiding
        multiple backends fighting over the same physical camera. The first
        backend that can both open and read a frame wins and scanning for that
        index stops immediately.
        """
        diagnostics = []
        available = None

        for backend_name, backend_id in cls.backend_candidates():
            cap = cv2.VideoCapture(index, backend_id)
            opened = cap.isOpened()
            read_ok = False

            try:
                if opened:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    read_ok, _ = cap.read()
            finally:
                cap.release()

            diagnostics.append({
                "index": index,
                "backend_name": backend_name,
                "backend_id": int(backend_id),
                "opened": bool(opened),
                "read": bool(read_ok),
            })

            if opened and read_ok:
                available = {
                    "label": f"Camera {index} - {backend_name}",
                    "index": index,
                    "backend_name": backend_name,
                    "backend_id": int(backend_id),
                }
                break

        return index, available, diagnostics

    @classmethod
    def scan(cls, max_index=7, max_workers=2):
        """Probe camera indices concurrently and return usable choices + diagnostics.

        Different camera indices are scanned in parallel. For each individual
        index, backends are tested sequentially and probing stops after the first
        backend that successfully reads a frame.
        """
        available = []
        diagnostics = []

        old_log_level = None
        try:
            if hasattr(cv2, "getLogLevel"):
                old_log_level = cv2.getLogLevel()
            if hasattr(cv2, "setLogLevel"):
                cv2.setLogLevel(0)
        except Exception:
            pass

        try:
            worker_count = max(1, min(int(max_workers), max_index + 1))
            with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="camera-scan") as executor:
                futures = {
                    executor.submit(cls._scan_index, index): index
                    for index in range(max_index + 1)
                }

                indexed_results = []
                for future in as_completed(futures):
                    indexed_results.append(future.result())

            # Stable ordering makes the GUI deterministic even though probing is concurrent.
            indexed_results.sort(key=lambda item: item[0])

            for _, choice, diag in indexed_results:
                diagnostics.extend(diag)
                if choice is not None:
                    available.append(choice)
        finally:
            try:
                if old_log_level is not None and hasattr(cv2, "setLogLevel"):
                    cv2.setLogLevel(old_log_level)
            except Exception:
                pass

        return available, diagnostics

    @staticmethod
    def _open_config(config):
        index = int(config["index"])
        backend_id = int(config["backend_id"])
        cap = cv2.VideoCapture(index, backend_id)

        if not cap.isOpened():
            cap.release()
            return None

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        ok, _ = cap.read()
        if not ok:
            cap.release()
            return None

        return cap

    def start(self, config_a, config_b):
        self.stop()

        if int(config_a["index"]) == int(config_b["index"]):
            raise ValueError("Camera A 與 Camera B 不可使用相同 Camera index")

        cap_a = self._open_config(config_a)
        if cap_a is None:
            raise RuntimeError(f"無法開啟 Camera A：{config_a['label']}")

        cap_b = self._open_config(config_b)
        if cap_b is None:
            cap_a.release()
            raise RuntimeError(f"無法開啟 Camera B：{config_b['label']}")

        self.cap_a = cap_a
        self.cap_b = cap_b
        self.config_a = dict(config_a)
        self.config_b = dict(config_b)

    def read(self):
        if self.cap_a is None or self.cap_b is None:
            return False, None, None

        ok_a, frame_a = self.cap_a.read()
        ok_b, frame_b = self.cap_b.read()
        return ok_a and ok_b, frame_a, frame_b

    def stop(self):
        for cap in (self.cap_a, self.cap_b):
            if cap is not None:
                cap.release()
        self.cap_a = None
        self.cap_b = None
        self.config_a = None
        self.config_b = None
