# Atualização OCR e fundamentação documental

Esta versão parte da atualização com barra de progresso que já foi testada com 30 páginas.

## Mudanças
- Analisa imagens raster relevantes em páginas mistas, mesmo quando há texto nativo.
- Mantém o limite configurável `DPM_MAX_IMAGE_REGIONS_PER_PAGE` (padrão 1).
- Não interrompe o protocolo quando uma imagem falha; registra aviso por página.
- Inclui evidências por página para temas documentais além das pendências.
- Informa quando uma página submetida a OCR não produziu texto reconhecido.
- Preserva barra de progresso, autenticação, histórico e minuta.

## Atenção
- Mais páginas podem acionar OCR e elevar tempo/RAM. Faça testes com PDFs fictícios de 12, 20 e 30 páginas antes de usar arquivos maiores.
- A barra indica o avanço das páginas, não a validação do conteúdo extraído.
- OCR e correspondências por palavras não comprovam autenticidade nem correção de um documento.
- Em caso de 502, consulte Logs do Render e reduza `DPM_OCR_DPI` ou `DPM_MAX_IMAGE_REGIONS_PER_PAGE` (não aumente workers).
- O sistema permanece apenas para documentos fictícios ou anonimizados em ambiente de teste.

## Instalação
1. Faça backup do repositório atual.
2. Extraia o ZIP e envie os arquivos da pasta `DPM-INTELIGENTE.-main` para a raiz do repositório no GitHub.
3. Aguarde o deploy no Render e teste um protocolo fictício.
