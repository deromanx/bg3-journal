#!/usr/bin/env python3
"""
gen_roast_images.py — 為靠北語錄生成奇幻風示意插圖
使用 Gemini 2.0 Flash Image Generation（免費 tier，須設 GEMINI_API_KEY）

風格參考：自動載入現有日誌插畫（data/images/20/img_001.jpg）
作為 style reference，讓生成結果符合日誌的漫畫 cel-shading 風格。

設定 API key：
  export GEMINI_API_KEY="your_key_here"
  # 免費 key：https://aistudio.google.com/app/apikey

用法：
  python3 gen_roast_images.py              # 補齊所有缺圖
  python3 gen_roast_images.py --test       # 只跑第一張測試
  python3 gen_roast_images.py --from 10   # 從第10集開始
  python3 gen_roast_images.py --rewrite 5 # 強制重跑第5集

圖片存至：data/images/roast/<img_id>.jpg
img_id 同時寫回 roast-stats.json 的 quotes[].img_id，
供前端 modal 載入。
"""

import json, hashlib, os, sys, time, argparse
from pathlib import Path
import io

BASE      = Path(__file__).parent
DATA      = BASE / "data"
ROAST_F   = DATA / "roast-stats.json"
OUT_DIR   = DATA / "images" / "roast"
IMG_MODEL = "gemini-2.0-flash-preview-image-generation"

# 風格參考圖：優先選有全體角色的漫畫 cel-shading 封面圖
STYLE_REF_CANDIDATES = [
    DATA / "images" / "20" / "img_001.jpg",  # 漫畫風全體角色圖
    DATA / "images" / "3"  / "img_001.jpg",  # 深色奇幻插畫封面
    DATA / "images" / "1"  / "img_001.jpg",  # 早期插畫備用
]

# 角色視覺描述（依現有插圖實際外貌校正）
CHAR_VISUAL = {
    "影心":    "a storm cleric with dark skin and white braided hair, wearing dark armor, surrounded by storm lightning",
    "阿斯代倫": "a tall pale elf with white/silver hair, calm cold expression, elegant dark robes",
    "曹":     "a human archer with short dark hair, drawing a longbow with intense focus",
    "卡拉克":  "a tiefling barbarian woman with red skin, small curved horns, a red tail, holding a massive greataxe, fierce grin",
    "貓咕咕":  "a small gnome sorcerer with pink-purple horns, wearing green robes, wide innocent eyes",
}

STYLE_PROMPT = (
    "Draw in the exact same comic book illustration style as the reference image: "
    "bold cel-shaded outlines, vibrant saturated colors, dramatic dark fantasy backgrounds "
    "(Gothic castle, dungeon, firelight), expressive exaggerated facial reactions, "
    "dynamic poses, strong contrast between light and shadow. "
    "No text, no speech bubbles, no UI elements. "
    "Horizontal composition, wide panel format. "
)


def stable_id(q: dict) -> str:
    froms = q.get("from", [])
    if isinstance(froms, str):
        froms = [froms]
    key = f"{q.get('session',0)}|{','.join(sorted(froms))}|{q.get('to','')}|{str(q.get('desc',''))[:40]}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def load_style_ref() -> bytes | None:
    for p in STYLE_REF_CANDIDATES:
        if p.exists():
            return p.read_bytes()
    return None


def build_prompt(q: dict) -> str:
    froms = q.get("from", [])
    if isinstance(froms, str):
        froms = [froms]
    tos = q.get("to", "")
    if isinstance(tos, str):
        tos = [tos] if tos else []

    involved = list(dict.fromkeys(list(froms) + list(tos)))  # 去重保序
    chars_desc = [CHAR_VISUAL[c] for c in involved if c in CHAR_VISUAL]
    chars_str  = "; ".join(chars_desc) if chars_desc else "fantasy adventurers"

    froms_zh = "、".join(froms)
    tos_zh   = tos[0] if isinstance(tos, list) else tos
    action_hint = f"{froms_zh} teasing or mocking {tos_zh}. "

    quote_hint = f'Mood: "{q["quote"]}". ' if q.get("quote") else ""
    scene_zh   = str(q.get("desc", ""))[:100]
    # 簡短英文情境（用描述的前半）
    scene_hint = f"Scene: party members reacting to: {scene_zh[:80]}. "

    return (
        STYLE_PROMPT
        + f"Characters in scene: {chars_str}. "
        + action_hint
        + scene_hint
        + quote_hint
        + "Show exaggerated comic expressions matching the comedic situation."
    )


def save_image(img_bytes: bytes, path: Path) -> None:
    try:
        from PIL import Image as PILImage
    except ImportError:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(img_bytes)
        return
    img = PILImage.open(io.BytesIO(img_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if w > 960:
        img = img.resize((960, int(h * 960 / w)), PILImage.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=88, optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",    action="store_true", help="只跑第一張測試")
    parser.add_argument("--from",    type=int, dest="from_session", metavar="N",
                        help="從第 N 集開始處理")
    parser.add_argument("--rewrite", type=int, metavar="N",
                        help="強制重跑第 N 集（刪除舊圖並重生成）")
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

    # 載入風格參考圖
    style_bytes = load_style_ref()
    if style_bytes:
        print(f"✓ 已載入風格參考圖（{len(style_bytes)//1024}KB）")
        style_part = gtypes.Part.from_bytes(data=style_bytes, mime_type="image/jpeg")
    else:
        print("⚠ 找不到風格參考圖，將只用文字描述風格")
        style_part = None

    # 載入語錄
    roast  = json.loads(ROAST_F.read_text("utf-8"))
    quotes = roast.get("quotes", roast.get("highlights", []))

    # 補 img_id
    changed = False
    for q in quotes:
        if not q.get("img_id"):
            q["img_id"] = stable_id(q)
            changed = True
    if changed:
        roast["quotes"] = quotes
        ROAST_F.write_text(json.dumps(roast, ensure_ascii=False, indent=2), "utf-8")
        print(f"✓ 寫入 {sum(1 for q in quotes if q.get('img_id'))} 筆 img_id\n")

    # 決定目標
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

    success = fail = 0
    for i, q in enumerate(targets, 1):
        img_id   = q["img_id"]
        out_path = OUT_DIR / f"{img_id}.jpg"
        prompt   = build_prompt(q)
        label    = f"S{q.get('session',0)}  {str(q.get('quote','') or q.get('desc',''))[:30]}"
        print(f"[{i}/{len(targets)}] {label}")

        # 組合 contents：風格參考圖（若有）+ 文字 prompt
        if style_part:
            contents = [
                style_part,
                gtypes.Part.from_text(
                    "Use the above image as the style reference. Now generate a new illustration:\n\n"
                    + prompt
                ),
            ]
        else:
            contents = prompt

        try:
            resp = client.models.generate_content(
                model=IMG_MODEL,
                contents=contents,
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
                print(f"  ✓ {out_path.name}  {len(img_bytes)//1024}KB")
                success += 1
            else:
                print(f"  ⚠ 無圖片回應")
                fail += 1

        except Exception as e:
            print(f"  ❌ {e}")
            fail += 1

        if i < len(targets):
            time.sleep(2.0)  # free tier: ~30 req/min for Flash

    print(f"\n完成：✓{success} 張  ❌{fail} 失敗")
    if success:
        print("→ 重新整理網站即可看到插圖（modal 自動載入圖片）")


if __name__ == "__main__":
    main()
