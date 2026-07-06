#!/usr/bin/env python3
"""
gen_char_quotes.py — 用 Gemini 逐集抽取每位角色的「代表台詞」，寫入角色名言錄。
輸出：data/character-stats.json（覆蓋每位角色的 quotes 欄位）

名言錄 = 角色檔案頁「💬 名言錄」，收錄角色本人親口說過、最經典/最好笑的台詞。
與 roast/praise 語錄不同：這裡只收「自己說的」金句，不含靠北/被靠北關係。

用法：
  python3 gen_char_quotes.py              # 全部重跑（--from 1）
  python3 gen_char_quotes.py --from 25    # 從第25集起增量（前面保留現有 quotes）
"""

import json, subprocess, re, argparse
from pathlib import Path

from common import BASE, DATA, load_json, save_json

CHAR_NAMES = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]

# 每位角色單集最多收錄幾句（避免某集台詞灌爆名言錄）
MAX_PER_CHAR_PER_SESSION = 1


def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)


def gemini_extract_quotes(sid, text):
    prompt = f"""你是柏德之門3跑團日誌的語錄編輯。從以下日誌中，為這五位玩家角色各挑出「本人親口說過、最能代表其個性或最經典好笑」的台詞，以純JSON陣列回傳（不加說明或markdown）。

日誌內容（第{sid}集）：
{text}

回傳格式（JSON陣列）：
[
  {{"char": "角色名", "text": "角色親口說的原話，直接引用日誌原文，25字內，不需加引號"}}
]

規則：
- 角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕
- 只收「該角色自己說出口的話」，不要收旁白、不要收別人對他說的話
- 每位角色本集最多 1 句；若某角色本集沒有值得收錄的經典台詞，就不要放他
- 偏好有記憶點、好笑、能代表人設的句子，而非普通的戰術溝通
- 直接引用日誌原文，不要改寫、不要自己編造
- 若本集全無值得收錄的台詞，回傳空陣列 []
- 直接回傳 JSON，不加任何其他文字"""

    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True, timeout=600
    )

    if result.returncode != 0:
        print(f"  ⚠ Gemini 錯誤：{result.stderr[:300]}")
        return None

    output = result.stdout.strip()
    arr_match = re.search(r'\[[\s\S]*\]', output)
    if arr_match:
        try:
            return json.loads(arr_match.group())
        except json.JSONDecodeError as e:
            print(f"  ⚠ JSON 解析失敗：{e}")
            print(f"  原始回應：{output[:400]}")
    else:
        print(f"  ⚠ 找不到 JSON 陣列，原始回應：{output[:400]}")
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start_from", type=int, default=1,
                        help="從哪一集開始重跑（之前的保留現有 quotes）")
    args = parser.parse_args()

    sessions   = load_json(DATA / "sessions.json", [])
    char_stats = load_json(DATA / "character-stats.json", {"characters": []})
    chars      = char_stats.get("characters", [])

    # 每位角色：保留 start_from 之前的既有 quotes，之後的重抽
    kept = {}
    for c in chars:
        existing = c.get("quotes", [])
        kept[c["char"]] = [q for q in existing if q.get("session", 0) < args.start_from]

    to_process = [
        s for s in sessions
        if not s.get("placeholder") and s.get("content") and s["id"] >= args.start_from
    ]

    kept_total = sum(len(v) for v in kept.values())
    print(f"保留 S1-S{args.start_from - 1} 共 {kept_total} 句")
    print(f"重新分析 S{args.start_from} 起共 {len(to_process)} 集...\n")

    # 累積結果（先塞入保留的），逐集擴充
    result_quotes = {name: list(kept.get(name, [])) for name in CHAR_NAMES}

    def flush():
        by_name = {c["char"]: c for c in chars}
        for name, qs in result_quotes.items():
            if name in by_name:
                by_name[name]["quotes"] = sorted(qs, key=lambda q: q.get("session", 0))
        save_json(DATA / "character-stats.json", char_stats)

    for session in to_process:
        sid = session["id"]
        print(f"Processing S{sid}...")
        text  = session_to_text(session)
        picks = gemini_extract_quotes(sid, text)

        if picks is None:
            print(f"  ⚠ 失敗，跳過")
            continue

        per_char_count = {name: 0 for name in CHAR_NAMES}
        count = 0
        for p in picks:
            name = p.get("char", "").strip()
            quote = p.get("text", "").strip().strip("「」\"' ")
            if name not in CHAR_NAMES or not quote:
                continue
            if per_char_count[name] >= MAX_PER_CHAR_PER_SESSION:
                continue
            result_quotes[name].append({"text": quote, "session": sid})
            per_char_count[name] += 1
            count += 1

        print(f"  S{sid}: {count} 句（{'、'.join(f'{n}{c}' for n, c in per_char_count.items() if c)})")

        # 每集完成後立即儲存，方便中途失敗時用 --from 接續
        flush()

    total = sum(len(v) for v in result_quotes.values())
    print(f"\n總計 {total} 句名言")
    flush()
    print("Saved character-stats.json")


if __name__ == "__main__":
    main()
