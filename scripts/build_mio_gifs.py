#!/usr/bin/env python3
"""Rebuild the nine Mio animations from the canonical WebP sprite sheet."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


FRAME_WIDTH = 192
FRAME_HEIGHT = 208

# Each animation occupies one 208px-high row. Frames are 192px wide.
ANIMATIONS = {
    "idle.gif": (0, [280, 110, 110, 140, 140, 320]),
    "running-right.gif": (1, [120, 120, 120, 120, 120, 120, 120, 220]),
    "running-left.gif": (2, [120, 120, 120, 120, 120, 120, 120, 220]),
    "waving.gif": (3, [140, 140, 140, 280]),
    "jumping.gif": (4, [140, 140, 140, 140, 280]),
    "failed.gif": (5, [140, 140, 140, 140, 140, 140, 140, 240]),
    "waiting.gif": (6, [150, 150, 150, 150, 150, 260]),
    "running.gif": (7, [120, 120, 120, 120, 120, 220]),
    "review.gif": (8, [150, 150, 150, 150, 150, 280]),
}


def gif_palette_frame(frame: Image.Image) -> Image.Image:
    """Use 255 adaptive colors and reserve palette index 255 for transparency."""

    rgba = frame.convert("RGBA")
    rgb = Image.new("RGB", rgba.size, (255, 255, 255))
    rgb.paste(rgba, mask=rgba.getchannel("A"))
    quantized = rgb.quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG,
    )

    alpha = rgba.getchannel("A").tobytes()
    pixels = bytearray(quantized.tobytes())
    for index, opacity in enumerate(alpha):
        if opacity < 96:
            pixels[index] = 255

    result = Image.frombytes("P", rgba.size, bytes(pixels))
    palette = (quantized.getpalette() or [])[: 255 * 3]
    result.putpalette(palette + [0, 0, 0] + [0] * (768 - len(palette) - 3))
    result.info["transparency"] = 255
    result.info["disposal"] = 2
    return result


def build(sprite_path: Path, output_dir: Path, scale: int = 2) -> None:
    sheet = Image.open(sprite_path).convert("RGBA")
    expected_size = (FRAME_WIDTH * 8, FRAME_HEIGHT * 9)
    if sheet.size != expected_size:
        raise ValueError(f"Expected sprite sheet {expected_size}, got {sheet.size}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, (row, durations) in ANIMATIONS.items():
        frames = []
        for column in range(len(durations)):
            bounds = (
                column * FRAME_WIDTH,
                row * FRAME_HEIGHT,
                (column + 1) * FRAME_WIDTH,
                (row + 1) * FRAME_HEIGHT,
            )
            frame = sheet.crop(bounds)
            if scale > 1:
                frame = frame.resize(
                    (FRAME_WIDTH * scale, FRAME_HEIGHT * scale),
                    Image.Resampling.LANCZOS,
                )
            frames.append(gif_palette_frame(frame))

        target = output_dir / filename
        frames[0].save(
            target,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
            transparency=255,
            optimize=False,
        )
        print(f"Built {target} ({len(frames)} frames)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sprite_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--scale", type=int, default=2, choices=(1, 2, 3))
    args = parser.parse_args()
    build(args.sprite_path, args.output_dir, args.scale)


if __name__ == "__main__":
    main()
