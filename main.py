
import os
import time
import secrets
import tempfile
import re
import psycopg
from psycopg.rows import dict_row

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

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL ausente. Configure a URL interna do PostgreSQL no Render.")


def db_connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)


def init_database():
    with db_connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS dpm_users (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            username VARCHAR(60) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role VARCHAR(16) NOT NULL CHECK (role IN ('admin','analyst')),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS dpm_audit (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            actor_id BIGINT,
            action VARCHAR(80) NOT NULL,
            target_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        row = conn.execute("SELECT id FROM dpm_users WHERE username=%s", (ADMIN_USER,)).fetchone()
        if not row:
            conn.execute("INSERT INTO dpm_users (username,password_hash,role) VALUES (%s,%s,'admin')",
                         (ADMIN_USER, generate_password_hash(ADMIN_PASSWORD, method='scrypt')))


init_database()
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(24), method="scrypt")


def audit(conn, action, target_id=None):
    conn.execute("INSERT INTO dpm_audit(actor_id,action,target_id) VALUES (%s,%s,%s)",
                 (session.get('user_id'), action, target_id))


def admin_only():
    if session.get('role') != 'admin':
        return jsonify({'error':'Acesso permitido apenas a administradores.'}), 403
    return None


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

    # Confere se o usuário ainda está ativo e preserva permissões atualizadas.
    user_id = session.get('user_id')
    if not user_id:
        session.clear()
        return jsonify({'error':'Sessão inválida.'}), 401
    with db_connect() as conn:
        current = conn.execute('SELECT username,role,active FROM dpm_users WHERE id=%s', (user_id,)).fetchone()
    if not current or not current['active']:
        session.clear()
        return jsonify({'error':'Conta desativada ou inexistente.'}), 401
    session['role'] = current['role']
    session['username'] = current['username']

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

    with db_connect() as conn:
        user = conn.execute('SELECT id,username,password_hash,role,active FROM dpm_users WHERE username=%s',
                            (username,)).fetchone()
    # Executa uma verificação de hash mesmo para usuários inexistentes.
    valid_password = check_password_hash(user['password_hash'] if user else DUMMY_HASH, password)
    if user and user['active'] and valid_password:
        session.clear()
        session['authenticated'] = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['csrf'] = secrets.token_urlsafe(32)
        session.permanent = True
        _attempts.pop(key, None)
        return redirect(url_for('home'))

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
        "role": session.get("role"),
    })


# ==========================================
# ENCERRAR SESSÃO
# ==========================================

@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==========================================
# GERENCIAMENTO DA EQUIPE
# ==========================================

@app.get('/api/users')
def list_users():
    denied = admin_only()
    if denied: return denied
    with db_connect() as conn:
        rows = conn.execute('SELECT id,username,role,active,created_at FROM dpm_users ORDER BY id').fetchall()
    return jsonify({'users':[{**u,'created_at':u['created_at'].isoformat()} for u in rows]})


@app.post('/api/users')
def create_user():
    denied = admin_only()
    if denied: return denied
    data = request.get_json(silent=True) or {}
    username = str(data.get('username','')).strip().lower()
    password = str(data.get('password',''))
    role = data.get('role','analyst')
    if not re.fullmatch(r'[a-z0-9_.-]{3,60}', username):
        return jsonify({'error':'Usuário: 3 a 60 caracteres, letras minúsculas, números, ponto, hífen ou _.'}),400
    if len(password) < 12 or len(password)>256:
        return jsonify({'error':'A senha deve ter entre 12 e 256 caracteres.'}),400
    if role not in ('admin','analyst'):
        return jsonify({'error':'Permissão inválida.'}),400
    try:
        with db_connect() as conn:
            row = conn.execute('INSERT INTO dpm_users(username,password_hash,role) VALUES (%s,%s,%s) RETURNING id',
                               (username,generate_password_hash(password,method='scrypt'),role)).fetchone()
            audit(conn,'user_created',row['id'])
    except psycopg.errors.UniqueViolation:
        return jsonify({'error':'Esse nome de usuário já existe.'}),409
    return jsonify({'ok':True}),201


@app.patch('/api/users/<int:user_id>')
def update_user(user_id):
    denied = admin_only()
    if denied: return denied
    data = request.get_json(silent=True) or {}
    allowed = {'role','active','password'}
    if not data or set(data)-allowed:
        return jsonify({'error':'Campos inválidos.'}),400
    if 'role' in data and data['role'] not in ('admin','analyst'):
        return jsonify({'error':'Permissão inválida.'}),400
    if 'active' in data and not isinstance(data['active'],bool):
        return jsonify({'error':'Status inválido.'}),400
    if 'password' in data and (not isinstance(data['password'],str) or not 12<=len(data['password'])<=256):
        return jsonify({'error':'Senha deve ter entre 12 e 256 caracteres.'}),400
    if user_id == session['user_id'] and (data.get('active') is False or data.get('role')=='analyst'):
        return jsonify({'error':'Não é permitido desativar ou rebaixar sua própria conta.'}),400
    with db_connect() as conn:
        target = conn.execute('SELECT id FROM dpm_users WHERE id=%s FOR UPDATE',(user_id,)).fetchone()
        if not target: return jsonify({'error':'Usuário não encontrado.'}),404
        if 'role' in data:
            conn.execute('UPDATE dpm_users SET role=%s WHERE id=%s',(data['role'],user_id))
        if 'active' in data:
            conn.execute('UPDATE dpm_users SET active=%s WHERE id=%s',(data['active'],user_id))
        if 'password' in data:
            conn.execute('UPDATE dpm_users SET password_hash=%s WHERE id=%s',
                         (generate_password_hash(data['password'],method='scrypt'),user_id))
        audit(conn,'user_updated',user_id)
    return jsonify({'ok':True})


@app.get('/api/audit')
def audit_list():
    denied = admin_only()
    if denied: return denied
    with db_connect() as conn:
        rows = conn.execute("""SELECT a.action,a.created_at,u.username AS actor
                               FROM dpm_audit a LEFT JOIN dpm_users u ON u.id=a.actor_id
                               ORDER BY a.id DESC LIMIT 100""").fetchall()
    return jsonify({'events':[{'action':r['action'],'actor':r['actor'],
                               'date':r['created_at'].isoformat()} for r in rows]})


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
