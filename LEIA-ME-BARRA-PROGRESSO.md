# Atualização: barra de progresso

A análise agora começa em `/api/analyze/start`, atualiza a contagem de páginas no PostgreSQL e a interface consulta `/api/analyze/progress/<id>` a cada 1,5 segundo. O relatório é recuperado em `/api/analyze/result/<id>` após a conclusão.

## Instalação

Substitua os arquivos do repositório pelos desta pasta e faça deploy no Render. Preserve as variáveis `DATABASE_URL`, `DPM_SECRET_KEY` e `DPM_ADMIN_PASSWORD`. Não execute migração que apague tabelas: a nova tabela `dpm_analysis_jobs` é criada automaticamente.

## Limitações importantes

- Apenas uma análise simultânea por processo Gunicorn. Manter `--workers 1`; a trava de processamento é local ao processo.
- O resultado completo fica apenas temporariamente na memória do processo e é retirado quando consultado. Não é salvo no histórico. Se o Render reiniciar antes da consulta, será necessário reenviar o arquivo.
- Reinícios e falta de memória podem interromper a tarefa. A barra não evita esgotamento de RAM, não garante OCR de 58 páginas e não é uma fila durável de produção.
- Para arquivos ZIP, o progresso mostra páginas concluídas mas não possui total pré-calculado, portanto a barra fica indeterminada até o relatório estar pronto.
- A tabela de tarefas registra somente ID, usuário, status, contagens e etapa, sem conteúdo do documento.
- Use somente documentos fictícios/anonimizados neste ambiente de teste.
