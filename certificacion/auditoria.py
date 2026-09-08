"""Escritura de la auditoría independiente de certificación."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from collections.abc import Iterable
from typing import Any, Mapping

from .constantes import (
    ACCIONES_AUDITORIA,
    CAMPOS_AUTOMATICOS,
    CAMPOS_CLAVE,
    TABLA_AUDITORIA,
)


def _json_default(valor: Any) -> str:
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(f"No se puede serializar {type(valor).__name__}")


def serializar_snapshot_automatico(fila: Mapping[str, Any]) -> str:
    """Genera un snapshot JSON estable de los catorce campos automáticos."""
    snapshot = {campo: fila.get(campo) for campo in CAMPOS_AUTOMATICOS}
    return json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def serializar_valor(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (dict, list, tuple)):
        return json.dumps(valor, ensure_ascii=False, default=_json_default)
    return str(valor)


def insertar_evento(
    cursor,
    *,
    id_certificacion: str,
    fila_clave: Mapping[str, Any],
    usuario: str,
    accion: str,
    campo_modificado: str,
    valor_anterior: Any,
    valor_nuevo: Any,
) -> None:
    """Inserta un evento usando el cursor de la transacción principal."""
    parametros = _parametros_evento(
        id_certificacion=id_certificacion,
        fila_clave=fila_clave,
        usuario=usuario,
        accion=accion,
        campo_modificado=campo_modificado,
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
    )

    cursor.execute(_sql_insertar_evento(), parametros)


def _sql_insertar_evento(*, fecha_parametrizada: bool = False) -> str:
    """Construye el INSERT usando el nombre de tabla activo en la sesión."""
    valor_fecha = "%s" if fecha_parametrizada else "CURRENT_TIMESTAMP"
    return f"""
        INSERT INTO {TABLA_AUDITORIA} (
            id_certificacion,
            n_contenedor,
            oc,
            gd,
            sku,
            usuario,
            accion,
            campo_modificado,
            valor_anterior,
            valor_nuevo,
            fecha_modificacion
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, {valor_fecha}
        )
    """


def _parametros_evento(
    *,
    id_certificacion: str,
    fila_clave: Mapping[str, Any],
    usuario: str,
    accion: str,
    campo_modificado: str,
    valor_anterior: Any,
    valor_nuevo: Any,
) -> tuple[Any, ...]:
    """Valida y serializa un evento para INSERT simple o masivo."""
    if accion not in ACCIONES_AUDITORIA:
        raise ValueError(f"Acción de auditoría no permitida: {accion}")

    return (
        id_certificacion,
        *(fila_clave[campo] for campo in CAMPOS_CLAVE),
        usuario,
        accion,
        campo_modificado,
        serializar_valor(valor_anterior),
        serializar_valor(valor_nuevo),
    )


def _insertar_eventos_masivos(
    cursor,
    parametros: Iterable[tuple[Any, ...]],
    *,
    tamano_lote: int = 500,
) -> int:
    """Inserta eventos en lotes para evitar un viaje de red por cada campo."""
    filas = list(parametros)
    if not filas:
        return 0
    if tamano_lote < 1:
        raise ValueError("El tamaño de lote de auditoría debe ser positivo")

    cursor.execute("SELECT CURRENT_TIMESTAMP AS fecha_modificacion")
    fecha_modificacion = cursor.fetchone()["fecha_modificacion"]
    for inicio in range(0, len(filas), tamano_lote):
        lote = [
            (*fila, fecha_modificacion)
            for fila in filas[inicio : inicio + tamano_lote]
        ]
        cursor.executemany(
            _sql_insertar_evento(fecha_parametrizada=True),
            lote,
        )
    return len(filas)


def insertar_creacion(
    cursor,
    *,
    id_certificacion: str,
    fila: Mapping[str, Any],
    usuario: str,
) -> None:
    insertar_evento(
        cursor,
        id_certificacion=id_certificacion,
        fila_clave=fila,
        usuario=usuario,
        accion="SYNC_CREATE",
        campo_modificado="REGISTRO",
        valor_anterior=None,
        valor_nuevo=serializar_snapshot_automatico(fila),
    )


def insertar_cambios(
    cursor,
    *,
    id_certificacion: str,
    fila_clave: Mapping[str, Any],
    usuario: str,
    accion: str,
    cambios: Mapping[str, tuple[Any, Any]],
) -> None:
    """Registra exactamente una fila por campo realmente modificado."""
    for campo, (valor_anterior, valor_nuevo) in cambios.items():
        insertar_evento(
            cursor,
            id_certificacion=id_certificacion,
            fila_clave=fila_clave,
            usuario=usuario,
            accion=accion,
            campo_modificado=campo,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
        )


def insertar_creaciones_masivas(
    cursor,
    *,
    filas: Iterable[tuple[str, Mapping[str, Any]]],
    usuario: str,
    tamano_lote: int = 500,
) -> int:
    """Registra varios SYNC_CREATE mediante INSERT multi-fila."""
    parametros = (
        _parametros_evento(
            id_certificacion=id_certificacion,
            fila_clave=fila,
            usuario=usuario,
            accion="SYNC_CREATE",
            campo_modificado="REGISTRO",
            valor_anterior=None,
            valor_nuevo=serializar_snapshot_automatico(fila),
        )
        for id_certificacion, fila in filas
    )
    return _insertar_eventos_masivos(
        cursor,
        parametros,
        tamano_lote=tamano_lote,
    )


def insertar_cambios_masivos(
    cursor,
    *,
    operaciones: Iterable[
        tuple[
            str,
            Mapping[str, Any],
            Mapping[str, tuple[Any, Any]],
        ]
    ],
    usuario: str,
    accion: str,
    tamano_lote: int = 500,
) -> int:
    """Registra una fila por cambio real agrupando los INSERT de auditoría."""
    parametros = (
        _parametros_evento(
            id_certificacion=id_certificacion,
            fila_clave=fila_clave,
            usuario=usuario,
            accion=accion,
            campo_modificado=campo,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
        )
        for id_certificacion, fila_clave, cambios in operaciones
        for campo, (valor_anterior, valor_nuevo) in cambios.items()
    )
    return _insertar_eventos_masivos(
        cursor,
        parametros,
        tamano_lote=tamano_lote,
    )
