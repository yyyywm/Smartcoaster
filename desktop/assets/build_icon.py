"""Regenerate a high-contrast Smart Coaster icon for Windows DPI sizes."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import struct

from PIL import Image, ImageDraw


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def large_icon() -> Image.Image:
    size = 1024
    ramp = Image.new("RGB", (1, size))
    start, end = (24, 153, 187), (7, 101, 143)
    for y in range(size):
        fraction = y / (size - 1)
        ramp.putpixel((0, y), tuple(round(a + (b - a) * fraction)
                                     for a, b in zip(start, end)))
    tile = ramp.resize((size, size)).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((5, 5, 1018, 1018),
                                            radius=224, fill=255)
    tile.putalpha(mask)
    icon = tile
    draw = ImageDraw.Draw(icon)
    draw.polygon([(211, 225), (813, 225), (705, 817), (319, 817)],
                 fill="#F8FCFD")
    draw.polygon([(259, 494), (384, 485), (516, 497), (641, 486),
                  (765, 494), (696, 782), (328, 782)], fill="#73D9E9")
    draw.rounded_rectangle((188, 195, 836, 280), radius=42, fill="#F8FCFD")
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
    frames = [(size, master.resize((size, size), Image.Resampling.LANCZOS))
              for size in ICON_SIZES]
    frames[-1][1].save(output / "coaster.png")
    write_ico(output / "coaster.ico", frames)


if __name__ == "__main__":
    main()
