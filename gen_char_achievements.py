#!/usr/bin/env python3
"""
gen_char_achievements.py — 用 Gemini 全量重生成角色 achievements 欄位
輸出：data/character-stats.json（覆蓋 achievements 陣列）
用法：python3 gen_char_achievements.py
"""

import json, subprocess, re
from pathlib import Path
from placeholders import GUIDE as PLACEHOLDER_GUIDE

BASE = Path(__file__).parent
DATA = BASE / "data"
SESSIONS_RAW_DIR = DATA / "sessions-raw"


def load_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def extract_json_arr(text):
    m = re.search(r'\[[\s\S]*\]', text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


def build_char_context(c, sessions_meta, roast_stats, ff_stats, awards):
    lines = []
    lines.append(f"角色：{c['char']}（玩家：{c['player']}，職業：{c.get('class','')}）")

    deaths = c.get('deaths', 0)
    downed = c.get('downed', 0)
    mvp    = c.get('mvp_count', 0)
    duels  = c.get('duels', {})
    d_w, d_l, d_dr = duels.get('wins', 0), duels.get('losses', 0), duels.get('draws', 0)
    lines.append(f"陣亡：{deaths} 次，倒地：{downed} 次，MVP：{mvp} 次")
    lines.append(f"決鬥戰績：{d_w} 勝 {d_l} 敗 {d_dr} 平（共 {d_w+d_l+d_dr} 場）")

    death_notes = c.get('death_notes', [])
    if death_notes:
        lines.append("死亡記錄：" + "；".join(str(n) for n in death_notes))

    # 決鬥亮點（最近 5 集）
    highlights = duels.get('highlights', [])
    if highlights:
        recent = highlights[-5:]
        lines.append("近期決鬥亮點：" + "；".join(
            f"S{h['session_id']}：{h['text'][:60]}" for h in recent
        ))

    # MVP 場次
    mvp_sessions = [sid for sid, a in awards.items() if a.get('mvp') == c['char']]
    if mvp_sessions:
        lines.append(f"MVP 場次：S{'、S'.join(mvp_sessions)}")

    # 靠北統計（前 5 對）
    roast_matrix = roast_stats.get('matrix', [])
    sent   = sorted([r for r in roast_matrix if r.get('from') == c['char']],
                    key=lambda r: -r['count'])[:3]
    recv   = sorted([r for r in roast_matrix if r.get('to')   == c['char']],
                    key=lambda r: -r['count'])[:3]
    if sent:
        lines.append("最愛靠北：" + "、".join(f"{r['to']}（{r['count']}次）" for r in sent))
    if recv:
        lines.append("最常被靠北：" + "、".join(f"{r['from']}（{r['count']}次）" for r in recv))

    # 友軍傷害
    ff_incidents = ff_stats.get('incidents', [])
    ff_perp  = [i for i in ff_incidents if i.get('perp')   == c['char']]
    ff_victim= [i for i in ff_incidents if i.get('victim') == c['char']]
    if ff_perp:
        lines.append(f"友軍傷害（施暴）：{len(ff_perp)} 次")
    if ff_victim:
        lines.append(f"友軍傷害（受害）：{len(ff_victim)} 次")

    # 集數概覽
    titles = [f"S{s['id']}《{s['title']}》" for s in sessions_meta if not s.get('placeholder')]
    lines.append("全集數：" + "、".join(titles))

    return "\n".join(lines)


def gemini_generate(char_name, context):
    prompt = f"""你是柏德之門3跑團日誌的文案撰寫員。根據以下角色資料，為這位角色設計 3 個「成就」徽章，以純JSON陣列回傳。

角色資料：
{context}

{PLACEHOLDER_GUIDE}

成就設計要求：
1. 每個成就包含：icon（單一emoji）、name（6-10字的幽默稱號）、desc（30-60字，幽默有梗，必須引用具體事件）
2. 三個成就應涵蓋不同面向（例如：戰鬥特色、人設梗、特定代表事件）
3. 累計統計數字一律用上述佔位符（如 {{deaths}}、{{mvp}}），不要寫實際數字
4. 禁止出現「未嘗敗績」「全場第一」等可能因集數增加而過時的宣告
5. 如果有決鬥敗績，禁止說「不敗」

回傳格式（純JSON陣列，不加說明）：
[
  {{"icon": "emoji", "name": "成就名稱", "desc": "成就描述"}},
  {{"icon": "emoji", "name": "成就名稱", "desc": "成就描述"}},
  {{"icon": "emoji", "name": "成就名稱", "desc": "成就描述"}}
]"""

    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        print(f"  ⚠ Gemini 錯誤：{result.stderr[:200]}")
        return None

    arr = extract_json_arr(result.stdout.strip())
    if not arr:
        print(f"  ⚠ JSON 解析失敗，原始回應：{result.stdout[:300]}")
        return None
    return arr


def main():
    sessions_meta = load_json(DATA / "sessions-meta.json", [])
    char_stats    = load_json(DATA / "character-stats.json", {"characters": []})
    roast_stats   = load_json(DATA / "roast-stats.json", {})
    ff_stats      = load_json(DATA / "ff-stats.json", {})
    awards        = load_json(DATA / "awards.json", {})

    chars = char_stats.get("characters", [])
    print(f"共 {len(chars)} 位角色，{len([s for s in sessions_meta if not s.get('placeholder')])} 集資料\n")

    for c in chars:
        print(f"處理 {c['char']}...")
        context = build_char_context(c, sessions_meta, roast_stats, ff_stats, awards)
        result  = gemini_generate(c['char'], context)

        if not result:
            print(f"  ⚠ 跳過\n")
            continue

        # 驗證格式
        valid = [a for a in result if a.get('icon') and a.get('name') and a.get('desc')]
        if len(valid) < 3:
            print(f"  ⚠ 回傳條數不足（{len(valid)} 條），跳過\n")
            continue

        c["achievements"] = valid[:3]
        for a in valid[:3]:
            print(f"  {a['icon']} {a['name']}")

        save_json(DATA / "character-stats.json", char_stats)
        print()

    print("✅ 完成，已存入 character-stats.json")


if __name__ == "__main__":
    main()
