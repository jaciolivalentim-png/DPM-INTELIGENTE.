"""Relatório local por regras, com evidências e sem decisões automáticas."""
import re
from collections import defaultdict

TOPICS = {
    'Requerimento': r'\b(requer|solicita|pedido|requerimento)\b',
    'Atestado ou documento médico': r'\b(atestado|laudo\s+m[eé]dico|afastamento|declara[cç][aã]o\s+m[eé]dica)\b',
    'Despacho': r'\b(despacho|encaminhe-se|encaminhamento)\b',
    'Frequência funcional': r'\b(frequência|ausência|lotação|registro funcional)\b',
    'Juntada de documentos': r'\b(juntada|anexo|complementação)\b',
    'Prazo mencionado': r'\b(prazo|urg[eê]ncia|urgente)\b',
    'Comprovante ou declaração': r'\b(comprovante|declara[cç][aã]o|certid[aã]o)\b',
}
CHECKS = [
    ('Comprovante de recebimento não localizado ou insuficiente', r'\b(não localizou comprovante|sem comprovante|não comprova.*recebimento|não apresenta confirmação|comprovante.*ausente)\b'),
    ('Assinatura ou validação pendente', r'\b(sem assinatura|assinatura.*não preenchid|sem validação|autenticidade.*pendente|não validada|sem assinatura digital validada)\b'),
    ('Divergência de datas ou registros', r'\b(divergência|divergente|inconsistência|contradição)\b'),
    ('Necessidade de complementação documental', r'\b(pedido de complementação|solicita.se comprovante|documentos faltantes)\b'),
]
NOISE = re.compile(r'(?i)(documento ficticio|documento fictício|teste de sistema|sem validade oficial|registro documental de teste|controle de conferencia|controle de conferência|observacoes do tramitador|observações do tramitador|processo administrativo simulado|este conteudo e inteiramente inventado|este conteúdo é inteiramente inventado)')

def _pages(text):
    chunks = re.split(r'(?=\[Página\s+\d+\])', text or '', flags=re.I)
    for chunk in chunks:
        match = re.match(r'\[Página\s+(\d+)\]', chunk, re.I)
        if match:
            yield int(match.group(1)), chunk[match.end():]

def _clean_lines(chunk):
    out = []
    for line in chunk.splitlines():
        line = ' '.join(line.split())
        if len(line) < 12 or NOISE.search(line):
            continue
        if re.search(r'(?i)^p[aá]gina\s+\d+\s+de\s+\d+', line):
            continue
        out.append(line)
    return out

def _evidence(text, pattern, limit=3):
    found = []
    for page, chunk in _pages(text):
        lines = _clean_lines(chunk)
        for idx, line in enumerate(lines):
            if re.search(pattern, line, re.I):
                excerpt = line[:260]
                if not any(item['excerpt'] == excerpt for item in found):
                    found.append({'page': page, 'excerpt': excerpt})
                break
        if len(found) >= limit:
            break
    return found

def _infer_subject(text):
    # Prioriza o objeto do requerimento, não palavras isoladas de despachos.
    first = ' '.join(chunk for page, chunk in _pages(text) if page <= 3).lower()
    if re.search(r'frequ[eê]ncia|justificativa de aus[eê]ncia', first):
        return 'Regularização de frequência e justificativa de ausência'
    if re.search(r'revis[aã]o de cadastro|registro cadastral|cadastro funcional', first):
        return 'Revisão de cadastro funcional'
    return None


# Marcadores conservadores: são referências para conferência, não cálculos jurídicos.
DATE_RE = re.compile(r"(?<!\d)(\d{2}/\d{2}/\d{4})(?!\d)")
EVENT_PATTERNS = [
    ('Ciência da decisão', r'ci[eê]ncia(?:\s+eletr[oô]nica)?(?:\s+registrada)?|data\s+da\s+ci[eê]ncia'),
    ('Prazo indicado', r'vencimento|t[eé]rmino\s+do\s+prazo|prazo\s+(?:hipot[eé]tico|indicado|informado)'),
    ('Protocolo do recurso', r'recurso\s+(?:apresentado|protocolado)|protocolo\s+do\s+recurso'),
    ('Pedido de reconsideração', r'pedido\s+(?:formal\s+)?de\s+reconsidera[cç][aã]o|reconsidera[cç][aã]o\s+(?:apresentada|protocolada)'),
]

def _procedural_review(text):
    """Extrai eventos por contexto de página e evidência, sem presumir validade de prazo."""
    from datetime import datetime
    events, medical, claims, preexisting = [], [], [], []
    pages = list(_pages(text))
    page_map = {page: chunk for page, chunk in pages}
    # Páginas de relatório/minuta de exemplo não são fonte independente.
    for page, chunk in pages:
        heading = ' '.join(chunk[:600].split()).lower()
        if re.search(r'relat[oó]rio de an[aá]lise.*exemplo|minuta final.*exemplo', heading):
            preexisting.append(page)
    excluded = set(preexisting)
    # Preferir páginas documentais originais, e não quadros cronológicos ou pareceres recapitulativos.
    specs = [
        ('Ciência da decisão', r'ci[eê]ncia da decis[aã]o|registro de ci[eê]ncia', r'ci[eê]ncia(?: eletr[oô]nica)?(?: registrada)?\s+em\s+(\d{2}/\d{2}/\d{4})'),
        ('Prazo indicado', r'comunica[cç][aã]o de indeferimento|certid[aã]o administrativa de prazo', r'(?:prazo indicado na simula[cç][aã]o|vencimento hipot[eé]tico|vencimento)\s*[:em ]+\s*(\d{2}/\d{2}/\d{4})'),
        ('Protocolo do recurso', r'recurso apresentado fora do prazo', r'recurso apresentado em\s+(\d{2}/\d{2}/\d{4})'),
        ('Pedido de reconsideração', r'pedido formal de reconsidera[cç][aã]o', r'(?:(?:data|em)\s*[: ]+)(\d{2}/\d{2}/\d{4})'),
    ]
    for label, heading_pattern, date_pattern in specs:
        for page, chunk in pages:
            if page in excluded or not re.search(heading_pattern, chunk[:500], re.I):
                continue
            match = re.search(date_pattern, chunk, re.I)
            # Em páginas específicas, o campo Data pode ser apresentado isoladamente.
            if not match and label == 'Pedido de reconsideração':
                match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', chunk)
            if not match and label == 'Ciência da decisão':
                match = re.search(r'ci[eê]ncia eletr[oô]nica registrada em\s+(\d{2}/\d{2}/\d{4})', chunk, re.I)
            if not match and label == 'Prazo indicado':
                match = re.search(r'prazo indicado[^\n]{0,80}?(\d{2}/\d{2}/\d{4})', chunk, re.I)
            if not match and label == 'Prazo indicado':
                match = re.search(r'prazo indicado na\s+simula[cç][aã]o\s*:\s*(\d{2}/\d{2}/\d{4})', ' '.join(chunk.split()), re.I)
            if match:
                events.append({'type': label, 'date': match.group(1), 'page': page, 'excerpt': match.group(0)[:220]})
                break
    for page, chunk in pages:
        if page in excluded:
            continue
        for line in _clean_lines(chunk):
            if re.search(r'\b(alega|sustenta|afirma|relata|requer)\b', line, re.I) and len(claims) < 8:
                claims.append({'page': page, 'excerpt': line[:220]})
            if re.search(r'\b(atestado m[eé]dico simulado|declara[cç][aã]o de atendimento simulada|exame fict[ií]cio|relat[oó]rio cl[ií]nico fict[ií]cio)\b', line, re.I) and len(medical) < 12:
                medical.append({'page': page, 'excerpt': line[:220]})
    by_type = {event['type']: event for event in events}
    deadline = by_type.get('Prazo indicado')
    filed = by_type.get('Protocolo do recurso')
    delay = None
    if deadline and filed:
        try:
            delta = (datetime.strptime(filed['date'], '%d/%m/%Y') - datetime.strptime(deadline['date'], '%d/%m/%Y')).days
            if delta > 0:
                delay = {'days': delta, 'deadline': deadline['date'], 'filed': filed['date'], 'status': 'atraso_aparente'}
            else:
                delay = {'days': delta, 'deadline': deadline['date'], 'filed': filed['date'], 'status': 'sem_atraso_aparente'}
        except ValueError:
            pass
    return {'events': events, 'medical': medical, 'claims': claims,
            'preexisting_output_pages': preexisting, 'deadline_comparison': delay}

def generate_report(protocol, subject, observations, data):
    text = data.get('text', '') or ''
    documents = data.get('documents', []) or []
    pages = data.get('pages', 0)
    inferred = _infer_subject(text)
    procedural = _procedural_review(text)
    is_recourse = bool(re.search(r'recurso|reconsidera[cç][aã]o|intempestiv', text, re.I))
    # Assunto escolhido no formulário permanece visível, mas divergência é sinalizada.
    effective = inferred or subject or 'Não informado'
    findings = [label for label, pattern in TOPICS.items() if _evidence(text, pattern, 1)]
    # Avisos repetidos são agrupados sem apagar a referência às páginas.
    attention = list(dict.fromkeys(str(w) for w in data.get('ocr_warnings', []) if w))
    ocr_attempted = int(data.get('ocr_pages', 0) or 0)
    ocr_read = int(data.get('ocr_success_pages', 0) or 0)
    ocr_chars = int(data.get('ocr_characters', 0) or 0)
    if ocr_attempted and ocr_read < ocr_attempted:
        attention.append(f'Leitura OCR parcial: {ocr_read} de {ocr_attempted} página(s) com texto; conferir páginas sem leitura no original.')

    if subject and inferred and subject.casefold() != inferred.casefold():
        attention.append(f'Assunto informado no formulário ({subject}) difere do objeto identificado ({inferred}); conferir classificação.')
    evidence = []
    excluded_example_pages = set(procedural['preexisting_output_pages'])
    for label, pattern in CHECKS:
        hits = [h for h in _evidence(text, pattern, limit=12) if h['page'] not in excluded_example_pages][:3]
        if hits:
            refs = ', '.join(str(h['page']) for h in hits)
            attention.append(f'{label} (páginas {refs}); conferir documentos originais.')
            evidence.append({'topic': label, 'excerpt': f"[Página {hits[0]['page']}] {hits[0]['excerpt']}"})
    # Evidências de documentos e assuntos, não apenas de pendências.
    # Excertos sempre vêm do texto extraído e mantêm a referência de página.
    for label, pattern in TOPICS.items():
        if len(evidence) >= 12:
            break
        hits = [h for h in _evidence(text, pattern, limit=12) if h['page'] not in excluded_example_pages][:2]
        for hit in hits:
            if len(evidence) >= 12:
                break
            excerpt = f"[Página {hit['page']}] {hit['excerpt']}"
            if not any(e['excerpt'] == excerpt for e in evidence):
                evidence.append({'topic': label, 'excerpt': excerpt})
    # O reconhecimento de texto não comprova a autenticidade do documento.
    if data.get('ocr_pages', 0):
        successes = data.get('ocr_success_pages', 0)
        attempted = data.get('ocr_pages', 0)
        if successes < attempted:
            attention.append(f'OCR: texto reconhecido em {successes} de {attempted} página(s) submetida(s); conferir as demais no original.')
    if any(d.get('error') for d in documents):
        attention.append('Há arquivo com falha de leitura; conferir anexos.')
    if data.get('ocr_pages', 0) and data.get('ocr_success_pages', 0) == 0:
        attention.append('Nenhuma página submetida ao OCR produziu texto reconhecido; não utilizar esta análise como leitura integral.')
    attention = list(dict.fromkeys(attention))
    if not attention:
        attention.append('Nenhuma pendência identificada pelas regras; a conferência humana continua necessária.')
    opening = [f'Protocolo: {protocol or "não informado"}.', f'Objeto documental identificado: {effective}.',
               f'Foram contabilizadas {pages} páginas em {len(documents)} arquivo(s).']
    key_patterns = [
        ('Pedido principal', r'\b(requer|requerimento inicial|solicita|pedido de regulariza)\b'),
        ('Atestado', r'\b(atestado|afastamento)\b'),
        ('Despacho de encaminhamento', r'\b(despacho|encaminhe.se)\b'),
        ('Resposta administrativa', r'\b(resposta do setor|setor confirma|setor informa)\b'),
        ('Pendências', r'\b(pend[eê]ncia|n[aã]o localizou|sem assinatura|comprovante.*ausente)\b'),
    ]
    summary_lines = opening[:]
    if ocr_attempted:
        summary_lines.append(f'OCR: {ocr_read}/{ocr_attempted} página(s) com texto; {ocr_chars} caracteres reconhecidos. O reconhecimento não valida autenticidade.')
    summary_lines.append('Síntese de trechos localizados (não substitui leitura integral):')
    for label, pattern in key_patterns:
        hits = _evidence(text, pattern, 1)
        if hits:
            summary_lines.append(f"- {label}, p. {hits[0]['page']}: {hits[0]['excerpt'][:190]}")
    summary = '\n'.join(summary_lines)[:1600]
    detail = ['1. IDENTIFICAÇÃO', *opening, '', '2. DOCUMENTOS E TEMAS IDENTIFICADOS']
    detail.extend('- ' + x for x in findings)
    detail.extend(['', '3. PENDÊNCIAS PARA CONFERÊNCIA'])
    detail.extend('- ' + x for x in attention)
    detail.extend(['', '4. EVIDÊNCIAS COM PÁGINAS'])
    detail.extend('- ' + x['topic'] + ': ' + x['excerpt'] for x in evidence)
    if is_recourse:
        detail.extend(['', '5. SÍNTESE PROCESSUAL'])
        comp = procedural['deadline_comparison']
        if comp and comp['days'] > 0:
            detail.append(f"Atraso aritmético aparente de {comp['days']} dia(s) entre {comp['deadline']} e {comp['filed']}; não é conclusão jurídica sobre tempestividade.")
        else:
            detail.append('Não foi possível estabelecer atraso aparente a partir dos marcos extraídos.')
        detail.append('Alegações, documentos clínicos e cronologia são exibidos separadamente, com indicação das páginas para conferência.')
        detail.append('Os registros médicos não demonstram, por si só, impedimento juridicamente relevante.')
        if procedural['preexisting_output_pages']:
            detail.append('Relatório/minuta preexistentes no arquivo (p. ' + ', '.join(map(str, procedural['preexisting_output_pages'])) + ') não são conclusões independentes do sistema.')
    detail.extend(['', '9. CONTROLE DE LEITURA OCR',
                   f'Páginas submetidas: {ocr_attempted}; páginas com texto: {ocr_read}; caracteres reconhecidos: {ocr_chars}.',
                   'Uma página com texto reconhecido pode conter trechos ilegíveis ou erros de transcrição.',
                   '', '10. PROVIDÊNCIAS SUGERIDAS',
                   'Conferir a sequência de juntadas e os despachos anteriores; verificar documentos originais, datas, assinaturas e registros de recebimento.',
                   'Não inferir autenticidade de atestado, prazo legal, direito ou decisão administrativa a partir da extração textual.'])
    detail.extend(['', '11. CRITÉRIO DE CLASSIFICAÇÃO',
                   'Os temas acima são indicadores de palavras e expressões encontradas no texto extraído; não representam validação de documentos.',
                   'Referências e trechos devem ser conferidos visualmente no documento original, especialmente nas páginas processadas por OCR.'])
    # As orientações do analista não são tratadas como fatos verificados no PDF.
    draft_type = str(data.get('draft_type', 'encaminhamento') or 'encaminhamento')
    templates = {
        'encaminhamento': ('Encaminhamento',
            'Encaminhe-se o expediente à unidade competente para conferência documental e manifestação, sem decisão de mérito.'),
        'complementacao': ('Complementação documental',
            'Solicite-se à unidade responsável a verificação dos documentos e, se constatada ausência de peças necessárias, a complementação documental pelos canais institucionais.'),
        'devolucao': ('Devolução para saneamento',
            'Devolva-se o expediente à unidade de origem para conferência e eventual saneamento das inconsistências documentais, antes de novo encaminhamento.'),
        'conferencia': ('Conferência documental',
            'Proceda-se à conferência dos documentos juntados, datas, registros de recebimento e sequência dos despachos, registrando eventuais divergências.'),
    }
    draft_title, draft_instruction = templates.get(draft_type, templates['encaminhamento'])
    draft = [
        'DPM INTELIGENTE | MINUTA ADMINISTRATIVA PARA REVISÃO',
        'Documento de trabalho — sem aprovação institucional automática',
        f'Protocolo: {protocol or "[informar]"}',
        f'Assunto para conferência: {effective}',
        f'Natureza da minuta: {draft_title}',
        'Unidade destinatária: [preencher após conferência]',
        '',
        'I — CONTEXTUALIZAÇÃO',
        f'O expediente identificado pelo protocolo {protocol or "[informar]"} foi submetido a uma leitura documental automatizada de apoio, abrangendo {pages} página(s) e {len(documents)} arquivo(s).',
        'A presente minuta não atesta autenticidade, regularidade ou procedência do pedido.',
        'A classificação é indicativa e depende de conferência do conteúdo e das páginas originais.',
        f'Controle OCR: {ocr_read} de {ocr_attempted} página(s) submetida(s) com texto reconhecido; {ocr_chars} caracteres. O resultado não comprova leitura integral.',
        '',
        'II — PROVIDÊNCIA PROPOSTA',
        ('Tratando-se de recurso ou reconsideração, conferir previamente a ciência, o prazo aplicável, a data do protocolo e eventual fundamento normativo para apreciar a justificativa de atraso; somente após a admissibilidade avaliar o mérito. ' + draft_instruction) if is_recourse else draft_instruction,
        '',
        'III — REFERÊNCIAS PARA CONFERÊNCIA',
    ]
    # Agrupa temas e páginas, sem repetir categorias ou inventar fatos.
    references = []
    for item in evidence:
        topic = item['topic']
        if topic in TOPICS and topic not in [t for t, _ in references]:
            pages_found = sorted({int(m) for ev in evidence if ev['topic'] == topic
                                  for m in re.findall(r'\[Página\s+(\d+)\]', ev['excerpt'])})
            if pages_found:
                references.append((topic, pages_found))
    if references:
        items = [f"{topic.lower()} (p. {', '.join(map(str, page_list))})"
                 for topic, page_list in references[:5]]
        draft.append('Referências documentais a conferir no original: ' + '; '.join(items) + '.')
    else:
        draft.append('Não foram localizadas referências suficientes para individualizar os documentos; conferir o processo original.')
        if data.get('ocr_success_pages', 0):
            draft.append('Há texto reconhecido por OCR, mas não foi classificado como evidência documental pelas regras atuais.')
    if is_recourse and procedural['deadline_comparison'] and procedural['deadline_comparison']['days'] > 0:
        comp = procedural['deadline_comparison']
        draft.append(f"Atenção: há atraso aparente de {comp['days']} dia(s) entre o vencimento indicado ({comp['deadline']}) e o protocolo do recurso ({comp['filed']}). Conferir a regra aplicável antes de concluir pela intempestividade.")
    if is_recourse and procedural['events']:
        draft.append('Marcos essenciais: ' + '; '.join(f"{e['type'].lower()} em {e['date']} (p. {e['page']})" for e in procedural['events'][:4]) + '. Confirmar no original.')
    if is_recourse and procedural['preexisting_output_pages']:
        draft.append('Atenção: relatório/minuta de exemplo já constam no arquivo (p. ' + ', '.join(map(str, procedural['preexisting_output_pages'])) + '); não são validação independente.')
    if attention and not (len(attention) == 1 and attention[0].startswith('Nenhuma pendência')):
        draft.append('IV — ALERTAS PARA CONFERÊNCIA')
        draft.extend('- ' + str(a)[:240] for a in attention[:6])
    if observations and observations.strip():
        # Não apresenta as instruções do analista como prova documental.
        clean_obs = ' '.join(observations.split())[:1500]
        draft.append('Orientações adicionais fornecidas pelo analista (sujeitas à conferência): ' + clean_obs)
    if ocr_attempted and ocr_read < ocr_attempted:
        draft.append('A leitura OCR foi parcial; a unidade responsável deverá conferir diretamente as páginas sem texto reconhecido.')
    if data.get('ocr_warnings'):
        draft.append('As páginas com alerta de OCR deverão ser conferidas diretamente no PDF original.')
    draft.extend([
        '',
        'V — CONFERÊNCIA E RESPONSABILIDADE',
        'Responsável pela conferência: [nome / matrícula]',
        'Unidade: [preencher]',
        'Data: [preencher]',
        'Encaminhamento final: [preencher pelo agente competente]',
        '',
        'DOCUMENTO DE TRABALHO — exige conferência, revisão e aprovação formal por agente autorizado; não constitui conclusão médica, pericial ou jurídica.',
    ])
    comparison = procedural['deadline_comparison']
    conclusion = ('Atraso aparente de ' + str(comparison['days']) + ' dias entre o vencimento informado e o protocolo do recurso. ' if comparison and comparison['days'] > 0 else 'Prazo não conclusivamente determinado. ')
    conclusion += ('Conferir ciência, regra de contagem, expediente, justificativa e documentação clínica. '
                   'Os documentos médicos não comprovam automaticamente impossibilidade de recorrer. '
                   'A admissibilidade e o mérito dependem de análise humana pela unidade competente.')
    return {
        'technical_conclusion': conclusion,
        'protocol': protocol, 'subject': effective, 'observations': observations,
        'documents': documents, 'total_documents': len(documents), 'total_pages': pages,
        'summary': summary, 'attention_points': attention, 'identified_topics': findings,
        'ocr_diagnostics': {'attempted_pages': data.get('ocr_pages', 0),
                            'text_pages': data.get('ocr_success_pages', 0),
                            'characters': data.get('ocr_characters', 0),
                            'pages': data.get('ocr_page_diagnostics', [])},
        'evidence': evidence[:12], 'procedural_review': procedural, 'preliminary_analysis': '\n'.join(detail),
        'suggested_response': '\n\n'.join(draft),
        'classification_method': 'Regras de correspondência textual; categorias são indícios, não validação de documentos.',
        'review_required': True,
        'analysis_status': 'concluida_com_limitacoes' if (ocr_attempted and ocr_read < ocr_attempted) or data.get('ocr_warnings') else 'concluida_para_revisao',
        'limitations': ('Análise local baseada em regras, sem IA generativa e sem custo de API. '
                        'Páginas com falha de OCR podem conter informações não examinadas. '
                        'Não valida autenticidade, prazos, direitos ou decisões. Revisão humana obrigatória.'),
    }
