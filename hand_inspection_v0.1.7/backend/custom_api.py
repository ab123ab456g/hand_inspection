import base64
import json
from pathlib import Path
import cv2
import requests
from .base import VisionBackend

class CustomAPIBackend(VisionBackend):
    """通用 multipart/form-data 介面：image_a、image_b、model；Bearer token 可選。"""
    def __init__(self, uri, token="", model="", timeout=90):
        if not uri:
            raise ValueError("請輸入 Custom API URI")
        self.uri = uri
        self.token = token
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _jpeg_bytes(image):
        if isinstance(image, (str, Path)):
            return Path(image).read_bytes()
        ok, buf = cv2.imencode(".jpg", image)
        if not ok:
            raise ValueError("無法編碼影像")
        return buf.tobytes()

    def predict(self, image_a, image_b, metadata=None):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        files = {
            "image_a": ("image_a.jpg", self._jpeg_bytes(image_a), "image/jpeg"),
            "image_b": ("image_b.jpg", self._jpeg_bytes(image_b), "image/jpeg"),
        }
        data = {"model": self.model}
        r = requests.post(self.uri, headers=headers, files=files, data=data, timeout=self.timeout)
        if not r.ok:
            raise RuntimeError(f"Custom API 錯誤 HTTP {r.status_code}: {r.text[:500]}")
        result = r.json()
        result["backend"] = "custom_api"
        return result
