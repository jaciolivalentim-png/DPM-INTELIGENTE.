"""Processo separado para OCR; nunca recebe credenciais ou dados do banco."""
import os
import sys

# Evita que um motor OCR pesado monopolize os recursos da instância.
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'

if sys.platform.startswith('linux'):
    import resource
    # CPU e memória virtual por processo; limite ajustável via Render.
    memory_mb = int(os.environ.get('DPM_OCR_WORKER_MEMORY_MB', '340'))
    resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (22, 23))

from PIL import Image
import numpy as np
from rapidocr_onnxruntime import RapidOCR

with Image.open(sys.argv[1]) as source:
    data = np.asarray(source.convert('RGB'))
engine = RapidOCR()
result, _ = engine(data)
print('\n'.join(str(item[1]) for item in (result or []) if len(item) > 1))
