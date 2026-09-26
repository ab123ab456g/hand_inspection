import json
import shutil
from datetime import datetime
from pathlib import Path
import cv2

class ResultStorage:
    def __init__(self, root="runs"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, image_a, image_b, result, metadata=None):
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        out = self.root / stamp
        out.mkdir(parents=True, exist_ok=False)
        self._save_image(image_a, out / "image_a.jpg")
        self._save_image(image_b, out / "image_b.jpg")
        payload = {"metadata": metadata or {}, "result": result}
        (out / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    @staticmethod
    def _save_image(image, dest):
        if isinstance(image, (str, Path)):
            shutil.copy2(str(image), str(dest))
        else:
            cv2.imwrite(str(dest), image)
