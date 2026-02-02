from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.extract.pdf_render import render_pdf_to_images
from core.extract.image_preprocess import preprocess_for_ocr


def _to_bgr(page_obj) -> np.ndarray:
    """
    Normalize whatever render_pdf_to_images() returns into a BGR numpy image for OpenCV.
    This keeps the debug script resilient if you change the renderer later.
    """
    # Common patterns: page.image_bytes / page.png_bytes / page.image (bytes)
    for attr in ("image_bytes", "png_bytes", "bytes", "image"):
        if hasattr(page_obj, attr):
            data = getattr(page_obj, attr)
            if isinstance(data, (bytes, bytearray)):
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    return img

    # If the renderer returns a PIL image
    if hasattr(page_obj, "pil"):
        pil_img = page_obj.pil
        rgb = np.array(pil_img)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # If the renderer returns a numpy image directly
    if isinstance(page_obj, np.ndarray):
        img = page_obj
        if img.ndim == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        return img

    raise TypeError(f"Unsupported rendered page type: {type(page_obj)}")


def main() -> None:
    pdf_path = Path(
        "/Users/mohammedalharbi/Documents/HACKATHONS/UTURETHON/SANAD/data/pdfs/System 1 AC&DC SLD-Model-Model.pdf"
    )

    pdf_bytes = pdf_path.read_bytes()
    pages = render_pdf_to_images(pdf_bytes)

    # Keep the first pages for debugging so you don't waste time.
    pages = pages[:3]
    print(f"Rendered pages: {len(pages)}")

    # Lazy import so you don't pay import cost if rendering fails
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="en",
        show_log=False,
    )

    for i, p in enumerate(pages):
        bgr = _to_bgr(p)

        # Your preprocess function should return an OCR-friendly image
        bgr_pp = preprocess_for_ocr(bgr)

        # PaddleOCR expects RGB
        rgb = cv2.cvtColor(bgr_pp, cv2.COLOR_BGR2RGB)

        result = ocr.ocr(rgb, cls=True)

        print("\n" + "=" * 80)
        print(f"PAGE {i}")
        print("=" * 80)

        # result format: [[ [box, (text, conf)], ... ]]
        lines = result[0] if result else []
        # Sort top-to-bottom, left-to-right for readability
        def _y_then_x(item):
            box = item[0]
            ys = [pt[1] for pt in box]
            xs = [pt[0] for pt in box]
            return (min(ys), min(xs))

        lines = sorted(lines, key=_y_then_x)

        # Print the most useful lines first
        shown = 0
        for box, (text, conf) in lines:
            t = (text or "").strip()
            if not t:
                continue

            # Filter obvious garbage
            if len(t) < 2 and not any(ch.isdigit() for ch in t):
                continue

            print(f"{conf:0.2f}  {t}")
            shown += 1
            if shown >= 60:  # enough to confirm if OCR is working
                break


if __name__ == "__main__":
    main()
