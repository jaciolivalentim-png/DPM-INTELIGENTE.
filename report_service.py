import re
from collections import Counter

STOP = {"para","com","uma","por","dos","das","que","não","nos","nas","este","esta","como","mais","entre","sobre","ser","sua","seu","são","também","pela","pelo","aos","ainda","documento"}

def summary(text, limit=1400):
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "Não foi possível extrair texto do documento. O arquivo pode ser um PDF escaneado e necessitar de OCR."
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    out = []
    size = 0
    for s in sentences:
        if size + len(s) > limit: break
        out.append(s)
        size += len(s) + 1
    return " ".join(out) or clean[:limit]

def keywords(text, limit=12):
    words = re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", text.lower())
    count = Counter(w for w in words if w not in STOP)
    return [w for w, _ in count.most_common(limit)]

def attention(text):
    terms = ["urgente","prazo","pendência","irregularidade","recurso","solicitação","indeferimento","deferimento","documentação"]
    low = text.lower()
    found = [f"Referência identificada a: {t}." for t in terms if t in low]
    return found or ["Nenhum termo de atenção pré-configurado foi identificado automaticamente."]

def generate_report(protocol, subject, observations, data):
    text = data["text"]
    return {
        "protocol": protocol,
        "subject": subject,
        "observations": observations,
        "documents": data["documents"],
        "total_documents": len(data["documents"]),
        "total_pages": data["pages"],
        "summary": summary(text),
        "keywords": keywords(text),
        "attention_points": attention(text),
        "preliminary_analysis": "A análise abaixo é automatizada e tem caráter exclusivamente de apoio. O conteúdo do processo deve ser conferido por um servidor responsável antes de qualquer decisão, parecer ou despacho oficial.",
        "suggested_response": "Sugere-se revisar os documentos e as informações identificadas, verificar eventuais pendências e encaminhar o protocolo conforme a competência e as normas aplicáveis."
    }