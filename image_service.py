"""OCR isolado: falhas do motor não derrubam o servidor web."""
import os
import subprocess
import sys
import tempfile
import logging
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 8_000_000
OCR_TIMEOUT = int(os.environ.get('DPM_OCR_TIMEOUT', '180'))


def _cgroup_memory_limit():
    """Detecta limite real de RAM do contêiner (cgroups v1/v2)."""
    for path in ('/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes'):
        try:
            value = open(path, encoding='ascii').read().strip()
            if value.isdigit() and 0 < int(value) < (1 << 50):
                return int(value)
        except OSError:
            pass
    return None


def ocr_available():
    """Em RAM <= 768 MiB, evita iniciar ONNX, que pode matar o servidor inteiro.

    DPM_OCR_MODE=on permite testar OCR em ambiente com RAM dimensionada;
    DPM_OCR_MODE=off desativa sempre; auto usa limite do contêiner.
    """
    mode = os.environ.get('DPM_OCR_MODE', 'auto').strip().lower()
    if mode == 'off':
        return False
    if mode == 'on':
        return True
    limit = _cgroup_memory_limit()
    return limit is None or limit > 768 * 1024 * 1024


def ocr_unavailable_message():
    return ('OCR de imagens não executado por proteção de memória. '
            'O texto digitalizado pode estar incompleto. '
            'Para OCR integral, utilize um serviço de OCR separado ou instância com RAM adequada.')


def recognize_image(image):
    if not ocr_available():
        raise ValueError(ocr_unavailable_message())
    if image.width * image.height > MAX_PIXELS:
        raise ValueError('Imagem excede o limite de 8 megapixels para OCR.')
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'entrada.png')
        image.convert('RGB').save(path, format='PNG')
        env = os.environ.copy()
        for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[key] = '1'
        try:
            completed = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), 'ocr_worker.py'), path],
                capture_output=True, text=True, timeout=OCR_TIMEOUT, env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            logging.warning('OCR_TIMEOUT: limite de %s segundos', OCR_TIMEOUT)
            raise ValueError('OCR excedeu o tempo limite. Tente uma imagem menor ou mais nítida.') from exc
        if completed.returncode != 0:
            logging.warning('OCR_FAILED: código=%s, detalhe=%s', completed.returncode, completed.stderr[-450:])
            raise ValueError('OCR não pôde ser concluído com os recursos disponíveis no servidor.')
        return completed.stdout.strip()


def extract_text_from_image(path):
    try:
        with Image.open(path) as original:
            if original.format not in ('JPEG', 'PNG'):
                raise ValueError('O conteúdo não é JPG ou PNG válido.')
            if original.width * original.height > MAX_PIXELS:
                raise ValueError('Imagem excede o limite de 8 megapixels.')
            image = ImageOps.exif_transpose(original).convert('RGB')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Não foi possível abrir a imagem.') from exc
    try:
        text = recognize_image(image)
    finally:
        image.close()
    if not text:
        raise ValueError('Nenhum texto legível encontrado na imagem.')
    return {'text': text, 'pages': 1}
