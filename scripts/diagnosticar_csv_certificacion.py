"""Analiza Certificacion.csv sin escribir en MySQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certificacion.csv_historico import leer_csv_historico


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "archivo",
        nargs="?",
        default="Certificacion.csv",
        help="CSV histórico; por defecto usa Certificacion.csv de la carpeta actual",
    )
    argumentos = parser.parse_args()
    resultado = leer_csv_historico(argumentos.archivo)
    print(json.dumps(resultado.resumen(), ensure_ascii=False, indent=2, default=str))
    return 1 if resultado.bloquea_importacion else 0


if __name__ == "__main__":
    raise SystemExit(main())
