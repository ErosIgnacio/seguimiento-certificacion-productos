"""Busca coincidencias aproximadas para IDs del CSV ausentes de MySQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certificacion.carga_historica import previsualizar_carga_historica
from certificacion.coincidencias_historicas import analizar_coincidencias_faltantes
from certificacion.configuracion import crear_conexion
from certificacion.datos import RepositorioCertificacion
from certificacion.validaciones import preparar_filas_origen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo", default="Certificacion.csv")
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--config")
    parser.add_argument(
        "--solo-resumen",
        action="store_true",
        help="Omite el detalle por ID y muestra únicamente los conteos.",
    )
    argumentos = parser.parse_args()
    resultado = previsualizar_carga_historica(
        argumentos.archivo,
        argumentos.usuario,
        ruta_config=argumentos.config,
    )
    ids_faltantes = resultado.get("detalle_csv_sin_registro_db", [])
    diagnostico_operacional = {}
    resumen_origen = {}
    conexion = None
    if resultado.get("ok") and ids_faltantes:
        try:
            componentes = [identificador.split("_") for identificador in ids_faltantes]
            contenedores = [valores[0] for valores in componentes]
            ordenes_compra = [valores[1] for valores in componentes]
            conexion = crear_conexion(argumentos.config)
            filas_origen = RepositorioCertificacion(
                conexion
            ).obtener_origen_por_contenedor_oc(contenedores, ordenes_compra)
            validadas = preparar_filas_origen(filas_origen)
            ids_faltantes_set = set(ids_faltantes)
            coincidencias_exactas = {
                fila["id_certificacion"]: {
                    "id_certificacion": fila["id_certificacion"],
                    "codigo_depto": fila.get("codigo_depto"),
                    "eta": fila.get("eta"),
                    "nave": fila.get("nave"),
                    "fecha_programacion": fila.get("fecha_programacion"),
                }
                for fila in validadas.filas
                if fila["id_certificacion"] in ids_faltantes_set
            }
            diagnostico_operacional = analizar_coincidencias_faltantes(
                ids_faltantes,
                validadas.filas,
            )
            resumen_origen = {
                "filas_encontradas": len(filas_origen),
                "productos_validos": len(validadas.filas),
                "claves_incompletas": validadas.omitidos_clave_incompleta,
                "duplicados_consolidados": validadas.duplicados_consolidados,
                "duplicados_conflictivos": validadas.duplicados_conflictivos,
                "ids_completos_coincidentes": len(coincidencias_exactas),
                "detalle_ids_completos_coincidentes": list(
                    coincidencias_exactas.values()
                ),
            }
        finally:
            if conexion is not None:
                conexion.close()
    salida = {
        "ok": resultado.get("ok", False),
        "csv_sin_registro_db": resultado.get("csv_sin_registro_db", 0),
        "diagnostico_tabla_certificacion": resultado.get(
            "diagnostico_csv_sin_registro_db", {}
        ),
        "resumen_origen_operacional": resumen_origen,
        "diagnostico_origen_operacional": diagnostico_operacional,
        "errores": resultado.get("errores", []),
    }
    if argumentos.solo_resumen:
        salida["diagnostico_tabla_certificacion"].pop("detalles", None)
        salida["diagnostico_origen_operacional"].pop("detalles", None)
    print(json.dumps(salida, ensure_ascii=False, indent=2, default=str))
    return 0 if salida["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
