#!/usr/bin/env python3
"""
週測題庫（Kahoot 式問答）：data/quiz/bank.json

兩類題目：
- 資料題：從既有統計（MVP、死亡、友傷、決鬥、名言、章名、里程碑）組題，答案取自資料，不呼叫 Gemini。
  只出「單集事實」，不出累計排名這類會隨新集數變動的題目。
- 情節題：每集 1 次 Gemini，從日誌原文出 6 題，每題附原文出處；出處在原文找不到就整題丟棄。
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
from gen_quote_by import find_speaker_in_text

QUIZ_DIR = DATA / "quiz"
BANK_F = QUIZ_DIR / "bank.json"
PLOT_F = QUIZ_DIR / "plot.json"
CHARS = ['影心', '阿斯代倫', '曹', '卡拉克', '貓咕咕']
# 玩家本名不得出現在題目（網站不顯示本名）
REAL_NAMES = ['游尚傑', '林昱宇', '曹祐誠', '丁丁', '昱如']
PLOT_PER_SESSION = 6
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

def data_questions(sessions, awards, raws, sstats, chars, milestones):
    out = []
    meta = {s['id']: s for s in sessions}

    def add(sid, kind, key, q, options, answer, source=''):
        i = qid(kind, sid, key)
        opts, ans = shuffled(options, answer, i) if kind != 'duel' else (options, options.index(answer))
        if has_real_name(q, source, *opts):
            return
        out.append({'id': i, 'sid': sid, 'kind': kind, 'q': q, 'options': opts,
                    'answer': ans, 'source': source})

    for s in sessions:
        sid = s['id']
        ch = s['chapter']
        aw = awards.get(str(sid), {})

        # MVP
        if aw.get('mvp') in CHARS:
            opts, _ = char_options(aw['mvp'], qid('mvp', sid))
            add(sid, 'mvp', '', f"{ch}《{s['title']}》的 MVP 是誰？", opts, aw['mvp'],
                aw.get('mvp_reason', ''))

        # 最佳金句：說話者要能在原文驗證，Gemini 猜的不出題（S35 曾猜錯）
        bq = aw.get('best_quote')
        if bq and aw.get('best_quote_by') in CHARS and \
                find_speaker_in_text(bq, s) == aw['best_quote_by']:
            opts, _ = char_options(aw['best_quote_by'], qid('bq', sid))
            add(sid, 'quote', 'best', f"{ch}的最佳金句「{bq}」是誰說的？", opts, aw['best_quote_by'])

        # 死亡：本集只有一位角色符合這個死因才出題
        raw = raws.get(sid, {})
        notes = {}
        for d in raw.get('deaths', []):
            if d.get('is_downed') or d.get('char') not in CHARS or len(d.get('note', '')) < 3:
                continue
            notes.setdefault(d['note'], set()).add(d['char'])
        for note, who in notes.items():
            if len(who) == 1:
                c = next(iter(who))
                opts, _ = char_options(c, qid('death', sid, note))
                add(sid, 'death', note, f"{ch}裡，是誰「{note}」？", opts, c)

        # 決鬥：有勝負才出（平手當選項之一）；同一對本集打不只一場就有歧義，不出
        duels = sstats.get(str(sid), {}).get('duels', [])
        pair = lambda d: frozenset(d.get('chars') or [d.get('winner'), d.get('loser')])
        pair_n = {}
        for d in duels:
            pair_n[pair(d)] = pair_n.get(pair(d), 0) + 1
        for di, d in enumerate(duels):
            w, l = d.get('winner'), d.get('loser')
            if w in CHARS and l in CHARS and pair_n[pair(d)] == 1:
                a, b = sorted([w, l], key=CHARS.index)
                add(sid, 'duel', di, f"{ch}，{a}和{b}的決鬥，結果是？",
                    [f'{a}贏', f'{b}贏', '平手'], f'{w}贏')

    # 友軍傷害：同集「手法＋受害者」相同但加害者不同就有歧義，不出
    ff_key = lambda x: (x['session'], x.get('victim'), x.get('method'))
    ff_perps = {}
    for inc in chars.get('_ff', []):
        ff_perps.setdefault(ff_key(inc), set()).add(inc.get('perp'))
    for inc in chars.get('_ff', []):
        if len(ff_perps[ff_key(inc)]) > 1:
            continue
        sid, perp, victim, method = inc['session'], inc.get('perp'), inc.get('victim'), inc.get('method', '')
        if perp in CHARS and victim in CHARS and perp != victim and method and sid in meta:
            others = [c for c in CHARS if c not in (perp, victim)]
            random.Random(qid('ff', sid, method)).shuffle(others)
            add(sid, 'ff', f'{perp}{method}', f"{meta[sid]['chapter']}，是誰用「{method}」誤傷了{victim}？",
                [perp] + others[:3], perp, inc.get('desc', ''))

    # 名言錄：說話者要能在原文驗證
    for c in chars.get('characters', []):
        for qt in c.get('quotes', []):
            sid, text = qt.get('session'), qt.get('text', '')
            if sid in meta and len(_norm(text)) >= 4 and find_speaker_in_text(text, meta[sid]) == c['char']:
                opts, _ = char_options(c['char'], qid('cq', sid, text))
                add(sid, 'quote', text, f"「{text.strip('「」')}」是誰說的？（{meta[sid]['chapter']}）",
                    opts, c['char'])

    # 章名：本章標題是哪一個（干擾項取前後章）
    real = [s for s in sessions if not s.get('placeholder')]
    for i, s in enumerate(real):
        near = [x['title'] for x in real[max(0, i - 4):i + 5] if x['id'] != s['id']]
        random.Random(qid('title', s['id'])).shuffle(near)
        if len(near) >= 3:
            add(s['id'], 'title', '', f"{s['chapter']}的標題是？", [s['title']] + near[:3], s['title'])

    # 里程碑：發生在哪一章（干擾項取相鄰章）
    for m in milestones:
        sid = m.get('session_id')
        if sid not in meta or not m.get('title'):
            continue
        ids = [x['id'] for x in real]
        k = ids.index(sid) if sid in ids else None
        if k is None:
            continue
        near = [ids[j] for j in range(max(0, k - 3), min(len(ids), k + 4)) if j != k]
        random.Random(qid('ms', sid, m['title'])).shuffle(near)
        if len(near) < 3:
            continue
        opts = [meta[x]['chapter'] for x in [sid] + near[:3]]
        add(sid, 'milestone', m['title'], f"里程碑「{m['title']}」發生在哪一章？", opts, meta[sid]['chapter'],
            m.get('desc', ''))
    return out


# ── 情節題（Gemini）──────────────────────────────────────

PLOT_PROMPT = """你是《柏德之門3》TRPG 團的問答出題者。以下是第{sid}集「{title}」的日誌原文。
角色只有：影心、阿斯代倫、曹、卡拉克、貓咕咕。

請出 {n} 題四選一的情節題，讓有讀過這集的隊友答得出來、沒讀過的會猶豫。規則：
- 題目必須能從原文直接找到答案，不可推測或補充原文沒有的細節
- 優先考好笑、荒謬或關鍵的劇情，不考無聊細節（例如數字、裝備名）
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
    chars = load_json(DATA / 'character-stats.json', {})
    chars['_ff'] = load_json(DATA / 'ff-stats.json', {}).get('incidents', [])
    qs = data_questions(sessions, load_json(DATA / 'awards.json', {}), raws,
                        load_json(DATA / 'session-stats.json', {}), chars,
                        load_json(DATA / 'milestones.json', []))
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
