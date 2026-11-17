"""Extração híbrida de PDFs: texto nativo e OCR de imagens incorporadas.

OCR local, limitado para reduzir uso de CPU/RAM em hospedagens pequenas.
"""
import os
import gc
import pymupdf as fitz

MAX_PAGES = int(os.environ.get('DPM_MAX_PDF_PAGES', '75'))
MAX_OCR_PAGES = int(os.environ.get('DPM_MAX_OCR_PAGES', '58'))
MAX_IMAGE_REGIONS_PER_PAGE = int(os.environ.get('DPM_MAX_IMAGE_REGIONS_PER_PAGE', '1'))
OCR_DPI = int(os.environ.get('DPM_OCR_DPI', '160'))
MAX_RENDER_PIXELS = 3_000_000


def _ocr_clip(page, clip):
    from PIL import Image
    from image_service import recognize_image
    scale = OCR_DPI / 72
    # Reduce scale automatically for large pages/regions.
    pixels = clip.width * clip.height * scale * scale
    if pixels > MAX_RENDER_PIXELS:
        scale *= (MAX_RENDER_PIXELS / pixels) ** 0.5
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip,
                          colorspace=fitz.csRGB, alpha=False)
    try:
        image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    finally:
        del pix
    try:
        return recognize_image(image).strip()
    finally:
        image.close()


def _image_regions(page):
    """Find sizable embedded raster images; ignore logos, icons, duplicates."""
    bounds = page.rect
    total = max(bounds.width * bounds.height, 1)
    regions = []
    for info in page.get_image_info(xrefs=False):
        rect = fitz.Rect(info['bbox']) & bounds
        if rect.is_empty or rect.width < 85 or rect.height < 45:
            continue
        if rect.width * rect.height < total * 0.025:
            continue
        # A tiny source image enlarged in the PDF is unlikely to have legible text.
        if info.get('width', 0) < 110 or info.get('height', 0) < 55:
            continue
        if any(abs(rect.x0 - other.x0) < 3 and abs(rect.y0 - other.y0) < 3
               and abs(rect.x1 - other.x1) < 3 and abs(rect.y1 - other.y1) < 3
               for other in regions):
            continue
        regions.append(rect)
    return sorted(regions, key=lambda r: r.width * r.height, reverse=True)


def extract_text_from_pdf(file_path, progress_callback=None):
    parts, warnings = [], []
    ocr_pages, ocr_regions, ocr_success_pages = 0, 0, 0
    ocr_characters = 0
    ocr_page_diagnostics = []
    from image_service import ocr_available, ocr_unavailable_message
    can_ocr = ocr_available()
    if not can_ocr:
        warnings.append(ocr_unavailable_message())
    try:
        source = fitz.open(stream=file_path.read(), filetype='pdf') if hasattr(file_path, 'read') else fitz.open(file_path)
        with source as doc:
            count = len(doc)
            if count > MAX_PAGES:
                raise ValueError(f'PDF com {count} páginas excede o limite de {MAX_PAGES} páginas. Divida o arquivo.')
            if doc.needs_pass:
                raise ValueError('PDF protegido por senha. Envie uma cópia autorizada e desbloqueada.')
            for index in range(count):
                page = doc.load_page(index)
                native = (page.get_text('text') or '').strip()
                pieces = [native] if native else []
                # Sempre verifica imagens raster relevantes, mesmo em páginas mistas.
                # Limita a quantidade para preservar a memória do Render gratuito.
                candidates = _image_regions(page)
                if len(native) < 45:
                    regions = [page.rect]  # Página digitalizada sem texto nativo suficiente.
                else:
                    regions = candidates[:MAX_IMAGE_REGIONS_PER_PAGE]
                    if len(candidates) > MAX_IMAGE_REGIONS_PER_PAGE:
                        warnings.append(
                            f'Página {index + 1}: {len(candidates) - MAX_IMAGE_REGIONS_PER_PAGE} imagem(ns) não analisada(s) pelo limite por página.'
                        )
                if regions and can_ocr:
                    if ocr_pages >= MAX_OCR_PAGES:
                        warnings.append(f'Página {index + 1}: OCR não executado; limite de {MAX_OCR_PAGES} páginas atingido. Divida o PDF para leitura integral.')
                    else:
                        ocr_pages += 1
                        page_ocr_ok = False
                        for region in regions:
                            try:
                                detected = _ocr_clip(page, region)
                                ocr_regions += 1
                                if detected:
                                    page_ocr_ok = True
                                    ocr_characters += len(detected)
                                    ocr_page_diagnostics.append({"page": index + 1, "characters": len(detected), "preview": detected[:700]})
                                # Do not append OCR text that is already in the native layer.
                                normalized_native = ' '.join(native.casefold().split())
                                normalized_detected = ' '.join(detected.casefold().split())
                                if detected and normalized_detected not in normalized_native:
                                    pieces.append('[Texto identificado em imagem]\n' + detected)
                            except Exception as exc:
                                import logging
                                logging.warning('OCR_PAGINA_%s: %s: %s', index + 1, type(exc).__name__, str(exc)[:160])
                                warnings.append(f'Página {index + 1}: OCR não concluído nesta imagem; texto pode estar incompleto.')
                        if page_ocr_ok:
                            ocr_success_pages += 1
                        else:
                            warnings.append(f"Página {index + 1}: OCR não retornou texto legível; confira o original.")
                parts.append('\n\n'.join(pieces))
                del page
                if index % 5 == 0:
                    gc.collect()
                if progress_callback: progress_callback(index + 1, count)
            combined = '\n\n'.join(f'[Página {i+1}]\n{t}' for i, t in enumerate(parts) if t).strip()
            if not combined:
                raise ValueError('Nenhum texto legível foi identificado no PDF. Confira a digitalização e os avisos de OCR.')
            return {'text': combined, 'pages': count, 'ocr_pages': ocr_pages,
                    'ocr_regions': ocr_regions, 'ocr_success_pages': ocr_success_pages,
                    'ocr_characters': ocr_characters, 'ocr_page_diagnostics': ocr_page_diagnostics,
                    'warnings': warnings}
    except fitz.FileDataError as exc:
        raise ValueError('PDF inválido ou corrompido.') from exc
