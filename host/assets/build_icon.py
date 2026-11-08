"""Regenerate crisp Smart Coaster icons for Windows taskbar DPI sizes."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import struct

from PIL import Image, ImageDraw


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def large_icon() -> Image.Image:
    size = 1024
    ramp = Image.new("RGB", (1, size))
    start, end = (248, 253, 254), (215, 239, 245)
    for y in range(size):
        fraction = y / (size - 1)
        ramp.putpixel((0, y), tuple(round(a + (b - a) * fraction)
                                     for a, b in zip(start, end)))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, size - 9, size - 9),
                                            radius=226, fill=255)
    icon = ramp.resize((size, size)).convert("RGBA")
    icon.putalpha(mask)
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((8, 8, size - 9, size - 9), radius=226,
                           outline="#B6DCE6", width=12)
    draw.polygon([(252, 308), (772, 308), (699, 754), (325, 754)],
                 fill="#F7FDFF")
    draw.polygon([(291, 510), (404, 497), (523, 512), (643, 499),
                  (733, 508), (686, 713), (338, 713)], fill="#4DBDD9")
    draw.line([(263, 324), (327, 754), (697, 754), (761, 324)],
              fill="#23546A", width=46, joint="curve")
    draw.line([(238, 310), (786, 310)], fill="#23546A", width=48)
    draw.ellipse((214, 286, 262, 334), fill="#23546A")
    draw.ellipse((762, 286, 810, 334), fill="#23546A")
    return icon


def small_icon(size: int) -> Image.Image:
    """Keep the cup legible on the final taskbar pixel grid."""
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle((0, 0, size - 1, size - 1),
                           radius=max(3, round(size * 0.22)), fill="#E3F3F7")
    rim = round(size * 0.29)
    bottom = round(size * 0.78)
    left, right = round(size * 0.23), round(size * 0.77)
    foot_left, foot_right = round(size * 0.30), round(size * 0.70)
    stroke = max(1, round(size * 0.075))
    draw.polygon([(left, rim), (right, rim), (foot_right, bottom),
                  (foot_left, bottom)], fill="#F7FDFF")
    draw.polygon([(left + stroke, round(size * 0.52)),
                  (right - stroke, round(size * 0.52)),
                  (foot_right - stroke, bottom - stroke),
                  (foot_left + stroke, bottom - stroke)], fill="#4DBDD9")
    draw.line([(left, rim), (foot_left, bottom), (foot_right, bottom),
               (right, rim)], fill="#23546A", width=stroke, joint="curve")
    draw.line([(left - 1, rim), (right + 1, rim)],
              fill="#23546A", width=stroke)
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
