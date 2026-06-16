#!/usr/bin/env python3
"""common.py — 柏德之門日誌 gen/count 腳本共用工具。

集中各腳本原本各自重複定義的路徑常數與 JSON 讀寫 helper，
避免十多份腳本各持一份相同的 load_json/save_json/BASE/DATA。
"""

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
