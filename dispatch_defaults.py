"""Modelos iniciais de devolução, sem decisão de mérito ou dados médicos sensíveis."""

REASONS = [
    ('Esclarecimentos', 'Em atenção à solicitação, informamos que [ESCLARECIMENTO OBJETIVO].', 'Para esclarecimento da questão apresentada, verificou-se [INFORMAÇÕES VERIFICADAS]. Assim, informamos que [ESCLARECIMENTO OBJETIVO].'),
    ('Complementação de documentos', 'Para prosseguir com a análise, solicitamos a apresentação de [DOCUMENTOS PENDENTES].', 'A análise da solicitação depende da apresentação ou regularização de [DOCUMENTOS PENDENTES]. Após a complementação, o protocolo poderá ser reencaminhado para continuidade da análise.'),
    ('Resposta após análise', 'Após análise da solicitação, informamos que [RESULTADO DA ANÁLISE].', 'Após exame dos elementos disponíveis no protocolo, verificou-se [SÍNTESE DA ANÁLISE]. Em resposta à solicitação, informamos que [RESULTADO DA ANÁLISE].'),
    ('Regularização de pendências', 'Identificamos a seguinte pendência: [PENDÊNCIA IDENTIFICADA]. Solicitamos sua regularização.', 'Na conferência inicial do protocolo, identificou-se [PENDÊNCIA IDENTIFICADA]. Para dar continuidade ao procedimento, solicitamos [PROVIDÊNCIA NECESSÁRIA].'),
    ('Ciência de informação', 'Comunicamos que [INFORMAÇÃO A SER TRANSMITIDA], para ciência.', 'Em resposta ao protocolo, comunicamos que [INFORMAÇÃO A SER TRANSMITIDA]. A presente comunicação destina-se à ciência do destinatário e não substitui eventual decisão da autoridade competente.'),
]
OLD_TITLES = ('Encaminhamento para análise','Complementação documental','Pedido de reconsideração','Devolução para regularização','Encaminhamento para perícia')

def install_dispatch_defaults(conn):
    # Desativa apenas os dez modelos iniciais antigos. Não apaga histórico nem modelos personalizados.
    conn.execute('UPDATE dpm_dispatch_templates SET active=FALSE,updated_at=NOW() WHERE is_builtin=TRUE AND title=ANY(%s) AND active=TRUE', (list(OLD_TITLES),))
    for audience,category,recipient,return_to in (
        ('Servidor interessado','Servidor interessado','[NOME DO SERVIDOR]','ao(à) servidor(a) interessado(a)'),
        ('Unidade solicitante / RH','Unidade solicitante / RH','[UNIDADE SOLICITANTE / RH]','à unidade solicitante'),
    ):
        for reason,short,long in REASONS:
            title=f'Devolução — {reason} — {audience}'
            for fmt,paragraph in (('simplificado',short),('completo',long)):
                opening = f'DESPACHO — DEVOLUÇÃO DE PROTOCOLO\nProtocolo: [PROTOCOLO]\nAssunto: [ASSUNTO]\nDestinatário: {recipient}\n\n'
                if fmt=='simplificado':
                    body=opening+paragraph+f'\n\nRestituímos o protocolo {return_to} para ciência e providências cabíveis, quando necessárias.\n\n[CIDADE], [DATA].\n[RESPONSÁVEL / CARGO]\nDPM/SEAP'
                else:
                    body=opening+'1. SOLICITAÇÃO\nTrata-se de solicitação referente a [DESCRIÇÃO DO PEDIDO].\n\n2. MANIFESTAÇÃO DA DPM\n'+paragraph+f'\n\n3. DEVOLUÇÃO\nRestituímos o protocolo {return_to} para ciência e adoção das providências pertinentes, se houver.\n\n[CIDADE], [DATA].\n[RESPONSÁVEL / CARGO]\nDPM/SEAP'
                conn.execute("""INSERT INTO dpm_dispatch_templates(title,category,format,body,is_builtin,active)
                    VALUES (%s,%s,%s,%s,TRUE,TRUE)
                    ON CONFLICT (title,format,is_builtin)
                    DO UPDATE SET category=EXCLUDED.category,body=EXCLUDED.body,active=TRUE
                    WHERE dpm_dispatch_templates.category IS DISTINCT FROM EXCLUDED.category
                       OR dpm_dispatch_templates.body IS DISTINCT FROM EXCLUDED.body
                       OR dpm_dispatch_templates.active=FALSE""", (title,category,fmt,body))
