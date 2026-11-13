# Histórico e produtividade — DPM Inteligente

## Atualização
Substitua os arquivos na raiz do repositório GitHub e faça o deploy no Render. Não modifique as variáveis de ambiente. O banco existente é mantido; a tabela `dpm_analysis_history` é criada automaticamente na inicialização.

## Funcionalidades
- Histórico persistente das últimas 100 análises: administrador vê todas, analista vê apenas as próprias.
- Painel Produtividade exclusivo do administrador, com totais e contagem por usuário.
- Dados persistidos: ID do usuário, identificador do protocolo fornecido, número de documentos/páginas, status `completed` e data/hora.
- Não são armazenados PDFs, conteúdo textual, relatórios nem nomes dos arquivos.
- Registros anteriores à atualização não aparecem porque antes eram mantidos somente na memória do navegador.

## Atenção
**Somente documentos fictícios ou adequadamente anonimizados nos testes.** Não está pronto para protocolos médicos reais: falta revisão de LGPD, proteção de dados, autorização institucional, backup, retenção, auditoria de acesso, monitoramento e testes de segurança.
O identificador do protocolo é salvo no banco; não use identificadores reais/sensíveis nesta fase.
As métricas diárias seguem a data do banco de dados.
O sistema atual não implementa status de revisão ou fluxo de aprovação; apenas registra análises concluídas.
O PostgreSQL gratuito do Render não é apropriado como banco definitivo de produção com dados sensíveis.
