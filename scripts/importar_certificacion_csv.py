"""Previsualiza o aplica la carga histórica de Certificacion.csv."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certificacion.carga_historica import (
    importar_carga_historica,
    previsualizar_carga_historica,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo", default="Certificacion.csv")
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--config")
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Escribe campos manuales/vigencia; sin esta opción solo compara.",
    )
    parser.add_argument(
        "--permitir-csv-sin-db",
        action="store_true",
        help=(
            "Al aplicar, permite omitir productos del CSV que no existen en "
            "MySQL. Úselo solo después de revisar la previsualización."
        ),
    )
    parser.add_argument(
        "--solo-resumen",
        action="store_true",
        help="Muestra los contadores principales sin detalles por registro.",
    )
    argumentos = parser.parse_args()
    funcion = (
        importar_carga_historica
        if argumentos.aplicar
        else previsualizar_carga_historica
    )
    opciones = {"ruta_config": argumentos.config}
    if argumentos.aplicar:
        opciones["permitir_csv_sin_db"] = argumentos.permitir_csv_sin_db
    resultado = funcion(
        argumentos.archivo,
        argumentos.usuario,
        **opciones,
    )
    if argumentos.solo_resumen:
        claves = (
            "ok",
            "confirmado",
            "modo",
            "registros_validos",
            "registros_db",
            "coincidentes",
            "csv_sin_registro_db",
            "db_ausentes_del_csv",
            "actualizados_campos_usuario",
            "registros_con_cambio",
            "sin_cambios",
            "reactivados_por_csv",
            "desactivados_ausentes_csv",
            "desactivados_no_requiere_inspeccion",
            "auditorias_estimadas",
            "auditorias_generadas",
            "errores",
        )
        resultado = {clave: resultado.get(clave) for clave in claves}
    print(json.dumps(resultado, ensure_ascii=False, indent=2, default=str))
    return 0 if resultado.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
