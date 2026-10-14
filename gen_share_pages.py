#!/usr/bin/env python3
"""
為每集生成靜態分享 stub 頁（s/{id}.html）：
含該集專屬 og:title / og:description（本集亮點）/ og:image，供 LINE/FB/Discord 抓預覽卡片，
載入後立即導回 SPA 的 #s{id}。純本地生成，不呼叫 Gemini。

用法：python3 gen_share_pages.py
"""

import html
import json
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "s"
SITE = "https://deromanx.github.io/bg3-journal"

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <meta property="og:type" content="article">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{site}/s/{id}.html">
  <meta property="og:image" content="{image}">
  <meta property="og:locale" content="zh_TW">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="robots" content="noindex">
  <link rel="canonical" href="{site}/#s{id}">
  <meta http-equiv="refresh" content="0;url=../#s{id}">
  <script>location.replace('../#s{id}');</script>
</head>
<body>
  <p>正在前往 <a href="../#s{id}">{title}</a>…</p>
</body>
</html>
"""


def first_image(sid: int) -> str:
    """該集第一張插圖；無插圖則用全站封面。"""
    img_dir = BASE_DIR / "data" / "images" / str(sid)
    if img_dir.is_dir():
        imgs = sorted(img_dir.glob("img_*.webp"))
        if imgs:
            return f"{SITE}/data/images/{sid}/{imgs[0].name}"
    return f"{SITE}/data/images/cover.webp"


DESC_MAX = 150


def describe(s: dict, awards: dict) -> str:
    """og:description：日期＋本集亮點（awards.json highlight）；無亮點時退回通用描述。"""
    date = s.get("dateDisplay", "")
    hl = (awards.get(str(s["id"])) or {}).get("highlight", "").strip()
    if not hl:
        return f"{date} — 《柏德之門3》TRPG 跑團冒險日誌".strip(" —")
    desc = f"{date}｜{hl}" if date else hl
    return desc if len(desc) <= DESC_MAX else desc[:DESC_MAX - 1] + "…"


# ── 週測分享頁 q/{YYYY}-W{WW}.html ───────────────────────────
# 分享成績的連結指向本週專屬頁，LINE 預覽卡才會顯示「第 N 週」而非網站首頁。
# 週數由前端計算、pipeline 不一定每週跑，所以從上線週起預先產生到兩年後。
QUIZ_DIR = BASE_DIR / "q"
QUIZ_START = date(2026, 10, 12)        # 週測上線週（2026-W42）的週一
QUIZ_AHEAD_WEEKS = 104
QUIZ_DESC = "每週 10 題，考劇情和隊友互坑的名場面。限時作答、越快越高分，來比比看誰最懂這團。"
QUIZ_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <meta property="og:type" content="website">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{site}/q/{key}.html">
  <meta property="og:image" content="{site}/data/images/quiz-og.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:locale" content="zh_TW">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="robots" content="noindex">
  <link rel="canonical" href="{site}/#quiz">
  <meta http-equiv="refresh" content="0;url=../#quiz">
  <script>location.replace('../#quiz');</script>
</head>
<body>
  <p>正在前往 <a href="../#quiz">{title}</a>…</p>
</body>
</html>
"""


def quiz_pages():
    QUIZ_DIR.mkdir(exist_ok=True)
    last = date.today() + timedelta(weeks=QUIZ_AHEAD_WEEKS)
    mon, count, total = QUIZ_START, 0, 0
    while mon <= last:
        y, w, _ = mon.isocalendar()
        sun = mon + timedelta(days=6)
        key = f"{y}-W{w:02d}"
        title = html.escape(f"柏德之門週測｜{y} 第 {w} 週（{mon.month}/{mon.day}–{sun.month}/{sun.day}）")
        page = QUIZ_TEMPLATE.format(title=title, desc=html.escape(QUIZ_DESC), site=SITE, key=key)
        out = QUIZ_DIR / f"{key}.html"
        if not out.exists() or out.read_text() != page:
            out.write_text(page)
            count += 1
        total += 1
        mon += timedelta(weeks=1)
    print(f"週測分享頁：共 {total} 週，更新 {count} 頁 → q/")


def main():
    meta = json.loads((BASE_DIR / "data" / "sessions-meta.json").read_text())
    awards_f = BASE_DIR / "data" / "awards.json"
    awards = json.loads(awards_f.read_text()) if awards_f.exists() else {}
    OUT_DIR.mkdir(exist_ok=True)
    count = 0
    for s in meta:
        if s.get("placeholder"):
            continue
        title = html.escape(f"{s['chapter']}・{s['title']}｜前進柏德之門")
        desc = html.escape(describe(s, awards))
        page = TEMPLATE.format(
            title=title, desc=desc, site=SITE, id=s["id"], image=first_image(s["id"])
        )
        out = OUT_DIR / f"{s['id']}.html"
        if not out.exists() or out.read_text() != page:
            out.write_text(page)
            count += 1
    print(f"分享頁：共 {sum(1 for s in meta if not s.get('placeholder'))} 集，更新 {count} 頁 → s/")
    quiz_pages()


if __name__ == "__main__":
    main()
