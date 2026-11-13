
import os
import time
import secrets
import tempfile

from collections import defaultdict, deque
from functools import wraps

from flask import (
    Flask,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    render_template_string,
    send_from_directory,
    abort,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

from pdf_service import extract_text_from_pdf
from zip_analyzer import analyze_zip
from report_service import generate_report


# ==========================================
# CONFIGURAÇÕES DO PROJETO
# ==========================================

BASE = os.path.dirname(os.path.abspath(__file__))

# Arquivos da interface na raiz do GitHub
FRONT = BASE

app = Flask(__name__, static_folder=None)

# Render utiliza proxy HTTPS
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_proto=1,
    x_host=1,
)

# ==========================================
# VARIÁVEIS DE SEGURANÇA
# ==========================================

SECRET = os.environ.get("DPM_SECRET_KEY", "")
ADMIN_PASSWORD = os.environ.get(
    "DPM_ADMIN_PASSWORD", ""
)
ADMIN_USER = os.environ.get(
    "DPM_ADMIN_USER", "admin"
).strip()

if len(SECRET) < 32:
    raise RuntimeError(
        "ERRO: DPM_SECRET_KEY ausente ou "
        "menor que 32 caracteres."
    )


if not ADMIN_PASSWORD:
    raise RuntimeError(
        "ERRO: DPM_ADMIN_PASSWORD nao chegou ao Python."
    )

if len(ADMIN_PASSWORD) < 12:
    raise RuntimeError(
        "ERRO: DPM_ADMIN_PASSWORD foi recebida, "
        "mas tem menos de 12 caracteres."
    )

if not ADMIN_USER:
    raise RuntimeError(
        "ERRO: DPM_ADMIN_USER vazio."
    )

app.config.update(
    SECRET_KEY=SECRET,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=1800,
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
)

ADMIN_HASH = generate_password_hash(
    ADMIN_PASSWORD,
    method="scrypt",
)

# Controle básico de tentativas de login
_attempts = defaultdict(deque)


# ==========================================
# CABEÇALHOS DE SEGURANÇA
# ==========================================

@app.after_request
def security_headers(response):
    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"

    response.headers[
        "Cache-Control"
    ] = "no-store"

    response.headers[
        "Content-Security-Policy"
    ] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )

    return response


# ==========================================
# PROTEÇÃO DE ACESSO
# ==========================================

@app.before_request
def require_login():

    # Rotas públicas
    if request.endpoint in ("login", "health"):
        return None

    # Exige autenticação
    if not session.get("authenticated"):

        if request.path.startswith("/api/"):
            return jsonify({
                "error": (
                    "Sessão expirada. "
                    "Faça login novamente."
                )
            }), 401

        return redirect(url_for("login"))

    # Proteção CSRF
    if request.method in (
        "POST", "PUT", "PATCH", "DELETE"
    ):
        token = (
            request.headers.get("X-CSRF-Token")
            or request.form.get("csrf_token")
        )

        expected = session.get("csrf", "")

        if (
            not token
            or not expected
            or not secrets.compare_digest(
                token, expected
            )
        ):
            return jsonify({
                "error": (
                    "Token de segurança inválido."
                )
            }), 403


# ==========================================
# VERIFICAÇÃO DO SERVIDOR
# ==========================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "DPM Inteligente",
    })


# ==========================================
# TELA DE LOGIN
# ==========================================

LOGIN_HTML = """
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport"
content="width=device-width, initial-scale=1">

<title>Login | DPM Inteligente</title>

<style>
body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f3f6fa;
    color: #142b46;
    display: grid;
    place-items: center;
    min-height: 100vh;
}

main {
    background: white;
    padding: 32px;
    border-radius: 12px;
    box-shadow: 0 8px 35px #142b4620;
    width: min(380px, 85vw);
}

h1 {
    font-size: 24px;
}

p {
    color: #66798d;
    font-size: 14px;
}

label {
    display: block;
    margin-top: 18px;
    font-weight: bold;
    font-size: 13px;
}

input {
    box-sizing: border-box;
    width: 100%;
    padding: 12px;
    margin-top: 7px;
    border: 1px solid #ccd5df;
    border-radius: 7px;
}

button {
    margin-top: 24px;
    width: 100%;
    padding: 13px;
    background: #1769aa;
    border: 0;
    border-radius: 7px;
    color: white;
    font-weight: bold;
    cursor: pointer;
}

.error {
    color: #a11f28;
}
</style>
</head>

<body>
<main>

<h1>DPM Inteligente</h1>

<p>Acesso restrito — Ambiente de testes</p>

{% if error %}
<p class="error" role="alert">
{{ error }}
</p>
{% endif %}

<form method="post" action="/login">

<label for="u">Usuário</label>
<input
    id="u"
    name="username"
    autocomplete="username"
    required
>

<label for="p">Senha</label>
<input
    id="p"
    type="password"
    name="password"
    autocomplete="current-password"
    required
>

<button type="submit">
Entrar
</button>

</form>

<p>
Não envie documentos médicos reais
neste ambiente.
</p>

</main>
</body>
</html>
"""


# ==========================================
# AUTENTICAÇÃO
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":
        if session.get("authenticated"):
            return redirect(url_for("home"))

        return render_template_string(
            LOGIN_HTML,
            error=""
        )

    key = request.remote_addr or "unknown"
    now = time.monotonic()

    attempts = _attempts[key]

    while attempts and now - attempts[0] > 900:
        attempts.popleft()

    if len(attempts) >= 5:
        return render_template_string(
            LOGIN_HTML,
            error=(
                "Muitas tentativas. "
                "Aguarde 15 minutos."
            )
        ), 429

    username = request.form.get(
        "username", ""
    )

    password = request.form.get(
        "password", ""
    )

    valid_user = secrets.compare_digest(
        username,
        ADMIN_USER
    )

    valid_password = check_password_hash(
        ADMIN_HASH,
        password
    )

    if valid_user and valid_password:

        session.clear()

        session["authenticated"] = True
        session["username"] = ADMIN_USER
        session["csrf"] = (
            secrets.token_urlsafe(32)
        )

        session.permanent = True

        _attempts.pop(key, None)

        return redirect(url_for("home"))

    attempts.append(now)

    return render_template_string(
        LOGIN_HTML,
        error="Usuário ou senha inválidos."
    ), 401


# ==========================================
# SESSÃO ATUAL
# ==========================================

@app.route("/api/session")
def current_session():

    return jsonify({
        "username": session.get("username"),
        "csrf": session.get("csrf"),
    })


# ==========================================
# ENCERRAR SESSÃO
# ==========================================

@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==========================================
# INTERFACE PRINCIPAL
# ==========================================

@app.route("/")
def home():

    return send_from_directory(
        FRONT,
        "index.html"
    )


# Somente os arquivos públicos necessários
@app.route("/style.css")
def stylesheet():

    return send_from_directory(
        FRONT,
        "style.css"
    )


@app.route("/app.js")
def javascript():

    return send_from_directory(
        FRONT,
        "app.js"
    )


# ==========================================
# ANÁLISE DE PROTOCOLOS
# ==========================================

@app.route("/api/analyze", methods=["POST"])
def analyze():

    protocol = request.form.get(
        "protocol", ""
    ).strip()

    subject = request.form.get(
        "subject", ""
    ).strip()

    observations = request.form.get(
        "observations", ""
    ).strip()

    uploaded = request.files.get("file")

    if not uploaded:
        return jsonify({
            "error": (
                "Selecione um arquivo PDF ou ZIP."
            )
        }), 400

    name = secure_filename(
        uploaded.filename or ""
    )

    ext = os.path.splitext(name)[1].lower()

    if ext not in (".pdf", ".zip"):
        return jsonify({
            "error": (
                "Formato não suportado. "
                "Envie PDF ou ZIP."
            )
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
                    "error": (
                        "Nenhum PDF foi encontrado "
                        "no arquivo ZIP."
                    )
                }), 400

            report = generate_report(
                protocol,
                subject,
                observations,
                data
            )

            return jsonify(report)

    except Exception:

        app.logger.exception(
            "Falha ao analisar arquivo"
        )

        return jsonify({
            "error": (
                "Não foi possível processar "
                "o arquivo enviado."
            )
        }), 400


# ==========================================
# INICIALIZAÇÃO
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
