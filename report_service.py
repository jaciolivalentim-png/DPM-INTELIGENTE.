            break
    return result


def _snippets(text, pattern, limit=3):
    return [s[:260] for s in substantive_sentences(text) if re.search(pattern, s, re.I)][:limit]


def _page_refs(text, pattern, limit=3):
    # Só cita páginas se houver marcadores claros no texto extraído.
    hits = []
    chunks = re.split(r'(?=\[Página\s*\d+\]|\bPágina\s+\d+\s+de\s+\d+)', text or '', flags=re.I)
    for chunk in chunks:
        match = re.match(r'\s*(?:\[Página\s*(\d+)\]|Página\s+(\d+)\s+de\s+\d+)', chunk, re.I)
        if match and re.search(pattern, chunk, re.I):
            n = int(match.group(1) or match.group(2))
            if n not in hits:
                hits.append(n)
    return hits[:limit]


def summary(text, limit=1100):
    chunks = substantive_sentences(text)
    if not chunks:
        return 'Não foi possível extrair texto suficiente para resumir o expediente.'
    terms = Counter(w for w in re.findall(r'\b[a-zà-ÿ]{4,}\b', ' '.join(chunks).lower()) if w not in STOP)
    ranked = []
    for idx, s in enumerate(chunks):
        words = re.findall(r'\b[a-zà-ÿ]{4,}\b', s.lower())
        score = sum(min(terms[w], 6) for w in set(words)) / max(len(words), 8)
        if re.search(r'\b(solicita|requer|objeto|finalidade|divergência|pendência|ausência|comprovante|assinatura|conclusão)\b', s, re.I):
            score += 3
        ranked.append((score, idx))
    chosen = sorted(idx for _, idx in sorted(ranked, reverse=True)[:5])
    out = []
    for i in chosen:
        if sum(map(len, out)) + len(chunks[i]) > limit:
            continue
        out.append(chunks[i])
    return '\n\n'.join(out) if out else chunks[0][:limit]


def generate_report(protocol, subject, observations, data):
    text = data.get('text', '') or ''
    pages = data.get('pages', 0)
    documents = data.get('documents', [])
    findings = [label for label, pattern in PATTERNS.items() if re.search(pattern, text, re.I)]
    attention = list(data.get('ocr_warnings', []))
    if not text.strip():
        attention.append('Texto insuficiente; verificar OCR e qualidade dos arquivos.')
    if any(d.get('error') for d in documents):
        attention.append('Um ou mais arquivos apresentaram falha de leitura.')
    if not protocol:
        attention.append('Número do protocolo não informado.')
    if not subject:
        attention.append('Assunto não informado.')

    checks = [
        ('Possível ausência de assinatura', r'\b(sem assinatura|assinatura ausente|não apresenta assinatura|assinatura não verificável|falta de assinatura)\b'),
        ('Possível falta de comprovante de recebimento ou ciência', r'\b(sem comprovante|não demonstra recebimento|ausência de comprovante|não consta comprovante|sem confirmação de recebimento)\b'),
        ('Divergência documental ou de datas relatada', r'\b(divergência|datas divergentes|inconsistência|contradição)\b'),
        ('Prazo citado; conferir regra aplicável', PATTERNS['Prazo ou urgência']),
    ]
    detected = []
    for label, pattern in checks:
        matches = _snippets(text, pattern, 2)
        if matches:
            detected.append((label, matches, _page_refs(text, pattern)))
            ref = f" (páginas {', '.join(map(str, _page_refs(text, pattern)))})" if _page_refs(text, pattern) else ''
            attention.append(label + ref + '; confirmar no documento original.')
    if not attention:
        attention.append('Nenhuma pendência objetiva detectada; isso não comprova regularidade documental.')
    evidence = []
    for label, pattern in PATTERNS.items():
        matches = _snippets(text, pattern, 1)
        if matches:
            evidence.append({'topic': label, 'excerpt': matches[0]})

    doc_names = ', '.join(d.get('name', 'sem nome') for d in documents[:12])
    detail = [
        '1. IDENTIFICAÇÃO E ABRANGÊNCIA',
        f'Protocolo: {protocol or "não informado"}. Assunto informado: {subject or "não informado"}.',
        f'Arquivos recebidos: {len(documents)}; páginas: {pages}. Nomes: {doc_names or "não informado"}.',
        '', '2. SÍNTESE DOCUMENTAL', summary(text, 950),
        '', '3. PENDÊNCIAS E INCONSISTÊNCIAS PARA CONFERÊNCIA',
    ]
    detail.extend('- ' + a for a in attention)
    detail.extend(['', '4. TRECHOS DE APOIO (NÃO CONSTITUEM PROVA DE AUTENTICIDADE)'])
    for label, snippets, refs in detected[:8]:
        detail.append(f'- {label}' + (f" [páginas {', '.join(map(str, refs))}]" if refs else '') + ': ' + snippets[0])
    if not detected:
        detail.append('Não foram identificados trechos suficientes para apontamentos específicos.')
    detail.extend(['', '5. ENCAMINHAMENTO PRELIMINAR',
        'Conferir documentos originais e anexos, verificar datas e assinaturas, registrar lacunas comprovadas e encaminhar à unidade responsável. Não inferir prazos legais apenas da menção a urgência.',
        'A análise é auxiliar, baseada em regras locais, e exige revisão e autorização humana.'])
    draft_lines = [
        f'MINUTA PARA REVISÃO — Protocolo {protocol or "[informar]"}',
        f'Assunto: {subject or "[conferir assunto]"}', '',
        'Considerando os documentos apresentados, encaminhe-se o expediente para conferência documental, sem antecipação de decisão de mérito.',
    ]
    if detected:
        draft_lines.append('Solicita-se verificar especificamente: ' + '; '.join(label.lower() for label, _, _ in detected[:5]) + '.')
    if data.get('ocr_warnings'):
        draft_lines.append('Solicita-se também conferência manual das páginas com alerta de OCR.')
    draft_lines.extend(['Caso confirmadas as pendências, registre-se a necessidade de complementação pelos canais institucionais.',
                        'Esta minuta não estabelece direito, prazo legal, conclusão pericial ou decisão. Revisão e aprovação obrigatórias.'])
    return {
        'protocol': protocol, 'subject': subject, 'observations': observations,
        'documents': documents, 'total_documents': len(documents), 'total_pages': pages,
        'summary': summary(text), 'attention_points': attention,
        'identified_topics': findings, 'evidence': evidence[:8],
        'preliminary_analysis': '\n'.join(detail),
        'suggested_response': '\n\n'.join(draft_lines),
        'limitations': ('Análise local baseada em regras, sem IA generativa e sem custos de API. '
                        'Trechos OCR podem estar incompletos. Não valida autenticidade, prazos legais, '
                        'direitos ou decisões e exige revisão humana.'),
    }
