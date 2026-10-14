#!/usr/bin/env python3
"""bump_versions.py — index.html 的 cache-busting 版本號管理（update_all.sh 與 verify_data.py 共用）。

GitHub Pages 對所有檔案固定 Cache-Control: max-age=600，無法自訂；
因此前端讀的每類檔案都在 index.html 掛一個版本號，內容變了就遞增：
  - style.css?v=N / app.js?v=N        → 對應檔案本身
  - <meta name="data-version" content=N> → 前端 fetch 的 data/*.json、data/sessions/、data/story/

判斷基準是「相對 HEAD：內容有變，但版本號跟 HEAD 一樣」才遞增，
不能只看 index.html 有沒有改（改了 icon 之類別的行就會誤判已遞增）。

用法：python3 bump_versions.py          遞增所有過時的版本號
      python3 bump_versions.py --check  只列出過時項目（exit 1 表示有）
"""
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
INDEX = BASE / "index.html"

# (index.html 內的版本號 regex, 判斷「內容有變」的路徑前綴)
TOKENS = {
    "style.css":    (r"(style\.css\?v=)(\d+)", ("style.css",)),
    "app.js":       (r"(app\.js\?v=)(\d+)", ("app.js",)),
    "data-version": (r'(<meta name="data-version" content=")(\d+)',
                     ("data/sessions-meta.json", "data/awards.json",
                      "data/character-stats.json", "data/ff-stats.json",
                      "data/milestones.json", "data/praise-stats.json",
                      "data/roast-stats.json", "data/session-stats.json",
                      "data/sessions/", "data/story/")),
}


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=BASE, timeout=10).stdout


def changed_paths():
    """相對 HEAD 有變更（含未追蹤新檔）的路徑。"""
    out = git("status", "--porcelain", "--untracked-files=all")
    return {line[3:].strip('"') for line in out.splitlines() if line}


def stale_tokens():
    head_index = git("show", "HEAD:index.html")
    cur_index = INDEX.read_text("utf-8")
    changed = changed_paths()
    stale = []
    for name, (pat, prefixes) in TOKENS.items():
        if not any(p.startswith(prefixes) for p in changed):
            continue
        cur = re.search(pat, cur_index)
        head = re.search(pat, head_index)
        if not cur:
            stale.append((name, "index.html 缺少此版本號"))
        elif head and cur.group(2) == head.group(2):
            stale.append((name, f"內容已變更但版本號仍為 {cur.group(2)}"))
    return stale


def main():
    stale = stale_tokens()
    if "--check" in sys.argv:
        for name, why in stale:
            print(f"{name}: {why}")
        return 1 if stale else 0
    text = INDEX.read_text("utf-8")
    for name, _ in stale:
        pat = TOKENS[name][0]
        text, n = re.subn(pat, lambda m: m.group(1) + str(int(m.group(2)) + 1), text, count=1)
        if n:
            print(f"🔄 {name} 有變更，已遞增 index.html 版本號")
    INDEX.write_text(text, "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
