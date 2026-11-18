"""Biblioteca de PDFs normativos cadastrados por administrador; busca textual explicável.
Não valida vigência, autenticidade, aplicabilidade nem interpretação jurídica.
"""
import re
import unicodedata
from collections import Counter

STOP = set('para sobre entre como pelo pela pelos pelas este esta estes estas aquele aquela seus suas uma uns umas dos das com que por nao sim ser ter ao aos em de da do e ou um a o os as no na nos nas se mais documento processo pagina paginas protocolo interessado interessada'.split())

def words(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii','ignore').decode().lower()
    return [w for w in re.findall(r'[a-z]{4,}', value) if w not in STOP]

def select_matches(subject, protocol_text, rows, limit=5):
    """Compara assunto e início do protocolo com trechos reais; sem inventar dispositivos."""
    query = Counter(words(subject) * 3 + words((protocol_text or '')[:6500]))
    output = []
    for row in rows:
        if not row.get('active'):
            continue
        source = row.get('content') or ''
        if not source.strip():
            continue
        blocks = re.split(r'(?=\[Página\s+\d+\])', source, flags=re.I)
        scored = []
        for block in blocks[:150]:
            for part in re.split(r'\n\s*\n', block):
                clean = ' '.join(part.split())[:1250]
                if len(clean) < 45:
                    continue
                overlap = set(words(clean)) & query.keys()
                score = sum(min(query[w], 4) for w in overlap)
                if score >= 3 and len(overlap) >= 2:
                    page = re.search(r'\[Página\s+(\d+)\]', block, re.I)
                    scored.append((score, int(page.group(1)) if page else None, clean[:450]))
        if scored:
            score, page, excerpt = max(scored, key=lambda x:x[0])
            output.append({'id':row['id'],'title':row['title'], 'source_url':row.get('source_url') or '',
                           'page':page,'excerpt':excerpt,'score':score,
                           'status':'Trecho localizado; conferir original, vigência e aplicabilidade'})
    output.sort(key=lambda r:r['score'], reverse=True)
    return output[:limit]
