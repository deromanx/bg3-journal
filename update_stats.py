#!/usr/bin/env python3
"""
update_stats.py — 分析新集數，同步更新統計 JSON
用法：python3 update_stats.py              # 處理所有新集數
      python3 update_stats.py --reprocess 19  # 重新處理指定集數
"""

import json, subprocess, sys, re, argparse
from pathlib import Path

BASE = Path(__file__).parent
DATA = BASE / "data"
PROCESSED_FILE = DATA / ".stats_processed.json"

CHAR_NAMES = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]


# ── 工具函式 ────────────────────────────────────────────────────
def load_json(path, default):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return default

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def get_processed_ids():
    return set(load_json(PROCESSED_FILE, []))

def mark_processed(sid):
    ids = get_processed_ids()
    ids.add(sid)
    save_json(PROCESSED_FILE, sorted(ids))

def session_to_text(session):
    lines = [f"集數：{session['chapter']} 《{session['title']}》"]
    for item in session.get("content", []):
        if item["t"] != "img":
            lines.append(item["v"])
    return "\n".join(lines)


# ── Gemini 分析 ─────────────────────────────────────────────────
def gemini_analyze(text):
    prompt = f"""你是柏德之門3跑團日誌的數據分析員。分析以下日誌並以純JSON格式回傳（不加任何說明文字或markdown）。

日誌內容：
{text}

回傳格式（所有欄位必填，無資料則用空陣列）：
{{
  "awards": {{
    "mvp": "角色名（只能是：影心/阿斯代倫/曹/卡拉克/貓咕咕）或空字串",
    "mvp_reason": "一句話說明原因",
    "best_quote": "本集最佳金句原文（不含引號符號）",
    "worst_moment": "最慘時刻描述"
  }},
  "deaths": [
    {{"char": "角色名", "note": "死亡簡述（10字內）", "is_downed": false}}
  ],
  "duels": [
    {{"winner": "角色名", "loser": "角色名", "draw": false}}
  ],
  "duel_highlights": [
    "本集決鬥摘要（例：S19 曹以沉默戒指廢掉影心後爆擊獲勝）；只描述本集發生的事，禁止出現跨集累積戰績的宣告句，例如「全場未嘗敗績」、「決鬥霸主」等"
  ],
  "roasts": [
    {{"from": "角色名或角色名陣列（多人靠北同一人時用陣列）", "to": "角色名或角色名陣列（靠北對象多人時用陣列）", "count": 1, "desc": "事件描述（50-80字，含前因後果）"}}
  ],
  "milestones": [
    {{"type": "boss或location或achievement或death或item或custom", "icon": "單一emoji", "title": "里程碑標題（10字內）", "desc": "描述（30字內）"}}
  ]
}}

規則：
- 角色名只能是：影心、阿斯代倫、曹、卡拉克、貓咕咕
- deaths 中 is_downed=true 表示倒地後被救起；false 表示真正陣亡（需要復活捲軸或在營地復活）
- duels 只記錄玩家角色之間的 PvP 決鬥，不含對 NPC 或怪物的戰鬥
- 平局時 draw=true，winner 和 loser 填任一方即可
- milestones 只記錄本集最重要的 1-3 件大事"""

    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True, timeout=600
    )

    if result.returncode != 0:
        print(f"  ⚠ Gemini 錯誤：{result.stderr[:300]}")
        return None

    output = result.stdout.strip()
    # 嘗試從回應中取出 JSON
    json_match = re.search(r'\{[\s\S]*\}', output)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            print(f"  ⚠ JSON 解析失敗：{e}")
            print(f"  Gemini 原始回應：{output[:400]}")
    else:
        print(f"  ⚠ 找不到 JSON 結構，Gemini 原始回應：{output[:400]}")
    return None


# ── 更新各 JSON ─────────────────────────────────────────────────
def update_character_stats(char_stats, result, sid):
    chars = char_stats.get("characters", [])
    char_map = {c["char"]: c for c in chars}

    # 陣亡 / 倒地
    for death in result.get("deaths", []):
        name = death.get("char", "")
        if name not in char_map:
            continue
        c = char_map[name]
        note = f"第{sid}集 {death.get('note', '')}"
        if death.get("is_downed"):
            c["downed"] = c.get("downed", 0) + 1
        else:
            c["deaths"] = c.get("deaths", 0) + 1
            c.setdefault("death_notes", []).append(note)

    # 決鬥個人統計
    matchups = char_stats.get("matchups", [])
    for duel in result.get("duels", []):
        winner = duel.get("winner", "")
        loser  = duel.get("loser", "")
        draw   = duel.get("draw", False)
        if winner not in char_map or loser not in char_map:
            continue

        if draw:
            char_map[winner]["duels"]["draws"] = char_map[winner]["duels"].get("draws", 0) + 1
            char_map[loser]["duels"]["draws"]  = char_map[loser]["duels"].get("draws", 0) + 1
        else:
            char_map[winner]["duels"]["wins"]   = char_map[winner]["duels"].get("wins", 0) + 1
            char_map[loser]["duels"]["losses"]  = char_map[loser]["duels"].get("losses", 0) + 1

        # 更新 matchups 矩陣
        pair_key = tuple(sorted([winner, loser]))
        existing = next(
            (m for m in matchups if tuple(sorted(m["chars"])) == pair_key), None
        )
        if existing is None:
            existing = {"chars": [winner, loser], "wins": [0, 0], "draws": 0}
            matchups.append(existing)

        if draw:
            existing["draws"] = existing.get("draws", 0) + 1
        else:
            idx = 0 if existing["chars"][0] == winner else 1
            existing["wins"][idx] += 1

    # 將本集決鬥亮點追加進 detail 字串（每角色只加一次）
    highlights = result.get("duel_highlights", [])
    if highlights:
        additions = "；".join(highlights)
        involved = set()
        for duel in result.get("duels", []):
            for name in [duel.get("winner"), duel.get("loser")]:
                if name and name in char_map:
                    involved.add(name)
        for name in involved:
            c = char_map[name]
            existing_detail = c["duels"].get("detail", "")
            c["duels"]["detail"] = (existing_detail + "；" + additions).lstrip("；")

    char_stats["matchups"] = matchups
    return char_stats


def update_awards(awards, result, sid):
    a = result.get("awards", {})
    entry = {k: v for k, v in a.items() if v}
    if entry:
        awards[str(sid)] = entry
    return awards


def update_milestones(milestones, result, sid, session):
    for m in result.get("milestones", []):
        milestones.append({
            "type":       m.get("type", "custom"),
            "icon":       m.get("icon", "✦"),
            "title":      m.get("title", ""),
            "desc":       m.get("desc", ""),
            "date":       session.get("date", ""),
            "session_id": sid,
        })
    return milestones


def as_list(v):
    return v if isinstance(v, list) else [v]

def update_roast_stats(roast_stats, result, sid):
    matrix     = roast_stats.get("matrix", [])
    highlights = roast_stats.get("highlights", [])
    quotes     = roast_stats.get("quotes", [])

    for roast in result.get("roasts", []):
        frm_raw = roast.get("from", "")
        to_raw  = roast.get("to", "")
        count   = roast.get("count", 1)
        desc    = roast.get("desc", "")
        frm_list = [n for n in as_list(frm_raw) if n in CHAR_NAMES]
        to_list  = [n for n in as_list(to_raw)  if n in CHAR_NAMES]
        if not frm_list or not to_list:
            continue

        # matrix 展開所有 from×to 組合
        for frm in frm_list:
            for to in to_list:
                existing = next((r for r in matrix if r["from"] == frm and r["to"] == to), None)
                if existing:
                    existing["count"] += count
                else:
                    matrix.append({"from": frm, "to": to, "count": count})

        # quotes 保留原始陣列格式
        from_val = frm_list[0] if len(frm_list) == 1 else frm_list
        to_val   = to_list[0]  if len(to_list)  == 1 else to_list
        if desc:
            quotes.append({"session": sid, "from": from_val, "to": to_val, "desc": desc})
            frm_label = "、".join(frm_list)
            to_label  = "、".join(to_list)
            highlights.append({"session": sid, "desc": f"{frm_label}靠北{to_label}：{desc}"})

    roast_stats["matrix"]     = matrix
    roast_stats["highlights"] = highlights
    roast_stats["quotes"]     = quotes
    roast_stats["total"]      = sum(r["count"] for r in matrix)
    return roast_stats


# ── 故事生成 ────────────────────────────────────────────────
def gemini_story(session, prev_chapters):
    """以喬治馬丁風格將跑團紀錄改寫成一章奇幻小說散文。"""
    text = session_to_text(session)
    sid  = session["id"]

    prev_ctx = ""
    if prev_chapters:
        summaries = "\n".join(
            f"- {ch['title']}（第{ch['session_id']}集）"
            for ch in prev_chapters[-3:]
        )
        prev_ctx = f"\n\n前幾章已發生：\n{summaries}\n請在行文中保持與前章的連貫感。"

    prompt = f"""你是一位以喬治·馬丁（George R.R. Martin）風格著稱的奇幻小說家。
請將以下柏德之門3跑團記錄，改寫成一章奇幻小說（繁體中文，約1000-1500字）。

要求：
- 第三人稱敘事；史詩氣氛；豐富的環境描寫與感官細節
- 角色名保留：影心、阿斯代倫、曹、卡拉克、貓咕咕
- 徹底移除遊戲術語（HP、AC、法術欄、擲骰、命中率、技能等），改用敘事語言
- 保留真實發生的事件，但以散文奇幻風格呈現
- 章節開頭一句強烈的環境或氛圍描寫
- 包含角色的內心戲與奇幻化後的對話
- 結尾留有餘韻，帶出下一步的懸念{prev_ctx}

跑團記錄（第{sid}集 《{session['title']}》）：
{text}

請以純 JSON 格式回傳（不加說明文字或 markdown）：
{{"title": "本章標題（10字內，文學風格）", "text": "小說正文（純文字，段落以空行分隔）"}}"""

    # 長逐字稿生成 1500 字小說偶爾很慢；拉長 timeout 並重試，超時不讓整個 script crash
    for attempt in range(1, 3):
        try:
            result = subprocess.run(
                ["gemini", "-p", prompt],
                capture_output=True, text=True, timeout=600
            )
        except subprocess.TimeoutExpired:
            print(f"  ⚠ 故事生成超時（第 {attempt}/2 次）")
            continue
        if result.returncode != 0:
            print(f"  ⚠ Gemini 錯誤：{result.stderr[:200]}")
            return None
        output = result.stdout.strip()
        json_match = re.search(r'\{[\s\S]*\}', output)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        print(f"  ⚠ 故事 JSON 解析失敗（第 {attempt}/2 次），原始回應：{output[:200]}")
    return None


def update_story(story, session):
    chapters = story.get("chapters", [])
    sid = session["id"]
    # 跳過已生成的章節
    if any(ch["session_id"] == sid for ch in chapters):
        return story
    result = gemini_story(session, chapters)
    if result and result.get("text"):
        chapters.append({
            "session_id": sid,
            "title":      result.get("title", session["title"]),
            "text":       result["text"],
        })
        story["chapters"] = sorted(chapters, key=lambda c: c["session_id"])
    return story


# ── 主程式 ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reprocess", type=int, metavar="SESSION_ID",
                        help="強制重新處理指定集數")
    args = parser.parse_args()

    sessions    = load_json(DATA / "sessions.json", [])
    char_stats  = load_json(DATA / "character-stats.json", {"characters": []})
    awards      = load_json(DATA / "awards.json", {})
    milestones  = load_json(DATA / "milestones.json", [])
    roast_stats = load_json(DATA / "roast-stats.json",
                            {"matrix": [], "highlights": [], "total": 0})
    story       = load_json(DATA / "story.json", {"chapters": []})

    processed = get_processed_ids()

    if args.reprocess:
        target = next((s for s in sessions if s["id"] == args.reprocess), None)
        if not target:
            print(f"❌ 找不到第 {args.reprocess} 集")
            sys.exit(1)
        to_process = [target]
        print(f"🔄 重新處理第 {args.reprocess} 集\n")
    else:
        to_process = [
            s for s in sessions
            if s["id"] not in processed and not s.get("placeholder")
               and s.get("content")
        ]

    if not to_process:
        print("✓ 沒有新集數需要處理")
        return

    print(f"發現 {len(to_process)} 集待處理...\n")
    stat_done = []  # 統計成功的集數，稍後生成故事

    # ── 階段一：統計分析（穩定，先處理並落盤）──
    for session in to_process:
        sid = session["id"]
        print(f"📖 {session['chapter']} 《{session['title']}》")

        text = session_to_text(session)
        result = gemini_analyze(text)
        if not result:
            print("  ⚠ 分析失敗，跳過\n")
            continue

        # 印出摘要
        deaths = result.get("deaths", [])
        duels  = result.get("duels", [])
        ms     = result.get("milestones", [])
        print(f"  陣亡/倒地：{len(deaths)} 筆  決鬥：{len(duels)} 場  里程碑：{len(ms)} 條")

        char_stats  = update_character_stats(char_stats, result, sid)
        awards      = update_awards(awards, result, sid)
        milestones  = update_milestones(milestones, result, sid, session)
        roast_stats = update_roast_stats(roast_stats, result, sid)

        if not args.reprocess:
            mark_processed(sid)
        stat_done.append(session)
        print(f"  ✓ 統計完成\n")

    if not stat_done:
        print("✓ 無變更")
        return

    # 統計先落盤：即使後面故事生成出意外，這部分也不會回滾、不需重算
    save_json(DATA / "character-stats.json", char_stats)
    save_json(DATA / "awards.json",           awards)
    save_json(DATA / "milestones.json",       milestones)
    save_json(DATA / "roast-stats.json",      roast_stats)
    print("✓ 統計 JSON 已儲存\n")

    # ── 階段二：故事生成（慢且偶爾失敗，獨立處理；每集生成後立即存檔）──
    failed = []
    for session in stat_done:
        print(f"✍ 生成第 {session['id']} 集故事章節...")
        before = len(story.get("chapters", []))
        story = update_story(story, session)
        if len(story.get("chapters", [])) > before:
            save_json(DATA / "story.json", story)
            print("  ✓ 已存")
        else:
            failed.append(session["id"])
            print("  ⚠ 故事生成失敗")

    if failed:
        print(f"\n⚠ 第 {failed} 集故事缺失——統計已存妥，稍後執行 "
              f"`python3 gen_story.py` 即可補齊（不影響其他資料）")
    else:
        print("\n✓ 所有故事章節已儲存")

if __name__ == "__main__":
    main()
