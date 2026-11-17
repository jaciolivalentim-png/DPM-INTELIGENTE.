"""Optional isolated OCR HTTP service. Deploy on separate authorized infrastructure."""
import os
import hmac
import io
import logging
from flask import Flask, request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from image_service import MAX_PIXELS

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024

@app.post('/ocr')
def ocr():
    token = os.environ.get('DPM_OCR_REMOTE_TOKEN', '')
    provided = request.headers.get('Authorization', '')
    if not token or not hmac.compare_digest(provided, 'Bearer ' + token):
        return Response('Não autorizado', status=401)
    if request.mimetype != 'image/png':
        return Response('Formato inválido', status=415)
    try:
        with Image.open(io.BytesIO(request.get_data())) as source:
            if source.format != 'PNG' or source.width * source.height > MAX_PIXELS:
                return Response('Imagem inválida', status=400)
            image = ImageOps.exif_transpose(source).convert('RGB')
        from image_service import recognize_image
        # Worker process local on the separate OCR instance, never recursive remote call.
        os.environ['DPM_OCR_MODE'] = 'on'
        try:
            text = recognize_image(image)
        finally:
            image.close()
        return Response(text, mimetype='text/plain; charset=utf-8')
    except (UnidentifiedImageError, OSError, ValueError):
        logging.exception('Falha de OCR remoto')
        return Response('OCR não concluído', status=422)

@app.get('/health')
def health():
    return Response('ok', mimetype='text/plain')
