#!/usr/bin/env python3
"""
gen_ff_stats.py — 用 Gemini 分析所有集數的友軍傷害事件
輸出：data/ff-stats.json
用法：python3 gen_ff_stats.py              # 全部重跑
      python3 gen_ff_stats.py --from 5     # 從第5集開始（前面的保留）
"""

import json, subprocess, re, argparse
from pathlib import Path

from common import BASE, DATA, load_json, save_json
CHAR_NAMES = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]

def validate_char(v):
    return v if v in CHAR_NAMES else None

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)

def gemini_extract_ff(sid, text):
    prompt = f"""你是柏德之門3跑團日誌的分析員。從以下日誌中找出所有「友軍傷害」事件，以純JSON陣列回傳（不加說明或markdown）。

「友軍傷害」的定義：
- 隊友在戰鬥中（或戰鬥外）不小心或刻意對另一位隊友造成傷害、擊倒、甚至殺死
- 包括：範圍法術波及隊友、誤射、推落懸崖、環境傷害連帶傷到隊友等
- 包括：惡作劇性質的傷害（如推人下懸崖）
- 不包括：對自己造成的傷害
- 不包括：遊戲系統/NPC造成的傷害
- 不包括：雙方自願、事先約定好的決鬥或切磋（如「營地決鬥」、「單挑」、「切磋」、「睡前決鬥」、「測試傷害/裝備」等有共識的對戰，即使其中一方死亡也不算）

日誌內容（第{sid}集）：
{text}

回傳格式（JSON陣列）：
[
  {{
    "perp": "造成傷害的角色名",
    "victim": "受害角色名",
    "method": "傷害手段，10字以內（例如：閃電術波及、推落山谷、誤射箭矢）",
    "desc": "事件描述，30-60字，帶點幽默感，符合日誌風格"
  }}
]

規則：
- 角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕
- 若本集無友軍傷害事件，回傳空陣列 []
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
        if output.strip() == '[]' or not output.strip():
            return []
        print(f"  ⚠ 找不到 JSON 陣列，原始回應：{output[:400]}")
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start_from", type=int, default=1)
    args = parser.parse_args()

    sessions = load_json(DATA / "sessions.json", [])
    ff_stats = load_json(DATA / "ff-stats.json", {"incidents": [], "total": 0})

    existing = ff_stats.get("incidents", [])
    kept = [inc for inc in existing if inc.get("session", 0) < args.start_from]

    to_process = [
        s for s in sessions
        if not s.get("placeholder") and s.get("content") and s["id"] >= args.start_from
    ]

    print(f"保留 S1-S{args.start_from - 1} 共 {len(kept)} 筆")
    print(f"重新分析 S{args.start_from} 起共 {len(to_process)} 集...\n")

    new_incidents = list(kept)

    for session in to_process:
        sid = session["id"]
        print(f"Processing S{sid}...")
        text = session_to_text(session)
        events = gemini_extract_ff(sid, text)

        if events is None:
            print(f"  ⚠ 失敗，跳過")
            continue

        count = 0
        for e in events:
            perp   = validate_char(e.get("perp", ""))
            victim = validate_char(e.get("victim", ""))
            method = e.get("method", "").strip()
            desc   = e.get("desc", "").strip()
            if not perp or not victim or not desc:
                continue
            new_incidents.append({
                "session": sid,
                "perp": perp,
                "victim": victim,
                "method": method,
                "desc": desc
            })
            count += 1

        print(f"  S{sid}: {count} 事件")

        ff_stats["incidents"] = new_incidents
        ff_stats["total"]     = len(new_incidents)
        save_json(DATA / "ff-stats.json", ff_stats)

    ff_stats["incidents"] = new_incidents
    ff_stats["total"]     = len(new_incidents)
    save_json(DATA / "ff-stats.json", ff_stats)
    print(f"\n總計 {len(new_incidents)} 筆")
    print("Saved ff-stats.json")

if __name__ == "__main__":
    main()
