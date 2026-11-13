import io
import os
import zipfile
from pdf_service import extract_text_from_pdf

MAX_FILES = 30
MAX_TOTAL_UNCOMPRESSED = 60 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024


def analyze_zip(zip_path):
    documents, full_text, total_pages = [], [], 0
    with zipfile.ZipFile(zip_path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_TOTAL_UNCOMPRESSED:
            raise ValueError("ZIP excede os limites de arquivos ou tamanho.")
        for info in infos:
            if info.is_dir():
                continue
            # Only read PDFs directly from the archive, never extract arbitrary paths.
            if not info.filename.lower().endswith(".pdf"):
                continue
            if info.file_size > MAX_PDF_BYTES:
                raise ValueError("PDF dentro do ZIP excede o limite de 20 MB.")
            name = os.path.basename(info.filename.replace("\\", "/"))
            if not name:
                continue
            try:
                with archive.open(info) as source:
                    content = source.read(MAX_PDF_BYTES + 1)
                if len(content) > MAX_PDF_BYTES:
                    raise ValueError("PDF excede o limite permitido.")
                result = extract_text_from_pdf(io.BytesIO(content))
                documents.append({"name": name, "pages": result["pages"]})
                total_pages += result["pages"]
                full_text.append(f"\n--- {name} ---\n{result['text']}")
            except Exception:
                documents.append({"name": name, "pages": 0, "error": "Não foi possível ler este PDF."})
    return {"documents": documents, "pages": total_pages, "text": "\n".join(full_text)}
