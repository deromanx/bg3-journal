#!/usr/bin/env python3
"""llm_queue.py — Claude 模式的待辦佇列（見 llm.py）。

用法：
  python3 llm_queue.py list     列出待作答的 prompt 與對應原文檔、答案路徑
  python3 llm_queue.py count    只印待辦數（update_all.sh 用）
  python3 llm_queue.py clean    清掉沒有待辦引用的原文檔

作答流程（Claude Code session 內）：
  1. list → 每集先讀一次 text__S{id}__*.txt 原文
  2. 逐一讀 *.prompt.txt，依其格式與規則產出回應，寫到檔頭標示的答案路徑
  3. 重跑 ./update_all.sh（已作答的會被腳本吃進去；有依賴的下一輪待辦會再出現）
"""

import re
import sys

import llm


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    items = llm.pending()
    if cmd == "count":
        print(len(items))
        return
    if cmd == "clean":
        refs = "".join(p.read_text("utf-8") for p in items)
        n = 0
        for t in llm.PENDING.glob("text__*.txt"):
            if t.name not in refs:
                t.unlink()
                n += 1
        print(f"清掉 {n} 個未被引用的原文檔")
        return
    if not items:
        print("✓ 沒有待作答的 prompt")
        return
    texts = set()
    print(f"⏸ 待作答 {len(items)} 項（目錄 {llm.PENDING}）：")
    for p in items:
        body = p.read_text("utf-8")
        m = re.search(r"〔日誌原文見 (\S+)（", body)
        if m:
            texts.add(m.group(1))
        print(f"  - {p.name}" + (f"   ← 原文 {m.group(1)}" if m else ""))
    if texts:
        print("原文檔：")
        for t in sorted(texts):
            print(f"  - {llm.PENDING / t}")
    print(f"答案目錄：{llm.ANSWERS}（檔名＝prompt 檔名去掉 .prompt）")


if __name__ == "__main__":
    main()
