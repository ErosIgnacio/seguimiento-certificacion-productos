"""Acceso a datos para el CRUD manual de certificaciones."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pymysql

from . import auditoria
from .campos import COLUMNAS_LISTADO
from .constantes import (
    CAMPO_CLAVE_EDICION_MASIVA,
    CAMPOS_AUTOMATICOS,
    CAMPOS_CATALOGO,
    CAMPOS_CLAVE,
    CAMPOS_USUARIO,
    ESTADOS_GESTIONADOS,
    TABLA_AUDITORIA,
    TABLA_CATALOGOS,
    TABLA_PRODUCTOS,
)


TODOS_CAMPOS_PRODUCTO = (
    "id_certificacion",
    *CAMPOS_AUTOMATICOS,
    *CAMPOS_USUARIO,
    "activo",
    "creado_por",
    "fecha_creacion",
    "actualizado_por",
    "fecha_actualizacion",
    "fecha_ultima_sincronizacion",
)


class RepositorioProductos:
    """Consultas y escrituras del CRUD sobre una única conexión."""

    def __init__(self, conexion):
        self.conexion = conexion

    def iniciar_transaccion(self) -> None:
        self.conexion.begin()

    def commit(self) -> None:
        self.conexion.commit()

    def rollback(self) -> None:
        self.conexion.rollback()

    def edicion_masiva_disponible(self) -> bool:
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    f"SELECT {CAMPO_CLAVE_EDICION_MASIVA} "
                    f"FROM {TABLA_PRODUCTOS} LIMIT 0"
                )
            return True
        except pymysql.err.OperationalError as exc:
            if exc.args and exc.args[0] == 1054:  # Unknown column
                return False
            raise

    @staticmethod
    def _construir_filtros(
        filtros: Mapping[str, Any] | None,
    ) -> tuple[str, list[Any]]:
        filtros = filtros or {}
        condiciones: list[str] = []
        parametros: list[Any] = []

        buscar = str(filtros.get("buscar") or "").strip()
        if buscar:
            patron = f"%{buscar}%"
            condiciones.append(
                "(" + " OR ".join(
                    f"{campo} LIKE %s"
                    for campo in (
                        "id_certificacion",
                        "n_contenedor",
                        "oc",
                        "gd",
                        "sku",
                        "descripcion",
                        "codigo",
                        "numero_qr",
                        "nro_certificado",
                    )
                ) + ")"
            )
            parametros.extend([patron] * 9)

        for campo in (
            "estado_certificacion",
            "laboratorio",
            "prioridad",
            "codigo_depto",
        ):
            valor = str(filtros.get(campo) or "").strip()
            if valor:
                condiciones.append(f"{campo} = %s")
                parametros.append(valor)

        gestion = str(filtros.get("gestion") or "").strip().upper()
        if gestion:
            # Pendiente/Gestionado sólo tiene sentido dentro del universo activo.
            condiciones.append("activo = 1")
            estados = tuple(estado.upper() for estado in ESTADOS_GESTIONADOS)
            expresion = (
                "UPPER(TRIM(COALESCE(estado_certificacion, ''))) "
                "IN (" + ", ".join(["%s"] * len(estados)) + ")"
            )
            if gestion == "PENDIENTES":
                condiciones.append(f"NOT ({expresion})")
                parametros.extend(estados)
            elif gestion == "GESTIONADOS":
                condiciones.append(expresion)
                parametros.extend(estados)
            else:
                raise ValueError("Filtro de gestión no permitido")

        for nombre, operador in (("eta_desde", ">="), ("eta_hasta", "<=")):
            valor = filtros.get(nombre)
            if valor not in (None, ""):
                condiciones.append(f"eta {operador} %s")
                parametros.append(valor)

        activo = filtros.get("activo")
        if activo in (True, False, 0, 1):
            condiciones.append("activo = %s")
            parametros.append(1 if bool(activo) else 0)

        if not condiciones:
            return "", parametros
        return " WHERE " + " AND ".join(condiciones), parametros

    def listar(
        self,
        *,
        filtros: Mapping[str, Any] | None,
        pagina: int,
        tamano_pagina: int,
    ) -> dict[str, Any]:
        where, parametros = self._construir_filtros(filtros)
        offset = (pagina - 1) * tamano_pagina
        columnas = ", ".join(COLUMNAS_LISTADO)

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {TABLA_PRODUCTOS}{where}",
                parametros,
            )
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                f"""
                SELECT id_certificacion, {columnas}
                FROM {TABLA_PRODUCTOS}
                {where}
                ORDER BY
                    activo DESC,
                    eta IS NULL ASC,
                    eta ASC,
                    n_contenedor ASC,
                    oc ASC,
                    gd ASC,
                    sku ASC
                LIMIT %s OFFSET %s
                """,
                [*parametros, tamano_pagina, offset],
            )
            filas = list(cursor.fetchall())
        return {"total": total, "filas": filas}

    def obtener_metricas(self) -> dict[str, int]:
        estados = tuple(estado.upper() for estado in ESTADOS_GESTIONADOS)
        marcadores = ", ".join(["%s"] * len(estados))
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(activo = 1), 0) AS activos,
                    COALESCE(SUM(activo = 0), 0) AS inactivos,
                    COALESCE(SUM(
                        activo = 1
                        AND UPPER(TRIM(COALESCE(estado_certificacion, '')))
                            NOT IN ({marcadores})
                    ), 0) AS pendientes,
                    COALESCE(SUM(
                        activo = 1
                        AND UPPER(TRIM(COALESCE(estado_certificacion, '')))
                            IN ({marcadores})
                    ), 0) AS gestionados
                FROM {TABLA_PRODUCTOS}
                """,
                (*estados, *estados),
            )
            fila = cursor.fetchone()
        return {campo: int(valor or 0) for campo, valor in fila.items()}

    def obtener_catalogos(
        self,
        catalogos_activos: Mapping[str, list[str]] | None = None,
    ) -> dict[str, list[str]]:
        """Combina opciones activas e históricas con un solo barrido adicional."""
        activos = (
            self.obtener_catalogos_activos()
            if catalogos_activos is None
            else catalogos_activos
        )
        catalogos: dict[str, list[str]] = {
            campo: list(activos.get(campo, [])) for campo in CAMPOS_CATALOGO
        }
        consultas_historicas = [
            f"""
            SELECT '{campo}' AS tipo, {campo} AS valor
            FROM {TABLA_PRODUCTOS}
            WHERE {campo} IS NOT NULL
              AND TRIM({campo}) <> ''
            GROUP BY {campo}
            """
            for campo in CAMPOS_CATALOGO
        ]
        with self.conexion.cursor() as cursor:
            # Conserva en los combos valores históricos todavía presentes aunque
            # el catálogo se haya desactivado; así nunca se oculta un dato vigente.
            cursor.execute(
                "\nUNION ALL\n".join(consultas_historicas)
                + "\nORDER BY tipo, valor"
            )
            for fila in cursor.fetchall():
                tipo = fila["tipo"]
                if tipo in catalogos and fila["valor"] not in catalogos[tipo]:
                    catalogos[tipo].append(fila["valor"])
        return catalogos

    @staticmethod
    def _tabla_catalogos_existe(cursor) -> bool:
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            """,
            (TABLA_CATALOGOS,),
        )
        return bool(int(cursor.fetchone()["total"]))

    def obtener_catalogos_activos(self) -> dict[str, list[str]]:
        catalogos = {campo: [] for campo in CAMPOS_CATALOGO}
        with self.conexion.cursor() as cursor:
            if not self._tabla_catalogos_existe(cursor):
                return catalogos
            cursor.execute(
                f"""
                SELECT tipo, valor
                FROM {TABLA_CATALOGOS}
                WHERE activo = 1
                ORDER BY tipo, orden, valor
                """
            )
            for fila in cursor.fetchall():
                if fila["tipo"] in catalogos:
                    catalogos[fila["tipo"]].append(fila["valor"])
        return catalogos

    def obtener_calidad(self, *, limite: int = 200) -> dict[str, Any]:
        """Devuelve conteos y ejemplos de inconsistencias sin modificar datos."""
        reglas = {
            "fechas_invertidas": (
                "fecha_inspeccion IS NOT NULL "
                "AND fecha_certificacion IS NOT NULL "
                "AND fecha_certificacion < fecha_inspeccion"
            ),
            "muestras_inconsistentes": (
                "muestras_retiradas IS NOT NULL "
                "AND muestras_recepcionadas IS NOT NULL "
                "AND muestras_recepcionadas > muestras_retiradas"
            ),
            "certificado_sin_fecha": (
                "nro_certificado IS NOT NULL "
                "AND TRIM(nro_certificado) <> '' "
                "AND fecha_certificacion IS NULL"
            ),
            "fecha_sin_estado": (
                "fecha_certificacion IS NOT NULL "
                "AND (estado_certificacion IS NULL "
                "OR TRIM(estado_certificacion) = '')"
            ),
        }
        conteos: dict[str, int] = {}
        ejemplos: list[dict[str, Any]] = []
        with self.conexion.cursor() as cursor:
            for regla, condicion in reglas.items():
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM {TABLA_PRODUCTOS} "
                    f"WHERE {condicion}"
                )
                conteos[regla] = int(cursor.fetchone()["total"])
                restante = limite - len(ejemplos)
                if restante <= 0 or not conteos[regla]:
                    continue
                cursor.execute(
                    f"""
                    SELECT
                        id_certificacion,
                        n_contenedor,
                        oc,
                        gd,
                        sku,
                        fecha_inspeccion,
                        fecha_certificacion,
                        estado_certificacion,
                        nro_certificado,
                        muestras_retiradas,
                        muestras_recepcionadas
                    FROM {TABLA_PRODUCTOS}
                    WHERE {condicion}
                    ORDER BY id_certificacion
                    LIMIT %s
                    """,
                    (restante,),
                )
                for fila in cursor.fetchall():
                    detalle = dict(fila)
                    detalle["regla"] = regla
                    ejemplos.append(detalle)
        return {
            "conteos": conteos,
            "total_hallazgos": sum(conteos.values()),
            "ejemplos": ejemplos,
            "limite_ejemplos": limite,
        }

    def obtener(self, id_certificacion: str) -> dict[str, Any] | None:
        columnas = ", ".join(TODOS_CAMPOS_PRODUCTO)
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {columnas}
                FROM {TABLA_PRODUCTOS}
                WHERE id_certificacion = %s
                """,
                (id_certificacion,),
            )
            return cursor.fetchone()

    def obtener_todos(self) -> list[dict[str, Any]]:
        return self._obtener_todos(bloquear=False)

    def obtener_todos_para_actualizar(self) -> list[dict[str, Any]]:
        return self._obtener_todos(bloquear=True)

    def _obtener_todos(self, *, bloquear: bool) -> list[dict[str, Any]]:
        columnas = ", ".join(TODOS_CAMPOS_PRODUCTO)
        sufijo = "FOR UPDATE" if bloquear else ""
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {columnas}
                FROM {TABLA_PRODUCTOS}
                ORDER BY id_certificacion
                {sufijo}
                """
            )
            return list(cursor.fetchall())

    def obtener_con_clave_masiva(
        self, id_certificacion: str
    ) -> dict[str, Any] | None:
        columnas = ", ".join(
            (*TODOS_CAMPOS_PRODUCTO, CAMPO_CLAVE_EDICION_MASIVA)
        )
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {columnas}
                FROM {TABLA_PRODUCTOS}
                WHERE id_certificacion = %s
                """,
                (id_certificacion,),
            )
            return cursor.fetchone()

    def obtener_para_actualizar(
        self, id_certificacion: str
    ) -> dict[str, Any] | None:
        columnas = ", ".join(TODOS_CAMPOS_PRODUCTO)
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {columnas}
                FROM {TABLA_PRODUCTOS}
                WHERE id_certificacion = %s
                FOR UPDATE
                """,
                (id_certificacion,),
            )
            return cursor.fetchone()

    def obtener_resumen_grupo_masivo(
        self, clave_edicion_masiva: str
    ) -> dict[str, int]:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(activo = 1), 0) AS activos,
                    COALESCE(SUM(activo = 0), 0) AS inactivos
                FROM {TABLA_PRODUCTOS}
                WHERE {CAMPO_CLAVE_EDICION_MASIVA} = %s
                """,
                (clave_edicion_masiva,),
            )
            fila = cursor.fetchone()
        return {campo: int(valor or 0) for campo, valor in fila.items()}

    def obtener_grupo_masivo_para_actualizar(
        self, clave_edicion_masiva: str
    ) -> list[dict[str, Any]]:
        columnas = ", ".join(
            (*TODOS_CAMPOS_PRODUCTO, CAMPO_CLAVE_EDICION_MASIVA)
        )
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {columnas}
                FROM {TABLA_PRODUCTOS}
                WHERE {CAMPO_CLAVE_EDICION_MASIVA} = %s
                ORDER BY id_certificacion
                FOR UPDATE
                """,
                (clave_edicion_masiva,),
            )
            return list(cursor.fetchall())

    def actualizar_campos_usuario(
        self,
        id_certificacion: str,
        cambios: Mapping[str, tuple[Any, Any]],
        usuario: str,
    ) -> None:
        no_permitidos = set(cambios) - set(CAMPOS_USUARIO)
        if no_permitidos:
            raise ValueError(
                "Campos manuales no permitidos: "
                + ", ".join(sorted(no_permitidos))
            )
        if not cambios:
            return

        asignaciones = [f"{campo} = %s" for campo in cambios]
        asignaciones.extend(
            (
                "actualizado_por = %s",
                "fecha_actualizacion = CURRENT_TIMESTAMP",
            )
        )
        parametros = [cambios[campo][1] for campo in cambios]
        parametros.extend((usuario, id_certificacion))

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {TABLA_PRODUCTOS}
                SET {", ".join(asignaciones)}
                WHERE id_certificacion = %s
                """,
                parametros,
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"No se pudo actualizar exactamente una fila: {id_certificacion}"
                )

    def actualizar_campos_usuario_masivo(
        self,
        operaciones: list[tuple[str, Mapping[str, tuple[Any, Any]]]],
        usuario: str,
        *,
        tamano_lote: int = 100,
    ) -> int:
        """Actualiza por lotes filas ya bloqueadas, agrupadas por campos."""
        if not operaciones:
            return 0
        if tamano_lote < 1:
            raise ValueError("El tamaño de lote manual debe ser positivo")

        grupos: dict[tuple[str, ...], list[tuple[str, Mapping[str, tuple[Any, Any]]]]] = {}
        for identificador, cambios in operaciones:
            no_permitidos = set(cambios) - set(CAMPOS_USUARIO)
            if no_permitidos:
                raise ValueError(
                    "Campos manuales no permitidos: "
                    + ", ".join(sorted(no_permitidos))
                )
            if cambios:
                grupos.setdefault(tuple(sorted(cambios)), []).append(
                    (identificador, cambios)
                )

        actualizados = 0
        with self.conexion.cursor() as cursor:
            for campos, filas in grupos.items():
                for inicio in range(0, len(filas), tamano_lote):
                    lote = filas[inicio : inicio + tamano_lote]
                    asignaciones = []
                    parametros: list[Any] = []
                    for campo in campos:
                        casos = []
                        for identificador, cambios in lote:
                            casos.append("WHEN %s THEN %s")
                            parametros.extend(
                                (identificador, cambios[campo][1])
                            )
                        asignaciones.append(
                            f"{campo} = CASE id_certificacion "
                            f"{' '.join(casos)} ELSE {campo} END"
                        )
                    asignaciones.extend(
                        (
                            "actualizado_por = %s",
                            "fecha_actualizacion = CURRENT_TIMESTAMP",
                        )
                    )
                    parametros.append(usuario)
                    ids = [identificador for identificador, _ in lote]
                    marcadores = ", ".join(["%s"] * len(ids))
                    parametros.extend(ids)
                    cursor.execute(
                        f"""
                        UPDATE {TABLA_PRODUCTOS}
                        SET {", ".join(asignaciones)}
                        WHERE id_certificacion IN ({marcadores})
                        """,
                        parametros,
                    )
                    if cursor.rowcount != len(lote):
                        raise RuntimeError(
                            "No se actualizaron todas las filas de la "
                            "edición masiva"
                        )
                    actualizados += cursor.rowcount
        return actualizados

    def cambiar_activo(
        self,
        id_certificacion: str,
        activo: bool,
        usuario: str,
    ) -> None:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {TABLA_PRODUCTOS}
                SET
                    activo = %s,
                    actualizado_por = %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id_certificacion = %s
                """,
                (1 if activo else 0, usuario, id_certificacion),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"No se pudo cambiar el estado de: {id_certificacion}"
                )

    def cambiar_activos_masivo(
        self,
        operaciones: list[tuple[str, bool]],
        usuario: str,
        *,
        tamano_lote: int = 500,
    ) -> int:
        """Cambia vigencias ya comparadas y bloqueadas por el servicio."""
        if not operaciones:
            return 0
        if tamano_lote < 1:
            raise ValueError("El tamaño de lote de vigencia debe ser positivo")
        grupos: dict[bool, list[str]] = {False: [], True: []}
        for identificador, activo in operaciones:
            grupos[bool(activo)].append(identificador)

        actualizados = 0
        with self.conexion.cursor() as cursor:
            for activo, ids_grupo in grupos.items():
                objetivo = 1 if activo else 0
                for inicio in range(0, len(ids_grupo), tamano_lote):
                    ids = ids_grupo[inicio : inicio + tamano_lote]
                    marcadores = ", ".join(["%s"] * len(ids))
                    cursor.execute(
                        f"""
                        UPDATE {TABLA_PRODUCTOS}
                        SET
                            activo = %s,
                            actualizado_por = %s,
                            fecha_actualizacion = CURRENT_TIMESTAMP
                        WHERE id_certificacion IN ({marcadores})
                          AND activo <> %s
                        """,
                        (objetivo, usuario, *ids, objetivo),
                    )
                    if cursor.rowcount != len(ids):
                        raise RuntimeError(
                            "No se cambiaron todas las vigencias solicitadas"
                        )
                    actualizados += cursor.rowcount
        return actualizados

    def auditar_cambios(
        self,
        *,
        id_certificacion: str,
        fila_clave: Mapping[str, Any],
        usuario: str,
        accion: str,
        cambios: Mapping[str, tuple[Any, Any]],
    ) -> None:
        with self.conexion.cursor() as cursor:
            auditoria.insertar_cambios(
                cursor,
                id_certificacion=id_certificacion,
                fila_clave=fila_clave,
                usuario=usuario,
                accion=accion,
                cambios=cambios,
            )

    def auditar_cambios_masivos(
        self,
        *,
        operaciones: list[
            tuple[
                str,
                Mapping[str, Any],
                Mapping[str, tuple[Any, Any]],
            ]
        ],
        usuario: str,
        accion: str,
    ) -> int:
        with self.conexion.cursor() as cursor:
            return auditoria.insertar_cambios_masivos(
                cursor,
                operaciones=operaciones,
                usuario=usuario,
                accion=accion,
            )

    def listar_auditoria(
        self,
        id_certificacion: str,
        *,
        limite: int,
    ) -> list[dict[str, Any]]:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id_auditoria,
                    id_certificacion,
                    usuario,
                    accion,
                    campo_modificado,
                    valor_anterior,
                    valor_nuevo,
                    fecha_modificacion
                FROM {TABLA_AUDITORIA}
                WHERE id_certificacion = %s
                ORDER BY id_auditoria DESC
                LIMIT %s
                """,
                (id_certificacion, limite),
            )
            return list(cursor.fetchall())
