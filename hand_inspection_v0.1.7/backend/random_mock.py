import random
from .base import VisionBackend

class RandomBackend(VisionBackend):
    def predict(self, image_a, image_b, metadata=None):
        labels = {
            "normal": {
                "visible_findings": [],
                "reason": "Random Mock 測試結果：未分析圖片內容。",
                "need_medical_review": False,
            },
            "trauma": {
                "visible_findings": ["swelling", "abrasion"],
                "reason": "Random Mock 測試結果：此結果為隨機產生，未分析圖片內容。",
                "need_medical_review": True,
            },
            "suspected_fracture": {
                "visible_findings": ["deformation", "abnormal_angle"],
                "reason": "Random Mock 測試結果：此結果為隨機產生，未分析圖片內容。",
                "need_medical_review": True,
            },
        }
        label = random.choice(list(labels))
        return {
            "class": label,
            "confidence": round(random.uniform(0.70, 0.99), 2),
            **labels[label],
            "backend": "random_mock",
        }
