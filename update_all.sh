#!/usr/bin/env bash
#
# update_all.sh — 柏德之門3日誌網站一鍵更新 pipeline
#
# 依序執行整條流程；任一步失敗即停止（已完成步驟的結果已落盤，可直接重跑）。
# 內容生成全走 Gemini CLI 免費額度。
#
# 用法：
#   ./update_all.sh              一般更新
#   ./update_all.sh --roast-all  靠北統計全量重跑（改了 regen 邏輯時才需要）
#   ./update_all.sh --quotes-all 角色名言錄全量重抽（改了抽取邏輯時才需要）
#   ./update_all.sh --skip-chars 跳過角色介紹重生成（省 ~5 分鐘）
#
set -euo pipefail
cd "$(dirname "$0")"

trap 'echo; echo "❌ 上一步失敗，pipeline 已停止。已完成步驟的結果已落盤，修正後可直接重跑。" >&2' ERR

run() { echo; echo "▶ $*"; "$@"; }

# 1. 萃取最新 docx（圖片已存在會自動跳過）
run python3 extract.py

# 取得「最小待更新集數」：未有 sessions-raw、或內容指紋與既存 raw 不符
# （舊集被回頭修改）的最小 id；若全部都是最新則取最大 id。
# 用 min 而非 max，確保新增多集或修改舊集時 roast/praise/ff 能從該集起跑。
LATEST=$(python3 -c "
import json
from pathlib import Path
from common import content_fingerprint, load_json
sess = json.load(open('data/sessions.json'))
non_ph = [s for s in sess if not s.get('placeholder') and s.get('content')]
raw_dir = Path('data/sessions-raw')
def stale(s):
    p = raw_dir / f\"{s['id']}.json\"
    if not p.exists():
        return True
    return load_json(p, {}).get('_fp') != content_fingerprint(s['content'])
ids = [s['id'] for s in non_ph if stale(s)]
print(min(ids) if ids else max(s['id'] for s in non_ph))
")

# 2. 統計、里程碑、故事（內建超時容錯）
run python3 update_stats.py

# 3. 角色細項統計
run python3 count_praised.py
run python3 count_combat_contrib.py

# 4. 獎項、金句說話者、本集亮點（依序執行，避免 awards.json 競態）
run python3 gen_awards.py
run python3 gen_quote_by.py
run python3 gen_highlights.py

# 5. 補齊 update_stats 階段二可能漏掉的故事章節
run python3 gen_story.py

# 6. 靠北統計
if [[ "${1:-}" == "--roast-all" ]]; then
    run python3 regen_roast_quotes.py
else
    run python3 regen_roast_quotes.py --from "$LATEST"
fi

# 7. 稱讚統計
if [[ "${1:-}" == "--praise-all" || "${1:-}" == "--roast-all" ]]; then
    run python3 gen_praise_stats.py
else
    run python3 gen_praise_stats.py --from "$LATEST"
fi

# 8. 友軍傷害統計
if [[ "${1:-}" == "--ff-all" || "${1:-}" == "--roast-all" ]]; then
    run python3 gen_ff_stats.py
else
    run python3 gen_ff_stats.py --from "$LATEST"
fi

# 8.5 角色名言錄（增量，每集 1 次 Gemini；不受 --skip-chars 影響。
#     --quotes-all 或 --roast-all 全量重抽）
if [[ "${1:-}" == "--quotes-all" || "${1:-}" == "--roast-all" ]]; then
    run python3 gen_char_quotes.py
else
    run python3 gen_char_quotes.py --from "$LATEST"
fi

# 9. 角色介紹、死亡敘述、成就（預設每次重生成，加 --skip-chars 可略過；依序執行避免競態）
if [[ "${1:-}" != "--skip-chars" ]]; then
    run python3 gen_char_summaries.py
    run python3 gen_char_achievements.py
fi

# 10. 統一修正下游 JSON 的角色名錯字（收尾）
run python3 normalize_names.py

# 11. 資料一致性驗證（最後關卡；--warn 只警告不阻斷 pipeline）
run python3 verify_data.py --warn

echo
echo "✅ Pipeline 完成。檢查 git diff 後即可 commit / push。"
echo "   提示：加 --skip-chars 可跳過角色介紹重生成（省 ~5 分鐘）。"
echo "   若上方出現「文案數字脫鉤」警告，重跑 gen_char_achievements.py 即可。"
