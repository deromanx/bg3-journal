#!/usr/bin/env python3
"""
verify_data.py — 資料一致性驗證器（pipeline 最後關卡）

兩類檢查：
  A. 結構一致性：個人統計 vs 衍生來源（matchup 矩陣、awards、by_session 合計）
  B. 文案脫鉤：AI 生成的 prose（ai_intro / death_narrative / achievements）
     內嵌的累計數字，是否與真實統計一致。

設計動機：achievements、死亡敘述等由 Gemini 生成的文字會把「9次MVP」「14次陣亡」
這類累計數字寫死在句子裡。每次全量 rebuild 改變統計後，這些數字就過時；Gemini
重生成時也可能憑 context 幻覺出錯誤數字。本腳本同時攔截這兩種情況。

用法：
  python3 verify_data.py            # 印報告，有問題 exit 1
  python3 verify_data.py --warn     # 只警告，永遠 exit 0（pipeline 用，不阻斷）
"""

import json, re, sys, argparse
from pathlib import Path
from collections import defaultdict

DATA = Path(__file__).parent / "data"
CHARS = ["影心", "阿斯代倫", "曹", "卡拉克", "貓咕咕"]


def load(name, default):
    p = DATA / name
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def as_list(v):
    return v if isinstance(v, list) else [v]


def ground_truth():
    """從各資料檔算出每位角色的權威統計數字。"""
    cs = load("character-stats.json", {"characters": []})
    aw = load("awards.json", {})
    roast = load("roast-stats.json", {})
    ff = load("ff-stats.json", {})

    gt = {c["char"]: {} for c in cs["characters"]}

    # MVP：以 awards.json 為準（gen_awards.py 的權威來源）
    mvp = defaultdict(int)
    for e in aw.values():
        if e.get("mvp") in gt:
            mvp[e["mvp"]] += 1

    # 靠北：pairwise 與 from/to 合計
    rfrom = defaultdict(int)
    rto = defaultdict(int)
    rpairs = defaultdict(set)   # 每位角色涉及的所有配對數字（from 或 to 任一方）
    for m in roast.get("matrix", []):
        rfrom[m["from"]] += m["count"]
        rto[m["to"]] += m["count"]
        rpairs[m["from"]].add(m["count"])
        rpairs[m["to"]].add(m["count"])

    # 友軍傷害
    ff_perp = defaultdict(int)
    ff_victim = defaultdict(int)
    for i in ff.get("incidents", []):
        ff_perp[i.get("perp")] += 1
        ff_victim[i.get("victim")] += 1

    for c in cs["characters"]:
        n = c["char"]
        d = c.get("duels", {})
        gt[n] = {
            "deaths": c.get("deaths", 0),
            "downed": c.get("downed", 0),
            "wins": d.get("wins", 0),
            "losses": d.get("losses", 0),
            "draws": d.get("draws", 0),
            "mvp": mvp[n],
            "ff_perp": ff_perp[n],
            "ff_victim": ff_victim[n],
            "roast_from": rfrom[n],
            "roast_to": rto[n],
            # 靠北合法集合：主動/被動合計 + 所有相關配對值（容許 total 或 pairwise 措辭）
            "roast_ok": {rfrom[n], rto[n]} | rpairs[n],
        }
    return cs, gt


# ── A. 結構一致性 ──────────────────────────────────────────────
def check_structural(cs, gt):
    issues = []
    aw = load("awards.json", {})
    matchups = cs.get("matchups", [])

    # mvp_count vs awards.json
    for c in cs["characters"]:
        n = c["char"]
        if c.get("mvp_count", 0) != gt[n]["mvp"]:
            issues.append(f"{n}: mvp_count={c.get('mvp_count')} 但 awards.json 實際為 {gt[n]['mvp']}")

    # 決鬥個人 vs matchup 推算
    dw = defaultdict(int); dl = defaultdict(int); dd = defaultdict(int)
    for m in matchups:
        c0, c1 = m["chars"]; w0, w1 = m["wins"]; dr = m.get("draws", 0)
        dw[c0] += w0; dl[c0] += w1; dd[c0] += dr
        dw[c1] += w1; dl[c1] += w0; dd[c1] += dr
    for c in cs["characters"]:
        n = c["char"]; d = c.get("duels", {})
        if (dw[n], dl[n], dd[n]) != (d.get("wins",0), d.get("losses",0), d.get("draws",0)):
            issues.append(f"{n}: 決鬥個人 W{d.get('wins',0)}/L{d.get('losses',0)}/D{d.get('draws',0)} "
                          f"≠ matchup 推算 W{dw[n]}/L{dl[n]}/D{dd[n]}")

    # deaths vs death_notes 長度
    for c in cs["characters"]:
        n = c["char"]
        if c.get("deaths", 0) != len(c.get("death_notes", [])):
            issues.append(f"{n}: deaths={c.get('deaths')} 但 death_notes 有 {len(c.get('death_notes',[]))} 條")

    # praised / combat_contrib total vs by_session 合計
    for c in cs["characters"]:
        n = c["char"]
        for tot, by in [("praised", "praised_by_session"),
                        ("combat_contrib", "combat_contrib_by_session")]:
            s = sum(c.get(by, {}).values())
            if c.get(tot, 0) != s:
                issues.append(f"{n}: {tot}={c.get(tot,0)} ≠ {by} 合計 {s}")
    return issues


# ── B. 文案脫鉤 ────────────────────────────────────────────────
# 每條 (正則, 真實統計 key, 說明)。正則第一個 group 為聲稱數字。
# 只放「措辭明確、不會與集數/傷害值混淆」的 pattern，寧可漏報不要誤報。
PROSE_PATTERNS = [
    (r"(\d+)\s*次(?:陣亡|死亡)", "deaths", "陣亡次數"),
    (r"(?:陣亡|死亡)\s*(\d+)\s*次", "deaths", "陣亡次數"),
    (r"(\d+)\s*[次場]\s*MVP", "mvp", "MVP次數"),
    (r"MVP\s*(\d+)\s*[次場]", "mvp", "MVP次數"),
    (r"(?:奪得|奪下|拿過|拿下|榮膺)\s*(\d+)\s*[次場](?=[^，。；！]*MVP)", "mvp", "MVP次數"),
    (r"(\d+)\s*次倒地", "downed", "倒地次數"),
    (r"倒地\s*(\d+)\s*次", "downed", "倒地次數"),
]

# 友軍傷害：prose 難分「施暴 / 受害」，故聲稱數字符合任一即視為正確，
# 只攔截兩者皆不符（必為過時或幻覺）的情況。
FF_PATTERN = r"(\d+)\s*次友(?:軍|傷)"

# 靠北：prose 難分「主動/被動/配對」，數字符合任一合法值即可。
# 動詞關鍵字（靠北/吐槽/嘲諷/開噴/回敬）為靠北專屬，誤報風險低。
ROAST_PATTERNS = [
    r"(?:靠北|吐槽|嘲諷|開噴|回敬|噴)(?:達|了)?\s*(\d+)\s*次",
    r"(\d+)\s*次(?:靠北|吐槽|嘲諷)",
]


def check_prose(cs, gt, warn):
    issues = []
    for c in cs["characters"]:
        n = c["char"]
        g = gt[n]

        fields = [("ai_intro", c.get("ai_intro", "")),
                  ("death_narrative", c.get("death_narrative", ""))]
        for i, a in enumerate(c.get("achievements", [])):
            fields.append((f"achievements[{i}].desc", a.get("desc", "")))

        for fname, text in fields:
            # 戰績「N勝N敗(N平)」整組比對
            for m in re.finditer(r"(\d+)\s*勝\s*(\d+)\s*敗(?:\s*(\d+)\s*平)?", text):
                w, l = int(m.group(1)), int(m.group(2))
                dr = int(m.group(3)) if m.group(3) else None
                if w != g["wins"] or l != g["losses"] or (dr is not None and dr != g["draws"]):
                    real = f"{g['wins']}勝{g['losses']}敗{g['draws']}平"
                    issues.append(f"{n}.{fname}: 戰績「{m.group(0).strip()}」≠ 實際 {real}")

            # 單一統計數字比對
            for pat, key, label in PROSE_PATTERNS:
                for m in re.finditer(pat, text):
                    claimed = int(m.group(1))
                    real = g[key]
                    if claimed != real:
                        issues.append(
                            f"{n}.{fname}: {label}「{m.group(0).strip()}」聲稱 {claimed}，實際 {real}"
                        )

            # 友軍傷害：符合施暴或受害任一即可
            for m in re.finditer(FF_PATTERN, text):
                claimed = int(m.group(1))
                if claimed not in (g["ff_perp"], g["ff_victim"]):
                    issues.append(
                        f"{n}.{fname}: 友軍傷害「{m.group(0).strip()}」聲稱 {claimed}，"
                        f"實際施暴 {g['ff_perp']} / 受害 {g['ff_victim']}"
                    )

            # 靠北：符合主動/被動合計或任一配對值即可
            for pat in ROAST_PATTERNS:
                for m in re.finditer(pat, text):
                    claimed = int(m.group(1))
                    if claimed not in g["roast_ok"]:
                        issues.append(
                            f"{n}.{fname}: 靠北「{m.group(0).strip()}」聲稱 {claimed}，"
                            f"實際主動 {g['roast_from']} / 被動 {g['roast_to']}"
                        )
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn", action="store_true", help="只警告不阻斷（exit 0）")
    args = ap.parse_args()

    cs, gt = ground_truth()
    structural = check_structural(cs, gt)
    prose = check_prose(cs, gt, args.warn)

    print("═" * 56)
    print("資料一致性驗證")
    print("═" * 56)

    if structural:
        print(f"\n⚠ 結構一致性問題（{len(structural)}）：")
        for s in structural:
            print(f"  • {s}")
    else:
        print("\n✓ 結構一致性：個人統計 / matchup / awards / by_session 全部對齊")

    if prose:
        print(f"\n⚠ 文案數字脫鉤（{len(prose)}）：")
        for s in prose:
            print(f"  • {s}")
        print("\n  → 修法：重跑 gen_char_achievements.py / gen_char_summaries.py")
    else:
        print("✓ 文案數字：ai_intro / death_narrative / achievements 內嵌數字全部正確")

    total = len(structural) + len(prose)
    print()
    if total == 0:
        print("✅ 全部通過")
        return 0
    print(f"❌ 共 {total} 項不一致")
    return 0 if args.warn else 1


if __name__ == "__main__":
    sys.exit(main())
