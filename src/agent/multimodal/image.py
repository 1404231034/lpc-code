"""图像预处理 — 加载、缩放、构建多模态消息"""

import base64
import io
import logging
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# Gemma4 支持的图像尺寸
DEFAULT_MAX_SIZE = 1024
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def load_image(path: str) -> Image.Image:
    """
    加载图像文件。

    Args:
        path: 图像文件路径

    Returns:
        PIL Image 对象
    """
    img_path = Path(path)
    if not img_path.exists():
        raise FileNotFoundError(f"图像文件不存在: {path}")
    if img_path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的图像格式: {img_path.suffix}，支持: {SUPPORTED_FORMATS}")

    image = Image.open(img_path)
    # 转换为 RGB（处理 RGBA/灰度等）
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image


def preprocess_image(
    image: Image.Image,
    max_size: int = DEFAULT_MAX_SIZE,
) -> Image.Image:
    """
    预处理图像：缩放到模型支持的尺寸。

    Args:
        image: PIL Image 对象
        max_size: 最大边长

    Returns:
        处理后的 PIL Image
    """
    w, h = image.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        logger.debug(f"图像缩放: {w}x{h} -> {new_w}x{new_h}")

    return image


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """将 PIL Image 转为 base64 字符串"""
    buffer = io.BytesIO()
    image.save(buffer, format=format)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def build_image_message(
    image: Image.Image,
    text: str = "",
) -> dict[str, Any]:
    """
    构建多模态消息（图像 + 文本）。

    Args:
        image: PIL Image 对象
        text: 附加文本

    Returns:
        OpenAI 风格的多模态消息
    """
    processed = preprocess_image(image)

    content_parts = [{"type": "image", "image": processed}]
    if text:
        content_parts.append({"type": "text", "text": text})

    return {
        "role": "user",
        "content": content_parts,
    }


def load_and_preprocess(path: str, text: str = "") -> dict[str, Any]:
    """一步完成：加载图像 + 预处理 + 构建消息"""
    image = load_image(path)
    return build_image_message(image, text)
