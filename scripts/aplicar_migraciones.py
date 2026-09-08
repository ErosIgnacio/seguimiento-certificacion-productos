"""Prevalida o aplica las migraciones sin exponer credenciales en comandos."""

from __future__ import annotations

import argparse
import json

from certificacion.migraciones import ejecutar_migraciones


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Ruta al config.json existente")
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Aplica las DDL; sin esta opción sólo hace la prevalidación.",
    )
    argumentos = parser.parse_args()
    resultado = ejecutar_migraciones(
        ruta_config=argumentos.config,
        confirmar=argumentos.confirmar,
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
