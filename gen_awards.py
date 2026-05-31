#!/usr/bin/env python3
"""
gen_awards.py — 為缺少戰報的集數補齊 MVP/金句/最慘時刻
並更新 character-stats.json 的 mvp_count 欄位
用法：python3 gen_awards.py
      python3 gen_awards.py --rewrite 7
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

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)


def gemini_awards(text, sid):
    prompt = f"""你是柏德之門3跑團日誌的分析員。仔細閱讀以下日誌，評選本集的戰報三項。

角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕

評選標準：
- MVP：本集表現最突出的角色（戰鬥表現、關鍵決策、搞笑貢獻均可）
- 最佳金句：最有趣、最有記憶點的一句話（原文引用）
- 最慘時刻：本集最慘、最丟臉或最惱人的事件描述（30字內）

跑團記錄（第{sid}集）：
{text}

請以純 JSON 格式回傳（不加說明文字或 markdown）：
{{
  "mvp": "角色名或空字串",
  "mvp_reason": "一句話說明（30字內）",
  "best_quote": "金句原文（不含引號符號）",
  "worst_moment": "最慘時刻描述（30字內）"
}}"""

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


def recompute_mvp_counts(awards, char_stats):
    char_map = {c["char"]: c for c in char_stats.get("characters", [])}
    for c in char_map.values():
        c["mvp_count"] = 0
    for entry in awards.values():
        mvp = entry.get("mvp", "")
        if mvp in char_map:
            char_map[mvp]["mvp_count"] = char_map[mvp].get("mvp_count", 0) + 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rewrite", type=int, metavar="SESSION_ID")
    args = parser.parse_args()

    sessions   = load_json(DATA / "sessions.json", [])
    awards     = load_json(DATA / "awards.json", {})
    char_stats = load_json(DATA / "character-stats.json", {"characters": []})

    if args.rewrite:
        to_process = [s for s in sessions if s["id"] == args.rewrite
                      and not s.get("placeholder") and s.get("content")]
        print(f"強制重跑第 {args.rewrite} 集\n")
    else:
        to_process = [s for s in sessions
                      if str(s["id"]) not in awards
                      and not s.get("placeholder") and s.get("content")]
        print(f"待補齊 {len(to_process)} 集\n")

    for session in to_process:
        sid = session["id"]
        print(f"S{sid}《{session['title']}》...")
        text   = session_to_text(session)
        result = gemini_awards(text, sid)
        if result is None:
            print("  ⚠ 失敗，跳過")
            continue

        entry = {k: v for k, v in result.items() if v}
        awards[str(sid)] = entry
        mvp = entry.get("mvp", "—")
        print(f"  MVP: {mvp}　金句: {entry.get('best_quote','')[:20]}...")
        save_json(DATA / "awards.json", awards)
        print(f"  ✓\n")

    recompute_mvp_counts(awards, char_stats)
    save_json(DATA / "character-stats.json", char_stats)

    print("── MVP 統計 ──")
    for name in CHAR_NAMES:
        c = next((c for c in char_stats["characters"] if c["char"] == name), {})
        print(f"  {name}：{c.get('mvp_count', 0)} 次")

    print("\n✓ 已儲存 awards.json 與 character-stats.json")


if __name__ == "__main__":
    main()
