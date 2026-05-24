#!/usr/bin/env python3
"""
為 awards.json 每集的 best_quote 補上說話者（best_quote_by）。
用法：python3 gen_quote_by.py [--session N]
"""

import json, subprocess, os, re, argparse
from pathlib import Path

BASE        = Path(__file__).parent
SESSIONS_F  = BASE / "data" / "sessions.json"
AWARDS_F    = BASE / "data" / "awards.json"
CHARS       = ['影心', '阿斯代倫', '曹', '卡拉克', '貓咕咕']

def call_gemini(prompt):
    r = subprocess.run(["gemini", "-p", prompt], capture_output=True, text=True,
                       env={**os.environ, "NODE_OPTIONS": ""})
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()

def extract_text(content):
    lines = []
    for item in content:
        if item["t"] == "img": continue
        lines.append(item["v"])
    return "\n".join(lines)[:3000]

def guess_speaker(quote, session):
    text = extract_text(session["content"])
    char_list = "、".join(CHARS)
    prompt = f"""以下是《柏德之門3》TRPG 日誌第{session['id']}集的部分內容，角色：{char_list}。

請判斷這句話是誰說的，只回答角色名（從 {char_list} 中選一個），不要解釋：

「{quote}」

日誌節錄：
{text}
"""
    ans = call_gemini(prompt).strip()
    # 擷取第一個出現的角色名
    for c in CHARS:
        if c in ans:
            return c
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=int, default=None)
    args = parser.parse_args()

    with open(SESSIONS_F) as f:
        sessions = {s["id"]: s for s in json.load(f)}
    with open(AWARDS_F) as f:
        awards = json.load(f)

    for sid_str, aw in sorted(awards.items(), key=lambda x: int(x[0])):
        sid = int(sid_str)
        if args.session and sid != args.session:
            continue
        if not aw.get("best_quote"):
            continue
        if aw.get("best_quote_by"):
            print(f"  S{sid} 已有 best_quote_by={aw['best_quote_by']}，跳過")
            continue

        session = sessions.get(sid)
        if not session or not session["content"]:
            continue

        print(f"  S{sid} 判斷說話者…", end=" ", flush=True)
        try:
            speaker = guess_speaker(aw["best_quote"], session)
            if speaker:
                aw["best_quote_by"] = speaker
                print(f"→ {speaker}")
            else:
                print("→ 無法判斷")
        except Exception as e:
            print(f"✗ {e}")
            continue

        with open(AWARDS_F, "w") as f:
            json.dump(awards, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 完成")

if __name__ == "__main__":
    main()
