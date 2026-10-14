#!/usr/bin/env python3
"""
每集數據摘要（data/session-stats.json）：日誌頁「本集戰報」下方的數字列用。

單集頁原本只有 MVP／金句／最慘時刻，陣亡、決鬥、靠北、稱讚、友傷的逐集數字
散在統計頁的大 JSON 裡；這裡預先彙整成一個小檔，日誌頁只抓這個（數 KB），
不必為了幾個數字載入整份統計。純本地生成，不呼叫 Gemini。

用法：python3 gen_session_stats.py
"""

from collections import Counter

from common import DATA, load_json, save_json


def as_list(v):
    return v if isinstance(v, list) else [v] if v else []


def main():
    meta = load_json(DATA / "sessions-meta.json", [])
    roast = load_json(DATA / "roast-stats.json", {})
    praise = load_json(DATA / "praise-stats.json", {})
    ff = load_json(DATA / "ff-stats.json", {})

    # 靠北／稱讚以「發話者 × 對象」配對計次，與統計頁的 total（415/210…）同口徑
    def pair_count_by_session(items):
        c = Counter()
        for q in items:
            c[q.get("session")] += len(as_list(q.get("from"))) * len(as_list(q.get("to")))
        return c
    roasts = pair_count_by_session(roast.get("quotes") or [])
    praises = pair_count_by_session(praise.get("quotes") or [])
    ffs = Counter(i.get("session") for i in ff.get("incidents", []))

    out = {}
    for s in meta:
        sid = s["id"]
        if s.get("placeholder"):
            continue
        raw = load_json(DATA / "sessions-raw" / f"{sid}.json", None)
        if raw is None:
            continue   # 尚未萃取（verify_data 會另外報錯）
        deaths = [d for d in raw.get("deaths", []) if not d.get("is_downed")]
        downed = [d for d in raw.get("deaths", []) if d.get("is_downed")]
        by_char = Counter(d.get("char") for d in deaths + downed if d.get("char"))
        duels = [
            {"draw": True, "chars": [d.get("winner"), d.get("loser")]} if d.get("draw")
            else {"winner": d.get("winner"), "loser": d.get("loser")}
            for d in raw.get("duels", [])
        ]
        out[str(sid)] = {
            "deaths": len(deaths),
            "downed": len(downed),
            "fallen_by": dict(by_char.most_common()),
            "duels": duels,
            "roasts": roasts.get(sid, 0),
            "praises": praises.get(sid, 0),
            "ff": ffs.get(sid, 0),
        }

    save_json(DATA / "session-stats.json", out)
    print(f"每集數據摘要：{len(out)} 集 → data/session-stats.json")


if __name__ == "__main__":
    main()
