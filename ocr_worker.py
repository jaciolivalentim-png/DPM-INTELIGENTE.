"""Processo separado para OCR; nunca recebe credenciais ou dados do banco."""
import os
import sys

# Evita que um motor OCR pesado monopolize os recursos da instância.
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'

# Não limitar RLIMIT_AS: ONNX Runtime reserva memória virtual acima do RSS real.
# O processo continua isolado, com timeout controlado pelo serviço principal.
from PIL import Image
import numpy as np
from rapidocr_onnxruntime import RapidOCR

with Image.open(sys.argv[1]) as source:
    source.thumbnail((1700, 1700))
    data = np.asarray(source.convert('RGB'))
engine = RapidOCR()
result, _ = engine(data)
print('\n'.join(str(item[1]) for item in (result or []) if len(item) > 1))
