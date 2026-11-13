"""OCR local para JPG, PNG e páginas de PDF, sem API externa."""
from PIL import Image, ImageOps, UnidentifiedImageError

_ocr = None
MAX_PIXELS = 18_000_000


def recognize_image(image):
    global _ocr
    if image.width * image.height > MAX_PIXELS:
        raise ValueError('Imagem muito grande para OCR (limite: 18 megapixels).')
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    if _ocr is None:
        _ocr = RapidOCR()
    result, _ = _ocr(np.asarray(image.convert('RGB')))
    return '\n'.join(str(item[1]) for item in (result or []) if len(item) > 1).strip()


def extract_text_from_image(path):
    try:
        with Image.open(path) as original:
            if original.format not in ('JPEG', 'PNG'):
                raise ValueError('O conteúdo do arquivo não é JPG ou PNG válido.')
            if original.width * original.height > MAX_PIXELS:
                raise ValueError('Imagem muito grande. Limite: 18 megapixels.')
            image = ImageOps.exif_transpose(original).convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Não foi possível abrir a imagem. Envie JPG ou PNG válido.') from exc
    text = recognize_image(image)
    if not text:
        raise ValueError('Nenhum texto legível foi encontrado na imagem. Tente uma foto mais nítida.')
    return {'text': text, 'pages': 1}
