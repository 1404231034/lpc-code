"""PDF 解析 — 提取文本和页面图像"""

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PDFPage:
    """PDF 单页内容"""
    page_num: int
    text: str
    has_images: bool = False


@dataclass
class PDFContent:
    """PDF 完整内容"""
    path: str
    total_pages: int
    pages: list[PDFPage] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """获取所有页面的文本"""
        return "\n\n".join(
            f"--- 第 {p.page_num + 1} 页 ---\n{p.text}"
            for p in self.pages
            if p.text.strip()
        )


def parse_pdf(path: str, max_pages: int | None = None) -> PDFContent:
    """
    解析 PDF 文件，提取文本和页面信息。

    Args:
        path: PDF 文件路径
        max_pages: 最大解析页数 (None 表示全部)

    Returns:
        PDFContent
    """
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 文件不存在: {path}")

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    pages_to_read = min(total_pages, max_pages) if max_pages else total_pages

    content = PDFContent(path=str(pdf_path), total_pages=total_pages)

    for i in range(pages_to_read):
        page = doc[i]
        text = page.get_text("text")

        # 检测页面是否包含图像
        images = page.get_images(full=True)
        has_images = len(images) > 0

        content.pages.append(PDFPage(
            page_num=i,
            text=text.strip(),
            has_images=has_images,
        ))

    doc.close()
    logger.info(f"PDF 解析完成: {pages_to_read}/{total_pages} 页")
    return content


def extract_page_image(path: str, page_num: int, dpi: int = 150) -> Any:
    """
    将 PDF 指定页面渲染为 PIL Image。

    Args:
        path: PDF 文件路径
        page_num: 页码 (0-indexed)
        dpi: 渲染 DPI

    Returns:
        PIL Image 对象
    """
    from PIL import Image

    doc = fitz.open(path)
    if page_num >= len(doc):
        doc.close()
        raise ValueError(f"页码 {page_num} 超出范围 (共 {len(doc)} 页)")

    page = doc[page_num]
    # 渲染为像素图
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)

    # 转为 PIL Image
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img


def build_pdf_messages(
    pdf_content: PDFContent,
    question: str = "请分析这个文档",
) -> list[dict[str, Any]]:
    """
    将 PDF 内容构建为消息列表。

    纯文本页合并注入 prompt，有图像的页走图像通道。

    Args:
        pdf_content: 解析后的 PDF 内容
        question: 用户问题

    Returns:
        消息列表
    """
    from .image import preprocess_image

    # 收集所有文本
    text_parts = []
    image_pages = []

    for page in pdf_content.pages:
        if page.text.strip():
            text_parts.append(f"[第 {page.page_num + 1} 页]\n{page.text}")
        if page.has_images:
            image_pages.append(page.page_num)

    # 构建内容
    content_parts = []

    # 文本部分
    if text_parts:
        full_text = "\n\n".join(text_parts)
        # 限制文本长度
        max_chars = 30000
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + f"\n\n... (文档过长，已截断)"
        content_parts.append({"type": "text", "text": f"文档内容:\n{full_text}\n\n问题: {question}"})
    else:
        content_parts.append({"type": "text", "text": question})

    # 图像页（限制数量避免上下文过长）
    max_image_pages = 3
    for page_num in image_pages[:max_image_pages]:
        try:
            img = extract_page_image(pdf_content.path, page_num)
            processed = preprocess_image(img)
            content_parts.insert(len(content_parts) - 1, {"type": "image", "image": processed})
        except Exception as e:
            logger.warning(f"提取第 {page_num + 1} 页图像失败: {e}")

    return [{"role": "user", "content": content_parts}]
