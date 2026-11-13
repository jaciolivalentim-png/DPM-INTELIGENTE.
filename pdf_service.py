"""Extrai texto nativo de PDFs e aplica OCR local em páginas digitalizadas.
Não envia documentos a serviços externos.
"""
import os
import fitz

MAX_PAGES = int(os.environ.get('DPM_MAX_PDF_PAGES', '100'))
MAX_OCR_PAGES = int(os.environ.get('DPM_MAX_OCR_PAGES', '40'))
OCR_DPI = 125


def extract_text_from_pdf(file_path):
    from image_service import recognize_image
    parts = []
    ocr_count = 0
    try:
        with fitz.open(stream=file_path.read(), filetype='pdf') if hasattr(file_path, 'read') else fitz.open(file_path) as doc:
            count = len(doc)
            if count > MAX_PAGES:
                raise ValueError(f'PDF com {count} páginas excede o limite de {MAX_PAGES} páginas por análise. Divida o arquivo.')
            if doc.needs_pass:
                raise ValueError('PDF protegido por senha. Envie uma cópia autorizada e desbloqueada.')
            for index in range(count):
                page = doc.load_page(index)
                text = (page.get_text('text') or '').strip()
                # OCR somente em páginas sem texto suficiente.
                if len(text) < 45:
                    if ocr_count >= MAX_OCR_PAGES:
                        raise ValueError(f'O PDF exige OCR em mais de {MAX_OCR_PAGES} páginas. Divida-o em partes menores para evitar falhas no servidor.')
                    # Limita tamanho de renderização e memória.
                    scale = OCR_DPI / 72
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
                    if pix.width * pix.height > 12_000_000:
                        raise ValueError(f'Página {index + 1} grande demais para OCR seguro.')
                    from PIL import Image
                    image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                    del pix
                    ocr_text = recognize_image(image)
                    if len(ocr_text.strip()) > len(text):
                        text = ocr_text.strip()
                    ocr_count += 1
                parts.append(text)
            combined = '\n\n'.join(f'[Página {i+1}]\n{t}' for i, t in enumerate(parts) if t).strip()
            if not combined:
                raise ValueError('Nenhum texto legível foi identificado no PDF, mesmo após OCR. Confira a qualidade da digitalização.')
            return {'text': combined, 'pages': count, 'ocr_pages': ocr_count}
    except fitz.FileDataError as exc:
        raise ValueError('PDF inválido ou corrompido.') from exc
