"""Diagnóstico de sólo lectura para versión, esquema y calidad del origen."""

from __future__ import annotations

import argparse
import json
from collections import Counter

from certificacion.configuracion import crear_conexion
from certificacion.constantes import CAMPOS_CLAVE
from certificacion.datos import RepositorioCertificacion
from certificacion.validaciones import preparar_filas_origen


TABLAS_COLUMNAS = {
    "Log_Imp_Programacion_Contenedores": {
        "ETA",
        "fecha_liberacion",
        "Nave",
        "N_Contenedor",
        "Fecha_Programacion",
        "Status_Carga",
        "Destino",
        "CD_Destino",
        "Codigo_Depto",
        "OC",
    },
    "Log_Imp_Flujo_Consolidado": {
        "GD",
        "Articulo",
        "Descripcion",
        "Cant_GD",
        "N_Container",
        "Importacion",
    },
}


def diagnosticar(ruta_config=None) -> dict:
    conexion = crear_conexion(ruta_config)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    VERSION() AS version_mysql,
                    @@character_set_database AS character_set_database,
                    @@collation_database AS collation_database,
                    @@innodb_default_row_format AS innodb_default_row_format
                """
            )
            servidor = cursor.fetchone()

            condiciones = []
            parametros = []
            for tabla, columnas in TABLAS_COLUMNAS.items():
                marcadores = ", ".join(["%s"] * len(columnas))
                condiciones.append(
                    f"(TABLE_NAME = %s AND COLUMN_NAME IN ({marcadores}))"
                )
                parametros.append(tabla)
                parametros.extend(sorted(columnas))
            cursor.execute(
                f"""
                SELECT
                    TABLE_NAME,
                    COLUMN_NAME,
                    COLUMN_TYPE,
                    IS_NULLABLE,
                    CHARACTER_MAXIMUM_LENGTH,
                    NUMERIC_PRECISION,
                    NUMERIC_SCALE,
                    COLLATION_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND ({" OR ".join(condiciones)})
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                parametros,
            )
            columnas = list(cursor.fetchall())

        repositorio = RepositorioCertificacion(conexion)
        departamentos = repositorio.obtener_departamentos_sincronizacion()
        filas = repositorio.obtener_origen()

        validacion = preparar_filas_origen(filas)
        maximos_observados = {
            campo: max(
                (len(str(fila[campo]).strip()) for fila in filas if fila.get(campo) is not None),
                default=0,
            )
            for campo in CAMPOS_CLAVE
        }
        ids_conflictivos = [
            detalle.get("id_certificacion")
            for detalle in validacion.detalles_duplicados_conflictivos
            if detalle.get("id_certificacion")
        ]
        tipos_error = Counter(error["tipo"] for error in validacion.errores)

        return {
            "servidor": servidor,
            "columnas_origen": columnas,
            "departamentos_sincronizacion": departamentos,
            "calidad_origen": {
                "filas": len(filas),
                "validas_consolidadas": len(validacion.filas),
                "omitidas_clave_incompleta": (
                    validacion.omitidos_clave_incompleta
                ),
                "duplicados_identicos_consolidados": (
                    validacion.duplicados_consolidados
                ),
                "claves_duplicadas_conflictivas": (
                    validacion.duplicados_conflictivos
                ),
                "filas_con_separador": validacion.claves_con_separador,
                "maximos_observados": maximos_observados,
                "tipos_error": dict(tipos_error),
                "ids_conflictivos": ids_conflictivos[:100],
                "detalles_clave_incompleta": (
                    validacion.detalles_clave_incompleta[:100]
                ),
                "detalles_separador": (
                    validacion.detalles_claves_con_separador[:100]
                ),
                "detalles_conflictos": (
                    validacion.detalles_duplicados_conflictivos[:100]
                ),
                "detalles_truncados_a_100": True,
            },
        }
    finally:
        conexion.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Ruta al config.json existente")
    argumentos = parser.parse_args()
    resultado = diagnosticar(argumentos.config)
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
