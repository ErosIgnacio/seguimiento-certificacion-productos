"""Punto de ejecución manual controlado y sin credenciales embebidas."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Permite las dos formas de ejecución:
#   python -m certificacion
#   python certificacion\__main__.py
if __package__ in (None, ""):
    raiz_proyecto = Path(__file__).resolve().parent.parent
    if str(raiz_proyecto) not in sys.path:
        sys.path.insert(0, str(raiz_proyecto))
    from certificacion.sincronizacion import _ejecutar_con_nueva_conexion
    from certificacion.usuarios import resolver_usuario
else:
    from .sincronizacion import _ejecutar_con_nueva_conexion
    from .usuarios import resolver_usuario


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Previsualiza o aplica la sincronización de certificaciones."
    )
    parser.add_argument(
        "--usuario",
        help=(
            "Usuario opcional para soporte o pruebas. Si se omite, se usa "
            "automáticamente la cuenta de Windows del equipo."
        ),
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Confirma escrituras. Sin esta opción sólo se previsualiza.",
    )
    parser.add_argument(
        "--config",
        help="Ruta opcional al config.json existente de Log_Importado.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Muestra trazas técnicas en consola"
    )
    argumentos = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if argumentos.verbose else logging.ERROR,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    resumen = _ejecutar_con_nueva_conexion(
        resolver_usuario(argumentos.usuario),
        aplicar=argumentos.aplicar,
        ruta_config=argumentos.config,
    )
    print(json.dumps(resumen, ensure_ascii=False, indent=2, default=str))
    return 1 if resumen["errores"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
