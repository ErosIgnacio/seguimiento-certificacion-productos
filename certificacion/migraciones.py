"""Preverificación y aplicación controlada de las DDL de certificación."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .configuracion import crear_conexion
from .constantes import (
    LONGITUD_CLAVE_EDICION_MASIVA,
    LONGITUD_ID_CERTIFICACION,
    LONGITUDES_CLAVE,
)


RAIZ = Path(__file__).resolve().parent.parent
ARCHIVOS_MIGRACION = (
    RAIZ / "migraciones" / "001_crear_log_imp_certificacion_productos.sql",
    RAIZ / "migraciones" / "002_crear_log_imp_certificacion_auditoria.sql",
    RAIZ / "migraciones" / "003_crear_log_imp_certificacion_catalogos.sql",
    RAIZ / "migraciones" / "004_crear_log_imp_certificacion_catalogos_auditoria.sql",
    RAIZ / "migraciones" / "005_cargar_catalogos_iniciales.sql",
    RAIZ / "migraciones" / "006_agregar_clave_edicion_masiva.sql",
    RAIZ / "migraciones" / "007_cargar_departamentos_sincronizacion.sql",
)


class ErrorCompatibilidadMigracion(RuntimeError):
    """El servidor o el esquema origen no coincide con el diseño verificado."""


def _limite_indice_innodb(tamano_pagina: int) -> int:
    # Límites documentados para InnoDB DYNAMIC/COMPRESSED.
    if tamano_pagina <= 4096:
        return 768
    if tamano_pagina <= 8192:
        return 1536
    return 3072


def inspeccionar_compatibilidad(conexion) -> dict[str, Any]:
    with conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                VERSION() AS version_mysql,
                @@character_set_database AS character_set_database,
                @@collation_database AS collation_database,
                @@innodb_default_row_format AS innodb_default_row_format,
                @@innodb_page_size AS innodb_page_size
            """
        )
        servidor = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                TABLE_NAME,
                COLUMN_NAME,
                DATA_TYPE,
                COLUMN_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND (
                  (TABLE_NAME = 'Log_Imp_Programacion_Contenedores'
                   AND COLUMN_NAME IN ('N_Contenedor', 'OC'))
                  OR
                  (TABLE_NAME = 'Log_Imp_Flujo_Consolidado'
                   AND COLUMN_NAME IN ('GD', 'Articulo'))
              )
            """
        )
        columnas = {
            (fila["TABLE_NAME"], fila["COLUMN_NAME"]): fila
            for fila in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN (
                  'Log_Imp_Certificacion_Productos',
                  'Log_Imp_Certificacion_Auditoria',
                  'Log_Imp_Certificacion_Catalogos',
                  'Log_Imp_Certificacion_Catalogos_Auditoria'
              )
            ORDER BY TABLE_NAME
            """
        )
        tablas_existentes = [fila["TABLE_NAME"] for fila in cursor.fetchall()]

    requeridas = {
        ("Log_Imp_Programacion_Contenedores", "N_Contenedor"),
        ("Log_Imp_Programacion_Contenedores", "OC"),
        ("Log_Imp_Flujo_Consolidado", "GD"),
        ("Log_Imp_Flujo_Consolidado", "Articulo"),
    }
    faltantes = requeridas - set(columnas)
    if faltantes:
        raise ErrorCompatibilidadMigracion(
            "Faltan columnas fuente: "
            + ", ".join(f"{tabla}.{columna}" for tabla, columna in sorted(faltantes))
        )

    version = str(servidor["version_mysql"])
    if not version.startswith("8.") or "mariadb" in version.casefold():
        raise ErrorCompatibilidadMigracion(
            f"La migración fue validada para MySQL 8; servidor detectado: {version}"
        )
    if servidor["character_set_database"] != "utf8mb4":
        raise ErrorCompatibilidadMigracion(
            "La base debe utilizar utf8mb4 para conservar el diseño verificado"
        )

    longitudes_detectadas = {
        "n_contenedor": int(
            columnas[("Log_Imp_Programacion_Contenedores", "N_Contenedor")][
                "CHARACTER_MAXIMUM_LENGTH"
            ]
        ),
        "oc": int(
            columnas[("Log_Imp_Programacion_Contenedores", "OC")][
                "CHARACTER_MAXIMUM_LENGTH"
            ]
        ),
        # +1 reserva el signo en los INT actuales sin truncar ningún valor.
        "gd": int(
            columnas[("Log_Imp_Flujo_Consolidado", "GD")]["NUMERIC_PRECISION"]
        )
        + 1,
        "sku": int(
            columnas[("Log_Imp_Flujo_Consolidado", "Articulo")][
                "NUMERIC_PRECISION"
            ]
        )
        + 1,
    }
    if longitudes_detectadas != LONGITUDES_CLAVE:
        raise ErrorCompatibilidadMigracion(
            "Cambió el esquema de las claves fuente. Detectado: "
            f"{longitudes_detectadas}; diseñado: {LONGITUDES_CLAVE}"
        )

    bytes_id = LONGITUD_ID_CERTIFICACION * 4
    bytes_uq = sum(LONGITUDES_CLAVE.values()) * 4
    bytes_clave_masiva = LONGITUD_CLAVE_EDICION_MASIVA * 4
    limite_indice = _limite_indice_innodb(int(servidor["innodb_page_size"]))
    if max(bytes_id, bytes_uq, bytes_clave_masiva) > limite_indice:
        raise ErrorCompatibilidadMigracion(
            "La clave excede el límite de índice InnoDB del servidor"
        )

    return {
        "servidor": servidor,
        "longitudes_clave": longitudes_detectadas,
        "longitud_id_certificacion": LONGITUD_ID_CERTIFICACION,
        "bytes_maximos_pk_utf8mb4": bytes_id,
        "bytes_maximos_uq_utf8mb4": bytes_uq,
        "bytes_maximos_clave_masiva_utf8mb4": bytes_clave_masiva,
        "limite_indice_innodb": limite_indice,
        "tablas_destino_existentes": tablas_existentes,
    }


def _estado_migracion_clave_masiva(conexion) -> dict[str, bool]:
    with conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'Log_Imp_Certificacion_Productos'
              AND COLUMN_NAME = 'clave_edicion_masiva'
            """
        )
        columna = bool(int(cursor.fetchone()["total"]))
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'Log_Imp_Certificacion_Productos'
              AND INDEX_NAME = 'idx_certificacion_clave_masiva'
            """
        )
        indice = bool(int(cursor.fetchone()["total"]))
    return {"columna": columna, "indice": indice}


def _verificar_resultado(conexion) -> dict[str, Any]:
    with conexion.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                TABLE_NAME,
                COLUMN_TYPE,
                CHARACTER_MAXIMUM_LENGTH,
                COLLATION_NAME,
                EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND COLUMN_NAME = 'id_certificacion'
              AND TABLE_NAME IN (
                  'Log_Imp_Certificacion_Productos',
                  'Log_Imp_Certificacion_Auditoria'
              )
            ORDER BY TABLE_NAME
            """
        )
        ids = list(cursor.fetchall())
        cursor.execute(
            """
            SELECT COLUMN_TYPE, CHARACTER_MAXIMUM_LENGTH, COLLATION_NAME, EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'Log_Imp_Certificacion_Productos'
              AND COLUMN_NAME = 'clave_edicion_masiva'
            """
        )
        clave_masiva = cursor.fetchone()
        cursor.execute(
            """
            SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(
                COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ','
            ) AS columnas
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN (
                  'Log_Imp_Certificacion_Productos',
                  'Log_Imp_Certificacion_Auditoria'
              )
            GROUP BY TABLE_NAME, INDEX_NAME
            ORDER BY TABLE_NAME, INDEX_NAME
            """
        )
        indices = list(cursor.fetchall())
        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'Log_Imp_Certificacion_Catalogos'
            """
        )
        tabla_catalogos = cursor.fetchone()
        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'Log_Imp_Certificacion_Catalogos_Auditoria'
            """
        )
        tabla_catalogos_auditoria = cursor.fetchone()
        cursor.execute(
            """
            SELECT INDEX_NAME, GROUP_CONCAT(
                COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ','
            ) AS columnas
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'Log_Imp_Certificacion_Catalogos_Auditoria'
            GROUP BY INDEX_NAME
            """
        )
        indices_catalogos_auditoria = {
            fila["INDEX_NAME"]: fila["columnas"] for fila in cursor.fetchall()
        }
        cursor.execute(
            """
            SELECT tipo, COUNT(*) AS total
            FROM Log_Imp_Certificacion_Catalogos
            WHERE (tipo = 'estado_certificacion' AND valor IN (
                    'Liberado', 'Pendiente DI',
                    'Pendiente entrega de Etiquetas',
                    'Proceso pegado de etiqueta',
                    'Proceso de certificación',
                    'Espera resultado laboratorio tipo',
                    'Espera resultado laboratorio',
                    'Espera de la Liberación',
                    'Solicitud de inspección enviada',
                    'Productos no llegaron', 'Inspección confirmada',
                    'No necesita inspección', 'Sin certificar'
                ))
               OR (tipo = 'pegar_etiquetas' AND valor IN (
                    'No', 'Qr', 'Qr, Placa advertencias',
                    'Qr, Placa caracteristica',
                    'Qr, Placa caracteristica y advertencias'
                ))
               OR (tipo = 'prioridad' AND valor IN (
                    'PRIORIDAD', 'VENTILACION', 'CALEFACCION', 'SIN PRIORIDAD'
                ))
               OR (tipo = 'laboratorio' AND valor IN (
                    'INGCER', 'GASEI-ARBA-INGCER', 'LENOR', 'CESMEC'
                ))
               OR (tipo = 'codigo_depto' AND valor IN (
                    '700', '701', '702', '703', '720',
                    '726', '727', '730', '669'
                ))
            GROUP BY tipo
            """
        )
        catalogos_iniciales = {
            fila["tipo"]: int(fila["total"]) for fila in cursor.fetchall()
        }

    if len(ids) != 2:
        raise ErrorCompatibilidadMigracion(
            "No quedaron disponibles ambas columnas id_certificacion"
        )
    for columna in ids:
        if (
            columna["COLUMN_TYPE"] != "varchar(125)"
            or columna["COLLATION_NAME"] != "utf8mb4_0900_ai_ci"
        ):
            raise ErrorCompatibilidadMigracion(
                f"Tipo/collation inesperado en {columna['TABLE_NAME']}"
            )

    ids_por_tabla = {columna["TABLE_NAME"]: columna for columna in ids}
    if "STORED GENERATED" not in ids_por_tabla[
        "Log_Imp_Certificacion_Productos"
    ]["EXTRA"]:
        raise ErrorCompatibilidadMigracion(
            "id_certificacion de productos no quedó como STORED GENERATED"
        )
    if (
        not clave_masiva
        or clave_masiva["COLUMN_TYPE"] != "varchar(123)"
        or clave_masiva["COLLATION_NAME"] != "utf8mb4_0900_ai_ci"
        or "STORED GENERATED" not in clave_masiva["EXTRA"]
    ):
        raise ErrorCompatibilidadMigracion(
            "clave_edicion_masiva no quedó generada con el tipo esperado"
        )

    indices_detectados = {
        (indice["TABLE_NAME"], indice["INDEX_NAME"]): indice["columnas"]
        for indice in indices
    }
    indices_requeridos = {
        ("Log_Imp_Certificacion_Productos", "PRIMARY"): "id_certificacion",
        (
            "Log_Imp_Certificacion_Productos",
            "uq_certificacion_clave",
        ): "n_contenedor,oc,gd,sku",
        (
            "Log_Imp_Certificacion_Productos",
            "idx_certificacion_clave_masiva",
        ): "clave_edicion_masiva",
        ("Log_Imp_Certificacion_Auditoria", "PRIMARY"): "id_auditoria",
        (
            "Log_Imp_Certificacion_Auditoria",
            "idx_cert_auditoria_id",
        ): "id_certificacion",
        (
            "Log_Imp_Certificacion_Auditoria",
            "idx_cert_auditoria_fecha",
        ): "fecha_modificacion",
        (
            "Log_Imp_Certificacion_Auditoria",
            "idx_cert_auditoria_usuario",
        ): "usuario",
    }
    incorrectos = {
        f"{tabla}.{indice}": {
            "esperado": columnas_esperadas,
            "detectado": indices_detectados.get((tabla, indice)),
        }
        for (tabla, indice), columnas_esperadas in indices_requeridos.items()
        if indices_detectados.get((tabla, indice)) != columnas_esperadas
    }
    if incorrectos:
        raise ErrorCompatibilidadMigracion(
            f"Faltan índices o tienen columnas inesperadas: {incorrectos}"
        )

    if not tabla_catalogos:
        raise ErrorCompatibilidadMigracion(
            "No quedó disponible Log_Imp_Certificacion_Catalogos"
        )
    if not tabla_catalogos_auditoria:
        raise ErrorCompatibilidadMigracion(
            "No quedó disponible Log_Imp_Certificacion_Catalogos_Auditoria"
        )
    indices_catalogo_requeridos = {
        "PRIMARY": "id_auditoria",
        "idx_cert_catalogo_aud_id": "id_catalogo",
        "idx_cert_catalogo_aud_fecha": "fecha_modificacion",
        "idx_cert_catalogo_aud_usuario": "usuario",
    }
    if any(
        indices_catalogos_auditoria.get(nombre) != columnas
        for nombre, columnas in indices_catalogo_requeridos.items()
    ):
        raise ErrorCompatibilidadMigracion(
            "Faltan índices de auditoría de catálogos"
        )
    esperados = {
        "estado_certificacion": 13,
        "pegar_etiquetas": 5,
        "prioridad": 4,
        "laboratorio": 4,
        "codigo_depto": 9,
    }
    if catalogos_iniciales != esperados:
        raise ErrorCompatibilidadMigracion(
            f"No quedaron todos los catálogos iniciales: {catalogos_iniciales}"
        )

    return {
        "columnas_id": ids,
        "columna_clave_edicion_masiva": clave_masiva,
        "indices": indices,
        "tabla_catalogos": tabla_catalogos["TABLE_NAME"],
        "tabla_catalogos_auditoria": tabla_catalogos_auditoria["TABLE_NAME"],
        "catalogos_iniciales": catalogos_iniciales,
    }


def ejecutar_migraciones(
    *,
    ruta_config=None,
    confirmar: bool = False,
) -> dict[str, Any]:
    """Prevalida siempre; sólo ejecuta las DDL/DML con confirmar=True."""
    conexion = crear_conexion(ruta_config)
    try:
        resultado = {"compatibilidad": inspeccionar_compatibilidad(conexion)}
        if not confirmar:
            resultado.update({"aplicado": False, "mensaje": "Sólo prevalidación"})
            return resultado

        aplicadas = []
        omitidas = []
        for archivo in ARCHIVOS_MIGRACION:
            if archivo.name == "006_agregar_clave_edicion_masiva.sql":
                estado = _estado_migracion_clave_masiva(conexion)
                if estado == {"columna": True, "indice": True}:
                    omitidas.append(archivo.name)
                    continue
                if any(estado.values()):
                    raise ErrorCompatibilidadMigracion(
                        "La migración 006 está aplicada parcialmente; "
                        f"estado detectado: {estado}"
                    )
            sql = archivo.read_text(encoding="utf-8")
            with conexion.cursor() as cursor:
                cursor.execute(sql)
            aplicadas.append(archivo.name)
        conexion.commit()
        resultado.update(
            {
                "aplicado": True,
                "migraciones": aplicadas,
                "migraciones_omitidas": omitidas,
                "verificacion": _verificar_resultado(conexion),
            }
        )
        return resultado
    except Exception:
        # CREATE TABLE es DDL atómica por sentencia en MySQL 8, no una transacción
        # multi-DDL. El rollback protege cualquier DML futuro del mismo runner.
        conexion.rollback()
        raise
    finally:
        conexion.close()
