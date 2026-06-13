#!/usr/bin/env python3
"""
placeholders.py — 文案統計佔位符的單一來源

AI 生成的 prose（ai_intro / death_narrative / achievements）一律用佔位符代替
累計統計數字，前端 app.js 渲染時即時注入真實值，數字永遠同步、不脫鉤。

三方須一致：
  - 本檔（語彙定義 + 給 Gemini 的指引）
  - gen_char_summaries.py / gen_char_achievements.py（prompt 引用 GUIDE）
  - app.js computeCharNumbers()（前端注入，key 必須對應）
  - verify_data.py（偵測殘留裸數字）
"""

# 佔位符 → 中文說明。key 必須與 app.js computeCharNumbers() 回傳的 key 一致。
PLACEHOLDERS = {
    "deaths":     "陣亡次數",
    "downed":     "倒地次數",
    "wins":       "決鬥勝場",
    "losses":     "決鬥敗場",
    "draws":      "決鬥平場",
    "mvp":        "MVP 次數",
    "ff_perp":    "友軍傷害（施暴）次數",
    "ff_victim":  "友軍傷害（受害）次數",
    "roast_from": "主動靠北總次數",
    "roast_to":   "被靠北總次數",
}

# 餵給 Gemini 的指引（兩支 gen 腳本的 prompt 都附上這段）
GUIDE = (
    "【數字佔位符規則｜務必遵守】\n"
    "凡是下列「累計統計數字」，一律用花括號佔位符代替，絕對不要寫實際數字：\n"
    + "\n".join(f"  {{{k}}} = {v}" for k, v in PLACEHOLDERS.items())
    + "\n範例：「累計{deaths}次陣亡」「{wins}勝{losses}敗{draws}平」「{mvp}次MVP」"
    "「施暴友軍傷害{ff_perp}次」「被靠北{roast_to}次」。\n"
    "例外（維持實際數字，不要用佔位符）：集數編號（如 S20、第10集）、"
    "單次傷害數值（如 163 點）、對特定某人的配對靠北次數（如「對曹靠北15次」）。"
)
