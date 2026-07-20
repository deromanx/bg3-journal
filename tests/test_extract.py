#!/usr/bin/env python3
"""
extract.py 純函式回歸測試（不需 pytest，python3 tests/test_extract.py 直接跑）。

守護歷史上踩過的雷：
- 標題層級判斷（bold/縮排/VS 對戰名）曾兩次改壞（2026-06-08 修正）
- 規則單一來源：自身 left=0 → h1；left>0 → h2；VS 型固定 h2
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from extract import classify, resolve_type, clean, is_meta, parse_folder  # noqa: E402

FAILURES = []


def check(desc, actual, expected):
    if actual != expected:
        FAILURES.append(f"  ✗ {desc}: got {actual!r}, want {expected!r}")


# ── classify()：bold 標題 ──────────────────────────────────
check("bold 無標點 → h1", classify("誤入幽暗地域", bold=True), "h1")
check("bold 結尾驚嘆號允許 → h1", classify("吃蟲啊！", bold=True), "h1")
check("bold 結尾問號允許 → h1", classify("這是誰的錯？", bold=True), "h1")
check("bold 句中逗號 → p", classify("走著走著，就到了", bold=True), "p")
check("bold 句中句號 → p", classify("結束了。大家散會", bold=True), "p")
check("bold 括號開頭 → p", classify("(旁白：其實不然)", bold=True), "p")

# ── classify()：VS 對戰名固定 h2（不論大小寫與縮寫變體） ──
check("VS 型 → h2", classify("影心 vs 曹", bold=True), "h2")
check("VS 大寫 → h2", classify("卡拉克 VS. 貓咕咕", bold=True), "h2")
check("v.s. 變體 → h2", classify("阿斯代倫 v.s. 影心", bold=True), "h2")
check("非隊員 VS → 不匹配（一般 h1 規則）", classify("路人甲 vs 路人乙", bold=True), "h1")

# ── classify()：AI 點評與非 bold 備用 ──────────────────────
check("AI 點評 → ai", classify("(AI 點評：這步很蠢)", bold=False), "ai")
check("AI Comment 英文 → ai", classify("(AI Comment: bold move)", bold=False), "ai")
check("非 bold 短行 → h2", classify("戰利品清單", bold=False), "h2")
check("非 bold 數字開頭 → p", classify("3隻地精來襲", bold=False), "p")
check("非 bold 長句 → p", classify("這是一段超過十六個字的普通敘述文字內容啊", bold=False), "p")

# ── resolve_type()：縮排收斂規則（2026-06-08 確立） ────────
check("h1 left=0 保持 h1", resolve_type("h1", 0), "h1")
check("h1 left=480 降為 h2", resolve_type("h1", 480), "h2")
check("h1 left=660 降為 h2", resolve_type("h1", 660), "h2")
check("h2 不受縮排影響", resolve_type("h2", 0), "h2")
check("p left=0 → p", resolve_type("p", 0), "p")
check("p left=659 → p（未達 li 門檻）", resolve_type("p", 659), "p")
check("p left=660 → li", resolve_type("p", 660), "li")
check("p left=1199 → li", resolve_type("p", 1199), "li")
check("p left=1200 → li2", resolve_type("p", 1200), "li2")
check("img 不受影響", resolve_type("img", 999), "img")
check("ai 不受影響", resolve_type("ai", 999), "ai")

# ── clean() / is_meta() / parse_folder() ──────────────────
check("pdftotext 遺留字修正", clean("㇐個人"), "一個人")
check("meta 行過濾（時間戳）", is_meta("🕒 21:30 開團"), True)
check("meta 行過濾（AI評選）", is_meta("AI評選金句如下"), True)
check("一般內容非 meta", is_meta("影心施放火球術"), False)
check(
    "資料夾名解析",
    parse_folder("20260506-魚人、船票"),
    ("2026-05-06", "2026 年 5 月 6 日", "魚人、船票"),
)
check("無日期資料夾", parse_folder("雜項"), (None, None, "雜項"))

# ── 結果 ──────────────────────────────────────────────────
total = 29
if FAILURES:
    print(f"❌ extract.py 回歸測試失敗（{len(FAILURES)}/{total}）：")
    print("\n".join(FAILURES))
    sys.exit(1)
print(f"✅ extract.py 回歸測試通過（{total} 項）")
