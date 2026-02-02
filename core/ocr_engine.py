import json
from pathlib import Path

import cv2

def extract_text(
    image_path: str,
    engine: str = "easy",
    lang_mode: str = "en",
    min_conf: float = 0.0,
    save_json: str | None = None,
):
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError("Failed to read image.")

    results = []
    used_engine = engine
    note = None

    def run_easy():
        nonlocal results, used_engine, note
        try:
            import easyocr
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "easyocr is not installed. Run: pip install easyocr"
            )

        langs = (
            ["en"]
            if lang_mode == "en"
            else (["ar"] if lang_mode == "ar" else ["en", "ar"])
        )
        reader = easyocr.Reader(langs, gpu=False)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        ocr_results = reader.readtext(gray, detail=1)
        for _, text, conf in ocr_results:
            if float(conf) >= float(min_conf):
                results.append({"text": text, "confidence": float(conf)})

        used_engine = "easy"

    def run_paddle(paddle_lang: str):
        nonlocal results, used_engine, note
        try:
            from paddleocr import PaddleOCR
        except ModuleNotFoundError:
            note = "PaddleOCR is not installed. Falling back to EasyOCR."
            run_easy()
            return

        ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang, show_log=False)
        ocr_results = ocr.ocr(img, cls=True)

        if ocr_results and ocr_results[0]:
            for line in ocr_results[0]:
                text, conf = line[1]
                if float(conf) >= float(min_conf):
                    results.append({"text": text, "confidence": float(conf)})

        used_engine = "paddle"

    if engine == "paddle":
        if lang_mode == "ar":
            run_paddle("arabic")
        else:
            run_paddle("en")
    else:
        run_easy()

    output = {
        "image": str(image_path),
        "requested_engine": engine,
        "used_engine": used_engine,
        "language": lang_mode,
        "count": len(results),
        "texts": results,
    }
    if note:
        output["note"] = note

    if save_json:
        with open(save_json, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    return output

