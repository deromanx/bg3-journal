# 前進柏德之門 — 冒險日誌

《柏德之門3》TRPG 跑團戰役日誌網站：完整戰報、決鬥統計、靠北語錄、里程碑，與吟遊詩人瓦羅的故事集。

**🔗 線上閱讀：https://deromanx.github.io/bg3-journal/**

![冒險隊伍](data/images/cover.webp)

## 架構

純靜態 SPA（無框架、無建置步驟），資料由本地 pipeline 從 Google Drive 的場次記錄（.docx）萃取生成。

```
Google Drive docx ──extract.py──▶ data/sessions.json + sessions/{id}.json + images/{id}/*.webp
                                        │
                    update_stats.py ────┤  Gemini CLI 萃取各集事件 → data/sessions-raw/{id}.json
                                        │  （單一真實來源，統計全量 rebuild、idempotent）
                                        ▼
        gen_*.py ──▶ awards / character-stats / roast / praise / ff / milestones / story
                                        │
                     gen_share_pages.py ▶ s/{id}.html（每集 og 分享卡 stub）
                                        │
                       verify_data.py ──▶ 一致性驗證（結構／文案佔位符／集數同步／部署產物）
```

核心設計：

- **`data/sessions-raw/` 是統計的單一真實來源**——所有累計數據從各集原始萃取結果全量 rebuild，重跑不會重複計數
- **AI 文案用佔位符**（`{deaths}`、`{mvp}`…）由前端渲染時注入真實統計，數字永不脫鉤（語彙見 `placeholders.py`）
- **標題層級規則**：docx 以 bold 標記標題，層級由段落自身縮排決定（left=0 → h1、left>0 → h2、`A vs B` 型固定 h2），詳見 `extract.py` 的 `classify()` / `resolve_type()`

## 一鍵更新

```bash
./update_all.sh                # 一般更新（新增一集後跑）
./update_all.sh --skip-chars   # 跳過角色介紹重生成（省 ~10 次 Gemini 呼叫）
```

旗標可組合：`--roast-all` / `--praise-all` / `--ff-all` / `--quotes-all` / `--skip-chars`。
任一步失敗即停、已完成步驟已落盤，修正後直接重跑。輸出自動留檔於 `logs/`。

內容生成走 Gemini CLI 免費額度（每日約 20 次呼叫），pipeline 開跑會先顯示本次預估用量。

## 本機設定

1. 複製 `local_config.example.py` 為 `local_config.py`，填入日誌 docx 來源目錄（或設環境變數 `BG3_DRIVE_DIR`）
2. Gemini CLI 需可用（`gemini -p "test"`），API key 設定見 [AI Studio](https://aistudio.google.com/apikey)
3. 相依：`python-docx`、`lxml`、`Pillow`

## 測試

```bash
python3 tests/test_extract.py   # extract.py 純函式回歸測試（pipeline 第 0 步自動跑）
python3 verify_data.py          # 資料一致性驗證（pipeline 最後關卡）
```

## 部署

push 到 `main` 後由 GitHub Pages（legacy 建置）自動部署。改 `app.js` / `style.css` 時 pipeline 會自動遞增 `index.html` 的 `?v=N` 做 cache busting。
