#!/usr/bin/env bash
#
# update_all.sh — 柏德之門3日誌網站一鍵更新 pipeline
#
# 依序執行整條流程；任一步失敗即停止（已完成步驟的結果已落盤，可直接重跑）。
# 內容生成全走 Gemini CLI 免費額度。
#
# 用法（旗標可自由組合，如 ./update_all.sh --roast-all --skip-chars）：
#   ./update_all.sh              一般更新
#   --roast-all    靠北統計全量重跑（連帶 praise/ff/quotes 全量；改了 regen 邏輯時才需要）
#   --praise-all   稱讚統計全量重跑
#   --ff-all       友軍傷害統計全量重跑
#   --quotes-all   角色名言錄全量重抽（改了抽取邏輯時才需要）
#   --skip-chars   跳過角色介紹重生成（省 ~10 次 Gemini 呼叫）
#
set -euo pipefail
cd "$(dirname "$0")"

# 全程輸出留檔（logs/ 被 *.log 規則 gitignore）：過夜跑掛掉有屍體可驗，
# 也可事後 grep 統計實際 Gemini 呼叫數以校準配額預估
mkdir -p logs
exec > >(tee -a "logs/update_$(date +%Y%m%d_%H%M%S).log") 2>&1

trap 'echo; echo "❌ 上一步失敗，pipeline 已停止。已完成步驟的結果已落盤，修正後可直接重跑。" >&2' ERR

run() { echo; echo "▶ $*"; "$@"; }

# ── 旗標解析（可自由組合） ──────────────────────────────────
ROAST_ALL=0; PRAISE_ALL=0; FF_ALL=0; QUOTES_ALL=0; SKIP_CHARS=0
for arg in "$@"; do
    case "$arg" in
        --roast-all)  ROAST_ALL=1 ;;
        --praise-all) PRAISE_ALL=1 ;;
        --ff-all)     FF_ALL=1 ;;
        --quotes-all) QUOTES_ALL=1 ;;
        --skip-chars) SKIP_CHARS=1 ;;
        *) echo "未知旗標：$arg（可用：--roast-all --praise-all --ff-all --quotes-all --skip-chars）" >&2; exit 1 ;;
    esac
done

# 0. extract.py 回歸測試（標題層級判斷歷史上改壞過兩次；先擋再跑）
run python3 tests/test_extract.py

# 1. 萃取最新 docx（圖片已存在會自動跳過）
run python3 extract.py

# 取得「最小待更新集數」與待更新集數數量：未有 sessions-raw、或內容指紋
# 與既存 raw 不符（舊集被回頭修改）的最小 id；若全部都是最新則取最大 id。
# 用 min 而非 max，確保新增多集或修改舊集時 roast/praise/ff 能從該集起跑。
read -r LATEST STALE_COUNT <<< "$(python3 -c "
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
print(min(ids) if ids else max(s['id'] for s in non_ph), len(ids))
")"

# ── Gemini 配額預估（免費層每日約 20 次成功呼叫，Pacific 午夜重置） ──
# 粗估：每個待更新集約 10 次（萃取/統計/金句/亮點/故事/roast/praise/ff/名言錄），
# 角色介紹+成就固定 10 次（--skip-chars 可省）。全量旗標另計、不在此估算內。
EST=$(( STALE_COUNT * 10 + (SKIP_CHARS == 1 ? 0 : 10) ))
echo
echo "ℹ️  待更新集數：$STALE_COUNT（從 S$LATEST 起）；本次 Gemini 呼叫預估 ~$EST 次（每日上限約 20）"
if (( EST > 20 )); then
    echo "⚠️  預估超出每日免費配額，可能中途遇 TerminalQuotaError。"
    echo "    建議：加 --skip-chars 省 10 次；或分天跑（pipeline 可中斷重跑，不會重複計數）。"
fi

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
if (( ROAST_ALL )); then
    run python3 regen_roast_quotes.py
else
    run python3 regen_roast_quotes.py --from "$LATEST"
fi

# 7. 稱讚統計
if (( PRAISE_ALL || ROAST_ALL )); then
    run python3 gen_praise_stats.py
else
    run python3 gen_praise_stats.py --from "$LATEST"
fi

# 8. 友軍傷害統計
if (( FF_ALL || ROAST_ALL )); then
    run python3 gen_ff_stats.py
else
    run python3 gen_ff_stats.py --from "$LATEST"
fi

# 8.5 角色名言錄（增量，每集 1 次 Gemini；不受 --skip-chars 影響。
#     --quotes-all 或 --roast-all 全量重抽）
if (( QUOTES_ALL || ROAST_ALL )); then
    run python3 gen_char_quotes.py
else
    run python3 gen_char_quotes.py --from "$LATEST"
fi

# 9. 角色介紹、死亡敘述、成就（預設每次重生成，加 --skip-chars 可略過；依序執行避免競態）
if (( ! SKIP_CHARS )); then
    run python3 gen_char_summaries.py
    run python3 gen_char_achievements.py
fi

# 10. 統一修正下游 JSON 的角色名錯字（收尾）
run python3 normalize_names.py

# 10.5 每集分享 stub 頁（og 預覽卡；純本地生成，不呼叫 Gemini）
run python3 gen_share_pages.py

# 10.7 Cache busting：app.js / style.css 有變更時自動遞增 index.html 的 ?v=N
#      （須在 verify_data 之前，其部署產物檢查會驗證 ?v= 已同步）
for f in style.css app.js; do
    if ! git diff --quiet HEAD -- "$f" 2>/dev/null; then
        if git diff --quiet HEAD -- index.html 2>/dev/null; then
            perl -pi -e "s/(\Q$f\E\?v=)(\d+)/\$1.(\$2+1)/e" index.html
            echo "🔄 $f 有變更，已自動遞增 index.html 的版本號"
        fi
    fi
done

# 11. 資料一致性驗證（最後關卡；--warn 只警告不阻斷 pipeline）
run python3 verify_data.py --warn

echo
echo "✅ Pipeline 完成。檢查 git diff 後即可 commit / push。"
echo "   提示：加 --skip-chars 可跳過角色介紹重生成（省 ~10 次 Gemini 呼叫）。"
echo "   若上方出現「文案數字脫鉤」警告，重跑 gen_char_achievements.py 即可。"
