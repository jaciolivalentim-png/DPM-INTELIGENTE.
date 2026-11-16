# DPM Inteligente — integração opcional OpenAI

## Render → Environment
- `OPENAI_API_KEY`: chave privada da OpenAI. Nunca colocar no GitHub nem no navegador.
- `DPM_AI_ENABLED`: `true` para habilitar apenas testes com documentos fictícios ou adequadamente anonimizados; `false` para desabilitar.
- `DPM_OPENAI_MODEL`: `gpt-6-luna` (padrão; requer acesso ao modelo na conta API).
- `DPM_AI_MAX_CHARS`: `24000` (padrão; limita custo e tamanho do documento enviado).

O sistema usa a Responses API, `store:false`, com uma solicitação por análise. A OpenAI cobra por tokens; ChatGPT Plus não inclui créditos da API. Verifique disponibilidade do modelo, custos e limites no painel da API.

O relatório existente continua funcionando caso a chave esteja ausente ou a API falhe. A interface existente é preservada. A API recebe o texto OCR extraído, não o PDF original, mas esse texto ainda pode conter dados pessoais sensíveis.

**NÃO usar documentos reais com dados médicos ou pessoais nesta versão.** Antes de produção: avaliação LGPD, base legal e acordos, controles de acesso/auditoria, gestão de segredos, retenção, avaliação de segurança e autorização institucional.

## Teste
1. Publique no GitHub os arquivos do ZIP, sem segredos.
2. Configure as variáveis no Render e aguarde o deploy.
3. Teste com o PDF fictício de 3 páginas. Confira a qualidade e compare com as páginas originais.
4. Se houver falha de rede ou credenciais, o relatório local continua sendo exibido.
