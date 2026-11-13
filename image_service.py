"""OCR local para JPG e PNG. Não envia imagens para serviços externos."""
from PIL import Image, ImageOps, UnidentifiedImageError
from rapidocr_onnxruntime import RapidOCR

_ocr = None
MAX_PIXELS = 18_000_000

def extract_text_from_image(path):
    global _ocr
    try:
        with Image.open(path) as original:
            if original.format not in ("JPEG", "PNG"):
                raise ValueError("O conteúdo do arquivo não é JPG ou PNG válido.")
            if original.width * original.height > MAX_PIXELS:
                raise ValueError("Imagem muito grande. Limite: 18 megapixels.")
            image = ImageOps.exif_transpose(original).convert("RGB")
            # OCR em memória; sem retenção da imagem.
            import numpy as np
            pixels = np.asarray(image)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Não foi possível abrir a imagem. Envie JPG ou PNG válido.")
    if _ocr is None:
        _ocr = RapidOCR()
    results, _ = _ocr(pixels)
    text = "\n".join(str(item[1]) for item in (results or []) if len(item) > 1).strip()
    if not text:
        raise ValueError("Nenhum texto legível foi encontrado na imagem. Tente uma foto mais nítida.")
    return {"text": text, "pages": 1}
