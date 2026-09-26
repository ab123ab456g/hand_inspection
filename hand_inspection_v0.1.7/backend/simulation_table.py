import csv
import json
from pathlib import Path
from .base import VisionBackend

class SimulationTableBackend(VisionBackend):
    def __init__(self, table_path):
        self.table_path = Path(table_path)
        if not self.table_path.exists():
            raise FileNotFoundError(f"找不到模擬資料表：{self.table_path}")
        self.data = self._load()

    def _load(self):
        suffix = self.table_path.suffix.lower()
        if suffix == ".json":
            with self.table_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                return raw
            raise ValueError("JSON 模擬資料必須是以 case_id 為 key 的物件")

        if suffix == ".csv":
            result = {}
            with self.table_path.open("r", encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    case_id = (row.get("case_id") or "").strip()
                    if not case_id:
                        continue
                    findings = [x for x in (row.get("findings") or "").split("|") if x and x.lower() != "none"]
                    result[case_id] = {
                        "class": (row.get("class") or "").strip(),
                        "confidence": float(row.get("confidence") or 0),
                        "visible_findings": findings,
                        "reason": row.get("reason") or "",
                        "need_medical_review": str(row.get("need_medical_review") or "").strip().lower() in {"1", "true", "yes", "y"},
                    }
            return result

        raise ValueError("Simulation Table 僅支援 CSV 或 JSON")

    @staticmethod
    def _extract_case_id(filename):
        stem = Path(filename).stem
        suffixes = ["_front", "_side", "_left", "_right", "_a", "_b", "-front", "-side", "-a", "-b"]
        lowered = stem.lower()
        for suffix in suffixes:
            if lowered.endswith(suffix):
                return stem[: -len(suffix)]
        return stem

    def predict(self, image_a, image_b, metadata=None):
        metadata = metadata or {}
        fn_a = metadata.get("filename_a")
        fn_b = metadata.get("filename_b")
        if not fn_a or not fn_b:
            raise ValueError("Simulation Table 模式需要兩張圖片的原始檔名")

        case_a = self._extract_case_id(fn_a)
        case_b = self._extract_case_id(fn_b)
        if case_a != case_b:
            raise ValueError(f"兩張圖片不屬於同一案例：{case_a} != {case_b}")
        if case_a not in self.data:
            raise KeyError(f"Simulation data not found：{case_a}")

        result = dict(self.data[case_a])
        result["case_id"] = case_a
        result["backend"] = "simulation_table"
        return result
