#!/usr/bin/env python3
"""
count_combat_contrib.py — Gemini 分析每集日誌，統計每人「關鍵戰鬥貢獻」次數
（包含戰鬥中被稱讚 + 扭轉戰局的決定性行動）
結果寫入 data/character-stats.json 各角色的 combat_contrib 欄位
用法：python3 count_combat_contrib.py
      python3 count_combat_contrib.py --from 5
      python3 count_combat_contrib.py --rewrite 3
"""

import json, subprocess, re, argparse
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
CHAR_NAMES = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]
PROCESSED_FILE = DATA / ".combat_contrib_processed.json"


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


def gemini_count_contrib(text, sid):
    prompt = f"""你是一位分析桌上RPG跑團日誌的助手。請仔細閱讀以下跑團紀錄，統計每位角色的「關鍵戰鬥貢獻」次數。

「關鍵戰鬥貢獻」的定義（符合任一條件即計入）：
1. 在戰鬥中被隊友稱讚、驚呼、或肯定其表現（如「幹打得好」、「那一下超猛」、「靠你了」）
2. 執行了扭轉戰局的決定性行動（如：清場大招命中所有敵人、關鍵爆擊擊殺 Boss、在最危急時刻救活隊友、一招解決棘手局面）
3. 被日誌作者特別記錄為「關鍵」、「決定性」、「最重要」的戰鬥行動

不計入：
- 一般的攻擊或施法（未被特別標記）
- 失敗的行動（擲骰失敗、沒打中）
- 戰鬥以外的行動
- 諷刺或嘲笑中夾帶的假誇獎

角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕

跑團記錄（第{sid}集）：
{text}

請以純 JSON 格式回傳（不加說明文字或 markdown）：
{{
  "contributions": [
    {{"char": "角色名", "count": 次數, "examples": ["具體事件描述（15字內）"]}}
  ]
}}

若某角色本集沒有關鍵貢獻，不需列出。若整集沒有，回傳 {{"contributions": []}}"""

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
        sid = args.rewrite
        for c in chars:
            by_sess = c.setdefault("combat_contrib_by_session", {})
            old = by_sess.pop(str(sid), 0)
            c["combat_contrib"] = max(0, c.get("combat_contrib", 0) - old)
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
        result = gemini_count_contrib(text, sid)
        if result is None:
            print("  ⚠ 失敗，跳過")
            continue

        contribs = result.get("contributions", [])
        total = 0
        for item in contribs:
            name  = item.get("char", "")
            count = int(item.get("count", 0))
            if name not in char_map or count <= 0:
                continue
            c = char_map[name]
            c.setdefault("combat_contrib", 0)
            c.setdefault("combat_contrib_by_session", {})
            c["combat_contrib"] += count
            c["combat_contrib_by_session"][str(sid)] = count
            total += count
            examples = "、".join(item.get("examples", [])[:2])
            print(f"  {name} +{count}（{examples}）")

        if total == 0:
            print("  本集無關鍵貢獻記錄")

        save_json(DATA / "character-stats.json", char_stats)
        if not args.rewrite:
            mark_processed(sid)
        print(f"  ✓\n")

    print("── 最終統計 ──")
    for name in CHAR_NAMES:
        c = char_map.get(name, {})
        print(f"  {name}：{c.get('combat_contrib', 0)} 次")

    save_json(DATA / "character-stats.json", char_stats)
    print("\n✓ 已儲存 character-stats.json")


if __name__ == "__main__":
    main()
