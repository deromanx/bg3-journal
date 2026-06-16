#!/usr/bin/env python3
"""
gen_story.py — 用 Gemini 為所有集數生成 GRRM 風格故事章節
用法：python3 gen_story.py              # 跑全部（跳過已生成）
      python3 gen_story.py --from 5     # 從第5集開始
      python3 gen_story.py --rewrite 3  # 強制重寫第3集
"""

import json, subprocess, re, sys, argparse
from pathlib import Path

from common import BASE, DATA, load_json, save_json

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)

def gemini_story(session, prev_chapters):
    text = session_to_text(session)
    sid  = session["id"]

    prev_ctx = ""
    if prev_chapters:
        summaries = "\n".join(
            f"- 第{ch['session_id']}章《{ch['title']}》"
            for ch in prev_chapters[-3:]
        )
        prev_ctx = f"\n\n前幾章已發生：\n{summaries}\n請在行文中保持與前章連貫的敘事感。"

    prompt = f"""你是一位以喬治·馬丁（George R.R. Martin）風格著稱的奇幻小說家。
請將以下柏德之門3跑團記錄，改寫成一章奇幻小說（繁體中文，約1000-1500字）。

要求：
- 第三人稱史詩敘事，豐富的環境細節與感官描寫
- 角色名保留：影心、阿斯代倫、曹、卡拉克、貓咕咕
- 徹底移除遊戲術語（HP、AC、法術欄、擲骰、命中率、法術格等），改用奇幻敘事語言
- 保留原始事件，但以文學散文呈現（包括荒謬喜劇場面，用嚴肅的史詩語氣描述更有趣）
- 開頭一句強烈的環境或氛圍描寫
- 融入角色的內心戲與奇幻化對白
- 結尾留有懸念或餘韻{prev_ctx}

跑團記錄（第{sid}集 《{session['title']}》）：
{text}

請以純 JSON 格式回傳（不加說明文字或 markdown）：
{{"title": "本章文學標題（10字內）", "text": "小說正文（純文字，段落以空行分隔）"}}"""

    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        print(f"  ⚠ Gemini 錯誤：{result.stderr[:200]}")
        return None

    output = result.stdout.strip()
    m = re.search(r'\{[\s\S]*\}', output)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError as e:
            print(f"  ⚠ JSON 解析失敗：{e}\n  回應：{output[:300]}")
    else:
        print(f"  ⚠ 找不到 JSON，回應：{output[:300]}")
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start_from", type=int, default=1)
    parser.add_argument("--rewrite", type=int, metavar="SESSION_ID")
    args = parser.parse_args()

    sessions = load_json(DATA / "sessions.json", [])
    story    = load_json(DATA / "story.json", {"chapters": []})
    chapters = story.get("chapters", [])

    if args.rewrite:
        chapters = [c for c in chapters if c["session_id"] != args.rewrite]
        to_process = [s for s in sessions if s["id"] == args.rewrite and not s.get("placeholder") and s.get("content")]
        print(f"強制重寫第 {args.rewrite} 集\n")
    else:
        done_ids = {c["session_id"] for c in chapters}
        to_process = [
            s for s in sessions
            if s["id"] >= args.start_from
            and s["id"] not in done_ids
            and not s.get("placeholder")
            and s.get("content")
        ]
        kept = len([c for c in chapters if c["session_id"] < args.start_from])
        print(f"保留已完成 {len(done_ids)} 集，待生成 {len(to_process)} 集\n")

    for session in to_process:
        sid = session["id"]
        print(f"Processing S{sid}《{session['title']}》...")
        result = gemini_story(session, sorted(chapters, key=lambda c: c["session_id"]))
        if not result or not result.get("text"):
            print(f"  ⚠ 失敗，跳過")
            continue

        chapters.append({
            "session_id": sid,
            "title":      result.get("title", session["title"]),
            "text":       result["text"],
        })
        chapters_sorted = sorted(chapters, key=lambda c: c["session_id"])
        story["chapters"] = chapters_sorted
        save_json(DATA / "story.json", story)
        print(f"  S{sid}: 完成（{len(result['text'])} 字）")

    print(f"\n共 {len(story['chapters'])} 章，Saved story.json")

if __name__ == "__main__":
    main()
