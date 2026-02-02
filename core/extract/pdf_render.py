"""
PDF to image rendering using PyMuPDF (fitz).

This module renders PDF pages to PIL images for OCR processing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import fitz  # PyMuPDF
from PIL import Image


# -------------------------------------------------------------------
# Data Classes
# -------------------------------------------------------------------
@dataclass
class RenderedPage:
    """
    A rendered PDF page as a PIL image.

    Attributes:
        image: PIL Image of the rendered page
        page_index: Zero-based page number
        width: Image width in pixels
        height: Image height in pixels
    """
    image: Image.Image
    page_index: int
    width: int
    height: int


# -------------------------------------------------------------------
# PDF Rendering
# -------------------------------------------------------------------
def render_pdf_to_images(
    pdf_bytes: bytes,
    target_dpi: int = 300,
) -> List[RenderedPage]:
    """
    Render each page of a PDF to a PIL Image at the specified DPI.

    Args:
        pdf_bytes: Raw bytes of the PDF file
        target_dpi: Resolution for rendering (default 300 DPI for OCR)

    Returns:
        List of RenderedPage objects, one per PDF page
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: List[RenderedPage] = []

    # Calculate zoom factor (72 is default PDF DPI)
    zoom = target_dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for page_index in range(len(doc)):
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=matrix)

        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        pages.append(RenderedPage(
            image=img,
            page_index=page_index,
            width=pix.width,
            height=pix.height,
        ))

    doc.close()
    return pages
