import os, tempfile, time, secrets
from functools import wraps
from collections import defaultdict, deque
from flask import session, redirect, url_for, render_template_string, abort, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from pdf_service import extract_text_from_pdf
from zip_analyzer import analyze_zip
from report_service import generate_report

BASE = os.path.dirname(os.path.abspath(__file__))
FRONT = BASE  # Arquivos do site na raiz do repositório GitHub
app = Flask(__name__, static_folder=FRONT, static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
SECRET = os.environ.get("DPM_SECRET_KEY", "")
ADMIN_PASSWORD = os.environ.get("DPM_ADMIN_PASSWORD", "")
ADMIN_USER = os.environ.get("DPM_ADMIN_USER", "admin")
if len(SECRET) < 32 or len(ADMIN_PASSWORD) < 12:
    raise RuntimeError("Configure DPM_SECRET_KEY (32+ caracteres) e DPM_ADMIN_PASSWORD (12+ caracteres) no Render antes do deploy.")
app.config.update(SECRET_KEY=SECRET, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=1800,
                  MAX_CONTENT_LENGTH=20 * 1024 * 1024)
# Senha convertida em hash no processo. Para produção institucional, usar
# gerenciador de identidade e armazenamento persistente apropriado.
ADMIN_HASH = generate_password_hash(ADMIN_PASSWORD, method="scrypt")
_attempts = defaultdict(deque)  # limitação por processo, não substitui Redis/WAF

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response

@app.before_request
def require_login():
    if request.endpoint in ("login", "health"):
        return None
    if not session.get("authenticated"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Sessão expirada. Faça login novamente."}), 401
        return redirect(url_for("login"))
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not token or not secrets.compare_digest(token, session.get("csrf", "")):
            return jsonify({"error": "Token de segurança inválido."}), 403

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        key = request.remote_addr or "unknown"
        now = time.monotonic()
        attempts = _attempts[key]
        while attempts and now - attempts[0] > 900:
            attempts.popleft()
        if len(attempts) >= 5:
            return render_template_string(LOGIN_HTML, error="Muitas tentativas. Aguarde 15 minutos."), 429
        user = request.form.get("username", "")
        password = request.form.get("password", "")
        if secrets.compare_digest(user, ADMIN_USER) and check_password_hash(ADMIN_HASH, password):
            session.clear()
            session["authenticated"] = True
            session["username"] = ADMIN_USER
            session["csrf"] = secrets.token_urlsafe(32)
            session.permanent = True
            _attempts.pop(key, None)
            return redirect(url_for("home"))
        attempts.append(now)
        return render_template_string(LOGIN_HTML, error="Usuário ou senha inválidos."), 401
    if session.get("authenticated"):
        return redirect(url_for("home"))
    return render_template_string(LOGIN_HTML, error="")

@app.route("/api/session")
def current_session():
    return jsonify({"username": session.get("username"), "csrf": session["csrf"]})

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

LOGIN_HTML = """<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Entrar | DPM Inteligente</title>
<style>body{margin:0;font-family:Arial,sans-serif;background:#f3f6fa;color:#142b46;display:grid;place-items:center;min-height:100vh}main{background:white;padding:32px;border-radius:12px;box-shadow:0 8px 35px #142b4620;width:min(380px,85vw)}h1{font-size:24px}p{color:#66798d;font-size:14px}label{display:block;margin-top:18px;font-weight:bold;font-size:13px}input{box-sizing:border-box;width:100%;padding:12px;margin-top:7px;border:1px solid #ccd5df;border-radius:7px}button{margin-top:24px;width:100%;padding:13px;background:#1769aa;border:0;border-radius:7px;color:white;font-weight:bold;cursor:pointer}.error{color:#a11f28}</style>
</head><body><main><h1>DPM Inteligente</h1><p>Acesso restrito • Ambiente de testes</p>
{% if error %}<p class='error' role='alert'>{{error}}</p>{% endif %}
<form method='post' action='/login'><label for='u'>Usuário</label><input id='u' name='username' autocomplete='username' required>
<label for='p'>Senha</label><input id='p' type='password' name='password' autocomplete='current-password' required>
<button type='submit'>Entrar</button></form><p>Não envie documentos médicos reais neste ambiente.</p></main></body></html>"""


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
        return jsonify({"error": "Selecione um arquivo PDF ou ZIP."}), 400
    name = secure_filename(uploaded.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in (".pdf", ".zip"):
        return jsonify({"error": "Formato não suportado. Envie PDF ou ZIP."}), 400
    try:
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, name)
            uploaded.save(path)
            if ext == ".pdf":
                pdf = extract_text_from_pdf(path)
                data = {"documents":[{"name":name,"pages":pdf["pages"]}], "pages":pdf["pages"], "text":pdf["text"]}
            else:
                data = analyze_zip(path)
            if not data["documents"]:
                return jsonify({"error":"Nenhum PDF foi encontrado no arquivo ZIP."}), 400
            return jsonify(generate_report(protocol, subject, observations, data))
    except Exception:
        app.logger.exception("Falha ao analisar arquivo")
        return jsonify({"error": "Não foi possível processar o arquivo enviado."}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
