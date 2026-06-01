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

import json, hashlib, os, sys, time, argparse, urllib.parse
from pathlib import Path
import io

BASE      = Path(__file__).parent
DATA      = BASE / "data"
ROAST_F   = DATA / "roast-stats.json"
OUT_DIR   = DATA / "images" / "roast"
CHARS_DIR = DATA / "images" / "characters"
IMG_MODEL = "gemini-2.0-flash-preview-image-generation"

# 風格參考圖：優先選有全體角色的漫畫 cel-shading 封面圖
STYLE_REF_CANDIDATES = [
    DATA / "images" / "20" / "img_001.jpg",  # 漫畫風全體角色圖
    DATA / "images" / "3"  / "img_001.jpg",  # 深色奇幻插畫封面
    DATA / "images" / "1"  / "img_001.jpg",  # 早期插畫備用
]

# 角色視覺描述（依角色創建截圖與現有插圖校正）
# 影心/阿斯代倫/卡拉克 為 BG3 原版角色，直接引用遊戲外型
CHAR_VISUAL = {
    "影心":    (
        "Shadowheart from Baldur's Gate 3, customized as a storm cleric: "
        "dark-skinned woman with white braided hair, dark armor, surrounded by storm lightning"
    ),
    "阿斯代倫": (
        "Astarion from Baldur's Gate 3: pale vampire elf with swept-back white/silver hair, "
        "red eyes, aristocratic expression — but wearing monk robes instead of rogue leathers"
    ),
    "卡拉克":  (
        "Karlach from Baldur's Gate 3: tiefling barbarian woman with red skin, "
        "small curved horns, red tail, glowing mechanical heart engine on chest, "
        "heavy armor, wielding a greataxe, fierce grin"
    ),
    "曹":     (
        "a High Elf Fighter archer: fair/pale skin, bright flame-orange upward mohawk hair, "
        "silver and gold ornate plate armor, longbow on back, confident expression"
    ),
    "貓咕咕":  (
        "an Asmodeus Tiefling Sorcerer woman: fair skin, large curved dark-grey horns, "
        "short pink/lavender hair, blue-grey eyes, elegant robes, "
        "arcane energy swirling around hands"
    ),
}

# 角色參考圖（自訂角色用，BG3 原版角色 Gemini 已知故不需要）
CHAR_REF_IMAGES = {
    "曹":    CHARS_DIR / "曹.jpg",
    "貓咕咕": CHARS_DIR / "貓咕咕.png",
}

STYLE_PROMPT = (
    "Draw in the exact same comic book illustration style as the style reference image: "
    "bold cel-shaded outlines, vibrant saturated colors, dramatic dark fantasy backgrounds "
    "(Gothic castle, dungeon, firelight), expressive exaggerated facial reactions, "
    "dynamic poses, strong contrast between light and shadow. "
    "No text, no speech bubbles, no UI elements. "
    "Horizontal composition, wide panel format. "
)


def asArr(v) -> list:
    if isinstance(v, list):
        return v
    return [v] if v else []


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


def load_char_refs(involved: list[str]) -> list[tuple[str, bytes, str]]:
    """回傳需要傳入的角色參考圖：(char_name, bytes, mime_type)"""
    refs = []
    for char in involved:
        p = CHAR_REF_IMAGES.get(char)
        if p and p.exists():
            mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            refs.append((char, p.read_bytes(), mime))
    return refs


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


FORGE_URL = os.environ.get("FORGE_URL", "http://127.0.0.1:7860")


def generate_forge(q: dict, prompt: str, out_path: Path) -> bool:
    """透過本機 Forge/A1111 API 生成圖片，用風格參考圖做 img2img。"""
    import base64, json
    import urllib.request

    style_bytes = load_style_ref()

    neg = (
        "text, speech bubble, watermark, signature, low quality, blurry, "
        "realistic photo, 3d render, nsfw, ugly, deformed, extra limbs"
    )
    payload = {
        "prompt": "(masterpiece, best quality, detailed illustration) " + prompt,
        "negative_prompt": neg,
        "steps": 30,
        "cfg_scale": 7,
        "width": 768,
        "height": 512,
        "sampler_name": "DPM++ 2M Karras",
        "restore_faces": False,
    }
    endpoint = f"{FORGE_URL}/sdapi/v1/txt2img"

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            endpoint, data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read())
        img_bytes = base64.b64decode(result["images"][0])
        save_image(img_bytes, out_path)
        print(f"  ✓ {out_path.name}  {len(img_bytes)//1024}KB")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False


def generate_pollinations(prompt: str, out_path: Path, seed: int = 42) -> bool:
    """透過 Pollinations.ai（免費，Flux 模型）生成圖片。"""
    import urllib.request
    encoded = urllib.parse.quote(prompt, safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=960&height=640&model=flux&nologo=true&seed={seed}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "bg3-journal/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            img_bytes = resp.read()
        save_image(img_bytes, out_path)
        print(f"  ✓ {out_path.name}  {len(img_bytes)//1024}KB")
        return True
    except Exception as e:
        print(f"  ❌ {e}")
        return False


def generate_gemini(q: dict, prompt: str, out_path: Path,
                    client, style_part, gtypes) -> bool:
    """透過 Gemini Image Generation API 生成圖片（需 GEMINI_API_KEY）。"""
    involved  = list(dict.fromkeys(asArr(q.get("from", [])) + asArr(q.get("to", ""))))
    char_refs = load_char_refs(involved)

    if style_part or char_refs:
        parts = []
        if style_part:
            parts.append(style_part)
            parts.append(gtypes.Part.from_text("↑ Style reference image (match this art style exactly)."))
        for char_name, ref_bytes, mime in char_refs:
            parts.append(gtypes.Part.from_bytes(data=ref_bytes, mime_type=mime))
            parts.append(gtypes.Part.from_text(f"↑ Character reference for {char_name} (match this character's appearance)."))
        parts.append(gtypes.Part.from_text("Now generate a new illustration:\n\n" + prompt))
        contents = parts
    else:
        contents = prompt

    resp = client.models.generate_content(
        model=IMG_MODEL,
        contents=contents,
        config=gtypes.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    img_bytes = None
    for part in (resp.candidates[0].content.parts if resp.candidates else []):
        if hasattr(part, "inline_data") and part.inline_data:
            img_bytes = part.inline_data.data
            break

    if img_bytes:
        save_image(img_bytes, out_path)
        print(f"  ✓ {out_path.name}  {len(img_bytes)//1024}KB")
        return True
    print(f"  ⚠ 無圖片回應")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["forge", "pollinations", "gemini"],
                        default="forge",
                        help="圖片生成來源（預設 forge：本機 SD Forge，須先啟動）")
    parser.add_argument("--test",    action="store_true", help="只跑前 5 張測試")
    parser.add_argument("--from",    type=int, dest="from_session", metavar="N",
                        help="從第 N 集開始處理")
    parser.add_argument("--rewrite", type=int, metavar="N",
                        help="強制重跑第 N 集")
    args = parser.parse_args()

    # Forge 檢查
    if args.provider == "forge":
        import urllib.request
        try:
            urllib.request.urlopen(f"{FORGE_URL}/sdapi/v1/sd-models", timeout=5)
            print(f"✓ 使用本機 Forge（{FORGE_URL}）")
        except Exception:
            print(f"❌ 無法連線 Forge（{FORGE_URL}），請先啟動 webui.sh --api")
            sys.exit(1)

    # Gemini 才需要 API key
    client = style_part = gtypes = None
    if args.provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("❌ Gemini 需設定 GEMINI_API_KEY")
            sys.exit(1)
        try:
            import google.genai as genai
            from google.genai import types as _gtypes
            gtypes = _gtypes
        except ImportError:
            print("❌ 請安裝：pip3 install google-genai pillow")
            sys.exit(1)
        client     = genai.Client(api_key=api_key)
        style_bytes = load_style_ref()
        style_part  = gtypes.Part.from_bytes(data=style_bytes, mime_type="image/jpeg") if style_bytes else None
        print(f"✓ 使用 Gemini Image Generation" + (f"（含風格參考圖 {len(style_bytes)//1024}KB）" if style_bytes else ""))
    elif args.provider == "pollinations":
        print("✓ 使用 Pollinations.ai（Flux，免費）")

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
        print(f"✓ 寫入 img_id")

    # 決定目標
    if args.rewrite:
        targets = [q for q in quotes if q.get("session") == args.rewrite]
    elif args.from_session:
        targets = [q for q in quotes if q.get("session", 0) >= args.from_session]
    elif args.test:
        targets = quotes[:5]
    else:
        targets = [q for q in quotes if not (OUT_DIR / f"{q['img_id']}.jpg").exists()]

    print(f"\n共 {len(quotes)} 筆語錄，待生成 {len(targets)} 張\n")
    if not targets:
        print("✓ 全部已生成")
        return

    success = fail = 0
    for i, q in enumerate(targets, 1):
        img_id   = q["img_id"]
        out_path = OUT_DIR / f"{img_id}.jpg"
        prompt   = build_prompt(q)
        label    = f"S{q.get('session',0)}  {str(q.get('quote','') or q.get('desc',''))[:35]}"
        print(f"[{i}/{len(targets)}] {label}")

        try:
            if args.provider == "forge":
                ok = generate_forge(q, prompt, out_path)
            elif args.provider == "pollinations":
                ok = generate_pollinations(prompt, out_path, seed=i * 7)
            else:
                ok = generate_gemini(q, prompt, out_path, client, style_part, gtypes)
            if ok:
                success += 1
            else:
                fail += 1
        except Exception as e:
            print(f"  ❌ {e}")
            fail += 1

        if i < len(targets):
            time.sleep(1 if args.provider == "forge" else (3 if args.provider == "pollinations" else 2))

    print(f"\n完成：✓{success} 張  ❌{fail} 失敗")
    if success:
        print("→ 重新整理網站即可看到插圖（modal 自動載入圖片）")


if __name__ == "__main__":
    main()
