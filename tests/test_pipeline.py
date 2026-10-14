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
        w("session-stats.json", {"2": {}})
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


# ── 4. 金句說話者以原文標示為準（S35 Gemini 把影心猜成曹、S26 把「阿：」猜成曹）──
import gen_quote_by  # noqa: E402

def _sess(*lines):
    return {"content": [{"t": "p", "v": v} for v in lines]}

check("前綴全名", gen_quote_by.find_speaker_in_text("假屌他不帶走？", _sess("影心：「假屌他不帶走？」")), "影心")
check("前綴簡稱 阿：", gen_quote_by.find_speaker_in_text("在座各位都是垃圾，上吧！",
      _sess("曹：「靠杯啊」", "阿：「不然我在這裡一挑三啦。在座各位都是垃圾，上吧！」")), "阿斯代倫")
check("前綴帶描述", gen_quote_by.find_speaker_in_text("那邊潮濕啊，電一下很爽啊",
      _sess("影心毫無悔意：「那邊潮濕啊（濕潤狀態雙倍傷害），電一下很爽啊。」")), "影心")
check("後綴署名", gen_quote_by.find_speaker_in_text("你永遠知道哪個杯子上有洨。",
      _sess("「那是一種精神上的汙染，你永遠知道哪個杯子上有洨。」—— 阿斯代倫")), "阿斯代倫")
check("無標示回傳 None", gen_quote_by.find_speaker_in_text("台灣的所有水餃吊打日本所有水餃。",
      _sess("「台灣的所有水餃吊打日本所有水餃。」—— 關於餃子的堅持")), None)
check("兩處標示不同 → 歧義回傳 None", gen_quote_by.find_speaker_in_text("上吧",
      _sess("曹：「上吧」", "卡：「上吧」")), None)


# ── 5. 週測出題防呆 ──────────────────────────────────────────
import gen_quiz  # noqa: E402

_s = {"id": 9, "content": [{"t": "p", "v": "影心：「把卡拉克從屋頂往地面摔，所幸沒死，還有4滴血。」"}]}
_ok = {"q": "影心對卡拉克做了什麼？", "options": ["從屋頂往地面摔", "推下懸崖", "丟進河裡", "關進籠子"],
       "answer": 0, "source": "把卡拉克從屋頂往地面摔，所幸沒死"}
keep, drop = gen_quiz.validate_plot([
    _ok,
    {**_ok, "source": "原文沒有這句話喔喔喔喔"},
    {**_ok, "options": ["a", "a", "b", "c"]},
    {**_ok, "q": "游尚傑做了什麼？"},
    {**_ok, "answer": 4},
], _s)
check("情節題：只保留出處在原文、選項相異、無本名的題目", len(keep), 1)
check("情節題：丟棄原因各自標明", len(drop), 4)

_s2 = {"id": 32, "content": [{"t": "p", "v": "隊伍惦記著四人行願望，把好感度列為第一要務，還刻意不去找雙胞胎卓爾，當作驚喜。"}]}
check("情節題：錯誤選項用字取自原文 → 丟棄（S32 一題多解）",
      gen_quiz.distractor_from_text(["刻意不找卓爾", "將好感度列為第一要務", "送她禮物", "幫她報仇"], 0,
                                    "還刻意不去找雙胞胎卓爾", _s2), "將好感度列為第一要務")
check("情節題：錯誤選項是原文沒有的事 → 保留",
      gen_quiz.distractor_from_text(["刻意不找卓爾", "幫她買蛋糕", "送她禮物", "幫她報仇"], 0,
                                    "還刻意不去找雙胞胎卓爾", _s2), None)

_orig_call = gen_quiz.call_gemini
try:
    gen_quiz.call_gemini = lambda prompt: [{"i": 0, "ok": True}, {"i": 1, "ok": False, "reason": "選項C也成立"}]
    keep, drop = gen_quiz.verify_plot([_ok, _ok, _ok], _s)
    check("驗證：只保留明確判為合格的題目（不合格、未回覆都丟）", (len(keep), len(drop)), (1, 2))
finally:
    gen_quiz.call_gemini = _orig_call

_sess = [{"id": 1, "chapter": "第一章", "title": "T1", "content": []},
         {"id": 2, "chapter": "第二章", "title": "T2", "content": []}]
qs = gen_quiz.data_questions(
    _sess,
    {1: {"deaths": [{"char": "影心", "note": "被小貓咬死了"}, {"char": "卡拉克", "note": "墜落懸崖摔死"}]},
     2: {"deaths": [{"char": "曹", "note": "被小貓咬死了"}]}},
    [{"session": 1, "perp": "影心", "victim": "曹", "method": "閃電",
      "desc": "影心召雷劈向敵人，結果把曹一起電成焦炭，坑隊友不手軟。"},
     {"session": 2, "perp": "貓咕咕", "victim": "曹", "method": "火球", "desc": "太短"}])
check("資料題：只出死因與友傷（不出 MVP／誰說的／章名／里程碑）", {q["kind"] for q in qs}, {"death", "ff"})
check("資料題：題目不帶章節", any("章" in q["q"] for q in qs), False)
check("資料題：死因跨集重複（不同人）不出、全戰役唯一才出", [q["q"] for q in qs if q["kind"] == "death"],
      ["是誰「墜落懸崖摔死」？"])
ff = [q for q in qs if q["kind"] == "ff"]
check("資料題：友傷用事件描述並遮住加害者", (len(ff), "影心" in ff[0]["q"], "○○" in ff[0]["q"]), (1, False, True))
check("情節題：擋下考記憶的題型", bool(gen_quiz.BANNED_Q.search("「假屌他不帶走」是誰說的？")), True)

if FAILURES:
    print(f"❌ pipeline 測試失敗（{len(FAILURES)} 項）：")
    print("\n".join(FAILURES))
    sys.exit(1)
print("✅ pipeline 測試全部通過")
