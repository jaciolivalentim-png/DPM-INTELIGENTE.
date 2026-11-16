
"""Processo isolado para reconhecimento OCR de imagens."""

import os
import sys

# Limita o número de threads das bibliotecas numéricas.
for name in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
):
    os.environ[name] = "1"

from PIL import Image
import numpy as np
from rapidocr_onnxruntime import RapidOCR


def main():
    if len(sys.argv) < 2:
        print("Arquivo de imagem não informado.", file=sys.stderr)
        sys.exit(2)

    image_path = sys.argv[1]

    try:
        with Image.open(image_path) as source:
            source = source.convert("RGB")
            source.thumbnail((1600, 1600))
            image_array = np.asarray(source)

        engine = RapidOCR()
        result, _ = engine(image_array)

        lines = [
            str(item[1])
            for item in (result or [])
            if len(item) > 1
        ]

        print("\n".join(lines))

    except Exception as exc:
        print(
            f"Erro no OCR: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
