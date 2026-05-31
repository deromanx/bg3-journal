#!/usr/bin/env python3
"""
name_fixes.py — 角色名錯字的單一來源。
extract.py 與 normalize_names.py 都從這裡 import，避免各處重複維護。

新增錯字時只改這個 dict 即可，然後重跑 extract.py（修 sessions.json）
與 normalize_names.py（修下游 awards/roast/story 等已生成內容）。
"""

# 錯字 → 正確（值不可包含其 key 作為子字串，否則會無限放大）
NAME_FIXES = {
    "卡菈克": "卡拉克",
    "阿斯戴倫": "阿斯代倫",
    "阿斯代輪": "阿斯代倫",
    "曹誠": "曹祐誠",
}


def fix_text(s: str) -> str:
    for wrong, right in NAME_FIXES.items():
        s = s.replace(wrong, right)
    return s


def fix_obj(obj):
    """遞迴修正 dict / list / str 內所有字串值，其餘型別原樣回傳。"""
    if isinstance(obj, str):
        return fix_text(obj)
    if isinstance(obj, list):
        return [fix_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: fix_obj(v) for k, v in obj.items()}
    return obj
