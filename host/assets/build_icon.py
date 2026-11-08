"""Regenerate crisp Smart Coaster icons for Windows taskbar DPI sizes."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import struct

from PIL import Image, ImageDraw


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def large_icon() -> Image.Image:
    size = 1024
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((0, 0, 1023, 1023), radius=225, fill="#101820")
    draw.ellipse((120, 120, 904, 904), fill="#1A303B")
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
    return icon


def small_icon(size: int) -> Image.Image:
    """Draw the cup on the final pixel grid instead of shrinking fine detail."""
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((0, 0, size - 1, size - 1),
                           radius=max(3, round(size * 0.22)), fill="#101820")
    center = size // 2
    drop_top = max(2, round(size * 0.12))
    drop_bottom = round(size * 0.33)
    drop_half = max(1, round(size * 0.065))
    draw.polygon([(center, drop_top), (center - drop_half, drop_bottom - 1),
                  (center + drop_half, drop_bottom - 1)], fill="#65D6A6")
    draw.ellipse((center - drop_half, drop_bottom - drop_half,
                  center + drop_half, drop_bottom), fill="#65D6A6")

    rim_y = round(size * 0.39)
    bottom_y = round(size * 0.83)
    left = round(size * 0.24)
    right = size - left - 1
    bottom_left = round(size * 0.31)
    bottom_right = size - bottom_left - 1
    stroke = max(2, round(size * 0.075))
    water_y = round(size * 0.59)
    draw.polygon([(left + stroke, water_y), (right - stroke, water_y),
                  (bottom_right - 1, bottom_y - stroke),
                  (bottom_left + 1, bottom_y - stroke)], fill="#5FB9DC")
    draw.line([(left, rim_y), (bottom_left, bottom_y),
               (bottom_right, bottom_y), (right, rim_y)],
              fill="#F4F2EA", width=stroke, joint="curve")
    draw.line([(left - 1, rim_y), (right + 1, rim_y)],
              fill="#F4F2EA", width=stroke)
    return icon


def write_ico(path: Path, frames: list[tuple[int, Image.Image]]) -> None:
    """Store an independently rendered PNG frame for each Windows icon size."""
    payloads = []
    for _size, frame in frames:
        buffer = BytesIO()
        frame.save(buffer, format="PNG")
        payloads.append(buffer.getvalue())
    directory = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    offset = 6 + 16 * len(frames)
    for (size, _frame), payload in zip(frames, payloads):
        directory.extend(struct.pack("<BBBBHHII", size if size < 256 else 0,
                                     size if size < 256 else 0, 0, 0, 1, 32,
                                     len(payload), offset))
        offset += len(payload)
    path.write_bytes(bytes(directory) + b"".join(payloads))


def main() -> None:
    output = Path(__file__).parent
    master = large_icon()
    frames = [(size, small_icon(size) if size <= 40 else
               master.resize((size, size), Image.Resampling.LANCZOS))
              for size in ICON_SIZES]
    frames[-1][1].save(output / "coaster.png")
    write_ico(output / "coaster.ico", frames)


if __name__ == "__main__":
    main()
