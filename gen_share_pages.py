#!/usr/bin/env python3
"""
為每集生成靜態分享 stub 頁（s/{id}.html）：
含該集專屬 og:title / og:image，供 LINE/FB/Discord 抓預覽卡片，
載入後立即導回 SPA 的 #s{id}。純本地生成，不呼叫 Gemini。

用法：python3 gen_share_pages.py
"""

import html
import json
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


def main():
    meta = json.loads((BASE_DIR / "data" / "sessions-meta.json").read_text())
    OUT_DIR.mkdir(exist_ok=True)
    count = 0
    for s in meta:
        if s.get("placeholder"):
            continue
        title = html.escape(f"{s['chapter']}・{s['title']}｜前進柏德之門")
        desc = html.escape(
            f"{s.get('dateDisplay', '')} — 《柏德之門3》TRPG 跑團冒險日誌".strip(" —")
        )
        page = TEMPLATE.format(
            title=title, desc=desc, site=SITE, id=s["id"], image=first_image(s["id"])
        )
        out = OUT_DIR / f"{s['id']}.html"
        if not out.exists() or out.read_text() != page:
            out.write_text(page)
            count += 1
    print(f"分享頁：共 {sum(1 for s in meta if not s.get('placeholder'))} 集，更新 {count} 頁 → s/")


if __name__ == "__main__":
    main()
