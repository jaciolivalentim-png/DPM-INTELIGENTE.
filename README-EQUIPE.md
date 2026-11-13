# Gestão da equipe — DPM Inteligente

## Render
- Serviço web e PostgreSQL na mesma região e conta.
- Em Environment, manter `DPM_SECRET_KEY`, `DPM_ADMIN_USER`, `DPM_ADMIN_PASSWORD` e adicionar `DATABASE_URL` (Internal Database URL).
- Build: `pip install -r requirements.txt`
- Start: `gunicorn --bind 0.0.0.0:$PORT main:app`
- O primeiro deploy cria as tabelas `dpm_users` e `dpm_audit` e a conta administrativa inicial.
- A senha administrativa do ambiente é usada **somente na criação inicial**. Alterações posteriores nessa variável não redefinem automaticamente a senha no banco.
- Entrar como administrador e abrir **Equipe** para criar contas. Analistas não podem administrar usuários.
- Para atualizar senhas, usar o botão **Redefinir senha** do painel administrativo.

## Avisos importantes
- O PostgreSQL gratuito do Render é temporário e não oferece backups adequados para produção.
- Antes de utilizar dados médicos reais, implementar auditoria completa de acesso a documentos, MFA, recuperação de acesso, políticas LGPD, limites persistentes de tentativas de login e revisão de segurança.
- O log incluído cobre somente alterações de contas, não todas as operações.
- A sessão de um usuário desativado é rejeitada na próxima requisição.
- Não enviar `DATABASE_URL`, senhas ou chaves de API ao GitHub.
- A integração OpenAI não foi alterada neste pacote.
