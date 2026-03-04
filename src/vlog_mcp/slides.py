from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def render_slide_to_image(markdown_path: str, output_path: str, width: int = 1920, height: int = 1080) -> str:
    md = Path(markdown_path).read_text(encoding="utf-8")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", (width, height), color=(18, 18, 25))
    draw = ImageDraw.Draw(image)

    y = 60
    for line in md.splitlines():
        if not line.strip():
            y += 18
            continue
        if line.startswith("# "):
            draw.text((70, y), line[2:], fill=(245, 245, 245))
            y += 52
        else:
            draw.text((90, y), line, fill=(210, 210, 210))
            y += 34

    image.save(out, format="PNG")
    return str(out)
