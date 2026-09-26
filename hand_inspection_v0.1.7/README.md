# 雙攝影機手部影像辨識系統 v0.1

Windows 本機 GUI Demo。支援：

- Photo：一次載入兩張照片
- Camera：兩台攝影機同步預覽與擷取
- OpenAI API：預設 `https://api.openai.com/v1/responses` + `gpt-5.6-luna`
- Custom API：通用 multipart/form-data adapter
- Random Mock：完全不分析圖片，直接隨機回傳答案
- Simulation Table：依兩張照片檔名解析 Case ID，再查 CSV/JSON 固定回傳
- 背景 Thread API 呼叫，不阻塞 GUI
- 自動保存 `runs/` 影像與結果 JSON

## 重要限制

一般 RGB 照片無法確診骨折。本程式中的 `suspected_fracture / 疑似骨折` 只代表外觀上存在疑似變形、異常角度、嚴重腫脹等特徵，不是醫療診斷。

## 安裝

建議 Python 3.11+。

```powershell
cd hand_inspection_v0.1
pip install -r requirements.txt
python main.py
```

## 最快 Demo：Random Mock

1. 輸入來源選 `Photo`
2. 任選兩張圖片
3. 辨識模式選 `Random Mock`
4. 按「開始辨識」
5. 系統會完全不看圖片內容，直接隨機回傳：正常 / 外傷 / 疑似骨折

## Simulation Table Demo

內建 `simulation/simulation_data.csv`：

- `hand_001` → normal
- `hand_002` → trauma
- `hand_003` → suspected_fracture

同一案例兩張照片必須同 Case ID，例如：

```text
hand_002_front.jpg
hand_002_side.jpg
```

系統會解析出 `hand_002`，再查 Simulation Table。

支援尾碼：

```text
_front / _side / _left / _right / _A / _B
-front / -side / -A / -B
```

第一版 `Camera + Simulation Table` 會禁止，因為攝影機 Frame 沒有原始案例檔名。

## OpenAI API

1. 辨識模式選 `OpenAI API`
2. URI 預設：`https://api.openai.com/v1/responses`
3. Model 預設：`gpt-5.6-luna`
4. 在 GUI 輸入 API Token
5. 載入兩張照片或啟動兩台 Camera
6. 按「開始辨識」

Token **不會寫入 `settings.json`**。

OpenAI Backend 會一次送出兩張圖片，要求模型僅回傳：

```json
{
  "class": "normal|trauma|suspected_fracture",
  "confidence": 0.0,
  "visible_findings": [],
  "reason": "...",
  "need_medical_review": true
}
```

## Custom API 契約

POST multipart/form-data：

- `image_a`: JPEG/file bytes
- `image_b`: JPEG/file bytes
- `model`: string
- `Authorization: Bearer <token>`：若 Token 非空

預期 response body 直接是統一結果 JSON。

## 結果保存

開啟「自動保存辨識結果」後，每次成功會產生：

```text
runs/
└── 2026-09-11_120000_xxxxxx/
    ├── image_a.jpg
    ├── image_b.jpg
    └── result.json
```

## 專案結構

```text
hand_inspection_v0.1/
├── main.py
├── backend/
│   ├── base.py
│   ├── manager.py
│   ├── openai_api.py
│   ├── custom_api.py
│   ├── random_mock.py
│   └── simulation_table.py
├── camera/
│   └── camera_manager.py
├── services/
│   └── result_storage.py
├── config/
│   └── settings.json
├── simulation/
│   └── simulation_data.csv
├── runs/
├── requirements.txt
└── README.md
```


## v0.1.6 修正
- 修正辨識完成 callback 跨 QThread 直接更新 GUI 導致的 QObject/QBackingStore 錯誤。
- Worker 結果改由 MainWindow Qt Slot 在主執行緒更新畫面。


## v0.1.6 Camera compatibility
Windows 上「載入 Camera Index」不再實際掃描/開啟 0~7 裝置，避免不存在的 index 造成大量 MSMF/DSHOW/FFMPEG 警告。請選擇 Camera A/B index（通常 0、1），按「開始攝影」後才會驗證這兩個裝置。


## v0.1.6 Camera 掃描
- Camera 模式按「掃描攝影機」後，背景測試 index 0~7 與 DSHOW/MSMF/ANY。
- 只有 `opened=True` 且 `read=True` 的組合會進入 Camera A/B 下拉選單。
- 完整掃描結果會顯示在 GUI 內。
- Camera A/B 必須使用不同的 Camera index。


## v0.1.6 Camera scan optimization

- Different camera indices are scanned concurrently with a ThreadPoolExecutor.
- Backends for the same camera index are tested sequentially to avoid device contention.
- Scanning stops at the first backend that successfully opens and reads a frame for each index.
- GUI scanning still runs in its existing QThread, so the interface remains responsive.


## v0.1.7
Camera scan thread pool is capped at 2 workers to reduce simultaneous camera/USB backend initialization while retaining parallel scanning.
