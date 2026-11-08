"""Validate, retain, and render user-selected reminder backgrounds."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError


MAX_FILE_BYTES = 30 * 1024 * 1024
MAX_PIXELS = 50_000_000
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp"}


def load_picture(path: Path) -> Image.Image:
    """Decode a bounded still image without holding the source file open."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("图片不能超过 30 MB")
        with Image.open(path) as opened:
            if opened.format not in EXTENSIONS:
                raise ValueError("请选择 PNG、JPG、WebP 或 BMP 图片")
            width, height = opened.size
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise ValueError("图片尺寸过大，最多支持 5000 万像素")
            opened.load()
            picture = ImageOps.exif_transpose(opened)
            if picture.mode in ("RGBA", "LA") or "transparency" in picture.info:
                layer = Image.new("RGBA", picture.size, (16, 24, 32, 255))
                layer.alpha_composite(picture.convert("RGBA"))
                return layer.convert("RGB")
            return picture.convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError(f"无法读取背景图片：{exc}") from exc


def import_picture(source: Path, data_dir: Path) -> tuple[Path, tuple[int, int]]:
    """Keep a validated copy so removing the original does not break reminders."""
    picture = load_picture(source)
    size = picture.size
    with Image.open(source) as opened:
        extension = EXTENSIONS[opened.format]
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    destination = data_dir / "reminder_images" / f"{digest.hexdigest()[:20]}{extension}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve() and not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination, size


def render_picture(picture: Image.Image, size: tuple[int, int], mode: str) -> Image.Image:
    """Preserve aspect ratio; keep small pictures crisp in smart/contain modes."""
    width, height = size
    if width <= 0 or height <= 0:
        raise ValueError("显示器尺寸无效")
    if mode not in ("smart", "cover", "contain"):
        raise ValueError("提醒背景适配方式无效")
    fit_mode = "contain" if mode == "smart" and (
        picture.width < width or picture.height < height) else mode
    if fit_mode == "cover":
        result = ImageOps.fit(picture, size, method=Image.Resampling.LANCZOS)
        return ImageEnhance.Brightness(result).enhance(0.55)

    backdrop = ImageOps.fit(picture, size, method=Image.Resampling.LANCZOS)
    backdrop = backdrop.filter(ImageFilter.GaussianBlur(max(12, min(size) // 45)))
    backdrop = ImageEnhance.Brightness(backdrop).enhance(0.38)
    scale = min(1.0, width / picture.width, height / picture.height)
    foreground = picture.resize((max(1, round(picture.width * scale)),
                                 max(1, round(picture.height * scale))),
                                Image.Resampling.LANCZOS)
    foreground = ImageEnhance.Brightness(foreground).enhance(0.8)
    x = (width - foreground.width) // 2
    y = (height - foreground.height) // 2
    backdrop.paste(foreground, (x, y))
    return backdrop
