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

# 日誌常用的說話者寫法：「影心：」「影：」前綴，或「」—— 阿斯代倫」後綴
ALIASES = {'影心': '影心', '影': '影心', '阿斯代倫': '阿斯代倫', '阿斯': '阿斯代倫', '阿': '阿斯代倫',
           '曹': '曹', '卡拉克': '卡拉克', '卡': '卡拉克', '貓咕咕': '貓咕咕', '貓': '貓咕咕'}
_norm = lambda t: re.sub(r'[^\w]', '', t)


def find_speaker_in_text(quote, session):
    """在日誌原文找出金句所在行，從前綴/後綴標示判斷說話者；找不到或有歧義回傳 None。"""
    q = _norm(quote)
    if not q:
        return None
    hits = set()
    for item in session["content"]:
        v = item.get("v")
        if not isinstance(v, str) or "「" not in v:
            continue
        # 金句常被節錄或刪去括號註解，比對時容許原文較長
        if q not in _norm(re.sub(r'[（(][^）)]*[）)]', '', v)) and q not in _norm(v):
            continue
        head, _, rest = v.partition("「")
        tail = rest.rpartition("」")[2]
        m = re.search(r'(影心|阿斯代倫|阿斯|貓咕咕|卡拉克|影|阿|曹|卡|貓)[^「]{0,8}[：:]?\s*$', head)
        if not m:
            m = re.match(r'\s*[—\-–]+\s*(影心|阿斯代倫|貓咕咕|卡拉克|曹)', tail)
        if m:
            hits.add(ALIASES[m.group(1)])
    return hits.pop() if len(hits) == 1 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=int, default=None)
    parser.add_argument("--recheck", action="store_true",
                        help="已有 best_quote_by 的也用原文比對校正（不呼叫 Gemini）")
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
        session = sessions.get(sid)
        if not session or not session["content"]:
            continue

        # 原文有標示說話者就以原文為準（S35 曾被 Gemini 猜錯成曹，原文寫的是影心）
        found = find_speaker_in_text(aw["best_quote"], session)
        if aw.get("best_quote_by"):
            if args.recheck and found and found != aw["best_quote_by"]:
                print(f"  S{sid} 校正 {aw['best_quote_by']} → {found}（依原文）")
                aw["best_quote_by"] = found
                with open(AWARDS_F, "w") as f:
                    json.dump(awards, f, ensure_ascii=False, indent=2)
            elif not args.recheck:
                print(f"  S{sid} 已有 best_quote_by={aw['best_quote_by']}，跳過")
            continue
        if found:
            aw["best_quote_by"] = found
            print(f"  S{sid} → {found}（原文比對）")
            with open(AWARDS_F, "w") as f:
                json.dump(awards, f, ensure_ascii=False, indent=2)
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
