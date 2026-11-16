# Atualização: arquivos grandes e relatório detalhado

- Limite de upload do Flask: 100 MiB. ZIP: até 100 arquivos e até 250 MiB de conteúdo descompactado, com PDF individual até 100 MiB.
- O relatório passou a selecionar até 18 trechos distintos, em vez de 5, com limite de 6.500 caracteres na síntese e análise preliminar em seções.
- Esta versão **não** usa a OpenAI; os textos são extrativos e baseados em regras. A extensão do relatório depende da qualidade do texto do PDF.
- PDFs digitalizados sem camada textual ainda não possuem OCR; JPG/PNG usam RapidOCR.
- Uploads grandes podem exceder memória ou tempo no Render. Não enviar dados sensíveis reais sem revisão de segurança, privacidade e infraestrutura.
- Dependências existentes foram preservadas; se o deploy falhar por RapidOCR, verifique compatibilidade da versão do Python no Render.
