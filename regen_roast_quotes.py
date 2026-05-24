#!/usr/bin/env python3
"""
regen_roast_quotes.py — 重新用 Gemini 分析所有集數的靠北事件，支援多人靠北
用法：python3 regen_roast_quotes.py              # 全部重跑
      python3 regen_roast_quotes.py --from 5     # 從第5集開始（前面的從現有 quotes 保留）
"""

import json, subprocess, re, sys, argparse
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"

CHAR_NAMES = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]


def load_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def as_list(v):
    return v if isinstance(v, list) else [v]

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)

def validate_chars(v):
    return [c for c in as_list(v) if c in CHAR_NAMES]

def gemini_extract_roasts(sid, text):
    prompt = f"""你是柏德之門3跑團日誌的分析員。從以下日誌中找出所有「靠北/吐槽/嘲笑/批評」事件，以純JSON陣列回傳（不加說明或markdown）。

日誌內容（第{sid}集）：
{text}

回傳格式（JSON陣列）：
[
  {{
    "from": "靠北發起者角色名，若多人一起靠北同一目標則用陣列，例如 [\\"曹\\", \\"阿斯代倫\\"]",
    "to": "被靠北的角色名，若同時靠北多人則用陣列",
    "quote": "靠北的原話或最精華句子，直接引用日誌原文，20字內，不需加引號",
    "desc": "事件描述，50-80字，包含前因後果，說明為什麼靠北、靠北的內容是什麼"
  }}
]

規則：
- 角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕
- from 和 to 都可以是字串（單人）或陣列（多人）
- 多人同時靠北一個人：from 用陣列，to 用字串
- 一個人同時靠北多人（少見）：from 用字串，to 用陣列
- 不含決鬥嘲諷、不含對 NPC/怪物的吐槽
- 自嘲也算（from 和 to 相同）
- 若本集無靠北事件，回傳空陣列 []
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


def build_matrix_highlights(quotes):
    matrix = []
    highlights = []
    for q in quotes:
        frm_list = as_list(q["from"])
        to_list  = as_list(q["to"])
        sid      = q["session"]
        desc     = q["desc"]
        for frm in frm_list:
            for to in to_list:
                ex = next((m for m in matrix if m["from"] == frm and m["to"] == to), None)
                if ex:
                    ex["count"] += 1
                else:
                    matrix.append({"from": frm, "to": to, "count": 1})
        frm_label = "、".join(frm_list)
        to_label  = "、".join(to_list)
        highlights.append({"session": sid, "desc": f"{frm_label}靠北{to_label}：{desc}"})
    return matrix, highlights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start_from", type=int, default=1,
                        help="從哪一集開始重跑（之前的保留現有 quotes）")
    args = parser.parse_args()

    sessions    = load_json(DATA / "sessions.json", [])
    roast_stats = load_json(DATA / "roast-stats.json",
                            {"matrix": [], "highlights": [], "quotes": [], "total": 0})

    existing_quotes = roast_stats.get("quotes", [])
    # 保留 start_from 之前的 quotes
    kept_quotes = [q for q in existing_quotes if q["session"] < args.start_from]

    to_process = [
        s for s in sessions
        if not s.get("placeholder") and s.get("content") and s["id"] >= args.start_from
    ]

    print(f"保留 S1-S{args.start_from - 1} 共 {len(kept_quotes)} 條")
    print(f"重新分析 S{args.start_from} 起共 {len(to_process)} 集...\n")

    new_quotes = list(kept_quotes)

    for session in to_process:
        sid = session["id"]
        print(f"Processing S{sid}...")
        text = session_to_text(session)
        roasts = gemini_extract_roasts(sid, text)

        if roasts is None:
            print(f"  ⚠ 失敗，跳過")
            continue

        count = 0
        for r in roasts:
            frm_list = validate_chars(r.get("from", ""))
            to_list  = validate_chars(r.get("to", ""))
            desc     = r.get("desc", "").strip()
            if not frm_list or not to_list or not desc:
                continue
            from_val = frm_list[0] if len(frm_list) == 1 else frm_list
            to_val   = to_list[0]  if len(to_list)  == 1 else to_list
            quote    = r.get("quote", "").strip()
            entry = {"session": sid, "from": from_val, "to": to_val, "desc": desc}
            if quote:
                entry["quote"] = quote
            new_quotes.append(entry)
            count += 1

        print(f"  S{sid}: {count} 事件")

        # 每集完成後立即儲存，方便中途失敗時用 --from 接續
        matrix, highlights = build_matrix_highlights(new_quotes)
        roast_stats["quotes"]     = new_quotes
        roast_stats["matrix"]     = matrix
        roast_stats["highlights"] = highlights
        roast_stats["total"]      = sum(m["count"] for m in matrix)
        save_json(DATA / "roast-stats.json", roast_stats)

    matrix, highlights = build_matrix_highlights(new_quotes)
    print(f"\n總計 {len(new_quotes)} 條")
    roast_stats["quotes"]     = new_quotes
    roast_stats["matrix"]     = matrix
    roast_stats["highlights"] = highlights
    roast_stats["total"]      = sum(m["count"] for m in matrix)
    save_json(DATA / "roast-stats.json", roast_stats)
    print("Saved roast-stats.json")


if __name__ == "__main__":
    main()
