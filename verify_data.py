#!/usr/bin/env python3
"""
verify_data.py — 資料一致性驗證器（pipeline 最後關卡）

兩類檢查：
  A. 結構一致性：個人統計 vs 衍生來源（matchup 矩陣、awards、by_session 合計）
  B. 文案脫鉤：AI 生成的 prose（ai_intro / death_narrative / achievements）
     內嵌的累計數字，是否與真實統計一致。
  C. 集數同步：最新集數的衍生資料是否都已生成、各 _note 集數字串是否過時。

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


# ── B. 文案佔位符檢查 ──────────────────────────────────────────
# 資料已改用佔位符（{deaths} 等），由 app.js 渲染時注入真實值，數字永遠同步。
# 驗證器的職責因此轉為：偵測「該用佔位符卻寫死的裸數字」——Gemini 漏用佔位符
# 時會留下裸數字，未來統計變動就脫鉤。各 pattern 命中即代表應改佔位符。
# 例外（合法的裸數字，不攔截）：集數編號 S20/第10集、單次傷害值、對特定人的配對靠北。

# (正則, 應改用的佔位符, 說明)。命中即視為該佔位符化。
BARE_PATTERNS = [
    (r"\d+\s*次(?:陣亡|死亡)", "deaths", "陣亡次數"),
    (r"(?:陣亡|死亡)\s*\d+\s*次", "deaths", "陣亡次數"),
    (r"\d+\s*[次場]\s*MVP", "mvp", "MVP次數"),
    (r"MVP\s*\d+\s*[次場]", "mvp", "MVP次數"),
    (r"\d+\s*次倒地", "downed", "倒地次數"),
    (r"倒地\s*\d+\s*次", "downed", "倒地次數"),
    (r"\d+\s*勝\s*\d+\s*敗(?:\s*\d+\s*平)?", "wins/losses/draws", "決鬥戰績"),
    (r"\d+\s*次友(?:軍|傷)", "ff_perp/ff_victim", "友軍傷害次數"),
]

# 靠北裸數字（須排除「對X」配對語境，配對是合法裸數字）。
ROAST_BARE = [
    r"(?:靠北|吐槽|嘲諷|開噴|回敬)(?:達|了)?\s*\d+\s*次",
    r"\d+\s*次(?:靠北|吐槽|嘲諷)",
]


def check_prose(cs, gt, warn):
    """偵測 prose 內該用佔位符卻寫死的裸統計數字。"""
    issues = []
    for c in cs["characters"]:
        n = c["char"]

        fields = [("ai_intro", c.get("ai_intro", "")),
                  ("death_narrative", c.get("death_narrative", ""))]
        for i, a in enumerate(c.get("achievements", [])):
            fields.append((f"achievements[{i}].name", a.get("name", "")))
            fields.append((f"achievements[{i}].desc", a.get("desc", "")))

        for fname, text in fields:
            for pat, ph, label in BARE_PATTERNS:
                for m in re.finditer(pat, text):
                    issues.append(
                        f"{n}.{fname}: {label}「{m.group(0).strip()}」是寫死的裸數字，"
                        f"應改用佔位符 {{{ph}}}"
                    )
            # 靠北：排除「對X」配對
            for pat in ROAST_BARE:
                for m in re.finditer(pat, text):
                    prefix = text[max(0, m.start() - 5):m.start()]
                    if "對" in prefix and any(ch in prefix for ch in CHARS):
                        continue  # 配對靠北，合法裸數字
                    issues.append(
                        f"{n}.{fname}: 靠北「{m.group(0).strip()}」是寫死的裸數字，"
                        f"應改用佔位符 {{roast_from}} 或 {{roast_to}}"
                    )
    return issues


# ── C. 集數同步檢查 ─────────────────────────────────────────────
def check_session_sync():
    """確認最新集數的衍生資料都已生成，且 _note 集數字串未過時。"""
    issues = []
    sessions = load("sessions.json", [])
    real_ids = [s["id"] for s in sessions
                if not s.get("placeholder") and s.get("content")]
    if not real_ids:
        return issues
    n_sessions = len(real_ids)
    latest = max(real_ids)

    # C1. 最新集覆蓋：roast / awards 每集必有衍生資料；缺即代表對應腳本漏跑。
    #     （praise / ff 某集可能合法零事件，故不檢查其最新集覆蓋）
    roast = load("roast-stats.json", {})
    roast_sessions = {h.get("session") for h in roast.get("highlights", [])}
    if latest not in roast_sessions:
        issues.append(f"靠北統計缺最新第 {latest} 集（roast-stats highlights 未含），"
                      f"regen_roast_quotes.py 可能漏跑")

    aw = load("awards.json", {})
    if str(latest) not in aw and latest not in aw:
        issues.append(f"獎項缺最新第 {latest} 集（awards.json 無此 key），gen_awards.py 可能漏跑")

    # C2. 角色逐集處理進度 marker
    for marker, script in [(".praised_processed.json", "count_praised.py"),
                           (".combat_contrib_processed.json", "count_combat_contrib.py")]:
        done = load(marker, [])
        if isinstance(done, list) and latest not in done:
            issues.append(f"{marker} 未含第 {latest} 集，{script} 未處理最新集")

    # C3. 過時集數字串：掃描各 JSON 的 _note，比對「分析 N 集 / 共 N 集」
    pat = re.compile(r"(?:分析|共)\s*(\d+)\s*集")
    for fname in ["roast-stats.json", "praise-stats.json", "ff-stats.json",
                  "milestones.json", "story.json"]:
        d = load(fname, None)
        note = d.get("_note", "") if isinstance(d, dict) else ""
        for m in pat.finditer(note):
            if int(m.group(1)) != n_sessions:
                issues.append(f"{fname} _note 集數過時：「{m.group(0)}」應為 {n_sessions} 集")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--warn", action="store_true", help="只警告不阻斷（exit 0）")
    args = ap.parse_args()

    cs, gt = ground_truth()
    structural = check_structural(cs, gt)
    prose = check_prose(cs, gt, args.warn)
    sync = check_session_sync()

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
        print(f"\n⚠ 文案寫死裸數字（{len(prose)}）：")
        for s in prose:
            print(f"  • {s}")
        print("\n  → 這些數字未來統計變動就會脫鉤；應改用佔位符（見 placeholders.py），"
              "\n    手動改或重跑 gen_char_*.py（prompt 已要求輸出佔位符）")
    else:
        print("✓ 文案佔位符：ai_intro / death_narrative / achievements 無寫死的統計裸數字")

    if sync:
        print(f"\n⚠ 集數同步問題（{len(sync)}）：")
        for s in sync:
            print(f"  • {s}")
        print("\n  → 最新集衍生資料漏生成時重跑對應腳本；_note 集數過時則手動更新字串")
    else:
        print("✓ 集數同步：最新集衍生資料齊全，各 _note 集數字串無過時")

    total = len(structural) + len(prose) + len(sync)
    print()
    if total == 0:
        print("✅ 全部通過")
        return 0
    print(f"❌ 共 {total} 項不一致")
    return 0 if args.warn else 1


if __name__ == "__main__":
    sys.exit(main())
