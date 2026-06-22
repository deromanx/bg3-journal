#!/usr/bin/env python3
"""
name_fixes.py — 角色名錯字的單一來源。
extract.py 與 normalize_names.py 都從這裡 import，避免各處重複維護。

新增錯字時只改這個 dict 即可，然後重跑 extract.py（修 sessions.json）
與 normalize_names.py（修下游 awards/roast/story 等已生成內容）。
"""

import re

# 錯字 → 正確（值不可包含其 key 作為子字串，否則 .replace 會無限放大）
NAME_FIXES = {
    "卡菈克": "卡拉克",
    "阿斯戴倫": "阿斯代倫",
    "阿斯代輪": "阿斯代倫",
    "曹誠": "曹祐誠",
}

# 正則修正：用於「錯字本身是正確值的子字串」的情況（NAME_FIXES 的 .replace 無法處理）。
# 例：「貓咕」→「貓咕咕」，但已正確的「貓咕咕」不可再被加長，故用負向前瞻 (?!咕)。
REGEX_FIXES = [
    (re.compile(r"貓咕(?!咕)"), "貓咕咕"),
]


def fix_text(s: str) -> str:
    for wrong, right in NAME_FIXES.items():
        s = s.replace(wrong, right)
    for pat, right in REGEX_FIXES:
        s = pat.sub(right, s)
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
