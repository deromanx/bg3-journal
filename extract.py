#!/usr/bin/env python3
"""
從 Google Drive BG3 場次資料夾讀取 .docx，萃取文字段落 + 插圖，
輸出 data/sessions.json 與 data/images/<id>/*.webp。
新增場次後重跑即可更新。

用法：python3 extract.py
"""

import os, re, json, io, sys, zipfile
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from lxml import etree
from name_fixes import fix_text

try:
    from PIL import Image as PILImage
    PILLOW = True
except ImportError:
    PILLOW = False

# ── 路徑設定 ──────────────────────────────────────────────────
# 日誌來源目錄（含個人帳號路徑，不進版控）：
# 環境變數 BG3_DRIVE_DIR 優先，否則讀 gitignored 的 local_config.py
if os.environ.get("BG3_DRIVE_DIR"):
    GOOGLE_DRIVE = Path(os.environ["BG3_DRIVE_DIR"])
else:
    try:
        from local_config import GOOGLE_DRIVE
    except ImportError:
        sys.exit("錯誤：未設定日誌來源目錄。請設環境變數 BG3_DRIVE_DIR，"
                 "或建立 local_config.py（參考 local_config.example.py）。")
BASE_DIR   = Path(__file__).parent
OUTPUT     = BASE_DIR / "data" / "sessions.json"
IMAGES_DIR = BASE_DIR / "data" / "images"
# id → 資料夾日期前綴的穩定映射；用來偵測資料夾插入/刪除/重排導致的 id 位移
FOLDERS_MAP = BASE_DIR / "data" / ".session_folders.json"

# ── 章節名 ────────────────────────────────────────────────────
# 全站章名單一來源（前端、故事集、分享頁都讀 sessions-meta 的 chapter）。
# 舊版寫死 25 個中文章名，第 26 集起退化成「第26章」，造成全站混用兩種格式。
_CN_DIGITS = "零一二三四五六七八九"

def cn_number(n: int) -> str:
    """1–999 轉中文數字：10→十、11→十一、20→二十、105→一百零五、110→一百一十。"""
    if not 0 < n < 1000:
        return str(n)
    h, t, o = n // 100, n // 10 % 10, n % 10
    out = ""
    if h:
        out += _CN_DIGITS[h] + "百"
    if t:
        out += ("" if (t == 1 and not h) else _CN_DIGITS[t]) + "十"
    elif h and o:
        out += "零"
    if o:
        out += _CN_DIGITS[o]
    return out

def chapter_name(n: int) -> str:
    return f"第{cn_number(n)}章"

# ── 文字清洗 ──────────────────────────────────────────────────
_BAD_CHARS = str.maketrans({
    "㇐": "一",  # pdftotext 遺留
    "": "",  # Wingdings bullet
    "⾧": "長",   # CJK 相容字
})

META_PATTERNS = [
    r"^🕒",
    r"AI評選金句",
    r"^不是啊，為什麼日期",
]

def clean(text: str) -> str:
    t = text.translate(_BAD_CHARS).strip()
    return fix_text(t)

def is_meta(text: str) -> bool:
    return any(re.search(p, text) for p in META_PATTERNS)

_CHAR_PAT = r'(?:影心|阿斯代倫|曹|卡拉克|貓咕咕)'
_VS_DUEL  = re.compile(rf'^\s*{_CHAR_PAT}\s*(?:vs\.?|VS\.?|v\.s\.?)\s*{_CHAR_PAT}\s*$')

def classify(text: str, bold: bool = False) -> str:
    """回傳段落類型：h1 / h2 / ai / p"""
    if re.match(r"^\(AI\s*(點評|Comment)", text, re.I):
        return "ai"
    # 標題允許結尾帶！？（如「吃蟲啊！」），只有句中標點才排除
    text_for_punct = re.sub(r'[！？]+$', '', text)
    no_punct = not re.search(r"[，。！？…」]", text_for_punct)
    # 純對戰子標題（A vs B）→ h2 副標題
    if bold and _VS_DUEL.match(text):
        return "h2"
    # Word 用 bold 標記所有標題（無 Heading 樣式）
    if bold and no_punct and not text.startswith("("):
        return "h1"
    # 非 bold 的短行備用（極少發生）
    if (not bold and len(text) <= 16 and no_punct
            and not text.startswith("(")
            and not re.match(r"^\d", text)):
        return "h2"
    return "p"

def resolve_type(t: str, left: int) -> str:
    """依自身縮排收斂段落型別：p → li/li2；h1 有縮排 → 降為 h2（left=0 才是主節）"""
    if t == "p":
        if left >= 1200:
            return "li2"
        if left >= 660:
            return "li"
        return "p"
    if t == "h1" and left > 0:
        return "h2"
    return t

# ── 圖片存檔 ──────────────────────────────────────────────────
IMG_MAX_W = 900   # 最大寬度（px），超過則縮小

def save_image(blob: bytes, out_path: Path, ext: str):
    # 回傳值：成功且能取得尺寸 → (w, h)；成功但無尺寸 → True；失敗 → False。
    # 已存在則跳過解碼/縮放（只改文字重跑時不必重存全部圖片），但仍讀回尺寸。
    # 若某集圖片有更動，先刪掉 data/images/<id>/ 再重跑 extract.py。
    webp = out_path.with_suffix(".webp")
    if webp.exists():
        try:
            with PILImage.open(webp) as im:
                return im.size
        except Exception:
            return True
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if PILLOW:
            img = PILImage.open(io.BytesIO(blob))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            w, h = img.size
            if w > IMG_MAX_W:
                h = int(h * IMG_MAX_W / w)
                w = IMG_MAX_W
                img = img.resize((w, h), PILImage.LANCZOS)
            img.save(webp, "WEBP", quality=75, method=6)
            return (w, h)
        else:
            out_path.write_bytes(blob)
            return True
    except Exception as e:
        print(f"    ⚠ 圖片儲存失敗：{e}")
        return False

# ── 讀取 numbering.xml，建立 numId → 有效縮排（left-hanging）對應表 ──
def _build_num_indent_map(docx_path: Path) -> dict:
    W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    def wtag(n): return f'{{{W}}}{n}'
    try:
        with zipfile.ZipFile(docx_path, 'r') as z:
            if 'word/numbering.xml' not in z.namelist():
                return {}
            root = etree.fromstring(z.read('word/numbering.xml'))
    except Exception:
        return {}

    abstract_eff: dict[str, int] = {}
    for an in root.iter(wtag('abstractNum')):
        aid = an.get(wtag('abstractNumId'))
        for lvl in an.iter(wtag('lvl')):
            if lvl.get(wtag('ilvl')) != '0':
                continue
            # w:ind 位於 w:lvl/w:pPr/w:ind
            ind = lvl.find(f'.//{wtag("ind")}')
            if ind is not None:
                left    = int(ind.get(wtag('left'),    '0') or '0')
                hanging = int(ind.get(wtag('hanging'), '0') or '0')
                abstract_eff[aid] = max(0, left - hanging)
            else:
                abstract_eff[aid] = 0
            break

    result: dict[str, int] = {}
    for num in root.iter(wtag('num')):
        nid = num.get(wtag('numId'))
        an_ref = num.find(wtag('abstractNumId'))
        if an_ref is not None:
            result[nid] = abstract_eff.get(an_ref.get(wtag('val')), 0)
    return result


# ── DOCX 內容萃取 ─────────────────────────────────────────────
def extract_docx(docx_path: Path, session_id: int) -> list[dict]:
    """
    回傳內容項目清單，每項為：
      {"t": "p"|"h1"|"h2"|"ai"|"img", "v": "文字或相對路徑"}
    """
    doc = Document(docx_path)
    rels = doc.part.rels
    img_dir = IMAGES_DIR / str(session_id)
    img_counter = 0
    raw = []  # {"t": ..., "v": ..., "left": int}
    num_indent = _build_num_indent_map(docx_path)

    for para in doc.paragraphs:
        drawings = para._element.findall(".//" + qn("w:drawing"))

        # ── 圖片 ──
        if drawings:
            for drawing in drawings:
                blip = drawing.find(".//" + qn("a:blip"))
                if blip is None:
                    continue
                embed_id = blip.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                )
                if embed_id not in rels:
                    continue
                rel = rels[embed_id]
                try:
                    blob = rel.target_part.blob
                    ext  = Path(rel.target_ref).suffix or ".png"
                    img_counter += 1
                    fname = f"img_{img_counter:03d}.webp"
                    out   = img_dir / fname
                    dims = save_image(blob, out, ext)
                    if dims:
                        img_item = {"t": "img",
                                    "v": f"data/images/{session_id}/{fname}",
                                    "left": 0}
                        if isinstance(dims, tuple):
                            img_item["w"], img_item["h"] = dims
                        raw.append(img_item)
                except Exception as e:
                    print(f"    ⚠ 圖片關係錯誤：{e}")

        # ── 文字 ──
        text = clean(para.text)
        if not text or is_meta(text):
            continue
        bold = any(run.bold for run in para.runs if run.text.strip())
        # 讀縮排值：優先用段落自身 w:ind；若無則從 numbering 定義推算
        pPr = para._element.find(qn("w:pPr"))
        ind_el = pPr.find(qn("w:ind")) if pPr is not None else None
        left_raw = ind_el.get(qn("w:left"), "0") if ind_el is not None else "0"
        left = int(left_raw) if left_raw.isdigit() else 0
        # 段落沒有自訂 w:ind 時，從 numbering.xml 取有效縮排
        if ind_el is None and pPr is not None:
            numPr = pPr.find(qn("w:numPr"))
            if numPr is not None:
                nid_el = numPr.find(qn("w:numId"))
                if nid_el is not None:
                    left = num_indent.get(nid_el.get(qn("w:val")), 0)
        t = classify(text, bold=bold)
        raw.append({"t": t, "v": text, "left": left})

    # ── 後處理：依自身縮排收斂型別（p→li/li2；h1 left>0 → h2）──
    items = []
    for item in raw:
        t = resolve_type(item["t"], item["left"])
        new_item = {"t": t, "v": item["v"]}
        if "w" in item:
            new_item["w"], new_item["h"] = item["w"], item["h"]
        items.append(new_item)

    return items

# ── 資料夾解析 ────────────────────────────────────────────────
def parse_folder(name: str):
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(?:-(.+))?$", name)
    if not m:
        return None, None, name
    y, mo, d, title = m.groups()
    date_iso     = f"{y}-{mo}-{d}"
    date_display = f"{y} 年 {int(mo)} 月 {int(d)} 日"
    return date_iso, date_display, title or "（尚待命名）"

def is_session_folder(name: str) -> bool:
    """「YYYYMMDD-標題」或純「YYYYMMDD」才是日誌場次。
    「20260915 PARTY」這類空白分隔的非日誌資料夾不算（S33 實例：誤判成空白集，後續 id 全位移）；
    純日期資料夾不能排除（S35 實例：標題只寫在 docx 檔名，曾被整集靜默跳過）。"""
    return re.match(r"^\d{8}(-|$)", name) is not None

def title_from_docx(folder_name: str, docx_stem: str, title: str) -> str:
    """資料夾未命名（純日期）時，從「YYYYMMDD-標題.docx」取標題；否則維持資料夾標題。"""
    if "-" in folder_name:
        return title
    m = re.match(r"^\d{8}-(.+)$", docx_stem)
    return m.group(1).strip() if m else title

def find_pdf(folder: Path) -> bool:
    """資料夾中有 PDF 代表該集日誌已定稿，可以更新網頁"""
    return any(f.suffix.lower() == ".pdf" for f in folder.iterdir())

def find_docx(folder: Path) -> Path | None:
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() == ".docx":
            return f
    return None

# ── 主程式 ────────────────────────────────────────────────────
def main():
    try:
        entries = sorted(
            e for e in GOOGLE_DRIVE.iterdir()
            if e.is_dir() and is_session_folder(e.name)
        )
    except OSError as e:
        print(f"❌ 無法讀取 Google Drive：{e}")
        return

    sessions = []
    id_dates = {}   # id → 資料夾日期前綴（YYYYMMDD），用於位移偵測
    for idx, folder in enumerate(entries):
        date_iso, date_display, title = parse_folder(folder.name)
        chapter = chapter_name(idx + 1)
        id_dates[idx + 1] = folder.name[:8]

        has_pdf   = find_pdf(folder)
        docx_path = find_docx(folder) if has_pdf else None
        if docx_path:
            title = title_from_docx(folder.name, docx_path.stem, title)
        placeholder = not has_pdf

        if docx_path:
            print(f"✓ {chapter}  {title[:28]}")
            content = extract_docx(docx_path, idx + 1)
        elif has_pdf:
            # 有 PDF 但找不到 docx，以空白內容顯示
            print(f"⚠ {chapter}  {title[:28]}  ← 有 PDF 但無 docx")
            content = []
        else:
            print(f"⊘ {chapter}  {title[:28]}  ← 無 PDF，跳過")
            content = []

        sessions.append({
            "id":          idx + 1,
            "chapter":     chapter,
            "date":        date_iso,
            "dateDisplay": date_display,
            "title":       title,
            "content":     content,
            "placeholder": placeholder,
        })

    # ── id 位移守衛：確認既有 id 仍對應同一集（日期前綴）──────────────
    # 若中間插入/刪除/重排資料夾，id 會整批位移，導致 sessions-raw/N、
    # data/images/N/、各 by_session 統計全部對到錯的內容且難以察覺。
    # 此處在覆寫資料前比對，發現位移即中止並要求人工確認。
    try:
        stored_map = json.loads(FOLDERS_MAP.read_text("utf-8")) if FOLDERS_MAP.exists() else {}
    except Exception:
        stored_map = {}
    conflicts = [
        (sid, stored_map[str(sid)], d8)
        for sid, d8 in id_dates.items()
        if str(sid) in stored_map and stored_map[str(sid)] != d8
    ]
    if conflicts:
        print("\n❌ 偵測到 session id 位移（資料夾插入／刪除／重排）：")
        for sid, old, new in conflicts:
            print(f"   第 {sid} 集：原日期 {old} → 現在 {new}")
        print("   已中止，未覆寫任何資料。請確認資料夾順序，或若確為刻意調整，")
        print(f"   手動修正／刪除 {FOLDERS_MAP.name} 後重跑（注意 sessions-raw/、images/ 需同步搬移）。")
        raise SystemExit(1)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), "utf-8")
    # 更新 id → 日期映射（合併既有，納入新集）
    stored_map.update({str(k): v for k, v in id_dates.items()})
    FOLDERS_MAP.write_text(json.dumps(stored_map, ensure_ascii=False, indent=2), "utf-8")

    # ── Lazy-load 拆分：metadata + 各集內容 ───────────────────────────
    meta_only = [{k: v for k, v in s.items() if k != "content"} for s in sessions]
    meta_path = OUTPUT.parent / "sessions-meta.json"
    meta_path.write_text(json.dumps(meta_only, ensure_ascii=False, indent=2), "utf-8")

    session_dir = OUTPUT.parent / "sessions"
    session_dir.mkdir(exist_ok=True)
    for s in sessions:
        (session_dir / f"{s['id']}.json").write_text(
            json.dumps(s["content"], ensure_ascii=False, indent=2), "utf-8"
        )

    total_imgs = sum(
        len([x for x in s["content"] if x["t"] == "img"]) for s in sessions
    )
    print(f"\n✓ 已產生 {OUTPUT}")
    print(f"  已產生 {meta_path.name}（{len(meta_only)} 集 metadata）")
    print(f"  已產生 data/sessions/<id>.json（各集內容，lazy load 用）")
    print(f"  共 {len(sessions)} 集，{sum(1 for s in sessions if not s['placeholder'])} 集有內容，{total_imgs} 張插圖")

if __name__ == "__main__":
    main()
