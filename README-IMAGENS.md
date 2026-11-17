# Imagens JPG e PNG no DPM Inteligente

Esta atualização adiciona OCR **local** para JPG, JPEG e PNG via RapidOCR/ONNX Runtime e Pillow. Não usa nem cobra API da OpenAI. A primeira análise pode demorar devido à inicialização do OCR. Render com pouca memória pode precisar de plano com mais recursos.

Também melhora a mensagem de erro quando `/api/analyze` responde HTML em vez de JSON. **Isso não corrige necessariamente a causa do erro anterior**; consulte os logs do Render se ocorrer.

## Deploy
Substitua os arquivos no repositório, incluindo o novo `image_service.py` e `requirements.txt`. Mantenha `DATABASE_URL`, `DPM_SECRET_KEY` e demais variáveis existentes. Não envie arquivos `.env`.

## Limitações
OCR não é perfeito: fotos borradas, documentos manuscritos, baixa resolução e layouts complexos podem produzir texto incorreto. O relatório gerado continua baseado em regras, não em IA generativa. Não use dados médicos reais até avaliação de segurança, LGPD, retenção e controle de acesso. O ZIP continua aceitando PDFs; JPG/PNG devem ser enviados individualmente.
