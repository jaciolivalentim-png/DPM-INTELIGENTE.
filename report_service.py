"""Relatório auxiliar determinístico: não realiza decisão médica ou jurídica."""
import re
from collections import Counter

STOP = set('para com uma por dos das que não nos nas este esta como mais entre sobre ser sua seu são também pela pelo aos ainda documento processo protocolo requerente conforme mediante tendo referente através'.split())
PATTERNS = {
    'Solicitação ou requerimento': r'\b(requer|solicita|pedido|requerimento|solicitação)\b',
    'Prazo ou urgência': r'\b(prazo|urgente|urgência|vencimento|intimação)\b',
    'Recurso ou contestação': r'\b(recurso|contestação|impugnação|reconsideração)\b',
    'Documentação complementar': r'\b(anexo|anexado|documentação|complementação|juntada)\b',
    'Avaliação pericial': r'\b(perícia|pericial|avaliação médica|laudo médico)\b',
    'Decisão mencionada': r'\b(indeferimento|deferimento|decisão|despacho)\b',
}

def sentences(text):
    clean = re.sub(r'\s+', ' ', text).strip()
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+|(?<=;)\s+', clean) if len(s.strip()) >= 25]

def summary(text, limit=3500):
    chunks = sentences(text)
    if not chunks:
        return ('Não foi possível extrair texto suficiente. O PDF pode ser digitalizado '
                'como imagem e exigir OCR antes de uma análise textual.')
    # Pick salient sentences, then retain source order to avoid fabricated prose.
    terms = Counter(w for w in re.findall(r'\b[a-zà-ÿ]{4,}\b', text.lower()) if w not in STOP)
    scores = []
    for idx, sentence in enumerate(chunks[:350]):
        tokens = re.findall(r'\b[a-zà-ÿ]{4,}\b', sentence.lower())
        score = sum(min(terms[t], 12) for t in set(tokens)) / max(len(tokens), 6)
        if re.search(r'\b(solicita|requer|objeto|finalidade|conclusão|encaminha)\b', sentence, re.I):
            score += 3
        scores.append((score, idx))
    chosen = sorted(i for _, i in sorted(scores, reverse=True)[:min(14, len(scores))])
    result = '\n\n'.join(chunks[i][:550] for i in chosen)
    return result[:limit].rstrip() + ('…' if len(result) > limit else '')

def keywords(text, limit=12):
    words = re.findall(r'\b[a-zA-ZÀ-ÿ]{4,}\b', text.lower())
    return [w for w, _ in Counter(w for w in words if w not in STOP).most_common(limit)]

def generate_report(protocol, subject, observations, data):
    text = data.get('text', '')
    pages = data.get('pages', 0)
    documents = data.get('documents', [])
    findings = [label for label, pattern in PATTERNS.items() if re.search(pattern, text, re.I)]
    attention = []
    if not text.strip():
        attention.append('Texto não extraído; conferir se o arquivo exige OCR.')
    if any(d.get('error') for d in documents):
        attention.append('Um ou mais PDFs não puderam ser lidos integralmente.')
    if not protocol:
        attention.append('Número do protocolo não informado no formulário.')
    if not subject:
        attention.append('Assunto não informado no formulário.')
    if re.search(PATTERNS['Prazo ou urgência'], text, re.I):
        attention.append('Há menção a prazo ou urgência; verificar datas e condições no documento original.')
    if re.search(PATTERNS['Recurso ou contestação'], text, re.I):
        attention.append('Há menção a recurso/contestação; verificar tramitação e competência.')
    if not attention:
        attention.append('Nenhuma pendência objetiva foi detectada pelas regras disponíveis; revisão humana permanece necessária.')
    evidence = []
    for label, pattern in PATTERNS.items():
        matches = [s for s in sentences(text) if re.search(pattern, s, re.I)]
        if matches:
            evidence.append({'topic': label, 'excerpt': matches[0][:320]})
    doc_names = ', '.join(d.get('name', 'arquivo sem nome') for d in documents[:12])
    preliminary = (f'Foram recebidos {len(documents)} arquivo(s) PDF, totalizando {pages} página(s). '
                   f'Documentos: {doc_names or "nenhum"}. '
                   f'Assuntos identificados por termos: {", ".join(findings) if findings else "nenhum termo classificado"}. '
                   'Esses achados são indicadores textuais, não confirmação de fatos, diagnóstico ou conclusão jurídica. '
                   'É necessário conferir a íntegra, a autenticidade e a sequência dos documentos.')
    draft = (f'MINUTA PARA REVISÃO — Protocolo: {protocol or "[informar]"}\n'
             f'Assunto: {subject or "[informar]"}\n\n'
             'Considerando a documentação apresentada, encaminhe-se o expediente à unidade competente '
             'para conferência da integridade documental, identificação do pedido e avaliação das '
             'providências cabíveis, observadas as normas efetivamente aplicáveis ao caso.\n\n'
             'Registrem-se eventuais pendências e, se necessário, solicite-se complementação documental '
             'pelos canais institucionais.\n\n'
             'Esta minuta não representa decisão, conclusão pericial ou fundamentação normativa validada. '
             'Exige revisão e aprovação por agente autorizado.')
    return {
        'protocol': protocol, 'subject': subject, 'observations': observations,
        'documents': documents, 'total_documents': len(documents), 'total_pages': pages,
        'summary': summary(text), 'keywords': keywords(text),
        'attention_points': attention, 'identified_topics': findings,
        'evidence': evidence[:8], 'preliminary_analysis': preliminary,
        'suggested_response': draft,
        'limitations': ('Análise por regras e extração de texto, sem IA generativa ou OCR. '
                        'Não verifica autenticidade, não consulta legislação e não substitui revisão humana.'),
    }
