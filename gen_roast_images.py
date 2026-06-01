#!/usr/bin/env python3
"""
gen_roast_images.py — 為靠北語錄生成奇幻風示意插圖
使用 Gemini 2.0 Flash Image Generation（免費 tier，須設 GEMINI_API_KEY）

設定 API key：
  export GEMINI_API_KEY="your_key_here"
  # 免費 key 取得：https://aistudio.google.com/app/apikey

用法：
  python3 gen_roast_images.py              # 補齊所有缺圖
  python3 gen_roast_images.py --test       # 只跑第一張測試
  python3 gen_roast_images.py --from 10   # 從第10集開始
  python3 gen_roast_images.py --rewrite 5 # 強制重跑第5集

圖片存至：data/images/roast/<img_id>.jpg
img_id 同時寫回 roast-stats.json 的 quotes[].img_id 欄位，
供前端 modal 載入。
"""

import json, hashlib, os, sys, time, argparse
from pathlib import Path
from PIL import Image as PILImage
import io

BASE      = Path(__file__).parent
DATA      = BASE / "data"
ROAST_F   = DATA / "roast-stats.json"
OUT_DIR   = DATA / "images" / "roast"
IMG_MODEL = "gemini-2.0-flash-preview-image-generation"

CHAR_VISUAL = {
    "影心":   "a dark-skinned half-elf storm cleric with white hair and stormy eyes",
    "阿斯代倫": "a pale vampire rogue with silver hair and fangs in leather armor",
    "曹":    "a nimble human archer with short black hair, holding a longbow",
    "卡拉克":  "a sturdy dwarf barbarian woman with braided red hair and a greataxe",
    "貓咕咕":  "a gnome sorcerer with fluffy teal hair and colorful robes",
}


def stable_id(q: dict) -> str:
    """從 session/from/to/desc 前 40 字計算 8 碼 hex，作為穩定圖片 ID。"""
    froms = q.get("from", [])
    if isinstance(froms, str):
        froms = [froms]
    key = f"{q.get('session',0)}|{','.join(sorted(froms))}|{q.get('to','')}|{str(q.get('desc',''))[:40]}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def build_prompt(q: dict) -> str:
    froms = q.get("from", [])
    if isinstance(froms, str):
        froms = [froms]
    tos = q.get("to", "")
    if isinstance(tos, str):
        tos = [tos] if tos else []

    chars_desc = []
    for c in list(froms) + list(tos):
        if c in CHAR_VISUAL:
            chars_desc.append(CHAR_VISUAL[c])

    quote_hint = f'"{q["quote"]}"' if q.get("quote") else ""
    scene_hint = str(q.get("desc", ""))[:120]

    chars_str = "; ".join(chars_desc) if chars_desc else "fantasy adventurers"
    return (
        "Illustration in a dark fantasy comic style inspired by Baldur's Gate 3. "
        "Warm candlelight, tavern or dungeon setting, slightly exaggerated expressions. "
        f"Characters: {chars_str}. "
        f"Scene hint: {scene_hint} "
        f"{quote_hint} "
        "No text or speech bubbles. Cinematic composition, rich detail."
    )


def save_image(img_bytes: bytes, path: Path) -> None:
    img = PILImage.open(io.BytesIO(img_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if w > 900:
        img = img.resize((900, int(h * 900 / w)), PILImage.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=85, optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",    action="store_true", help="只跑第一張")
    parser.add_argument("--from",    type=int, dest="from_session", metavar="N",
                        help="從第 N 集開始處理")
    parser.add_argument("--rewrite", type=int, metavar="N",
                        help="強制重跑第 N 集")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("❌ 請先設定環境變數：export GEMINI_API_KEY='your_key'")
        print("   免費 key：https://aistudio.google.com/app/apikey")
        sys.exit(1)

    try:
        import google.genai as genai
        from google.genai import types as gtypes
    except ImportError:
        print("❌ 請安裝：pip3 install google-genai pillow")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    roast = json.loads(ROAST_F.read_text("utf-8"))
    quotes = roast.get("quotes", roast.get("highlights", []))

    # 確保每筆 quote 都有穩定 img_id
    changed = False
    for q in quotes:
        if not q.get("img_id"):
            q["img_id"] = stable_id(q)
            changed = True

    if changed:
        roast["quotes"] = quotes
        ROAST_F.write_text(json.dumps(roast, ensure_ascii=False, indent=2), "utf-8")
        print("✓ img_id 已寫入 roast-stats.json")

    # 篩選要處理的 quotes
    if args.rewrite:
        targets = [q for q in quotes if q.get("session") == args.rewrite]
    elif args.from_session:
        targets = [q for q in quotes if q.get("session", 0) >= args.from_session]
    elif args.test:
        targets = quotes[:1]
    else:
        targets = [q for q in quotes if not (OUT_DIR / f"{q['img_id']}.jpg").exists()]

    print(f"共 {len(quotes)} 筆語錄，待生成插圖 {len(targets)} 張\n")
    if not targets:
        print("✓ 全部已生成，無需處理")
        return

    success = fail = skip = 0
    for i, q in enumerate(targets, 1):
        img_id   = q["img_id"]
        out_path = OUT_DIR / f"{img_id}.jpg"

        if args.rewrite is None and args.test is False and out_path.exists():
            skip += 1
            continue

        prompt = build_prompt(q)
        label  = f"S{q.get('session',0)} {str(q.get('quote',''))[:20] or str(q.get('desc',''))[:20]}"
        print(f"[{i}/{len(targets)}] {label}")

        try:
            resp = client.models.generate_content(
                model=IMG_MODEL,
                contents=prompt,
                config=gtypes.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"]
                ),
            )
            img_bytes = None
            for part in (resp.candidates[0].content.parts if resp.candidates else []):
                if hasattr(part, "inline_data") and part.inline_data:
                    img_bytes = part.inline_data.data
                    break

            if img_bytes:
                save_image(img_bytes, out_path)
                print(f"  ✓ 已存 {out_path.name} ({len(img_bytes)//1024}KB)")
                success += 1
            else:
                print(f"  ⚠ 無圖片回應（可能模型限制）")
                fail += 1

        except Exception as e:
            print(f"  ❌ {e}")
            fail += 1

        if i < len(targets):
            time.sleep(1.5)  # 避免超過 free tier rate limit

    print(f"\n完成：✓{success} 張  ⚠{fail} 失敗  ⊘{skip} 已跳過")
    if success:
        print("→ 重新整理網站即可看到插圖（modal 自動載入）")


if __name__ == "__main__":
    main()
