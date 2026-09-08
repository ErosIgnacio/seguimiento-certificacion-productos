"""Normalización y validaciones puras de claves y duplicados."""

from __future__ import annotations

import math
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .constantes import (
    CAMPOS_AUTOMATICOS,
    CAMPOS_CLAVE,
    LONGITUD_ID_CERTIFICACION,
    LONGITUDES_CLAVE,
)


VALORES_CLAVE_INVALIDOS = frozenset({"", "nan", "none", "null"})


class ClaveIncompletaError(ValueError):
    """No es posible construir una clave con componentes incompletos."""


class ClaveDemasiadoLargaError(ValueError):
    """Un componente excede la capacidad calculada desde el origen."""


class ClaveConSeparadorError(ValueError):
    """Un componente contiene el separador reservado del identificador."""


@dataclass
class ResultadoValidacion:
    filas: list[dict[str, Any]] = field(default_factory=list)
    omitidos_clave_incompleta: int = 0
    duplicados_consolidados: int = 0
    duplicados_conflictivos: int = 0
    claves_con_separador: int = 0
    errores: list[dict[str, Any]] = field(default_factory=list)
    detalles_clave_incompleta: list[dict[str, Any]] = field(default_factory=list)
    detalles_claves_con_separador: list[dict[str, Any]] = field(default_factory=list)
    detalles_duplicados_conflictivos: list[dict[str, Any]] = field(
        default_factory=list
    )

    @property
    def bloquea_sincronizacion(self) -> bool:
        return bool(self.claves_con_separador or self.duplicados_conflictivos)


def normalizar_componente(valor: Any) -> str | None:
    """Aplica TRIM/UPPER y reconoce los marcadores inválidos solicitados."""
    if valor is None:
        return None

    if isinstance(valor, float):
        if math.isnan(valor):
            return None
        if valor.is_integer():
            valor = int(valor)
    elif isinstance(valor, Decimal) and valor == valor.to_integral_value():
        valor = int(valor)

    texto = str(valor).strip()
    if texto.casefold() in VALORES_CLAVE_INVALIDOS:
        return None
    return texto.upper()


def construir_id_certificacion(
    n_contenedor: Any,
    oc: Any,
    gd: Any,
    sku: Any,
) -> str:
    """Construye el valor esperado de la columna generada de MySQL."""
    componentes = tuple(
        normalizar_componente(valor) for valor in (n_contenedor, oc, gd, sku)
    )
    if any(valor is None for valor in componentes):
        raise ClaveIncompletaError("Los cuatro componentes de la clave son obligatorios")
    campos_con_separador = [
        campo
        for campo, valor in zip(CAMPOS_CLAVE, componentes)
        if "_" in valor
    ]
    if campos_con_separador:
        raise ClaveConSeparadorError(
            "El separador '_' aparece dentro de: "
            + ", ".join(campos_con_separador)
        )

    for campo, valor in zip(CAMPOS_CLAVE, componentes):
        if len(valor) > LONGITUDES_CLAVE[campo]:
            raise ClaveDemasiadoLargaError(
                f"{campo} usa {len(valor)} caracteres y admite "
                f"{LONGITUDES_CLAVE[campo]}"
            )

    identificador = "_".join(componentes)
    if len(identificador) > LONGITUD_ID_CERTIFICACION:
        raise ClaveDemasiadoLargaError(
            f"id_certificacion usa {len(identificador)} caracteres y admite "
            f"{LONGITUD_ID_CERTIFICACION}"
        )
    return identificador


def _normalizar_valor_automatico(campo: str, valor: Any) -> Any:
    if campo in CAMPOS_CLAVE:
        return normalizar_componente(valor)
    if isinstance(valor, str):
        return valor.strip()
    if campo in {"eta", "fecha_liberacion", "fecha_programacion"}:
        if isinstance(valor, datetime):
            return valor.date()
    if campo == "unidades" and isinstance(valor, Decimal):
        if valor == valor.to_integral_value():
            return int(valor)
    return valor


def normalizar_fila_origen(fila: Mapping[str, Any]) -> dict[str, Any]:
    """Devuelve únicamente los catorce campos automáticos esperados."""
    return {
        campo: _normalizar_valor_automatico(campo, fila.get(campo))
        for campo in CAMPOS_AUTOMATICOS
    }


def valores_equivalentes(valor_a: Any, valor_b: Any) -> bool:
    """Compara valores tal como se almacenan en los tipos elegidos."""
    if isinstance(valor_a, datetime) and isinstance(valor_b, date):
        valor_a = valor_a.date()
    if isinstance(valor_b, datetime) and isinstance(valor_a, date):
        valor_b = valor_b.date()
    if isinstance(valor_a, Decimal) and valor_a == valor_a.to_integral_value():
        valor_a = int(valor_a)
    if isinstance(valor_b, Decimal) and valor_b == valor_b.to_integral_value():
        valor_b = int(valor_b)
    return valor_a == valor_b


def _valor_detalle(valor: Any) -> Any:
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def _diferencias_entre_filas(
    filas: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    diferencias: dict[str, list[Any]] = {}
    for campo in CAMPOS_AUTOMATICOS:
        unicos: list[Any] = []
        for fila in filas:
            valor = fila[campo]
            if not any(valores_equivalentes(valor, actual) for actual in unicos):
                unicos.append(valor)
        if len(unicos) > 1:
            diferencias[campo] = [_valor_detalle(valor) for valor in unicos]
    return diferencias


def _clave_colacion_mysql(identificador: str) -> str:
    """Aproxima utf8mb4_0900_ai_ci para anticipar colisiones de índice."""
    descompuesto = unicodedata.normalize("NFKD", identificador.casefold())
    return "".join(
        caracter
        for caracter in descompuesto
        if not unicodedata.combining(caracter)
    )


def preparar_filas_origen(
    filas_origen: Iterable[Mapping[str, Any]],
) -> ResultadoValidacion:
    """Normaliza, omite incompletas y clasifica duplicados antes del UPSERT."""
    resultado = ResultadoValidacion()
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for numero_fila, fila_original in enumerate(filas_origen, start=1):
        fila = normalizar_fila_origen(fila_original)
        incompletos = [campo for campo in CAMPOS_CLAVE if fila[campo] is None]
        separadores = [
            campo
            for campo in CAMPOS_CLAVE
            if fila[campo] is not None and "_" in fila[campo]
        ]

        if separadores:
            resultado.claves_con_separador += 1
            resultado.detalles_claves_con_separador.append(
                {
                    "fila_origen": numero_fila,
                    "campos": separadores,
                    "valores": {campo: fila[campo] for campo in separadores},
                }
            )

        if incompletos:
            resultado.omitidos_clave_incompleta += 1
            resultado.detalles_clave_incompleta.append(
                {"fila_origen": numero_fila, "campos": incompletos}
            )
            continue

        if separadores:
            continue

        try:
            identificador = construir_id_certificacion(
                *(fila[campo] for campo in CAMPOS_CLAVE)
            )
        except ClaveDemasiadoLargaError as exc:
            resultado.duplicados_conflictivos += 1
            resultado.detalles_duplicados_conflictivos.append(
                {
                    "fila_origen": numero_fila,
                    "id_certificacion": None,
                    "campos": {"longitud": [str(exc)]},
                }
            )
            continue

        fila["id_certificacion"] = identificador
        grupos[identificador].append(fila)

    for identificador, filas in grupos.items():
        diferencias = _diferencias_entre_filas(filas)
        if diferencias:
            resultado.duplicados_conflictivos += 1
            resultado.detalles_duplicados_conflictivos.append(
                {
                    "id_certificacion": identificador,
                    "campos": diferencias,
                    "filas": len(filas),
                }
            )
            continue

        resultado.filas.append(filas[0])
        resultado.duplicados_consolidados += len(filas) - 1

    # Dos textos distintos pueden colisionar bajo la collation ai_ci del proyecto.
    por_colacion: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fila in resultado.filas:
        por_colacion[_clave_colacion_mysql(fila["id_certificacion"])].append(fila)

    ids_colisionados: set[str] = set()
    for filas in por_colacion.values():
        ids = {fila["id_certificacion"] for fila in filas}
        if len(ids) <= 1:
            continue
        resultado.duplicados_conflictivos += 1
        ids_colisionados.update(ids)
        resultado.detalles_duplicados_conflictivos.append(
            {
                "tipo": "COLISION_COLLATION",
                "ids_certificacion": sorted(ids),
                "campos": {"id_certificacion": sorted(ids)},
                "filas": len(filas),
            }
        )

    if ids_colisionados:
        resultado.filas = [
            fila
            for fila in resultado.filas
            if fila["id_certificacion"] not in ids_colisionados
        ]

    if resultado.claves_con_separador:
        resultado.errores.append(
            {
                "tipo": "CLAVE_CON_SEPARADOR",
                "mensaje": (
                    "La sincronización se detuvo: hay componentes de clave con '_'."
                ),
                "registros": resultado.detalles_claves_con_separador,
            }
        )
    if resultado.duplicados_conflictivos:
        resultado.errores.append(
            {
                "tipo": "DUPLICADO_CONFLICTIVO",
                "mensaje": (
                    "La sincronización se detuvo: una misma clave tiene valores "
                    "automáticos diferentes o excede la longitud permitida."
                ),
                "registros": resultado.detalles_duplicados_conflictivos,
            }
        )

    return resultado
