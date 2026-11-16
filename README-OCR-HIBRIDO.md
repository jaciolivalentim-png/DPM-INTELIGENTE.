# OCR híbrido — atualização

- PDFs com texto digital e imagens: extrai texto nativo e reconhece imagens incorporadas relevantes.
- PDFs digitalizados: OCR da página completa quando houver pouco texto nativo.
- OCR local, sem envio dos documentos para API externa.
- Para preservar recursos do Render, limita o OCR a 40 páginas por arquivo (configurável por `DPM_MAX_OCR_PAGES`) e até 3 regiões de imagem por página (`DPM_MAX_IMAGE_REGIONS_PER_PAGE`).
- Imagens pequenas, logotipos e ícones podem ser ignorados; o relatório registra avisos de processamento parcial em "Pontos de atenção".
- O OCR pode errar ou deixar trechos de fora. Confira sempre o documento original.
- Se o OCR falhar em uma região e houver texto nativo, o relatório prossegue com aviso, sem esconder a falha.
- Não muda banco de dados, contas de usuário ou chaves de API.
- Não use documentos médicos reais até validação institucional de segurança, LGPD e infraestrutura.

## Teste sugerido

Use um PDF fictício de 2 páginas, com texto selecionável e uma imagem grande contendo texto. Confirme se ambos aparecem no resumo e no relatório. Em seguida, teste PDF totalmente digitalizado. Monitore os logs do Render.
