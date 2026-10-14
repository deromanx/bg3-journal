#!/usr/bin/env python3
"""
週測題庫（Kahoot 式問答）：data/quiz/bank.json

兩類題目：
- 情節題（主力）：每集 2 次 Gemini（出題＋逐題驗證），考劇情內容與玩家互動，每題附原文出處；
  出處對不上原文、有一題多解嫌疑的整題丟棄。
- 資料題（少量）：從死亡、友傷統計組題，答案取自資料，不呼叫 Gemini。
不出「這句是誰說的」「發生在哪一章」這類純考記憶的題（使用者 2026-10-14 要求）。
  存在 data/quiz/plot.json，已有的集數不重出（內容指紋變了才重出）。

每週題目由前端依「週數 + 題目 id」決定性挑選，題庫只需持續累積。
每題記錄 added（加入題庫的日期）；前端只用「本週一之前」加入的題目，
所以週中跑 pipeline 補新題不會改動本週已經在玩的那一份。

用法：
  python3 gen_quiz.py                  # 重建資料題；情節題只補缺漏中最新的 1 集（pipeline 用）
  python3 gen_quiz.py --backfill 15    # 情節題最多補 15 集（歷史回填，分天跑以免超出免費額度）
  python3 gen_quiz.py --no-gemini      # 只重建資料題
"""

import argparse
import hashlib
import json
import random
import re
import subprocess
from datetime import datetime, timedelta, timezone

from common import DATA, content_fingerprint, load_json, save_json

QUIZ_DIR = DATA / "quiz"
BANK_F = QUIZ_DIR / "bank.json"
PLOT_F = QUIZ_DIR / "plot.json"
CHARS = ['影心', '阿斯代倫', '曹', '卡拉克', '貓咕咕']
# 玩家本名不得出現在題目（網站不顯示本名）
REAL_NAMES = ['游尚傑', '林昱宇', '曹祐誠', '丁丁', '昱如']
PLOT_PER_SESSION = 8
TPE = timezone(timedelta(hours=8))

_norm = lambda t: re.sub(r'[^\w]', '', t or '')


def today():
    return datetime.now(TPE).strftime('%Y-%m-%d')


def qid(*parts):
    return hashlib.sha1('|'.join(map(str, parts)).encode()).hexdigest()[:10]


def shuffled(options, answer, seed):
    """選項順序以題目 id 為種子打散（Gemini 出的題答案常擠在前兩個）；回傳 (options, answer_index)。"""
    opts = list(options)
    rnd = random.Random(seed)
    rnd.shuffle(opts)
    return opts, opts.index(answer)


def char_options(answer, seed, n=4):
    """角色題：正解 + 隨機 3 位其他角色。"""
    others = [c for c in CHARS if c != answer]
    random.Random(seed + 'o').shuffle(others)
    return shuffled([answer] + others[:n - 1], answer, seed)


def session_text(session):
    return "\n".join(it["v"] for it in session["content"]
                     if it.get("t") != "img" and isinstance(it.get("v"), str))


def has_real_name(*texts):
    return any(n in (t or '') for t in texts for n in REAL_NAMES)


# ── 資料題 ─────────────────────────────────────────────────

def data_questions(sessions, raws, ff_incidents):
    """只出劇情與玩家互動相關的資料題（死因、友傷）。
    不出「第幾章」「誰說的」「MVP」這類考記憶的題（使用者 2026-10-14 明確要求避開）；
    題目不帶章節，所以事實必須在整個戰役中唯一，否則不出。"""
    out = []
    meta = {s['id']: s for s in sessions}

    def add(sid, kind, key, q, options, answer, source=''):
        i = qid(kind, sid, key)
        opts, ans = shuffled(options, answer, i)
        if has_real_name(q, source, *opts):
            return
        out.append({'id': i, 'sid': sid, 'kind': kind, 'q': q, 'options': opts,
                    'answer': ans, 'source': source})

    # 死因：全戰役只有一位角色這樣死過才出
    notes = {}
    for sid, raw in raws.items():
        for d in raw.get('deaths', []):
            if d.get('is_downed') or d.get('char') not in CHARS or len(d.get('note', '')) < 5:
                continue
            notes.setdefault(d['note'], set()).add((sid, d['char']))
    for note, hits in notes.items():
        if len({c for _, c in hits}) == 1 and len(hits) == 1:
            sid, c = next(iter(hits))
            opts, _ = char_options(c, qid('death', sid, note))
            add(sid, 'death', note, f"是誰「{note}」？", opts, c)

    # 友傷：用事件描述出題、遮住加害者（只給手法太空泛，例如「普攻」根本無從答起）
    for inc in ff_incidents:
        sid, perp, victim, desc = inc['session'], inc.get('perp'), inc.get('victim'), inc.get('desc', '')
        if sid not in meta or perp not in CHARS or victim not in CHARS or perp == victim:
            continue
        if perp not in desc or len(desc) < 20:
            continue
        masked = desc.replace(perp, '○○')
        others = [c for c in CHARS if c not in (perp, victim)]
        random.Random(qid('ff', sid, desc)).shuffle(others)
        add(sid, 'ff', f'{perp}{inc.get("method", "")}', f"「{masked}」這是誰幹的好事？",
            [perp] + others[:3], perp)
    return out


# ── 情節題（Gemini）──────────────────────────────────────

PLOT_PROMPT = """你是《柏德之門3》TRPG 團的問答出題者。以下是第{sid}集「{title}」的日誌原文。
角色只有：影心、阿斯代倫、曹、卡拉克、貓咕咕。

請出 {n} 題四選一的題目，讓有玩過、讀過這集的隊友答得出來、沒讀過的會猶豫。
題目範圍，兩類大約各半：
- 劇情內容：冒險中發生了什麼事、隊伍做了什麼決定、戰鬥怎麼打贏或翻車、NPC 做了什麼
- 玩家互動：隊友之間的吐槽、互坑、誤傷、決鬥、閒聊的話題、搞笑操作、對彼此行為的反應
規則：
- 題目必須能從原文直接找到答案，不可推測或補充原文沒有的細節
- 優先考好笑、荒謬或關鍵的事，不考無聊細節
- 不要出這些題型：「這句話是誰說的」「發生在第幾章／哪一集」、考數字（傷害、血量、骰值、金額）、考裝備或法術名稱
- 四個選項同類型、長度相近；四個之中只能有一個符合原文
- 錯誤選項必須是這一集「沒有發生」的事：要合理、像這群人會做的事，但原文沒有。
  不可以拿原文裡別的真實事件、或對同一題也說得通的描述當錯誤選項（例：問「影心被變成什麼」，
  不可把原文同一場景也成立的「被防死結界護住」當錯誤選項）
- 題目不可洩漏答案；選項各 2–14 字
- source 必須「逐字」抄自原文，15–60 字，是能證明答案的那一句
- 提到角色一律寫角色名，不要用「她」「他」等性別代稱（角色性別與玩家不一定一致）
- 不要出現玩家本名，只用角色名
- 題目用口語化的繁體中文，可以帶點幽默

只回傳 JSON 陣列，不要其他文字：
[{{"q": "題目", "options": ["正解", "錯誤1", "錯誤2", "錯誤3"], "answer": 0, "source": "原文逐字節錄"}}]

日誌原文：
{text}
"""


VERIFY_PROMPT = """以下是《柏德之門3》TRPG 日誌第{sid}集的原文，以及根據原文出的四選一題目。
請逐題嚴格檢查：是否「標示的正解符合原文，而且其他三個選項在原文中都不成立」。

判為不合格的情況：
- 正解與原文不符
- 任何一個錯誤選項，在原文中也是事實、或對這一題也說得通（就算只是部分成立也算）
- 題目有歧義，或需要原文以外的知識才能作答

只回傳 JSON 陣列，不要其他文字：
[{{"i": 題號, "ok": true 或 false, "reason": "不合格原因（合格留空字串）"}}]

題目：
{items}

日誌原文：
{text}
"""


def verify_plot(items, session):
    """第二次呼叫 Gemini 逐題檢查歧義；只保留判為合格的題目。回傳 (保留, 丟棄原因列表)。"""
    if not items:
        return [], []
    listing = "\n".join(
        f"{i}. {it['q']}　選項：{' / '.join(it['options'])}；正解：{it['options'][it['answer']]}"
        for i, it in enumerate(items))
    res = call_gemini(VERIFY_PROMPT.format(sid=session['id'], items=listing, text=session_text(session)))
    verdict = {r.get('i'): r for r in res if isinstance(r, dict)}
    keep, dropped = [], []
    for i, it in enumerate(items):
        r = verdict.get(i)
        if r and r.get('ok') is True:
            keep.append(it)
        else:
            dropped.append(f"驗證不合格（{(r or {}).get('reason') or '未回覆'}）：{it['q'][:30]}")
    return keep, dropped


def call_gemini(prompt):
    r = subprocess.run(["gemini", "-p", prompt], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    m = re.search(r'\[[\s\S]*\]', r.stdout)
    if not m:
        raise RuntimeError(f"找不到 JSON 陣列：{r.stdout[:200]}")
    return json.loads(m.group(), strict=False)


def _bigrams(t):
    t = _norm(t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def distractor_from_text(opts, ans, src, session, thresh=0.75):
    """錯誤選項的用字大多出現在出處附近原文 → 很可能也是事實（S32「將好感度列為第一要務」）。
    Gemini 驗證會漏，這裡用字面重疊再擋一次；寧可錯殺。"""
    paras = [it["v"] for it in session["content"] if it.get("t") != "img" and isinstance(it.get("v"), str)]
    hit = [i for i, v in enumerate(paras) if _norm(src) in _norm(v)]
    if not hit:
        return None
    near = _bigrams("".join(paras[max(0, hit[0] - 1):hit[0] + 2]))
    for k, o in enumerate(opts):
        bg = _bigrams(o)
        if k != ans and len(bg) >= 4 and len(bg & near) / len(bg) >= thresh:
            return o
    return None


# 不要的題型（考記憶而非劇情）：Gemini 偶爾仍會出，本地再擋
BANNED_Q = re.compile(r'是誰說的|誰說了這句|哪一章|第幾章|哪一集|第幾集|幾滴血|多少血|多少傷害|骰出幾')


def validate_plot(items, session):
    """丟棄出處對不上原文、選項不完整、含本名的題目。回傳 (保留, 丟棄原因列表)。"""
    text = _norm(session_text(session))
    keep, dropped = [], []
    for it in items if isinstance(items, list) else []:
        q, opts, ans, src = it.get('q', ''), it.get('options'), it.get('answer'), it.get('source', '')
        why = None
        if not q or not isinstance(opts, list) or len(opts) != 4 or len(set(map(str, opts))) != 4:
            why = '選項不是 4 個相異值'
        elif not isinstance(ans, int) or not 0 <= ans < 4:
            why = 'answer 超出範圍'
        elif len(_norm(src)) < 8 or _norm(src) not in text:
            why = '出處不在原文'
        elif has_real_name(q, src, *map(str, opts)):
            why = '含本名'
        elif '她' in q + ''.join(map(str, opts)):
            why = '用了性別代稱「她」（prompt 已禁止，Gemini 仍會用）'
        elif BANNED_Q.search(q):
            why = '題型考記憶（誰說的／哪一章／數字）'
        elif (o := distractor_from_text(opts, ans, src, session)):
            why = f'錯誤選項「{o}」用字取自原文，可能也成立'
        if why:
            dropped.append(f"{why}：{q[:30]}")
        else:
            keep.append({'q': q.strip(), 'options': [str(o).strip() for o in opts],
                         'answer': ans, 'source': src.strip()})
    return keep, dropped


def recheck_local(plot, sessions):
    """規則更新後，對已驗證的題目重跑本地檢查（不呼叫 Gemini）。"""
    by_id = {s['id']: s for s in sessions}
    for sid_s, entry in plot.items():
        s = by_id.get(int(sid_s))
        if not s or not entry.get('verified'):
            continue
        keep, dropped = validate_plot(entry.get('items', []), s)
        if dropped:
            entry['items'] = keep
            for d in dropped:
                print(f"  S{sid_s} ⊘ {d}")
    save_json(PLOT_F, plot)


def plot_questions(plot):
    out = []
    for sid_s, entry in plot.items():
        if not entry.get('verified'):
            continue      # 未經歧義驗證的題目不進題庫
        sid = int(sid_s)
        for it in entry.get('items', []):
            i = qid('plot', sid, it['q'])
            opts, ans = shuffled(it['options'], it['options'][it['answer']], i)
            out.append({'id': i, 'sid': sid, 'kind': 'plot', 'q': it['q'], 'options': opts,
                        'answer': ans, 'source': it['source']})
    return out


def fill_plot(sessions, plot, limit):
    """補情節題：缺漏、內容已變動或尚未驗證的集數，由新到舊最多 limit 集。
    每集 2 次 Gemini（出題＋驗證）；已出題但未驗證的只補驗證（1 次）。"""
    def need(s):
        e = plot.get(str(s['id']), {})
        return e.get('_fp') != content_fingerprint(s['content']) or not e.get('verified')
    todo = [s for s in reversed(sessions) if not s.get('placeholder') and s['content'] and need(s)]
    for s in todo[:limit]:
        entry = plot.get(str(s['id']), {})
        regen = entry.get('_fp') != content_fingerprint(s['content'])
        print(f"  S{s['id']} 情節題{'' if regen else '（補驗證）'}…", end=' ', flush=True)
        try:
            if regen:
                items = call_gemini(PLOT_PROMPT.format(sid=s['id'], title=s['title'], n=PLOT_PER_SESSION,
                                                       text=session_text(s)))
                items, dropped = validate_plot(items, s)
            else:
                items, dropped = validate_plot(entry.get('items', []), s)
            keep, bad = verify_plot(items, s)
        except Exception as e:
            print(f"✗ {e}")
            if 'Quota' in str(e) or '429' in str(e):
                print("  ⚠ Gemini 額度用盡，剩下的集數改天再補")
                break
            continue      # 未驗證不落盤：題目不進題庫，下次再補
        dropped += bad
        plot[str(s['id'])] = {'_fp': content_fingerprint(s['content']), 'verified': True, 'items': keep}
        save_json(PLOT_F, plot)
        print(f"保留 {len(keep)} 題" + (f"，丟棄 {len(dropped)} 題" if dropped else ''))
        for d in dropped:
            print(f"     ⊘ {d}")
    left = len(todo) - min(limit, len(todo))
    if left:
        print(f"  ℹ 還有 {left} 集沒有情節題（python3 gen_quiz.py --backfill N 補齊）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backfill', type=int, default=1, help='情節題最多補幾集（預設 1：只補最新）')
    ap.add_argument('--no-gemini', action='store_true')
    ap.add_argument('--added', default=None, help='新題目的加入日期（預設今天，台北時間）')
    args = ap.parse_args()

    QUIZ_DIR.mkdir(exist_ok=True)
    sessions = json.loads((DATA / 'sessions.json').read_text('utf-8'))
    sessions = [s for s in sessions if not s.get('placeholder')]
    plot = load_json(PLOT_F, {})
    recheck_local(plot, sessions)
    if not args.no_gemini:
        fill_plot(sessions, plot, args.backfill)

    raws = {s['id']: load_json(DATA / 'sessions-raw' / f"{s['id']}.json", {}) for s in sessions}
    qs = data_questions(sessions, raws, load_json(DATA / 'ff-stats.json', {}).get('incidents', []))
    qs += plot_questions(plot)

    # 同 id 去重；保留舊題的 added，週中重建不會讓本週題目變動
    old = {q['id']: q.get('added') for q in load_json(BANK_F, {}).get('questions', [])}
    added = args.added or today()
    seen, bank = set(), []
    for q in qs:
        if q['id'] in seen:
            continue
        seen.add(q['id'])
        q['added'] = old.get(q['id']) or added
        bank.append(q)
    bank.sort(key=lambda q: (q['sid'], q['kind'], q['id']))
    save_json(BANK_F, {'_note': '週測題庫（gen_quiz.py 產生）；前端依週數挑題，只用本週一之前加入的題目',
                       'questions': bank})

    from collections import Counter
    print(f"✓ 題庫 {len(bank)} 題：" + '、'.join(f"{k} {v}" for k, v in Counter(q['kind'] for q in bank).items()))


if __name__ == '__main__':
    main()
