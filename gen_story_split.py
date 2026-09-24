#!/usr/bin/env python3
"""
把 data/story.json 拆成前端逐章延遲載入用的小檔：
  data/story/index.json   章節目錄（session_id / title / chars），故事分頁首屏只抓這個
  data/story/{sid}.json   單章全文 {"text": ...}，捲動接近時才抓

story.json 仍是 pipeline 的單一來源（gen_story.py / update_stats.py 讀寫它）；
本腳本只產部署用的衍生檔，重跑 idempotent，也會清掉已不存在章節的孤兒檔。
純本地生成，不呼叫 Gemini。

用法：python3 gen_story_split.py
"""

import json
from pathlib import Path

from common import DATA, load_json

OUT_DIR = DATA / "story"


def write_if_changed(path: Path, obj) -> bool:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if path.exists() and path.read_text("utf-8") == text:
        return False
    path.write_text(text, "utf-8")
    return True


def main():
    story = load_json(DATA / "story.json", {"chapters": []})
    chapters = sorted(story.get("chapters", []), key=lambda c: c["session_id"])
    OUT_DIR.mkdir(exist_ok=True)

    changed = 0
    index = []
    for ch in chapters:
        sid, text = ch["session_id"], ch.get("text", "")
        index.append({"session_id": sid, "title": ch.get("title", ""), "chars": len(text)})
        changed += write_if_changed(OUT_DIR / f"{sid}.json", {"text": text})
    changed += write_if_changed(OUT_DIR / "index.json", {"chapters": index})

    want = {f"{c['session_id']}.json" for c in chapters} | {"index.json"}
    orphans = [p for p in OUT_DIR.glob("*.json") if p.name not in want]
    for p in orphans:
        p.unlink()

    print(f"故事拆檔：共 {len(chapters)} 章，更新 {changed} 檔，刪除孤兒 {len(orphans)} 檔 → data/story/")


if __name__ == "__main__":
    main()
