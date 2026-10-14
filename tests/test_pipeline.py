#!/usr/bin/env python3
"""
pipeline 防呆回歸測試（不需 pytest，python3 tests/test_pipeline.py 直接跑）。

守護 S35 踩過的靜默失敗：
- Gemini 回傳 JSON 字串內含原始換行 → json.loads 嚴格模式整集失敗（故事章節缺失）
- update_stats 單集失敗只印警告 → sessions-raw 缺集，verify_data 卻全部通過
- index.html 版本號只看「index.html 有沒有改」→ 改了別行就漏遞增
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import bump_versions  # noqa: E402
import verify_data    # noqa: E402

FAILURES = []


def check(desc, actual, expected):
    if actual != expected:
        FAILURES.append(f"  ✗ {desc}: got {actual!r}, want {expected!r}")


# ── 1. Gemini JSON 解析一律寬鬆模式 ─────────────────────────
# 靜態掃描：解析 Gemini 輸出（regex 擷取後 json.loads）都要 strict=False
for py in sorted(ROOT.glob("*.py")):
    for i, line in enumerate(py.read_text("utf-8").splitlines(), 1):
        if re.search(r"json\.loads\(\w+\.group\(\)", line) and "strict=False" not in line:
            FAILURES.append(f"  ✗ {py.name}:{i} 解析 Gemini JSON 未加 strict=False")
raw = '{"title": "章", "text": "第一段\n\n第二段"}'   # 字串內含原始換行
try:
    check("寬鬆模式可解析原始換行", json.loads(raw, strict=False)["text"], "第一段\n\n第二段")
except json.JSONDecodeError as e:
    FAILURES.append(f"  ✗ 寬鬆模式解析失敗：{e}")


# ── 2. verify_data 攔下最新集缺萃取 / 缺故事 ─────────────────
def sync_issues(with_raw, with_story):
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "sessions-raw").mkdir()
        w = lambda name, d: (tmp / name).write_text(json.dumps(d, ensure_ascii=False), "utf-8")
        w("sessions.json", [{"id": 1, "content": [{"t": "p", "v": "x"}]},
                            {"id": 2, "content": [{"t": "p", "v": "y"}]}])
        w("roast-stats.json", {"highlights": [{"session": 2}]})
        w("awards.json", {"2": {}})
        w(".praised_processed.json", [1, 2])
        w(".combat_contrib_processed.json", [1, 2])
        w("story.json", {"chapters": [{"session_id": 1}] + ([{"session_id": 2}] if with_story else [])})
        if with_raw:
            w("sessions-raw/2.json", {})
        orig, verify_data.DATA = verify_data.DATA, tmp
        try:
            return verify_data.check_session_sync()
        finally:
            verify_data.DATA = orig
    finally:
        shutil.rmtree(tmp)

has = lambda issues, kw: any(kw in s for s in issues)
check("缺 sessions-raw 最新集 → 報錯", has(sync_issues(False, True), "未萃取"), True)
check("缺最新集故事 → 報錯", has(sync_issues(True, False), "故事集缺"), True)
check("資料齊全 → 無萃取/故事問題",
      [s for s in sync_issues(True, True) if "未萃取" in s or "故事集缺" in s], [])


# ── 3. bump_versions：逐一比對版本號 ────────────────────────
index_now = (ROOT / "index.html").read_text("utf-8")
for name, (pat, _) in bump_versions.TOKENS.items():
    check(f"index.html 含 {name} 版本號", bool(re.search(pat, index_now)), True)

def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)

repo = Path(tempfile.mkdtemp())
try:
    (repo / "data").mkdir()
    (repo / "index.html").write_text(
        '<meta name="data-version" content="1">\n<link href="style.css?v=3">\n'
        '<script src="app.js?v=5"></script>\n<link rel="icon" href="a.webp">\n', "utf-8")
    (repo / "app.js").write_text("1", "utf-8")
    (repo / "style.css").write_text("1", "utf-8")
    (repo / "data" / "awards.json").write_text("{}", "utf-8")
    git(repo, "init", "-q"); git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    orig = bump_versions.BASE, bump_versions.INDEX
    bump_versions.BASE, bump_versions.INDEX = repo, repo / "index.html"
    try:
        stale = lambda: sorted(n for n, _ in bump_versions.stale_tokens())
        check("無變更 → 無過時", stale(), [])
        (repo / "app.js").write_text("2", "utf-8")
        # 改了 index.html 的其他行（icon）不能被當成已遞增
        idx = repo / "index.html"
        idx.write_text(idx.read_text("utf-8").replace("a.webp", "b.png"), "utf-8")
        (repo / "data" / "sessions").mkdir()
        (repo / "data" / "sessions" / "2.json").write_text("{}", "utf-8")   # 未追蹤新檔
        check("app.js 改 + 新集 JSON → 兩者過時", stale(), ["app.js", "data-version"])
        with open(Path(tempfile.gettempdir()) / "bump_test.out", "w") as devnull:
            sys.stdout, saved = devnull, sys.stdout
            try:
                bump_versions.main()
            finally:
                sys.stdout = saved
        check("遞增後 → 無過時", stale(), [])
        txt = idx.read_text("utf-8")
        check("app.js 版本 5→6", "app.js?v=6" in txt, True)
        check("data-version 1→2", 'content="2"' in txt, True)
        check("style.css 未變更不遞增", "style.css?v=3" in txt, True)
    finally:
        bump_versions.BASE, bump_versions.INDEX = orig
finally:
    shutil.rmtree(repo)


if FAILURES:
    print(f"❌ pipeline 測試失敗（{len(FAILURES)} 項）：")
    print("\n".join(FAILURES))
    sys.exit(1)
print("✅ pipeline 測試全部通過")
