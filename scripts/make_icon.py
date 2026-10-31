"""Regenerate airdebug/resources/icon.png and icon.ico (needs Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "airdebug" / "resources"
S = 512


def draw(connected: bool = True) -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (61, 220, 132, 255) if connected else (140, 150, 160, 255)  # Android green / grey
    d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=bg)
    # phone body
    d.rounded_rectangle((176, 196, 336, 452), radius=26, fill=(255, 255, 255, 255))
    d.rounded_rectangle((192, 224, 320, 412), radius=8, fill=bg)
    d.ellipse((246, 422, 266, 442), fill=bg)
    # wireless arcs above the phone
    cx, cy = 256, 196
    for r in (60, 110, 160):
        w = 26
        d.arc((cx - r, cy - r, cx + r, cy + r), start=225, end=315, fill=(255, 255, 255, 255), width=w)
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    on = draw(True)
    on.save(OUT / "icon.png")
    on.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    draw(False).save(OUT / "icon_off.png")
    print("written to", OUT)
