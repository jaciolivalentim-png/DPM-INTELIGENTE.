
import os
import time
import secrets
import hashlib
import tempfile
import threading
import uuid
import shutil
import gc
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
from image_service import extract_text_from_image
from report_service import generate_report
from normative_service import select_matches
from ai_service import enhance_report


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
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,
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
        conn.execute("""CREATE TABLE IF NOT EXISTS dpm_analysis_history (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES dpm_users(id),
            protocol_label VARCHAR(80),
            document_count INTEGER NOT NULL DEFAULT 0,
            page_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'completed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS dpm_analysis_jobs (
            id UUID PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES dpm_users(id),
            status VARCHAR(16) NOT NULL, current_page INTEGER NOT NULL DEFAULT 0,
            total_pages INTEGER NOT NULL DEFAULT 0, stage VARCHAR(160) NOT NULL DEFAULT 'Aguardando',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        # Somente textos normativos autorizados; PDFs originais não são armazenados.
        conn.execute("""CREATE TABLE IF NOT EXISTS dpm_normative_documents (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            title VARCHAR(200) NOT NULL, source_url TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by BIGINT REFERENCES dpm_users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS dpm_dispatch_templates (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            title VARCHAR(160) NOT NULL,
            category VARCHAR(80) NOT NULL,
            format VARCHAR(16) NOT NULL CHECK (format IN ('simplificado','completo')),
            body TEXT NOT NULL,
            is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by BIGINT REFERENCES dpm_users(id),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (title, format, is_builtin)
        )""")
        # Atualiza somente modelos iniciais; preserva os modelos personalizados da equipe.
        from dispatch_defaults import install_dispatch_defaults
        install_dispatch_defaults(conn)
        # Metadados mínimos de OCR e revisão; não armazenar texto nem arquivos.
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS ocr_attempted INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS ocr_read INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS ocr_characters INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS review_status VARCHAR(24) NOT NULL DEFAULT 'pending'")
        conn.execute("CREATE INDEX IF NOT EXISTS dpm_audit_date_idx ON dpm_audit(created_at DESC)")
        # Migração segura: preserva o histórico já existente.
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS assigned_to BIGINT REFERENCES dpm_users(id)")
        conn.execute("ALTER TABLE dpm_analysis_history ADD COLUMN IF NOT EXISTS report_data JSONB")
        conn.execute("ALTER TABLE dpm_users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
        conn.execute("""CREATE TABLE IF NOT EXISTS dpm_password_requests (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES dpm_users(id),
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','issued','completed','rejected','expired')),
            token_hash VARCHAR(64),
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            handled_at TIMESTAMPTZ,
            handled_by BIGINT REFERENCES dpm_users(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS dpm_password_requests_status_idx ON dpm_password_requests(status,created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS dpm_history_assigned_idx ON dpm_analysis_history(assigned_to, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS dpm_history_date_idx ON dpm_analysis_history(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS dpm_history_user_idx ON dpm_analysis_history(user_id, created_at DESC)")
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
    if request.endpoint in ("login", "health", "bandeira_parana", "password_help", "password_redeem"):
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
    position: relative;
    isolation: isolate;
    display: grid;
    place-items: center;
    min-height: 100vh;
}

body::before {
    content: "";
    position: fixed;
    inset: 0;
    background: url('/bandeira-parana.svg') center center / cover no-repeat;
    opacity: .30;
    z-index: -1;
    pointer-events: none;
}
main {
    background: rgba(255,255,255,.97);
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

.error { color: #a11f28; }
.password-link { display:block; text-align:center; margin:14px 0 0; color:#1769aa; font-size:14px; }
.login-brand { display:flex; align-items:center; gap:16px; margin-bottom:18px; }
.login-brand img { width:76px; height:76px; object-fit:contain; padding:4px; background:#fff; border-radius:12px; border:1px solid #d6e1ea; }
.login-brand h1 { margin:0; font-size:23px; }
.login-brand p { margin:6px 0 0; font-size:12px; }
</style>
</head>

<body>
<main>

<div class="login-brand"><img src="https://commons.wikimedia.org/wiki/Special:Redirect/file/Bras%C3%A3o_do_Paran%C3%A1.svg" onerror="this.onerror=null;this.src='/bandeira-parana.svg'" alt="Brasão do Paraná (bandeira como alternativa)"><div><h1>DPM Inteligente</h1><p>Divisão de Perícia Médica</p></div></div>

<p>Acesso restrito</p>

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
<a class="password-link" href="/password-help">Esqueceu sua senha?</a>

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


# Recuperação assistida: o administrador nunca vê a senha nem pode obter o token antigo.
# A identidade deve ser confirmada por canal institucional independente.
_password_attempts = defaultdict(deque)

def _password_rate_limited(key, limit=5, window=3600):
    now = time.monotonic()
    q = _password_attempts[key]
    while q and now-q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False

def _reset_hash(token):
    return hashlib.sha256((SECRET + ':' + token).encode('utf-8')).hexdigest()

PASSWORD_HELP_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recuperação de acesso — DPM Inteligente</title><style>
body{font-family:Arial,sans-serif;background:#eef3f7;margin:0;min-height:100vh;display:grid;place-items:center;color:#102e4a}main{background:white;border-radius:14px;box-shadow:0 12px 35px #19334b25;width:min(420px,90vw);padding:30px}h1{font-size:23px}label{display:block;margin:18px 0 6px;font-weight:600;font-size:14px}input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #b9c9d9;border-radius:7px}button{width:100%;margin-top:20px;padding:12px;background:#1769aa;color:white;border:0;border-radius:7px;cursor:pointer}a{color:#1769aa}p{line-height:1.5;font-size:14px}.notice{padding:12px;background:#e8f2fa;border-radius:8px}</style></head><body><main><h1>{{ title }}</h1><p>{{ description }}</p>{% if message %}<p class="notice" role="status">{{ message }}</p>{% endif %}<form method="post"><input type="hidden" name="form_token" value="{{ form_token }}">{% if mode == 'request' %}<label for="username">Usuário</label><input id="username" name="username" autocomplete="username" maxlength="60" required>{% else %}<label for="username">Usuário</label><input id="username" name="username" autocomplete="username" required><label for="code">Código de recuperação</label><input id="code" name="code" autocomplete="off" required><label for="password">Nova senha (mínimo 12 caracteres)</label><input id="password" type="password" name="password" autocomplete="new-password" minlength="12" maxlength="256" required>{% endif %}<button type="submit">{{ button }}</button></form><p><a href="/login">Voltar ao login</a>{% if mode == 'request' %} · <a href="/password-redeem">Já tenho um código</a>{% endif %}</p></main></body></html>"""

def _password_form(mode, message='', status=200):
    if 'password_form_token' not in session:
        session['password_form_token'] = secrets.token_urlsafe(32)
    return render_template_string(PASSWORD_HELP_HTML, mode=mode,
        title='Solicitar redefinição de senha' if mode=='request' else 'Criar nova senha',
        description=('Informe seu usuário. A equipe administrativa receberá a solicitação.' if mode=='request' else 'Use o código entregue após confirmação da sua identidade.'),
        button='Enviar solicitação' if mode=='request' else 'Redefinir senha',
        form_token=session['password_form_token'], message=message), status

def _valid_password_form():
    token=request.form.get('form_token','')
    expected=session.get('password_form_token','')
    return bool(token and expected and secrets.compare_digest(token,expected))

@app.route('/password-help',methods=['GET','POST'])
def password_help():
    if request.method=='GET':
        return _password_form('request')
    if not _valid_password_form():
        return _password_form('request','Recarregue a página e tente novamente.',403)
    if _password_rate_limited('request:'+str(request.remote_addr)):
        return _password_form('request','Aguarde antes de enviar outra solicitação.',429)
    username=request.form.get('username','').strip()[:60]
    if username:
        with db_connect() as conn:
            user=conn.execute('SELECT id FROM dpm_users WHERE username=%s AND active AND deleted_at IS NULL',(username,)).fetchone()
            if user:
                pending=conn.execute("SELECT id FROM dpm_password_requests WHERE user_id=%s AND status IN ('pending','issued') AND created_at>NOW()-INTERVAL '24 hours' LIMIT 1",(user['id'],)).fetchone()
                if not pending:
                    row=conn.execute('INSERT INTO dpm_password_requests(user_id) VALUES (%s) RETURNING id',(user['id'],)).fetchone()
                    conn.execute("INSERT INTO dpm_audit(actor_id,action,target_id) VALUES (NULL,'password_reset_requested',%s)",(row['id'],))
    return _password_form('request','Se a conta estiver habilitada, a solicitação será encaminhada à administração.')

@app.route('/password-redeem',methods=['GET','POST'])
def password_redeem():
    if request.method=='GET':
        return _password_form('redeem')
    if not _valid_password_form():
        return _password_form('redeem','Recarregue a página e tente novamente.',403)
    if _password_rate_limited('redeem:'+str(request.remote_addr),8):
        return _password_form('redeem','Aguarde antes de tentar novamente.',429)
    username=request.form.get('username','').strip()[:60]
    token=request.form.get('code','').strip()
    password=request.form.get('password','')
    if not 12<=len(password)<=256 or len(token)>128:
        return _password_form('redeem','Verifique o código e use uma senha de 12 a 256 caracteres.',400)
    with db_connect() as conn:
        req=conn.execute("""SELECT r.id,r.user_id FROM dpm_password_requests r JOIN dpm_users u ON u.id=r.user_id
            WHERE u.username=%s AND u.active AND u.deleted_at IS NULL AND r.status='issued'
            AND r.token_hash=%s AND r.expires_at>NOW() FOR UPDATE OF r""",(username,_reset_hash(token))).fetchone()
        if not req:
            return _password_form('redeem','Código inválido ou expirado. Solicite um novo código.',400)
        conn.execute('UPDATE dpm_users SET password_hash=%s WHERE id=%s',(generate_password_hash(password,method='scrypt'),req['user_id']))
        conn.execute("UPDATE dpm_password_requests SET status='completed',token_hash=NULL,handled_at=NOW() WHERE id=%s",(req['id'],))
        conn.execute("INSERT INTO dpm_audit(actor_id,action,target_id) VALUES (NULL,'password_reset_completed',%s)",(req['id'],))
    session.clear()
    return redirect(url_for('login'))

@app.get('/api/password-requests')
def password_requests_list():
    denied=admin_only()
    if denied:return denied
    with db_connect() as conn:
        rows=conn.execute("""SELECT r.id,r.status,r.created_at,r.expires_at,u.username
            FROM dpm_password_requests r JOIN dpm_users u ON u.id=r.user_id
            ORDER BY r.created_at DESC LIMIT 100""").fetchall()
    return jsonify({'requests':[{**r,'created_at':r['created_at'].isoformat(),
        'expires_at':r['expires_at'].isoformat() if r['expires_at'] else None} for r in rows]})

@app.post('/api/password-requests/<int:request_id>/issue')
def password_request_issue(request_id):
    denied=admin_only()
    if denied:return denied
    token=secrets.token_urlsafe(32)
    with db_connect() as conn:
        row=conn.execute("""SELECT r.id FROM dpm_password_requests r JOIN dpm_users u ON u.id=r.user_id
            WHERE r.id=%s AND r.status='pending' AND u.active AND u.deleted_at IS NULL FOR UPDATE OF r""",(request_id,)).fetchone()
        if not row:return jsonify({'error':'Solicitação indisponível.'}),409
        conn.execute("""UPDATE dpm_password_requests SET status='issued',token_hash=%s,
            expires_at=NOW()+INTERVAL '30 minutes',handled_by=%s,handled_at=NOW() WHERE id=%s""",
            (_reset_hash(token),session['user_id'],request_id))
        audit(conn,'password_reset_issued',request_id)
    return jsonify({'ok':True,'code':token,'message':'Exiba este código uma única vez e entregue apenas após confirmar a identidade do solicitante.'})

@app.post('/api/password-requests/<int:request_id>/reject')
def password_request_reject(request_id):
    denied=admin_only()
    if denied:return denied
    with db_connect() as conn:
        row=conn.execute("UPDATE dpm_password_requests SET status='rejected',token_hash=NULL,handled_by=%s,handled_at=NOW() WHERE id=%s AND status IN ('pending','issued') RETURNING id",(session['user_id'],request_id)).fetchone()
        if not row:return jsonify({'error':'Solicitação indisponível.'}),409
        audit(conn,'password_reset_rejected',request_id)
    return jsonify({'ok':True})

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
        rows = conn.execute('SELECT id,username,role,active,created_at FROM dpm_users WHERE deleted_at IS NULL ORDER BY id').fetchall()
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
        target = conn.execute('SELECT id FROM dpm_users WHERE id=%s AND deleted_at IS NULL FOR UPDATE',(user_id,)).fetchone()
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


@app.delete('/api/users/<int:user_id>')
def delete_user(user_id):
    """Exclusão lógica: revoga acesso, preserva autoria, protocolos e auditoria."""
    denied = admin_only()
    if denied: return denied
    if user_id == session.get('user_id'):
        return jsonify({'error':'Não é possível excluir a própria conta.'}),400
    with db_connect() as conn:
        target = conn.execute('SELECT id,role,active FROM dpm_users WHERE id=%s AND deleted_at IS NULL FOR UPDATE', (user_id,)).fetchone()
        if not target: return jsonify({'error':'Conta não encontrada.'}),404
        if target['role']=='admin' and target['active']:
            count = conn.execute("SELECT COUNT(*) AS total FROM dpm_users WHERE role='admin' AND active AND deleted_at IS NULL").fetchone()['total']
            if count <= 1: return jsonify({'error':'Não é possível excluir o último administrador ativo.'}),409
        conn.execute('UPDATE dpm_analysis_history SET assigned_to=NULL WHERE assigned_to=%s', (user_id,))
        conn.execute('UPDATE dpm_users SET active=FALSE,deleted_at=NOW() WHERE id=%s', (user_id,))
        audit(conn,'user_deleted_soft',user_id)
    return jsonify({'ok':True,'message':'Acesso removido. Protocolos e auditoria preservados.'})

@app.get('/api/reports/storage-status')
def report_storage_status():
    if not session.get('user_id'):
        return jsonify({'error':'Autenticação necessária.'}),401
    return jsonify({'enabled':os.environ.get('DPM_PERSIST_REPORTS')=='1',
                    'message':'Armazenamento de relatórios habilitado' if os.environ.get('DPM_PERSIST_REPORTS')=='1' else 'Armazenamento de relatórios desativado no servidor'})

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


@app.get('/api/audit/analyses')
def audit_analyses():
    denied = admin_only()
    if denied: return denied
    with db_connect() as conn:
        rows = conn.execute("""SELECT h.id,h.protocol_label,h.document_count,h.page_count,
                     h.status,h.review_status,h.ocr_attempted,h.ocr_read,h.ocr_characters,
                     h.created_at,u.username
                     FROM dpm_analysis_history h JOIN dpm_users u ON u.id=h.user_id
                     ORDER BY h.id DESC LIMIT 100""").fetchall()
    return jsonify({'analyses':[{
        'id':r['id'], 'protocol':r['protocol_label'], 'documents':r['document_count'],
        'pages':r['page_count'], 'status':r['status'],
        'review_status':r['review_status'], 'ocr_attempted':r['ocr_attempted'],
        'ocr_read':r['ocr_read'], 'ocr_characters':r['ocr_characters'],
        'date':r['created_at'].isoformat(), 'actor':r['username']
    } for r in rows]})

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


@app.route("/bandeira-parana.svg")
def bandeira_parana():
    return send_from_directory(FRONT, "bandeira-parana.svg", mimetype="image/svg+xml")


@app.route("/app.js")
def javascript():

    return send_from_directory(
        FRONT,
        "app.js"
    )


# ==========================================
# ANÁLISE DE PROTOCOLOS
# ==========================================


# Histórico mínimo: não armazena PDFs, textos, relatórios ou nomes de arquivos.
def _attach_normative_matches(report, text):
    try:
        with db_connect() as conn:
            rows = conn.execute("SELECT id,title,source_url,content,active FROM dpm_normative_documents WHERE active=TRUE ORDER BY id DESC LIMIT 80").fetchall()
        report['normative_matches'] = select_matches(report.get('subject',''), text, rows)
        report['normative_notice'] = ('Trechos localizados nos documentos cadastrados. Não comprova vigência, autenticidade, artigo aplicável ou conclusão jurídica. Conferir o PDF original e a fonte oficial.')
    except Exception:
        app.logger.exception('Falha na busca normativa')
        report['normative_matches'] = []
        report['normative_notice'] = 'Base normativa temporariamente indisponível; conferir as fontes oficiais.'


# Modelos de despacho: biblioteca compartilhada, com escrita restrita ao administrador.
@app.get('/api/dispatch-templates')
def list_dispatch_templates():
    show_inactive = request.args.get('include_inactive') == '1' and session.get('role') == 'admin'
    with db_connect() as conn:
        rows=conn.execute("SELECT id,title,category,format,body,is_builtin,active,updated_at FROM dpm_dispatch_templates WHERE active=TRUE OR %s ORDER BY active DESC,category,title,format LIMIT 250",(show_inactive,)).fetchall()
    return jsonify([dict(r,updated_at=r['updated_at'].isoformat()) for r in rows])

@app.post('/api/dispatch-templates')
def create_dispatch_template():
    denied=admin_only()
    if denied: return denied
    data=request.get_json(silent=True) or {}
    title=str(data.get('title') or '').strip()
    category=str(data.get('category') or '').strip()
    fmt=str(data.get('format') or '')
    body=str(data.get('body') or '').strip()
    if not (3<=len(title)<=160 and 2<=len(category)<=80 and fmt in ('simplificado','completo') and 20<=len(body)<=12000):
        return jsonify({'error':'Informe nome, categoria, formato e texto (20 a 12.000 caracteres).'}),400
    with db_connect() as conn:
        try:
            row=conn.execute("INSERT INTO dpm_dispatch_templates(title,category,format,body,created_by) VALUES (%s,%s,%s,%s,%s) RETURNING id",(title,category,fmt,body,session['user_id'])).fetchone()
        except psycopg.errors.UniqueViolation:
            return jsonify({'error':'Já existe um modelo personalizado com esse nome e formato.'}),409
        audit(conn,'dispatch_template_created',row['id'])
    return jsonify({'id':row['id']}),201

@app.patch('/api/dispatch-templates/<int:template_id>')
def update_dispatch_template(template_id):
    denied=admin_only()
    if denied: return denied
    data=request.get_json(silent=True) or {}
    title=str(data.get('title') or '').strip()
    category=str(data.get('category') or '').strip()
    fmt=str(data.get('format') or '')
    body=str(data.get('body') or '').strip()
    if not (3<=len(title)<=160 and 2<=len(category)<=80 and fmt in ('simplificado','completo') and 20<=len(body)<=12000):
        return jsonify({'error':'Dados inválidos para o modelo.'}),400
    with db_connect() as conn:
        try:
            row=conn.execute("UPDATE dpm_dispatch_templates SET title=%s,category=%s,format=%s,body=%s,updated_at=NOW() WHERE id=%s AND is_builtin=FALSE AND active=TRUE RETURNING id",(title,category,fmt,body,template_id)).fetchone()
        except psycopg.errors.UniqueViolation:
            return jsonify({'error':'Já existe um modelo com esse nome e formato.'}),409
        if not row: return jsonify({'error':'Modelo personalizado não encontrado ou não editável.'}),404
        audit(conn,'dispatch_template_updated',template_id)
    return jsonify({'ok':True})

@app.delete('/api/dispatch-templates/<int:template_id>')
def deactivate_dispatch_template(template_id):
    denied=admin_only()
    if denied: return denied
    with db_connect() as conn:
        row=conn.execute("UPDATE dpm_dispatch_templates SET active=FALSE,updated_at=NOW() WHERE id=%s AND active=TRUE RETURNING id",(template_id,)).fetchone()
        if not row: return jsonify({'error':'Modelo não encontrado ou já ocultado.'}),404
        audit(conn,'dispatch_template_deactivated',template_id)
    return jsonify({'ok':True})

@app.post('/api/dispatch-templates/<int:template_id>/restore')
def restore_dispatch_template(template_id):
    denied=admin_only()
    if denied: return denied
    with db_connect() as conn:
        row=conn.execute("UPDATE dpm_dispatch_templates SET active=TRUE,updated_at=NOW() WHERE id=%s AND active=FALSE RETURNING id",(template_id,)).fetchone()
        if not row: return jsonify({'error':'Modelo não encontrado ou já ativo.'}),404
        audit(conn,'dispatch_template_restored',template_id)
    return jsonify({'ok':True})

@app.get('/api/normative/documents')
def normative_documents():
    with db_connect() as conn:
        rows = conn.execute("SELECT id,title,source_url,active,created_at,length(content) AS characters FROM dpm_normative_documents ORDER BY id DESC LIMIT 100").fetchall()
    return jsonify([dict(r,created_at=r['created_at'].isoformat()) for r in rows])

@app.post('/api/normative/documents')
def upload_normative_document():
    denied = admin_only()
    if denied: return denied
    uploaded = request.files.get('file')
    title = (request.form.get('title') or '').strip()[:200]
    url = (request.form.get('source_url') or '').strip()[:1200]
    if not title or not uploaded or not uploaded.filename.lower().endswith('.pdf'):
        return jsonify({'error':'Informe o título e um PDF.'}), 400
    if url and (not url.startswith('https://') or any(c.isspace() for c in url)):
        return jsonify({'error':'A fonte deve ser um endereço HTTPS válido.'}), 400
    content = uploaded.read(12 * 1024 * 1024 + 1)
    if len(content) > 12 * 1024 * 1024 or not content.startswith(b'%PDF-'):
        return jsonify({'error':'PDF inválido ou maior que 12 MB.'}), 400
    import pymupdf
    try:
        with pymupdf.open(stream=content,filetype='pdf') as doc:
            if doc.needs_pass or len(doc)>150:
                return jsonify({'error':'PDF protegido ou acima de 150 páginas.'}), 400
            parts = [f'[Página {i+1}]\n'+page.get_text('text') for i,page in enumerate(doc)]
    except Exception:
        return jsonify({'error':'Não foi possível ler o PDF.'}), 400
    text_content = '\n\n'.join(parts)
    if sum(len(part.split('\n', 1)[-1].strip()) for part in parts) < 100:
        return jsonify({'error':'PDF sem texto pesquisável suficiente. É necessário OCR e conferência antes do cadastro.'}), 400
    if len(text_content)>1_500_000:
        return jsonify({'error':'Texto normativo acima do limite de 1,5 milhão de caracteres.'}), 400
    with db_connect() as conn:
        row=conn.execute("INSERT INTO dpm_normative_documents (title,source_url,content,created_by) VALUES (%s,%s,%s,%s) RETURNING id",(title,url,text_content,session['user_id'])).fetchone()
        audit(conn,'normative_uploaded',row['id'])
    return jsonify({'id':row['id'],'characters':len(text_content),'message':'Texto extraído e armazenado para pesquisa; conferir o original.'}),201

@app.delete('/api/normative/documents/<int:doc_id>')
def disable_normative_document(doc_id):
    denied=admin_only()
    if denied: return denied
    with db_connect() as conn:
        result=conn.execute('UPDATE dpm_normative_documents SET active=FALSE WHERE id=%s',(doc_id,))
        audit(conn,'normative_disabled',doc_id)
    return jsonify({'ok':bool(result.rowcount)})

@app.get('/api/history/users')
def history_users():
    with db_connect() as conn:
        if session.get('role') == 'admin':
            rows = conn.execute("SELECT id,username,role FROM dpm_users WHERE deleted_at IS NULL AND active ORDER BY username").fetchall()
        else:
            rows = conn.execute("SELECT id,username,role FROM dpm_users WHERE id=%s", (session['user_id'],)).fetchall()
    return jsonify({'users': [dict(r) for r in rows]})


@app.get('/api/history')
def analysis_history():
    view = request.args.get('view', 'active')
    folder = request.args.get('folder', 'all')
    review_status = request.args.get('review_status', 'all')
    protocol_scope = request.args.get('scope') == 'protocols'
    if review_status not in ('all','pending','in_progress','completed'):
        return jsonify({'error':'Situação inválida.'}),400
    if view not in ('active','archived','all') or folder not in ('all','mine','unassigned') and not folder.startswith('user:'):
        return jsonify({'error':'Filtro inválido.'}),400
    conditions=[]; params=[]
    if review_status != 'all':
        conditions.append('h.review_status = %s');params.append(review_status)
    if view!='all':
        conditions.append('h.archived = %s');params.append(view=='archived')
    if session.get('role')!='admin':
        if protocol_scope:
            conditions.append('h.assigned_to = %s')
            params.append(session['user_id'])
            if folder not in ('mine','all') and folder != 'user:'+str(session['user_id']):
                return jsonify({'error':'Acesso negado à pasta.'}),403
        else:
            conditions.append('(h.assigned_to = %s OR (h.assigned_to IS NULL AND h.user_id = %s))')
            params.extend([session['user_id'],session['user_id']])
    if folder=='mine':
        conditions.append('h.assigned_to = %s');params.append(session['user_id'])
    elif folder=='unassigned':
        conditions.append('h.assigned_to IS NULL')
    elif folder.startswith('user:'):
        try: target=int(folder[5:])
        except ValueError: return jsonify({'error':'Pasta inválida.'}),400
        if session.get('role')!='admin' and target!=session['user_id']:
            return jsonify({'error':'Acesso negado.'}),403
        conditions.append('h.assigned_to = %s');params.append(target)
    where=' AND '.join(conditions) or 'TRUE'
    with db_connect() as conn:
        rows=conn.execute(f"""SELECT h.id,h.protocol_label,h.document_count,h.page_count,
            h.status,h.review_status,h.archived,h.created_at,h.assigned_to,h.report_data IS NOT NULL AS has_report,
            u.username, owner.username AS assignee
            FROM dpm_analysis_history h JOIN dpm_users u ON u.id=h.user_id
            LEFT JOIN dpm_users owner ON owner.id=h.assigned_to
            WHERE {where} ORDER BY h.created_at DESC LIMIT 100""",params).fetchall()
    return jsonify({'items':[dict(r,created_at=r['created_at'].isoformat()) for r in rows]})


@app.patch('/api/history/<int:record_id>/assign')
def assign_analysis(record_id):
    if session.get('role')!='admin':
        return jsonify({'error':'Somente administradores podem distribuir protocolos.'}),403
    payload=request.get_json(silent=True) or {}
    target=payload.get('user_id')
    if target is not None and (type(target) is not int or target<1):
        return jsonify({'error':'Responsável inválido.'}),400
    with db_connect() as conn:
        if target is not None and not conn.execute('SELECT id FROM dpm_users WHERE id=%s AND deleted_at IS NULL AND active',(target,)).fetchone():
            return jsonify({'error':'Usuário não encontrado.'}),404
        row=conn.execute('UPDATE dpm_analysis_history SET assigned_to=%s WHERE id=%s RETURNING id',(target,record_id)).fetchone()
        if not row:return jsonify({'error':'Registro não encontrado.'}),404
        audit(conn,'history_assigned',record_id)
    return jsonify({'ok':True,'assigned_to':target})


@app.patch('/api/history/<int:record_id>/status')
def update_protocol_status(record_id):
    payload=request.get_json(silent=True) or {}
    status=payload.get('status')
    if status not in ('pending','in_progress','completed'):
        return jsonify({'error':'Situação inválida.'}),400
    with db_connect() as conn:
        if session.get('role')=='admin':
            row=conn.execute('UPDATE dpm_analysis_history SET review_status=%s WHERE id=%s RETURNING id',(status,record_id)).fetchone()
        else:
            row=conn.execute("""UPDATE dpm_analysis_history SET review_status=%s WHERE id=%s
                AND (assigned_to=%s OR (assigned_to IS NULL AND user_id=%s)) RETURNING id""",
                (status,record_id,session['user_id'],session['user_id'])).fetchone()
        if not row:return jsonify({'error':'Registro não encontrado ou acesso negado.'}),404
        audit(conn,'history_status_updated',record_id)
    return jsonify({'ok':True,'status':status})

@app.get('/api/history/<int:record_id>/report')
def reopen_analysis(record_id):
    with db_connect() as conn:
        if session.get('role')=='admin':
            row=conn.execute('SELECT report_data FROM dpm_analysis_history WHERE id=%s',(record_id,)).fetchone()
        else:
            row=conn.execute("""SELECT report_data FROM dpm_analysis_history
                WHERE id=%s AND (assigned_to=%s OR (assigned_to IS NULL AND user_id=%s))""",
                (record_id,session['user_id'],session['user_id'])).fetchone()
    if not row:return jsonify({'error':'Registro não encontrado ou acesso negado.'}),404
    if row['report_data'] is None:
        return jsonify({'error':'Este registro não possui relatório salvo. Análises antigas guardam apenas metadados. Para salvar novos relatórios fictícios, configure DPM_PERSIST_REPORTS=1.'}),404
    return jsonify(row['report_data'])


@app.patch('/api/history/<int:record_id>/archive')
def archive_analysis(record_id):
    payload = request.get_json(silent=True) or {}
    if type(payload.get('archived')) is not bool:
        return jsonify({'error': 'Informe archived como true ou false.'}), 400
    archived = payload['archived']
    with db_connect() as conn:
        # Analistas só alteram registros próprios; administradores podem alterar todos.
        if session.get('role') == 'admin':
            row = conn.execute("""UPDATE dpm_analysis_history
                SET archived=%s, archived_at=CASE WHEN %s THEN NOW() ELSE NULL END
                WHERE id=%s RETURNING id""", (archived, archived, record_id)).fetchone()
        else:
            row = conn.execute("""UPDATE dpm_analysis_history
                SET archived=%s, archived_at=CASE WHEN %s THEN NOW() ELSE NULL END
                WHERE id=%s AND (assigned_to=%s OR (assigned_to IS NULL AND user_id=%s)) RETURNING id""",
                (archived, archived, record_id, session['user_id'],session['user_id'])).fetchone()
        if not row:
            return jsonify({'error': 'Registro não encontrado ou acesso negado.'}), 404
        audit(conn, 'history_archive' if archived else 'history_restore', record_id)
    return jsonify({'ok': True, 'id': record_id, 'archived': archived})


@app.delete('/api/history/<int:record_id>')
def delete_analysis(record_id):
    # Exclusão permanente restrita ao administrador e registrada em auditoria.
    forbidden = admin_only()
    if forbidden:
        return forbidden
    with db_connect() as conn:
        row = conn.execute('DELETE FROM dpm_analysis_history WHERE id=%s RETURNING id', (record_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Registro não encontrado.'}), 404
        audit(conn, 'history_delete', record_id)
    return jsonify({'ok': True, 'id': record_id})


@app.post('/api/history/batch')
def batch_history():
    payload = request.get_json(silent=True) or {}
    ids = payload.get('ids')
    action = payload.get('action')
    if not isinstance(ids, list) or not ids or len(ids) > 100 or any(type(v) is not int or v <= 0 for v in ids) or len(set(ids)) != len(ids):
        return jsonify({'error': 'Selecione de 1 a 100 registros válidos, sem repetição.'}), 400
    if action not in ('assign', 'archive', 'restore', 'delete'):
        return jsonify({'error': 'Ação inválida.'}), 400
    is_admin = session.get('role') == 'admin'
    if action in ('assign', 'delete') and not is_admin:
        return jsonify({'error': 'Somente administradores podem executar esta ação.'}), 403
    target = payload.get('user_id') if action == 'assign' else None
    if action == 'assign' and target is not None and (type(target) is not int or target <= 0):
        return jsonify({'error': 'Responsável inválido.'}), 400
    if action == 'delete' and payload.get('confirm') != 'EXCLUIR':
        return jsonify({'error': 'Confirmação obrigatória para exclusão.'}), 400
    with db_connect() as conn:
        if action == 'assign' and target is not None:
            user = conn.execute('SELECT id FROM dpm_users WHERE id=%s AND active AND deleted_at IS NULL', (target,)).fetchone()
            if not user:
                return jsonify({'error': 'Usuário de destino não encontrado ou inativo.'}), 404
        rows = conn.execute('SELECT id, user_id, assigned_to FROM dpm_analysis_history WHERE id = ANY(%s) FOR UPDATE', (ids,)).fetchall()
        if len(rows) != len(ids):
            return jsonify({'error': 'Um ou mais registros não foram encontrados. Nenhuma alteração realizada.'}), 404
        if not is_admin and any(r['assigned_to'] != session['user_id'] and not (r['assigned_to'] is None and r['user_id'] == session['user_id']) for r in rows):
            return jsonify({'error': 'Sem permissão para um ou mais registros. Nenhuma alteração realizada.'}), 403
        if action == 'assign':
            conn.execute('UPDATE dpm_analysis_history SET assigned_to=%s WHERE id=ANY(%s)', (target, ids))
        elif action in ('archive', 'restore'):
            archived = action == 'archive'
            conn.execute('UPDATE dpm_analysis_history SET archived=%s, archived_at=CASE WHEN %s THEN NOW() ELSE NULL END WHERE id=ANY(%s)', (archived, archived, ids))
        else:
            conn.execute('DELETE FROM dpm_analysis_history WHERE id=ANY(%s)', (ids,))
        for record_id in ids:
            audit(conn, 'history_batch_' + action, record_id)
    return jsonify({'ok': True, 'updated': len(ids)})


@app.get('/api/productivity')
def productivity():
    forbidden = admin_only()
    if forbidden: return forbidden
    try:
        days = int(request.args.get('days', '30'))
    except (ValueError, TypeError):
        return jsonify({'error': 'Período inválido.'}), 400
    if days not in (1, 7, 30, 90):
        return jsonify({'error': 'Período não permitido.'}), 400
    # Data de referência no Paraná; o filtro considera dias civis locais, não UTC.
    day_expr = "(h.created_at AT TIME ZONE 'America/Sao_Paulo')::date"
    period_filter = day_expr + " >= (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date - (%s::int - 1)"
    with db_connect() as conn:
        totals = conn.execute(f"""SELECT COUNT(*) AS analyses,
            COALESCE(SUM(h.document_count),0) AS documents,
            COUNT(*) FILTER (WHERE {day_expr} = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date) AS today
            FROM dpm_analysis_history h WHERE {period_filter}""", (days,)).fetchone()
        users = conn.execute(f"""SELECT u.username, u.role, u.active,
            COUNT(h.id) AS analyses,
            COALESCE(SUM(h.document_count),0) AS documents,
            COUNT(h.id) FILTER (WHERE {day_expr} = (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date) AS today
            FROM dpm_users u LEFT JOIN dpm_analysis_history h ON h.user_id=u.id AND {period_filter}
            WHERE u.deleted_at IS NULL
            GROUP BY u.id,u.username,u.role,u.active ORDER BY analyses DESC,u.username""", (days,)).fetchall()
        daily = conn.execute(f"""SELECT {day_expr} AS day, COUNT(*) AS analyses
            FROM dpm_analysis_history h WHERE {period_filter}
            GROUP BY 1 ORDER BY 1""", (days,)).fetchall()
        # Situação atual das pastas, independentemente do período de criação.
        folders = conn.execute("""SELECT
            COUNT(*) FILTER (WHERE NOT archived AND COALESCE(review_status,'pending') = 'pending') AS pending,
            COUNT(*) FILTER (WHERE NOT archived AND review_status = 'in_progress') AS in_progress,
            COUNT(*) FILTER (WHERE NOT archived AND review_status = 'completed') AS completed,
            COUNT(*) FILTER (WHERE NOT archived AND assigned_to IS NULL) AS unassigned
            FROM dpm_analysis_history""").fetchone()
    return jsonify({'totals': totals, 'users': users,
                    'daily': [{'day': str(row['day']), 'analyses': row['analyses']} for row in daily],
                    'folders': folders, 'days': days, 'timezone': 'America/Sao_Paulo'})


@app.errorhandler(413)
def upload_too_large(error):
    return jsonify({"error": "Arquivo acima de 100 MB. Envie um documento menor ou divida o processo."}), 413

# Uma tarefa por vez neste processo. Resultados temporários somente em RAM.
_job_lock = threading.Lock()
_job_results = {}
_job_results_lock = threading.Lock()


def _job_update(job_id, status=None, page=None, total=None, stage=None):
    with db_connect() as conn:
        conn.execute("""UPDATE dpm_analysis_jobs SET
            status=COALESCE(%s,status), current_page=COALESCE(%s,current_page),
            total_pages=COALESCE(%s,total_pages), stage=COALESCE(%s,stage),
            updated_at=NOW() WHERE id=%s""", (status,page,total,stage,str(job_id)))


def _run_analysis_job(job_id, user_id, protocol, subject, observations, draft_type, path, name, ext, folder):
    try:
        _job_update(job_id,'running',stage='Iniciando extração')
        def progress(page, total):
            _job_update(job_id,page=page,total=total,stage=f'Lendo página {page} de {total}')
        if ext == '.pdf':
            pdf = extract_text_from_pdf(path, progress_callback=progress)
            data = {'documents':[{'name':name,'pages':pdf['pages']}], 'pages':pdf['pages'],
                    'text':pdf['text'], 'ocr_warnings':pdf.get('warnings',[]),
                    'ocr_pages':pdf.get('ocr_pages',0), 'ocr_success_pages':pdf.get('ocr_success_pages',0),
                    'ocr_characters':pdf.get('ocr_characters',0),
                    'ocr_page_diagnostics':pdf.get('ocr_page_diagnostics',[])}
        elif ext in ('.jpg','.jpeg','.png'):
            _job_update(job_id,total=1,stage='Reconhecendo imagem')
            image_result = extract_text_from_image(path)
            progress(1,1)
            data = {'documents':[{'name':name,'pages':1}], 'pages':1,'text':image_result['text']}
        else:
            data = analyze_zip(path, progress_callback=progress)
        if not data['documents']:
            raise ValueError('Nenhum documento compatível encontrado.')
        _job_update(job_id,stage='Gerando relatório')
        data['draft_type'] = draft_type
        report = generate_report(protocol,subject,observations,data)
        report = enhance_report(report,data.get('text',''))
        _attach_normative_matches(report, data.get('text',''))
        report['limitations'] = 'STATUS DA IA: ' + report.get('ai_status','não informado') + '\n\n' + report.get('limitations','')
        with db_connect() as conn:
            ocr = report.get('ocr_diagnostics') or {}
            row = conn.execute("""INSERT INTO dpm_analysis_history
                (user_id,protocol_label,document_count,page_count,ocr_attempted,ocr_read,ocr_characters,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (user_id,protocol[:80] or None,int(report.get('total_documents',0)),
                 int(report.get('total_pages',0)),int(ocr.get('attempted_pages',0)),
                 int(ocr.get('text_pages',0)),int(ocr.get('characters',0)),
                 'partial' if report.get('analysis_status')=='concluida_com_limitacoes' else 'completed')).fetchone()
            conn.execute('INSERT INTO dpm_audit(actor_id,action,target_id) VALUES (%s,%s,%s)',
                         (user_id,'analysis_completed',row['id']))
        if os.environ.get('DPM_PERSIST_REPORTS') == '1':
            import json
            with db_connect() as conn:
                conn.execute('UPDATE dpm_analysis_history SET report_data=%s::jsonb WHERE id=%s',
                             (json.dumps(report,ensure_ascii=False,default=str),row['id']))
        with _job_results_lock:
            _job_results[str(job_id)] = report
        _job_update(job_id,'completed',stage='Análise concluída')
    except Exception as exc:
        app.logger.exception('Falha na tarefa de análise')
        message = str(exc) if isinstance(exc,ValueError) else 'Falha no processamento. Consulte os logs.'
        try: _job_update(job_id,'failed',stage=message[:160])
        except Exception: app.logger.exception('Falha ao registrar erro da tarefa')
    finally:
        shutil.rmtree(folder,ignore_errors=True)
        gc.collect()
        _job_lock.release()


@app.post('/api/analyze/start')
def start_analysis():
    if not _job_lock.acquire(blocking=False):
        return jsonify({'error':'Já existe uma análise em andamento. Aguarde sua conclusão.'}),409
    folder = None
    try:
        uploaded = request.files.get('file')
        if not uploaded or not uploaded.filename:
            raise ValueError('Selecione um arquivo.')
        name = secure_filename(uploaded.filename)
        ext = os.path.splitext(name)[1].lower()
        if ext not in ('.pdf','.zip','.jpg','.jpeg','.png'):
            raise ValueError('Formato não suportado.')
        folder = tempfile.mkdtemp(prefix='dpm_job_')
        path = os.path.join(folder,name)
        uploaded.save(path)
        if os.path.getsize(path) > 100*1024*1024:
            raise ValueError('Arquivo acima de 100 MB.')
        job_id = str(uuid.uuid4())
        user_id = session['user_id']
        with db_connect() as conn:
            conn.execute('INSERT INTO dpm_analysis_jobs(id,user_id,status) VALUES (%s,%s,%s)',(job_id,user_id,'queued'))
        worker = threading.Thread(target=_run_analysis_job,
            args=(job_id,user_id,request.form.get('protocol','').strip(),
                  request.form.get('subject','').strip(),request.form.get('observations','').strip(),
                  request.form.get('draft_type','encaminhamento').strip(),path,name,ext,folder),daemon=True)
        worker.start()
        return jsonify({'job_id':job_id}),202
    except ValueError as exc:
        if folder: shutil.rmtree(folder,ignore_errors=True)
        _job_lock.release()
        return jsonify({'error':str(exc)}),400
    except Exception:
        if folder: shutil.rmtree(folder,ignore_errors=True)
        _job_lock.release()
        app.logger.exception('Falha ao iniciar análise')
        return jsonify({'error':'Não foi possível iniciar a análise.'}),500


@app.get('/api/analyze/progress/<uuid:job_id>')
def analysis_progress(job_id):
    with db_connect() as conn:
        row=conn.execute("""SELECT status,current_page,total_pages,stage,updated_at
            FROM dpm_analysis_jobs WHERE id=%s AND user_id=%s""",(str(job_id),session['user_id'])).fetchone()
    if not row: return jsonify({'error':'Tarefa não encontrada.'}),404
    status=row['status']
    # Reinício da instância ou processo interrompido: progresso não é conclusão.
    if status in ('queued','running') and ( __import__('datetime').datetime.now(__import__('datetime').timezone.utc)-row['updated_at']).total_seconds()>240:
        status='interrupted'
        _job_update(job_id,'interrupted',stage='Processamento interrompido. Envie o arquivo novamente.')
    return jsonify({'status':status,'page':row['current_page'],'total':row['total_pages'],
                    'stage':row['stage'] if status!='interrupted' else 'Processamento interrompido. Envie novamente.'})


@app.get('/api/analyze/result/<uuid:job_id>')
def analysis_result(job_id):
    with db_connect() as conn:
        row=conn.execute('SELECT status FROM dpm_analysis_jobs WHERE id=%s AND user_id=%s',
                         (str(job_id),session['user_id'])).fetchone()
    if not row: return jsonify({'error':'Tarefa não encontrada.'}),404
    if row['status']!='completed': return jsonify({'error':'Análise ainda não concluída.'}),409
    with _job_results_lock:
        report=_job_results.pop(str(job_id),None)
    if report is None:
        return jsonify({'error':'Resultado temporário indisponível após reinício do servidor. Reenvie o arquivo.'}),410
    return jsonify(report)


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
                "Selecione um arquivo PDF, ZIP, JPG ou PNG."
            )
        }), 400

    name = secure_filename(
        uploaded.filename or ""
    )

    ext = os.path.splitext(name)[1].lower()

    if ext not in (".pdf", ".zip", ".jpg", ".jpeg", ".png"):
        return jsonify({
            "error": (
                "Formato não suportado. "
                "Envie PDF, ZIP, JPG ou PNG."
            )
        }), 400

    try:

        with tempfile.TemporaryDirectory() as temp:

            path = os.path.join(temp, name)

            uploaded.save(path)
            if os.path.getsize(path) > 100 * 1024 * 1024:
                raise ValueError("Arquivo acima de 100 MB.")

            if ext == ".pdf":

                pdf = extract_text_from_pdf(path)

                data = {
                    "documents": [{
                        "name": name,
                        "pages": pdf["pages"]
                    }],
                    "pages": pdf["pages"],
                    "text": pdf["text"],
                    "ocr_warnings": pdf.get("warnings", []),
                    "ocr_pages": pdf.get("ocr_pages", 0),
                    "ocr_success_pages": pdf.get("ocr_success_pages", 0),
                    "ocr_characters": pdf.get("ocr_characters", 0),
                    "ocr_page_diagnostics": pdf.get("ocr_page_diagnostics", [])
                }

            elif ext in (".jpg", ".jpeg", ".png"):
                image_result = extract_text_from_image(path)
                data = {
                    "documents": [{"name": name, "pages": 1}],
                    "pages": 1,
                    "text": image_result["text"]
                }
            else:
                data = analyze_zip(path)

            if not data["documents"]:

                return jsonify({
                    "error": (
                        "Nenhum documento compatível foi encontrado "
                        "no arquivo ZIP."
                    )
                }), 400

            data['draft_type'] = request.form.get('draft_type', 'encaminhamento').strip()
            report = generate_report(
                protocol,
                subject,
                observations,
                data
            )

            # A IA só é habilitada explicitamente e deve receber apenas dados
            # fictícios/anonimizados nesta fase de testes.
            report = enhance_report(report, data.get("text", ""))
            _attach_normative_matches(report, data.get("text", ""))
            report["limitations"] = "STATUS DA IA: " + report.get("ai_status", "não informado") + "\n\n" + report.get("limitations", "")

            # Grava apenas metadados mínimos após a análise bem-sucedida.
            # Não persiste conteúdo do arquivo nem o relatório gerado.
            with db_connect() as conn:
                conn.execute("""INSERT INTO dpm_analysis_history
                    (user_id, protocol_label, document_count, page_count)
                    VALUES (%s,%s,%s,%s)""", (
                        session['user_id'], protocol[:80] or None,
                        int(report.get('total_documents', 0)),
                        int(report.get('total_pages', 0))
                    ))
                audit(conn, 'analysis_completed')
            return jsonify(report)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
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
