#!/usr/bin/env python3
"""
從 Google Drive BG3 場次資料夾讀取 .docx，萃取文字段落 + 插圖，
輸出 data/sessions.json 與 data/images/<id>/*.jpg。
新增場次後重跑即可更新。

用法：python3 extract.py
"""

import os, re, json, io
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

try:
    from PIL import Image as PILImage
    PILLOW = True
except ImportError:
    PILLOW = False

# ── 路徑設定 ──────────────────────────────────────────────────
GOOGLE_DRIVE = Path.home() / "Library/CloudStorage" \
    / "GoogleDrive-deromanx@gmail.com/My Drive/To Baldur's Gate"
BASE_DIR   = Path(__file__).parent
OUTPUT     = BASE_DIR / "data" / "sessions.json"
IMAGES_DIR = BASE_DIR / "data" / "images"

# ── 章節名 ────────────────────────────────────────────────────
CHAPTERS = [
    "第一章", "第二章", "第三章", "第四章", "第五章",
    "第六章", "第七章", "第八章", "第九章", "第十章",
    "第十一章", "第十二章", "第十三章", "第十四章", "第十五章",
    "第十六章", "第十七章", "第十八章", "第十九章", "第二十章",
    "第二十一章", "第二十二章", "第二十三章", "第二十四章", "第二十五章",
]

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

_NAME_FIXES = {"卡菈克": "卡拉克"}

def clean(text: str) -> str:
    t = text.translate(_BAD_CHARS).strip()
    for wrong, right in _NAME_FIXES.items():
        t = t.replace(wrong, right)
    return t

def is_meta(text: str) -> bool:
    return any(re.search(p, text) for p in META_PATTERNS)

_CHAR_PAT = r'(?:影心|阿斯代倫|曹|卡拉克|貓咕咕)'
_VS_DUEL  = re.compile(rf'^\s*{_CHAR_PAT}\s*(?:vs\.?|VS\.?|v\.s\.?)\s*{_CHAR_PAT}\s*$')

def classify(text: str, bold: bool = False) -> str:
    """回傳段落類型：h1 / h2 / ai / p"""
    if re.match(r"^\(AI\s*(點評|Comment)", text, re.I):
        return "ai"
    no_punct = not re.search(r"[，。！？…」]", text)
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

# ── 圖片存檔 ──────────────────────────────────────────────────
IMG_MAX_W = 900   # 最大寬度（px），超過則縮小

def save_image(blob: bytes, out_path: Path, ext: str) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if PILLOW:
            img = PILImage.open(io.BytesIO(blob))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            w, h = img.size
            if w > IMG_MAX_W:
                img = img.resize((IMG_MAX_W, int(h * IMG_MAX_W / w)),
                                 PILImage.LANCZOS)
            img.save(out_path.with_suffix(".jpg"), "JPEG", quality=82, optimize=True)
        else:
            out_path.write_bytes(blob)
        return True
    except Exception as e:
        print(f"    ⚠ 圖片儲存失敗：{e}")
        return False

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
    items = []

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
                    fname = f"img_{img_counter:03d}.jpg"
                    out   = img_dir / fname
                    if save_image(blob, out, ext):
                        items.append({"t": "img",
                                      "v": f"data/images/{session_id}/{fname}"})
                except Exception as e:
                    print(f"    ⚠ 圖片關係錯誤：{e}")

        # ── 文字 ──
        text = clean(para.text)
        if not text or is_meta(text):
            continue
        bold = any(run.bold for run in para.runs if run.text.strip())
        # 讀縮排值判斷列表層級
        pPr = para._element.find(qn("w:pPr"))
        ind_el = pPr.find(qn("w:ind")) if pPr is not None else None
        left_raw = ind_el.get(qn("w:left"), "0") if ind_el is not None else "0"
        left = int(left_raw) if left_raw.isdigit() else 0
        t = classify(text, bold=bold)
        # 非標題段落：依縮排深度細分
        if t == "p":
            if left >= 1200:
                t = "li2"
            elif left >= 660:
                t = "li"
        items.append({"t": t, "v": text})

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
            if e.is_dir() and re.match(r"^\d{8}", e.name)
        )
    except OSError as e:
        print(f"❌ 無法讀取 Google Drive：{e}")
        return

    sessions = []
    for idx, folder in enumerate(entries):
        date_iso, date_display, title = parse_folder(folder.name)
        chapter = CHAPTERS[idx] if idx < len(CHAPTERS) else f"第{idx+1}章"

        has_pdf   = find_pdf(folder)
        docx_path = find_docx(folder) if has_pdf else None
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

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(sessions, ensure_ascii=False, indent=2), "utf-8")

    total_imgs = sum(
        len([x for x in s["content"] if x["t"] == "img"]) for s in sessions
    )
    print(f"\n✓ 已產生 {OUTPUT}")
    print(f"  共 {len(sessions)} 集，{sum(1 for s in sessions if not s['placeholder'])} 集有內容，{total_imgs} 張插圖")

if __name__ == "__main__":
    main()
