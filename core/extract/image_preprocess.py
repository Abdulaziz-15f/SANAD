from __future__ import annotations

import math
from PIL import Image, ImageOps, ImageFilter
import numpy as np


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """
    Preprocessing tuned for engineering drawings:
      - grayscale
      - auto-contrast
      - mild denoise
      - adaptive threshold-ish (fast)
    """
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g)

    # Mild denoise; avoid destroying thin lines.
    g = g.filter(ImageFilter.MedianFilter(size=3))

    arr = np.array(g, dtype=np.uint8)

    # Fast adaptive-ish threshold using local mean via downsample trick.
    # Keeps text readable on noisy scans.
    small = Image.fromarray(arr).resize((max(1, arr.shape[1] // 4), max(1, arr.shape[0] // 4)))
    small_arr = np.array(small, dtype=np.float32)
    small_blur = Image.fromarray(small_arr.astype(np.uint8)).filter(ImageFilter.GaussianBlur(radius=3))
    mean = np.array(small_blur, dtype=np.float32)

    mean_up = Image.fromarray(mean.astype(np.uint8)).resize((arr.shape[1], arr.shape[0]))
    mean_up_arr = np.array(mean_up, dtype=np.float32)

    # Threshold: pixel is text if darker than local mean - offset
    offset = 12.0
    bw = (arr < (mean_up_arr - offset)).astype(np.uint8) * 255

    out = Image.fromarray(bw, mode="L")
    return out
