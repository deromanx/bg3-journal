#!/usr/bin/env python3
"""
gen_praise_stats.py — 用 Gemini 分析所有集數的稱讚事件（不限情景，排除諷刺性稱讚）
輸出：data/praise-stats.json（與 roast-stats.json 結構相同）
用法：python3 gen_praise_stats.py              # 全部重跑
      python3 gen_praise_stats.py --from 5     # 從第5集開始（前面的保留）
"""

import json, subprocess, re, argparse
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

def validate_chars(v):
    return [c for c in as_list(v) if c in CHAR_NAMES]

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)


def gemini_extract_praise(sid, text):
    prompt = f"""你是柏德之門3跑團日誌的分析員。從以下日誌中找出所有廣義的「稱讚/讚美/認可/感謝」事件，以純JSON陣列回傳（不加說明或markdown）。

「稱讚」的廣義定義（盡量包含，寧可多抓不要漏）：
- 對隊友的行為、表現、決策、個性給予正面評價：「你這個做得很好」、「這波操作超強」、「你真的太穩了」
- 驚嘆讚美：「哇你怎麼這麼聰明」、「這招怎麼想到的」、「太猛了吧」
- 隱性稱讚/認可：「不愧是XXX」、「果然靠你了」、「還是XXX厲害」、「XXX出手了不同凡響」
- 感謝與救命之恩：「幸虧有你」、「謝謝你剛才救了我」、「多虧XXX」
- 承認對方能力/策略超強：「這配點真的很強」、「你這個思路不錯」、「XXX這波玩得很好」
- 對隊友表現感到impressed/佩服的任何表達
- AI敘事旁白中提到某角色「關鍵時刻力挽狂瀾」、「靠XXX才贏得這場戰鬥」等也算
- 不包括：純粹的諷刺/嘲諷中夾帶的假讚美、吐槽性靠北中帶嘲諷的假稱讚

日誌內容（第{sid}集）：
{text}

回傳格式（JSON陣列）：
[
  {{
    "from": "稱讚發起者角色名，若多人一起稱讚同一目標則用陣列",
    "to": "被稱讚的角色名，若同時稱讚多人則用陣列",
    "quote": "稱讚的原話或最精華句子，直接引用日誌原文，20字內，不需加引號",
    "desc": "事件描述，30-60字，說明情景與稱讚內容"
  }}
]

規則：
- 角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕
- from 和 to 都可以是字串（單人）或陣列（多人）
- 不含對 NPC/怪物的稱讚
- 若本集無稱讚事件，回傳空陣列 []
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
        highlights.append({"session": sid, "desc": f"{frm_label}稱讚{to_label}：{desc}"})
    return matrix, highlights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start_from", type=int, default=1)
    args = parser.parse_args()

    sessions     = load_json(DATA / "sessions.json", [])
    praise_stats = load_json(DATA / "praise-stats.json",
                             {"_note": "稱讚統計（不限情景，排除諷刺性稱讚）",
                              "matrix": [], "highlights": [], "quotes": [], "total": 0})

    existing_quotes = praise_stats.get("quotes", [])
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
        text   = session_to_text(session)
        praises = gemini_extract_praise(sid, text)

        if praises is None:
            print(f"  ⚠ 失敗，跳過")
            continue

        count = 0
        for p in praises:
            frm_list = validate_chars(p.get("from", ""))
            to_list  = validate_chars(p.get("to", ""))
            desc     = p.get("desc", "").strip()
            if not frm_list or not to_list or not desc:
                continue
            from_val = frm_list[0] if len(frm_list) == 1 else frm_list
            to_val   = to_list[0]  if len(to_list)  == 1 else to_list
            quote    = p.get("quote", "").strip()
            entry = {"session": sid, "from": from_val, "to": to_val, "desc": desc}
            if quote:
                entry["quote"] = quote
            new_quotes.append(entry)
            count += 1

        print(f"  S{sid}: {count} 事件")

        matrix, highlights = build_matrix_highlights(new_quotes)
        praise_stats["quotes"]     = new_quotes
        praise_stats["matrix"]     = matrix
        praise_stats["highlights"] = highlights
        praise_stats["total"]      = sum(m["count"] for m in matrix)
        save_json(DATA / "praise-stats.json", praise_stats)

    matrix, highlights = build_matrix_highlights(new_quotes)
    praise_stats["quotes"]     = new_quotes
    praise_stats["matrix"]     = matrix
    praise_stats["highlights"] = highlights
    praise_stats["total"]      = sum(m["count"] for m in matrix)
    save_json(DATA / "praise-stats.json", praise_stats)
    print(f"\n總計 {len(new_quotes)} 條")
    print("Saved praise-stats.json")


if __name__ == "__main__":
    main()
