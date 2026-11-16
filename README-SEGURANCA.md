# DPM Inteligente — login inicial de teste

Esta atualização mantém os arquivos na **raiz** do repositório (Root Directory vazio no Render).

## Configuração obrigatória no Render

Em **Environment**, adicione estas variáveis como valores secretos (não no GitHub):

- `DPM_ADMIN_USER`: nome do usuário administrador (ex.: admin)
- `DPM_ADMIN_PASSWORD`: senha exclusiva e forte de **pelo menos 12 caracteres**
- `DPM_SECRET_KEY`: sequência aleatória, exclusiva, com **pelo menos 32 caracteres**; use um gerador criptograficamente seguro ou a opção Generate do Render, se disponível.

**Não envie senhas ou chaves pelo chat, não coloque no código e não compartilhe capturas que as exibam.**

Render:
- Root Directory: vazio
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --bind 0.0.0.0:$PORT main:app`

Sem as duas variáveis secretas, o servidor falhará propositalmente ao iniciar.

## Teste após deploy
1. Abrir o site em aba anônima: deve aparecer o login.
2. Tentar senha incorreta: deve negar acesso.
3. Entrar com credenciais configuradas: deve mostrar a interface azul.
4. Testar análise somente com PDF fictício.
5. Clicar em Sair e confirmar que o painel não abre sem login.

## Limitações de segurança importantes
- É um **login administrativo único para testes**, não um sistema institucional multiusuário.
- A senha fica no gerenciador de variáveis de ambiente do Render e é transformada em hash em memória na inicialização; para produção, migrar para provedor de identidade e armazenamento de credenciais com hash persistente.
- Limitação de tentativas de login é por processo e não resiste a múltiplas instâncias/reinicializações; usar rate limiting centralizado/WAF antes de exposição pública.
- Não há ainda RBAC, MFA, logs de auditoria persistentes, retenção controlada, consentimento/avaliação LGPD, nem verificação antimalware.
- Sessões usam cookies assinados; não armazenar conteúdo médico no navegador. O histórico exibido é apenas da sessão da página.
- O endpoint `/health` é público e não revela dados.
- Não usar documentos reais ou sensíveis nesta versão.
