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

BASE = Path(__file__).parent
DATA = BASE / "data"
CHAR_NAMES = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]
PROCESSED_FILE = DATA / ".praised_processed.json"


def load_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)

def get_processed():
    return set(load_json(PROCESSED_FILE, []))

def mark_processed(sid):
    ids = get_processed()
    ids.add(sid)
    save_json(PROCESSED_FILE, sorted(ids))


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

    if args.rewrite:
        # 清除該集的貢獻（從 praised_by_session 追蹤）
        sid = args.rewrite
        for c in chars:
            by_sess = c.setdefault("praised_by_session", {})
            old = by_sess.pop(str(sid), 0)
            c["praised"] = max(0, c.get("praised", 0) - old)
        to_process = [s for s in sessions if s["id"] == sid
                      and not s.get("placeholder") and s.get("content")]
        print(f"強制重跑第 {sid} 集\n")
    else:
        to_process = [
            s for s in sessions
            if s["id"] >= args.start_from
            and s["id"] not in processed
            and not s.get("placeholder")
            and s.get("content")
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

        praised_list = result.get("praised", [])
        total = 0
        for item in praised_list:
            name  = item.get("char", "")
            count = int(item.get("count", 0))
            if name not in char_map or count <= 0:
                continue
            c = char_map[name]
            c.setdefault("praised", 0)
            c.setdefault("praised_by_session", {})
            c["praised"] += count
            c["praised_by_session"][str(sid)] = count
            total += count
            examples = "、".join(item.get("examples", [])[:2])
            print(f"  {name} +{count}（{examples}）")

        if not praised_list or total == 0:
            print("  本集無稱讚紀錄")

        save_json(DATA / "character-stats.json", char_stats)
        if not args.rewrite:
            mark_processed(sid)
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
