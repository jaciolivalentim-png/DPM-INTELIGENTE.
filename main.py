
import os
import tempfile

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from pdf_service import extract_text_from_pdf
from zip_analyzer import analyze_zip
from report_service import generate_report

# Pasta principal do projeto
BASE = os.path.dirname(os.path.abspath(__file__))

# Interface na mesma pasta do main.py
FRONT = BASE

app = Flask(__name__, static_folder=FRONT, static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


@app.route("/")
def home():
    return send_from_directory(FRONT, "index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    protocol = request.form.get("protocol", "").strip()
    subject = request.form.get("subject", "").strip()
    observations = request.form.get("observations", "").strip()

    uploaded = request.files.get("file")

    if not uploaded:
        return jsonify({
            "error": "Selecione um arquivo PDF ou ZIP."
        }), 400

    name = secure_filename(uploaded.filename or "")
    ext = os.path.splitext(name)[1].lower()

    if ext not in (".pdf", ".zip"):
        return jsonify({
            "error": "Formato não suportado. Envie PDF ou ZIP."
        }), 400

    try:
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, name)
            uploaded.save(path)

            if ext == ".pdf":
                pdf = extract_text_from_pdf(path)
                data = {
                    "documents": [{
                        "name": name,
                        "pages": pdf["pages"]
                    }],
                    "pages": pdf["pages"],
                    "text": pdf["text"]
                }
            else:
                data = analyze_zip(path)

            if not data["documents"]:
                return jsonify({
                    "error": "Nenhum PDF foi encontrado no arquivo ZIP."
                }), 400

            return jsonify(
                generate_report(
                    protocol,
                    subject,
                    observations,
                    data
                )
            )

    except Exception:
        app.logger.exception("Falha ao analisar arquivo")
        return jsonify({
            "error": "Não foi possível processar o arquivo enviado."
        }), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
