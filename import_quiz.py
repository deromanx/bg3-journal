#!/usr/bin/env python3
"""週測情節題：Claude 出題用的輔助工具（取代 gen_quiz.py 的 Gemini 出題，使用者 2026-10-15 定案）。

  python3 import_quiz.py --dump 36        # 印出第 36 集原文＋該集已有題目，供 Claude 讀原文出題
  python3 import_quiz.py q36.json         # 匯入題目（{"36": [items]}），取代該集原有情節題
  python3 import_quiz.py --append q.json  # 追加到該集既有題目後（同題目文字自動略過）

item 格式同 gen_quiz.PLOT_PROMPT：{"q", "options"(4 個，正解放第 0 個即可，題庫會打散), "answer", "source"}。
匯入一律經過 gen_quiz.validate_plot 本地過濾（出處須逐字在原文、不含本名、不用「她」、
不考誰說的／哪一章／數字、錯誤選項用字不可取自出處附近原文），被擋下的題目會列出原因，改寫後重匯即可。
匯入後跑 python3 gen_quiz.py --no-gemini 重建 bank.json。
"""
import argparse
import json
import sys

import gen_quiz as g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('files', nargs='*')
    ap.add_argument('--dump', type=int, metavar='SID')
    ap.add_argument('--append', action='store_true')
    args = ap.parse_args()

    sessions = {s['id']: s for s in json.loads((g.DATA / 'sessions.json').read_text('utf-8'))}
    plot = g.load_json(g.PLOT_F, {})

    if args.dump:
        s = sessions[args.dump]
        print(f"# S{s['id']}「{s['title']}」\n")
        print(g.session_text(s))
        have = plot.get(str(s['id']), {}).get('items', [])
        if have:
            print(f"\n# 已有情節題 {len(have)} 題（避開重複事件）")
            for it in have:
                print(f"- {it['q']}｜{it['options'][it['answer']]}")
        return

    if not args.files:
        ap.error('需要題目檔或 --dump SID')
    total_drop = 0
    for f in args.files:
        for sid, items in json.load(open(f, encoding='utf-8')).items():
            s = sessions[int(sid)]
            keep, dropped = g.validate_plot(items, s)
            old = plot.get(sid, {}).get('items', []) if args.append else []
            have = {x['q'] for x in old}
            keep = old + [k for k in keep if k['q'] not in have]
            plot[sid] = {'_fp': g.content_fingerprint(s['content']), 'verified': True, 'items': keep}
            print(f"S{sid} 情節題 {len(keep)} 題" + (f"，擋下 {len(dropped)} 題" if dropped else ''))
            for d in dropped:
                print(f"   ⊘ {d}")
            total_drop += len(dropped)
    g.save_json(g.PLOT_F, plot)
    sys.exit(1 if total_drop else 0)


if __name__ == '__main__':
    main()
