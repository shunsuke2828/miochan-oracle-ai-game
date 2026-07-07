#!/usr/bin/env python3
from __future__ import annotations

import html
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
PREVIEW_ROOT = ROOT / "previews" / "mio-generated-v1"
SHEET_DIR = PREVIEW_ROOT / "source-sheets"
GIF_DIR = PREVIEW_ROOT / "gifs"
CONTACT_DIR = PREVIEW_ROOT / "contact-sheet"

ANIMATIONS = (
    ("anxious", "不安・緊張", "ゲーム開始／困り度が高いとき"),
    ("overwhelmed", "仕事を抱えすぎ", "タスク過多の設問"),
    ("thinking", "考え中・混乱", "回答を考えているとき"),
    ("relieved", "安心・ほっとする", "良いアドバイスを受けたとき"),
    ("presentation", "発表の練習", "プレゼン関連の設問"),
    ("time-pressure", "時間切迫", "残り時間が少ないとき"),
    ("idea", "ひらめき", "具体的な行動案を理解したとき"),
    ("celebrate", "成功・お祝い", "高得点／ゲームクリア"),
    ("listening", "傾聴", "自由記述を入力・評価中"),
    ("retry", "やさしく再挑戦", "低品質・無効回答のとき"),
)


def gif_palette(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    alpha = rgba.getchannel("A")
    paletted = rgba.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    transparent = Image.new("L", rgba.size, 255)
    transparent.paste(0, mask=alpha.point(lambda value: 255 if value <= 24 else 0))
    paletted.paste(255, mask=transparent.point(lambda value: 255 if value == 0 else 0))
    palette = paletted.getpalette() or []
    palette.extend([0] * (768 - len(palette)))
    paletted.putpalette(palette[:768])
    paletted.info["transparency"] = 255
    paletted.info["disposal"] = 2
    return paletted


def split_sheet(path: Path) -> list[Image.Image]:
    sheet = Image.open(path).convert("RGBA")
    frames: list[Image.Image] = []
    target = (384, 512)
    for row in range(2):
        for column in range(4):
            left = round(column * sheet.width / 4)
            right = round((column + 1) * sheet.width / 4)
            top = round(row * sheet.height / 2)
            bottom = round((row + 1) * sheet.height / 2)
            crop = sheet.crop((left, top, right, bottom))
            scale = min(target[0] / crop.width, target[1] / crop.height)
            resized = crop.resize(
                (round(crop.width * scale), round(crop.height * scale)),
                Image.Resampling.LANCZOS,
            )
            canvas = Image.new("RGBA", target, (0, 0, 0, 0))
            canvas.alpha_composite(
                resized,
                ((target[0] - resized.width) // 2, (target[1] - resized.height) // 2),
            )
            frames.append(canvas)
    return frames


def build_gif(name: str) -> Path:
    frames = split_sheet(SHEET_DIR / f"{name}-alpha.png")
    output = GIF_DIR / f"{name}.gif"
    gif_frames = [gif_palette(frame) for frame in frames]
    gif_frames[0].save(
        output,
        save_all=True,
        append_images=gif_frames[1:],
        loop=0,
        duration=150,
        disposal=2,
        transparency=255,
        optimize=False,
    )
    return output


def build_contact_sheet() -> None:
    card_width, card_height = 330, 410
    contact = Image.new("RGB", (card_width * 5, card_height * 2), "#f6f1ea")
    draw = ImageDraw.Draw(contact)
    font = ImageFont.load_default()
    for index, (name, label, usage) in enumerate(ANIMATIONS):
        gif = Image.open(GIF_DIR / f"{name}.gif").convert("RGBA")
        gif.thumbnail((280, 320), Image.Resampling.LANCZOS)
        x = index % 5 * card_width
        y = index // 5 * card_height
        draw.rounded_rectangle(
            (x + 10, y + 10, x + card_width - 10, y + card_height - 10),
            radius=20,
            fill="#ffffff",
            outline="#ded4ca",
            width=2,
        )
        contact.paste(gif, (x + (card_width - gif.width) // 2, y + 20), gif)
        draw.text((x + 24, y + 340), f"{name}", fill="#c74634", font=font)
        draw.text((x + 24, y + 362), "8 frames | 384 x 512", fill="#172033", font=font)
        draw.text((x + 24, y + 382), "transparent looping GIF", fill="#687281", font=font)
    contact.save(CONTACT_DIR / "all-first-frames.png", quality=95)


def build_html() -> None:
    cards = []
    for name, label, usage in ANIMATIONS:
        cards.append(
            f"""
            <article>
              <div class="checker"><img src="../gifs/{html.escape(name)}.gif" alt="{html.escape(label)}" /></div>
              <h2>{html.escape(label)}</h2>
              <code>{html.escape(name)}.gif</code>
              <p>{html.escape(usage)}</p>
            </article>
            """
        )
    (PREVIEW_ROOT / "index.html").write_text(
        """<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>みおちゃん GIF候補 v1</title><style>
        :root{font-family:Inter,'Yu Gothic',sans-serif;color:#172033;background:#f6f1ea}body{max-width:1500px;margin:auto;padding:32px}header{margin-bottom:24px}h1{margin:0;font-size:32px}header p{color:#687281}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px}article{padding:16px;border:1px solid #ded4ca;border-radius:20px;background:white;box-shadow:0 12px 30px #49342212}.checker{height:320px;display:grid;place-items:center;border-radius:14px;background-color:#fff;background-image:linear-gradient(45deg,#e8e8e8 25%,transparent 25%),linear-gradient(-45deg,#e8e8e8 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#e8e8e8 75%),linear-gradient(-45deg,transparent 75%,#e8e8e8 75%);background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0}.checker img{width:240px;height:320px;object-fit:contain}h2{margin:14px 0 5px;font-size:18px}code{color:#c74634}article p{margin:8px 0 0;color:#687281;font-size:13px}</style></head><body><header><h1>みおちゃん GIFアニメーション候補 v1</h1><p>10種類・各8フレーム。システム未反映の確認用です。</p></header><main class="grid">"""
        + "".join(cards)
        + "</main></body></html>",
        encoding="utf-8",
    )


def main() -> None:
    GIF_DIR.mkdir(parents=True, exist_ok=True)
    CONTACT_DIR.mkdir(parents=True, exist_ok=True)
    for name, _label, _usage in ANIMATIONS:
        build_gif(name)
    build_contact_sheet()
    build_html()
    print(f"Built {len(ANIMATIONS)} GIF previews in {PREVIEW_ROOT}")


if __name__ == "__main__":
    main()
