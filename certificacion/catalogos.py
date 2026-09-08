"""Servicios transaccionales de catálogos configurables de certificación."""

from __future__ import annotations

import logging
import json
from typing import Any

from .configuracion import crear_conexion
from .constantes import (
    CAMPOS_CATALOGO,
    TABLA_CATALOGOS,
    TABLA_CATALOGOS_AUDITORIA,
)
from .usuarios import normalizar_usuario


LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

LONGITUD_VALOR_CATALOGO = 267
LONGITUD_DESCRIPCION_CATALOGO = 255
LONGITUD_CODIGO_DEPTO = 50


def _error(exc: Exception) -> dict[str, Any]:
    LOGGER.exception("Operación de catálogo de certificaciones fallida")
    return {
        "ok": False,
        "errores": [{"tipo": type(exc).__name__, "mensaje": str(exc)}],
    }


def validar_tipo_catalogo(tipo: str) -> str:
    normalizado = str(tipo or "").strip().lower()
    if normalizado not in CAMPOS_CATALOGO:
        raise ValueError(f"Tipo de catálogo no permitido: {tipo}")
    return normalizado


def normalizar_valor_catalogo(valor: str) -> str:
    normalizado = str(valor or "").strip()
    if not normalizado:
        raise ValueError("El valor del catálogo es obligatorio")
    if len(normalizado) > LONGITUD_VALOR_CATALOGO:
        raise ValueError(
            f"El valor usa {len(normalizado)} caracteres y admite "
            f"{LONGITUD_VALOR_CATALOGO}"
        )
    return normalizado


def normalizar_codigo_departamento(valor: str) -> str:
    """Valida un código de departamento sin alterar ceros iniciales."""
    normalizado = normalizar_valor_catalogo(valor)
    if len(normalizado) > LONGITUD_CODIGO_DEPTO:
        raise ValueError(
            f"El código de departamento admite hasta {LONGITUD_CODIGO_DEPTO} "
            "caracteres"
        )
    if not normalizado.isascii() or not normalizado.isdecimal():
        raise ValueError("El código de departamento debe contener solo dígitos")
    return normalizado


class RepositorioCatalogos:
    def __init__(self, conexion):
        self.conexion = conexion

    def listar(self, tipo: str | None = None) -> list[dict[str, Any]]:
        parametros = []
        where = ""
        if tipo:
            where = "WHERE tipo = %s"
            parametros.append(tipo)
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id_catalogo,
                    tipo,
                    valor,
                    descripcion,
                    orden,
                    activo,
                    creado_por,
                    fecha_creacion,
                    actualizado_por,
                    fecha_actualizacion
                FROM {TABLA_CATALOGOS}
                {where}
                ORDER BY tipo, activo DESC, orden, valor
                """,
                parametros,
            )
            return list(cursor.fetchall())

    def obtener_para_actualizar(self, id_catalogo: int):
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id_catalogo, tipo, valor, descripcion, orden, activo
                FROM {TABLA_CATALOGOS}
                WHERE id_catalogo = %s
                FOR UPDATE
                """,
                (id_catalogo,),
            )
            return cursor.fetchone()

    def crear(
        self,
        *,
        tipo: str,
        valor: str,
        descripcion: str | None,
        orden: int,
        usuario: str,
    ) -> int:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {TABLA_CATALOGOS} (
                    tipo, valor, descripcion, orden, activo,
                    creado_por, fecha_creacion
                ) VALUES (%s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
                """,
                (tipo, valor, descripcion, orden, usuario),
            )
            return int(cursor.lastrowid)

    def actualizar(
        self,
        id_catalogo: int,
        *,
        valor: str,
        descripcion: str | None,
        orden: int,
        usuario: str,
    ) -> None:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {TABLA_CATALOGOS}
                SET
                    valor = %s,
                    descripcion = %s,
                    orden = %s,
                    actualizado_por = %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id_catalogo = %s
                """,
                (valor, descripcion, orden, usuario, id_catalogo),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("No se pudo actualizar el valor de catálogo")

    def cambiar_activo(
        self, id_catalogo: int, activo: bool, usuario: str
    ) -> None:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {TABLA_CATALOGOS}
                SET
                    activo = %s,
                    actualizado_por = %s,
                    fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id_catalogo = %s
                """,
                (1 if activo else 0, usuario, id_catalogo),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("No se pudo cambiar la vigencia del catálogo")

    def auditar_evento(
        self,
        *,
        id_catalogo: int,
        tipo: str,
        usuario: str,
        accion: str,
        campo_modificado: str,
        valor_anterior: Any,
        valor_nuevo: Any,
    ) -> None:
        permitidas = {
            "CATALOG_CREATE",
            "CATALOG_UPDATE",
            "CATALOG_DEACTIVATE",
            "CATALOG_REACTIVATE",
        }
        if accion not in permitidas:
            raise ValueError(f"Acción de catálogo no permitida: {accion}")

        def serializar(valor):
            if valor is None:
                return None
            if isinstance(valor, (dict, list, tuple)):
                return json.dumps(valor, ensure_ascii=False, sort_keys=True)
            return str(valor)

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {TABLA_CATALOGOS_AUDITORIA} (
                    id_catalogo,
                    tipo,
                    usuario,
                    accion,
                    campo_modificado,
                    valor_anterior,
                    valor_nuevo,
                    fecha_modificacion
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    id_catalogo,
                    tipo,
                    usuario,
                    accion,
                    campo_modificado,
                    serializar(valor_anterior),
                    serializar(valor_nuevo),
                ),
            )

    def listar_auditoria(
        self, id_catalogo: int | None = None, *, limite: int = 1000
    ) -> list[dict[str, Any]]:
        where = ""
        parametros: list[Any] = []
        if id_catalogo is not None:
            where = "WHERE id_catalogo = %s"
            parametros.append(id_catalogo)
        parametros.append(limite)
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id_auditoria,
                    id_catalogo,
                    tipo,
                    usuario,
                    accion,
                    campo_modificado,
                    valor_anterior,
                    valor_nuevo,
                    fecha_modificacion
                FROM {TABLA_CATALOGOS_AUDITORIA}
                {where}
                ORDER BY id_auditoria DESC
                LIMIT %s
                """,
                parametros,
            )
            return list(cursor.fetchall())


def listar_catalogos(tipo: str | None = None) -> dict[str, Any]:
    conexion = None
    try:
        tipo_normalizado = validar_tipo_catalogo(tipo) if tipo else None
        conexion = crear_conexion()
        filas = RepositorioCatalogos(conexion).listar(tipo_normalizado)
        return {"ok": True, "filas": filas, "errores": []}
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def guardar_catalogo(
    *,
    tipo: str,
    valor: str,
    descripcion: str | None,
    orden: int,
    usuario: str,
    id_catalogo: int | None = None,
) -> dict[str, Any]:
    conexion = None
    try:
        tipo = validar_tipo_catalogo(tipo)
        valor = (
            normalizar_codigo_departamento(valor)
            if tipo == "codigo_depto"
            else normalizar_valor_catalogo(valor)
        )
        descripcion = str(descripcion or "").strip() or None
        if descripcion and len(descripcion) > LONGITUD_DESCRIPCION_CATALOGO:
            raise ValueError("La descripción admite hasta 255 caracteres")
        orden = int(orden)
        if orden < 0 or orden > 4_294_967_295:
            raise ValueError("El orden debe ser un entero no negativo")
        usuario = normalizar_usuario(usuario)

        conexion = crear_conexion()
        repositorio = RepositorioCatalogos(conexion)
        conexion.begin()
        try:
            if id_catalogo is None:
                id_catalogo = repositorio.crear(
                    tipo=tipo,
                    valor=valor,
                    descripcion=descripcion,
                    orden=orden,
                    usuario=usuario,
                )
                repositorio.auditar_evento(
                    id_catalogo=id_catalogo,
                    tipo=tipo,
                    usuario=usuario,
                    accion="CATALOG_CREATE",
                    campo_modificado="REGISTRO",
                    valor_anterior=None,
                    valor_nuevo={
                        "tipo": tipo,
                        "valor": valor,
                        "descripcion": descripcion,
                        "orden": orden,
                        "activo": 1,
                    },
                )
                mensaje = "Valor de catálogo creado"
            else:
                id_catalogo = int(id_catalogo)
                existente = repositorio.obtener_para_actualizar(id_catalogo)
                if existente is None:
                    raise LookupError("No existe el valor de catálogo")
                if existente["tipo"] != tipo:
                    raise ValueError("No se permite cambiar el tipo de catálogo")
                sin_cambios = (
                    existente["valor"] == valor
                    and (existente.get("descripcion") or None) == descripcion
                    and int(existente["orden"]) == orden
                )
                if sin_cambios:
                    conexion.rollback()
                    return {
                        "ok": True,
                        "id_catalogo": id_catalogo,
                        "actualizados": 0,
                        "mensaje": "No existen cambios para guardar",
                        "errores": [],
                    }
                cambios = {
                    campo: (existente.get(campo), nuevo)
                    for campo, nuevo in {
                        "valor": valor,
                        "descripcion": descripcion,
                        "orden": orden,
                    }.items()
                    if existente.get(campo) != nuevo
                }
                repositorio.actualizar(
                    id_catalogo,
                    valor=valor,
                    descripcion=descripcion,
                    orden=orden,
                    usuario=usuario,
                )
                for campo, (anterior, nuevo) in cambios.items():
                    repositorio.auditar_evento(
                        id_catalogo=id_catalogo,
                        tipo=tipo,
                        usuario=usuario,
                        accion="CATALOG_UPDATE",
                        campo_modificado=campo,
                        valor_anterior=anterior,
                        valor_nuevo=nuevo,
                    )
                mensaje = "Valor de catálogo actualizado"
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        return {
            "ok": True,
            "id_catalogo": id_catalogo,
            "actualizados": 1,
            "mensaje": mensaje,
            "errores": [],
        }
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def cambiar_estado_catalogo(
    id_catalogo: int, activo: bool, usuario: str
) -> dict[str, Any]:
    conexion = None
    try:
        if not isinstance(activo, bool):
            raise ValueError("El estado activo debe ser verdadero o falso")
        usuario = normalizar_usuario(usuario)
        id_catalogo = int(id_catalogo)
        conexion = crear_conexion()
        repositorio = RepositorioCatalogos(conexion)
        conexion.begin()
        try:
            existente = repositorio.obtener_para_actualizar(id_catalogo)
            if existente is None:
                raise LookupError("No existe el valor de catálogo")
            if bool(existente["activo"]) == activo:
                conexion.rollback()
                return {
                    "ok": True,
                    "actualizados": 0,
                    "mensaje": "El catálogo ya tenía el estado solicitado",
                    "errores": [],
                }
            repositorio.cambiar_activo(id_catalogo, activo, usuario)
            repositorio.auditar_evento(
                id_catalogo=id_catalogo,
                tipo=existente["tipo"],
                usuario=usuario,
                accion="CATALOG_REACTIVATE" if activo else "CATALOG_DEACTIVATE",
                campo_modificado="activo",
                valor_anterior=1 if existente["activo"] else 0,
                valor_nuevo=1 if activo else 0,
            )
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
        return {
            "ok": True,
            "actualizados": 1,
            "mensaje": "Catálogo reactivado" if activo else "Catálogo desactivado",
            "errores": [],
        }
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def consultar_auditoria_catalogos(
    id_catalogo: int | None = None, *, limite: int = 1000
) -> dict[str, Any]:
    conexion = None
    try:
        if id_catalogo is not None:
            id_catalogo = int(id_catalogo)
        limite = max(1, min(5000, int(limite)))
        conexion = crear_conexion()
        filas = RepositorioCatalogos(conexion).listar_auditoria(
            id_catalogo, limite=limite
        )
        return {"ok": True, "filas": filas, "errores": []}
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()
