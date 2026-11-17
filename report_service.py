"""Relatório local por regras, com evidências e sem decisões automáticas."""
import re

TOPICS = {
    'Requerimento': r'\b(requer|solicita|pedido|requerimento)\b',
    'Atestado ou documento médico': r'\b(atestado|laudo médico|afastamento)\b',
    'Despacho': r'\bdespacho\b',
    'Frequência funcional': r'\b(frequência|ausência|lotação|registro funcional)\b',
    'Juntada de documentos': r'\b(juntada|anexo|complementação)\b',
    'Prazo mencionado': r'\b(prazo|urgência|urgente)\b',
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

def generate_report(protocol, subject, observations, data):
    text = data.get('text', '') or ''
    documents = data.get('documents', []) or []
    pages = data.get('pages', 0)
    inferred = _infer_subject(text)
    # Assunto escolhido no formulário permanece visível, mas divergência é sinalizada.
    effective = inferred or subject or 'Não informado'
    findings = [label for label, pattern in TOPICS.items() if _evidence(text, pattern, 1)]
    attention = list(data.get('ocr_warnings', []))
    if subject and inferred and subject.casefold() != inferred.casefold():
        attention.append(f'Assunto informado no formulário ({subject}) difere do objeto identificado ({inferred}); conferir classificação.')
    evidence = []
    for label, pattern in CHECKS:
        hits = _evidence(text, pattern)
        if hits:
            refs = ', '.join(str(h['page']) for h in hits)
            attention.append(f'{label} (páginas {refs}); conferir documentos originais.')
            evidence.append({'topic': label, 'excerpt': f"[Página {hits[0]['page']}] {hits[0]['excerpt']}"})
    # Evidências de documentos e assuntos, não apenas de pendências.
    # Excertos sempre vêm do texto extraído e mantêm a referência de página.
    for label, pattern in TOPICS.items():
        if len(evidence) >= 12:
            break
        hits = _evidence(text, pattern, limit=2)
        for hit in hits:
            if len(evidence) >= 12:
                break
            excerpt = f"[Página {hit['page']}] {hit['excerpt']}"
            if not any(e['excerpt'] == excerpt for e in evidence):
                evidence.append({'topic': label, 'excerpt': excerpt})
    if data.get('ocr_pages', 0):
        successes = data.get('ocr_success_pages', 0)
        attempted = data.get('ocr_pages', 0)
        if successes < attempted:
            attention.append(f'OCR: texto reconhecido em {successes} de {attempted} página(s) submetida(s); conferir as demais no original.')
    if any(d.get('error') for d in documents):
        attention.append('Há arquivo com falha de leitura; conferir anexos.')
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
    detail.extend(['', '5. PROVIDÊNCIAS SUGERIDAS',
                   'Conferir a sequência de juntadas e os despachos anteriores; verificar documentos originais, datas, assinaturas e registros de recebimento.',
                   'Não inferir autenticidade de atestado, prazo legal, direito ou decisão administrativa a partir da extração textual.'])
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
    draft = [f'MINUTA PARA REVISÃO — Protocolo {protocol or "[informar]"}',
             f'Assunto: {effective}', f'Tipo: {draft_title}', '',
             'Considerando o requerimento e os documentos apresentados, registra-se a necessidade de conferência pela unidade competente.',
             draft_instruction]
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
    if observations and observations.strip():
        # Não apresenta as instruções do analista como prova documental.
        clean_obs = ' '.join(observations.split())[:1500]
        draft.append('Orientações adicionais fornecidas pelo analista (sujeitas à conferência): ' + clean_obs)
    if data.get('ocr_warnings'):
        draft.append('As páginas com alerta de OCR deverão ser conferidas diretamente no PDF original.')
    draft.append('DOCUMENTO DE TRABALHO — exige conferência, revisão e aprovação formal por agente autorizado; não constitui conclusão médica, pericial ou jurídica.')
    return {
        'protocol': protocol, 'subject': effective, 'observations': observations,
        'documents': documents, 'total_documents': len(documents), 'total_pages': pages,
        'summary': summary, 'attention_points': attention, 'identified_topics': findings,
        'evidence': evidence[:12], 'preliminary_analysis': '\n'.join(detail),
        'suggested_response': '\n\n'.join(draft),
        'limitations': ('Análise local baseada em regras, sem IA generativa e sem custo de API. '
                        'Páginas com falha de OCR podem conter informações não examinadas. '
                        'Não valida autenticidade, prazos, direitos ou decisões. Revisão humana obrigatória.'),
    }
