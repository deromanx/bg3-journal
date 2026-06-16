#!/usr/bin/env python3
"""
count_praised.py — 讓 Gemini 分析每集日誌，統計每人在戰鬥中被隊友稱讚的次數
結果寫入 data/character-stats.json 各角色的 praised 欄位
用法：python3 count_praised.py              # 跑全部
      python3 count_praised.py --from 5     # 從第5集開始
      python3 count_praised.py --rewrite 3  # 強制重跑第3集
"""

import json, subprocess, re, argparse
from pathlib import Path

from common import BASE, DATA, load_json, save_json, content_fingerprint
CHAR_NAMES = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]
PROCESSED_FILE = DATA / ".praised_processed.json"

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)

# 處理標記改存「id → 內容指紋」：內容被回頭修改時指紋改變，會自動重跑該集。
# 容錯：若讀到舊版 list 格式，視為「指紋未知」（值為 None），交由呼叫端決定。
def get_processed():
    raw = load_json(PROCESSED_FILE, {})
    if isinstance(raw, list):
        return {str(i): None for i in raw}
    return {str(k): v for k, v in raw.items()}

def mark_processed(sid, fp, store):
    store[str(sid)] = fp
    save_json(PROCESSED_FILE, store)

def gemini_count_praised(text, sid):
    prompt = f"""你是一位分析桌上RPG跑團日誌的助手。請仔細閱讀以下跑團紀錄，統計每位玩家角色在**戰鬥場景中**被隊友稱讚的次數。

「被稱讚」的定義：
- 隊友在戰鬥中或戰鬥後，對某人的攻擊、技能、判斷或表現給予正面評價
- 包括：「打得好」、「幹得漂亮」、「你真的太強了」、「那一下很猛」等類似表達
- 包括：驚呼讚嘆（「哇」、「這什麼神操作」）針對某人的戰鬥表現
- 不包括：一般日常對話的稱讚、諷刺性的稱讚、靠北中帶有嘲諷的假誇獎

角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕

跑團記錄（第{sid}集）：
{text}

請以純 JSON 格式回傳（不加說明文字或 markdown）：
{{
  "praised": [
    {{"char": "角色名", "count": 次數, "examples": ["具體例子（10字內）"]}}
  ]
}}

若某角色本集沒有被稱讚，不需列出。若整集沒有任何稱讚，回傳 {{"praised": []}}"""

    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True, timeout=300
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

    sessions   = load_json(DATA / "sessions.json", [])
    char_stats = load_json(DATA / "character-stats.json", {"characters": []})
    chars      = char_stats.get("characters", [])
    char_map   = {c["char"]: c for c in chars}

    processed = get_processed()

    def fp_of(s):
        return content_fingerprint(s.get("content", []))

    if args.rewrite:
        sid = args.rewrite
        to_process = [s for s in sessions if s["id"] == sid
                      and not s.get("placeholder") and s.get("content")]
        print(f"強制重跑第 {sid} 集\n")
    else:
        # 指紋不符（新集或內容被回頭修改）才處理
        to_process = [
            s for s in sessions
            if s["id"] >= args.start_from
            and not s.get("placeholder")
            and s.get("content")
            and processed.get(str(s["id"])) != fp_of(s)
        ]
        print(f"待處理 {len(to_process)} 集\n")

    for session in to_process:
        sid = session["id"]
        print(f"S{sid}《{session['title']}》...")
        text   = session_to_text(session)
        result = gemini_count_praised(text, sid)
        if result is None:
            print("  ⚠ 失敗，跳過")
            continue

        # 先清除本集舊貢獻（重跑時避免殘留），再依新結果重填
        for c in chars:
            c.get("praised_by_session", {}).pop(str(sid), None)

        praised_list = result.get("praised", [])
        total = 0
        for item in praised_list:
            name  = item.get("char", "")
            count = int(item.get("count", 0))
            if name not in char_map or count <= 0:
                continue
            c = char_map[name]
            c.setdefault("praised_by_session", {})[str(sid)] = count
            total += count
            examples = "、".join(item.get("examples", [])[:2])
            print(f"  {name} +{count}（{examples}）")

        # 純量一律由 by_session 推導：idempotent，免疫重跑與 reset 失步
        for c in chars:
            c["praised"] = sum(c.get("praised_by_session", {}).values())

        if not praised_list or total == 0:
            print("  本集無稱讚紀錄")

        save_json(DATA / "character-stats.json", char_stats)
        mark_processed(sid, fp_of(session), processed)
        print(f"  ✓\n")

    # 最終輸出統計
    print("── 最終統計 ──")
    for name in CHAR_NAMES:
        c = char_map.get(name, {})
        print(f"  {name}：{c.get('praised', 0)} 次")

    save_json(DATA / "character-stats.json", char_stats)
    print("\n✓ 已儲存 character-stats.json")

if __name__ == "__main__":
    main()
