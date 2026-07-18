from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "public" / "papermorrow-logo.png"
OUTPUT = ROOT / "desktop" / "icons"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as source:
        image = source.convert("RGBA")
        side = max(image.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))
        canvas.save(OUTPUT / "PaperMorrow.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        canvas.resize((1024, 1024), Image.Resampling.LANCZOS).save(OUTPUT / "PaperMorrow.icns")
    print(f"Desktop icons written to {OUTPUT}")


if __name__ == "__main__":
    main()
