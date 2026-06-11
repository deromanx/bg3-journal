#!/usr/bin/env python3
"""
為每集日誌生成本集亮點摘要，寫入 data/awards.json 的 highlight 欄位。
用法：python3 gen_highlights.py [--from N] [--session N]
"""

import json, subprocess, sys, argparse, re
from pathlib import Path

BASE = Path(__file__).parent
SESSIONS_FILE = BASE / "data" / "sessions.json"
AWARDS_FILE   = BASE / "data" / "awards.json"

def extract_text(content: list) -> str:
    """從 content items 提取純文字供 Gemini 閱讀"""
    lines = []
    for item in content:
        t = item["t"]
        if t == "img":
            continue
        prefix = {
            "h1": "【標題】", "h2": "【副標題】", "ai": "【AI點評】",
            "p": "", "li": "  • ", "li2": "    - ",
        }.get(t, "")
        lines.append(prefix + item["v"])
    return "\n".join(lines)

def call_gemini(prompt: str) -> str:
    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True, text=True,
        env={**__import__("os").environ, "NODE_OPTIONS": ""},
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    # Strip markdown fences if present
    out = result.stdout.strip()
    out = re.sub(r"^```.*?\n", "", out, flags=re.M)
    out = re.sub(r"\n?```$", "", out, flags=re.M)
    return out.strip()

def gen_highlight(session: dict) -> str:
    text = extract_text(session["content"])
    prompt = f"""以下是一份《柏德之門3》TRPG 桌遊日誌（{session['chapter']} {session['title']}），角色包含：影心、阿斯代倫、曹、卡拉克、貓咕咕。

請用 **繁體中文**，寫一段 2～3 句的亮點摘要（100 字以內），讓還沒看過這集的人快速判斷有沒有想看的梗或精彩橋段。語氣活潑幽默，重點放在最有趣的事件或名場面，不要列點，直接寫成一段話。

日誌內容：
{text[:3000]}
"""
    return call_gemini(prompt)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_n", type=int, default=1, help="從第 N 集開始（預設 1）")
    parser.add_argument("--session", type=int, default=None, help="只處理指定集數")
    args = parser.parse_args()

    with open(SESSIONS_FILE) as f:
        sessions = json.load(f)
    with open(AWARDS_FILE) as f:
        awards = json.load(f)

    for session in sessions:
        sid = session["id"]
        if args.session and sid != args.session:
            continue
        if not args.session and sid < args.from_n:
            continue
        if not session["content"]:
            continue

        key = str(sid)
        if key not in awards:
            awards[key] = {}

        # 已有 highlight 且非指定重跑時跳過
        if awards[key].get("highlight") and not args.session:
            print(f"  S{sid} 已有 highlight，跳過")
            continue

        print(f"  處理 {session['chapter']} {session['title']}...", end=" ", flush=True)
        try:
            highlight = gen_highlight(session)
            awards[key]["highlight"] = highlight
            print(f"✓ ({len(highlight)} 字)")
        except Exception as e:
            print(f"✗ {e}")
            continue

        with open(AWARDS_FILE, "w") as f:
            json.dump(awards, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 已更新 {AWARDS_FILE}")

if __name__ == "__main__":
    main()
