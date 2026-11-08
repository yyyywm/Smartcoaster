"""Regenerate the Smart Coaster PNG and Windows ICO from simple vector shapes."""
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    size = 1024
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((0, 0, 1023, 1023), radius=225, fill="#101820")
    draw.ellipse((120, 120, 904, 904), fill="#1A303B")

    # A single drop above a glass remains legible at taskbar size.
    draw.polygon([(512, 146), (426, 266), (435, 324), (471, 359),
                  (512, 373), (553, 359), (589, 324), (598, 266)],
                 fill="#65D6A6")
    draw.ellipse((426, 258, 598, 377), fill="#65D6A6")
    draw.ellipse((467, 287, 487, 307), fill="#D4FFF0")

    draw.polygon([(337, 560), (446, 542), (560, 560), (681, 537),
                  (650, 760), (374, 760)], fill="#5FB9DC")
    draw.line([(285, 400), (326, 775), (354, 808), (670, 808),
               (698, 775), (739, 400)], fill="#F4F2EA", width=43,
              joint="curve")
    draw.line([(274, 398), (750, 398)], fill="#F4F2EA", width=43)

    output = Path(__file__).parent
    base = icon.resize((256, 256), Image.Resampling.LANCZOS)
    base.save(output / "coaster.png")
    base.save(output / "coaster.ico", format="ICO",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                     (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
