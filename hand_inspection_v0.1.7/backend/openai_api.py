import base64
import json
import mimetypes
from pathlib import Path
import cv2
import requests
from .base import VisionBackend

PROMPT = """你是一個手部外觀影像分析系統。現在提供同一隻手不同角度的兩張圖片。
請只根據肉眼可見的外觀特徵分類，不要宣稱已完成醫療確診。
允許 class 僅有：normal、trauma、suspected_fracture。
suspected_fracture 代表圖片中出現明顯變形、異常角度、嚴重腫脹或其他疑似骨折外觀；真正骨折仍需醫療檢查確認。
請只輸出一個 JSON 物件，格式如下：
{
  "class": "normal|trauma|suspected_fracture",
  "confidence": 0.0,
  "visible_findings": ["..."],
  "reason": "簡短中文說明",
  "need_medical_review": true
}
不要輸出 Markdown code fence。"""

class OpenAIBackend(VisionBackend):
    def __init__(self, token, model="gpt-5.6-luna", uri="https://api.openai.com/v1/responses", timeout=90):
        if not token:
            raise ValueError("請輸入 OpenAI API Token")
        self.token = token
        self.model = model or "gpt-5.6-luna"
        self.uri = uri or "https://api.openai.com/v1/responses"
        self.timeout = timeout

    @staticmethod
    def _to_data_url(image):
        if isinstance(image, (str, Path)):
            path = Path(image)
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            raw = path.read_bytes()
        else:
            ok, buf = cv2.imencode(".jpg", image)
            if not ok:
                raise ValueError("無法編碼攝影機影像")
            raw = buf.tobytes()
            mime = "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    @staticmethod
    def _extract_text(data):
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        parts = []
        for item in data.get("output", []):
            for content in item.get("content", []) if isinstance(item, dict) else []:
                text = content.get("text") if isinstance(content, dict) else None
                if text:
                    parts.append(text)
        if parts:
            return "\n".join(parts)
        raise ValueError("OpenAI 回應中找不到文字輸出")

    def predict(self, image_a, image_b, metadata=None):
        payload = {
            "model": self.model,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": PROMPT},
                    {"type": "input_image", "image_url": self._to_data_url(image_a)},
                    {"type": "input_image", "image_url": self._to_data_url(image_b)},
                ],
            }],
        }
        r = requests.post(
            self.uri,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        if not r.ok:
            raise RuntimeError(f"OpenAI API 錯誤 HTTP {r.status_code}: {r.text[:500]}")
        text = self._extract_text(r.json()).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:].lstrip()
        result = json.loads(text)
        result["backend"] = "openai_api"
        self._validate(result)
        return result

    @staticmethod
    def _validate(result):
        allowed = {"normal", "trauma", "suspected_fracture"}
        if result.get("class") not in allowed:
            raise ValueError("模型回傳了不合法的 class")
        c = float(result.get("confidence", 0))
        if not 0 <= c <= 1:
            raise ValueError("confidence 必須介於 0 和 1")
        result["confidence"] = c
        result.setdefault("visible_findings", [])
        result.setdefault("reason", "")
        result.setdefault("need_medical_review", result["class"] != "normal")
