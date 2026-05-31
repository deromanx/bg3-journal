#!/usr/bin/env python3
"""
normalize_names.py — 對所有 data/*.json 套用 name_fixes，修正下游已生成內容
（awards / roast-stats / story / milestones / character-stats）裡的角色名錯字。

sessions.json 的錯字由 extract.py 在萃取時處理；但各 gen 腳本透過 Gemini
重述逐字稿時可能再製造錯字，故 pipeline 最後跑這支統一收尾。
只在內容真的有變動時才寫回，避免無謂的 git diff。

用法：python3 normalize_names.py
"""

import json
from pathlib import Path
from name_fixes import fix_obj

DATA = Path(__file__).parent / "data"


def main():
    changed = 0
    for path in sorted(DATA.glob("*.json")):
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception as e:
            print(f"⚠ 跳過 {path.name}：{e}")
            continue
        fixed = fix_obj(data)
        if fixed != data:
            path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2), "utf-8")
            print(f"✓ 修正 {path.name}")
            changed += 1
    print(f"\n完成，{changed} 個檔案有修正" if changed else "✓ 無錯字需修正")


if __name__ == "__main__":
    main()
