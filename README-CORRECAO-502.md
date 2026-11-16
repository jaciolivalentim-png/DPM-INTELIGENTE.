# Correção de estabilidade do OCR — DPM Inteligente

Esta versão isola o motor OCR em `ocr_worker.py`, executado por subprocesso com limite de tempo e memória. Também reduz a resolução das imagens extraídas dos PDFs.

**Não garante OCR no Render gratuito:** se os recursos forem insuficientes, o sistema deve informar falha de OCR; páginas com texto digital continuam sendo processadas. PDFs apenas digitalizados podem não gerar relatório quando o OCR não conseguir ler o conteúdo.

Arquivos alterados: `image_service.py`, `pdf_service.py`. Arquivo novo: `ocr_worker.py`. As demais funcionalidades foram preservadas.

Se o Render continuar apresentando HTTP 502, confira os logs e monitore se o próprio serviço é reiniciado. A limitação pode exigir uma arquitetura de fila e worker externo ou um motor OCR mais leve.

Não envie dados médicos reais antes de validação de segurança, conformidade e autorização institucional.
