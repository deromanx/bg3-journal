#!/usr/bin/env python3
"""
gen_char_summaries.py — 用 Gemini 全量重生成角色 ai_intro 與 death_narrative
輸出：data/character-stats.json（覆蓋 ai_intro / death_narrative 兩欄）
用法：python3 gen_char_summaries.py
"""

import json, subprocess, re
from pathlib import Path
from placeholders import GUIDE as PLACEHOLDER_GUIDE

from common import BASE, DATA, load_json, save_json

def extract_json_obj(text):
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None

def build_char_context(c, sessions, roast_stats, praise_stats):
    """整理角色摘要資料餵給 Gemini，避免輸入過大。"""
    lines = []

    # 基本資料
    lines.append(f"角色：{c['char']}（玩家：{c['player']}，職業：{c.get('class','')}）")

    # 統計數字
    deaths = c.get('deaths', 0)
    downed = c.get('downed', 0)
    mvp    = c.get('mvp_count', 0)
    duels  = c.get('duels', {})
    d_w, d_l, d_dr = duels.get('wins',0), duels.get('losses',0), duels.get('draws',0)
    lines.append(f"陣亡：{deaths} 次，倒地：{downed} 次，MVP：{mvp} 次")
    lines.append(f"決鬥戰績：{d_w} 勝 {d_l} 敗 {d_dr} 平")

    # 死亡紀錄
    death_notes = c.get('death_notes', [])
    if death_notes:
        lines.append("死亡記錄：" + "；".join(str(n) for n in death_notes[:10]))

    # 被靠北的事件（前 5 條）
    matrix = roast_stats.get('matrix', [])
    received_roasts = [r for r in matrix if r.get('to') == c['char']][:5]
    if received_roasts:
        snippets = []
        for r in received_roasts:
            snippets.append(f"{r.get('from','?')} 靠北：{r.get('desc','')[:40]}")
        lines.append("被靠北事件：" + "；".join(snippets))

    # 被稱讚的事件（前 3 條）
    praise_quotes = [q for q in praise_stats.get('quotes', []) if c['char'] in (q.get('to') or [])][:3]
    if praise_quotes:
        snippets = [q.get('quote','')[:40] for q in praise_quotes]
        lines.append("被稱讚：" + "；".join(snippets))

    # 集數標題（讓 Gemini 知道故事走到哪）
    titles = [f"S{s['id']}《{s['title']}》" for s in sessions if not s.get('placeholder')]
    lines.append("全集數：" + "、".join(titles))

    # 決鬥亮點（舊 detail，供參考）
    detail = duels.get('detail', '')
    if detail:
        lines.append("決鬥亮點（參考）：" + detail[:200])

    return "\n".join(lines)

def gemini_generate(char_name, context):
    prompt = f"""你是柏德之門3跑團日誌的文案撰寫員。根據以下角色資料，為這位角色撰寫兩段文字，以純JSON回傳。

角色資料：
{context}

{PLACEHOLDER_GUIDE}

要求：
1. ai_intro：60-100字，幽默、有個性。必須：①點出該角色在隊伍中的定位或特技、②提到至少一個具體的梗或事件、③末尾一句話點出性格。禁止使用「未嘗敗績」「全場第一」等可能過時的宣言。
2. death_narrative：40-70字，簡潔有諷刺感。依時間序描述該角色最有代表性的幾次死法。若死亡次數為0，寫「至今毫髮無傷，不知是實力還是運氣。」

回傳格式（JSON，不加說明）：
{{
  "ai_intro": "...",
  "death_narrative": "..."
}}"""

    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        print(f"  ⚠ Gemini 錯誤：{result.stderr[:200]}")
        return None

    obj = extract_json_obj(result.stdout.strip())
    if not obj:
        print(f"  ⚠ JSON 解析失敗，原始回應：{result.stdout[:300]}")
        return None
    return obj

def main():
    sessions    = load_json(DATA / "sessions.json", [])
    char_stats  = load_json(DATA / "character-stats.json", {"characters": []})
    roast_stats = load_json(DATA / "roast-stats.json", {})
    praise_stats = load_json(DATA / "praise-stats.json", {})

    sessions = [s for s in sessions if not s.get("placeholder") and s.get("content")]

    chars = char_stats.get("characters", [])
    print(f"共 {len(chars)} 位角色，{len(sessions)} 集資料\n")

    for c in chars:
        print(f"處理 {c['char']}...")
        context = build_char_context(c, sessions, roast_stats, praise_stats)
        result  = gemini_generate(c['char'], context)

        if not result:
            print(f"  ⚠ 跳過")
            continue

        intro = result.get("ai_intro", "").strip()
        narr  = result.get("death_narrative", "").strip()

        if intro:
            c["ai_intro"] = intro
            print(f"  ai_intro: {intro[:60]}...")
        if narr:
            c["death_narrative"] = narr
            print(f"  death_narrative: {narr[:60]}...")

        save_json(DATA / "character-stats.json", char_stats)

    print(f"\n✅ 完成，已存入 character-stats.json")

if __name__ == "__main__":
    main()
