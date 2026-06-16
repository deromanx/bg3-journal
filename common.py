#!/usr/bin/env python3
"""common.py — 柏德之門日誌 gen/count 腳本共用工具。

集中各腳本原本各自重複定義的路徑常數與 JSON 讀寫 helper，
避免十多份腳本各持一份相同的 load_json/save_json/BASE/DATA。
"""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"


def load_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def content_fingerprint(content) -> str:
    """以一集的 content（段落/圖片列表）算出穩定指紋。

    用於偵測「已處理過的集數內容是否被回頭修改」，避免統計與內容脫鉤。
    僅看文字內容（t/v），忽略圖片尺寸等衍生欄位，重存圖片不會誤判為改動。
    """
    if isinstance(content, dict):          # 容錯：傳入整個 session 物件時取 content
        content = content.get("content", [])
    sig = [[it.get("t"), it.get("v")] for it in (content or [])
           if isinstance(it, dict)]
    blob = json.dumps(sig, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()
