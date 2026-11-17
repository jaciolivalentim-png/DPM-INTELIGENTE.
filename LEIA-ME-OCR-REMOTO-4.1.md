# DPM Inteligente 4.1 — OCR separado (piloto)

## Importante
O OCR remoto **não está ativo automaticamente**. O site continua com OCR desativado em 512 MB até um serviço separado autorizado estar disponível. Não envie documentos reais/sensíveis ao piloto sem avaliação institucional de segurança, LGPD, retenção e infraestrutura.

## Arquivos alterados
- `image_service.py`: modo `remote` com HTTPS, token, timeout e limites.
- `ocr_remote_service.py`: servidor OCR separado, com autenticação por token e limite de upload.
- Demais arquivos foram preservados do ZIP recebido.

## Serviço OCR separado
Hospede em infraestrutura **separada**, com RAM adequada, acesso restrito, TLS, sem armazenamento persistente de imagens e controles operacionais. Configure a variável `DPM_OCR_REMOTE_TOKEN` com segredo forte (não colocar no GitHub). Comando de inicialização: `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 1 --timeout 180 ocr_remote_service:app`.

## Serviço principal
Configure no Render:
- `DPM_OCR_MODE=remote`
- `DPM_OCR_REMOTE_URL=https://SEU-SERVICO-AUTORIZADO/ocr`
- `DPM_OCR_REMOTE_TOKEN=` mesmo segredo do serviço OCR
- `DPM_OCR_TIMEOUT=180`

Não configure `DPM_OCR_MODE=on` no servidor principal de 512 MB. Se o serviço remoto falhar, o PDF mantém o texto nativo e informa aviso de OCR incompleto. O status 100% não garante OCR integral.

## Limitações e testes
Não há fila durável, retentativas automáticas, SSO, auditoria institucional ou homologação de segurança nesta versão. Execute testes com PDFs fictícios contendo imagens e confira o texto efetivamente extraído, páginas, logs e uso de RAM em ambos os serviços. Para produção, adicione isolamento por processo, limitação de requisições, gestão de segredos, políticas de retenção e auditoria. A interface oficial do e-Protocolo não foi integrada.
