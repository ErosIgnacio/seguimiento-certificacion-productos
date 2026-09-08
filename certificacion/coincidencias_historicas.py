"""Búsqueda explicable de posibles errores en claves históricas."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .constantes import CAMPOS_CLAVE
from .validaciones import normalizar_componente


LIMITE_CANDIDATOS_POR_ID = 20


def _distancia_damerau(valor_a: str, valor_b: str) -> int:
    """Distancia de edición con transposición adyacente como una operación."""
    if valor_a == valor_b:
        return 0
    if not valor_a:
        return len(valor_b)
    if not valor_b:
        return len(valor_a)

    anterior_anterior: list[int] | None = None
    anterior = list(range(len(valor_b) + 1))
    for indice_a, caracter_a in enumerate(valor_a, start=1):
        actual = [indice_a]
        for indice_b, caracter_b in enumerate(valor_b, start=1):
            costo = 0 if caracter_a == caracter_b else 1
            distancia = min(
                actual[indice_b - 1] + 1,
                anterior[indice_b] + 1,
                anterior[indice_b - 1] + costo,
            )
            if (
                anterior_anterior is not None
                and indice_a > 1
                and indice_b > 1
                and caracter_a == valor_b[indice_b - 2]
                and valor_a[indice_a - 2] == caracter_b
            ):
                distancia = min(
                    distancia,
                    anterior_anterior[indice_b - 2] + 1,
                )
            actual.append(distancia)
        anterior_anterior, anterior = anterior, actual
    return anterior[-1]


def _componentes_desde_id(identificador: str) -> dict[str, str]:
    componentes = identificador.split("_")
    if len(componentes) != len(CAMPOS_CLAVE):
        raise ValueError(f"id_certificacion no separable: {identificador}")
    return dict(zip(CAMPOS_CLAVE, componentes))


def _normalizar_registro(fila: Mapping[str, Any]) -> dict[str, str]:
    normalizado = {
        campo: normalizar_componente(fila.get(campo)) or ""
        for campo in CAMPOS_CLAVE
    }
    normalizado["id_certificacion"] = str(fila["id_certificacion"])
    return normalizado


def analizar_coincidencias_faltantes(
    ids_faltantes: Iterable[str],
    registros_db: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Busca coincidencias exactas y errores de una edición en OC/contenedor."""
    filas_db = [_normalizar_registro(fila) for fila in registros_db]
    por_contenedor: dict[str, list[dict[str, str]]] = defaultdict(list)
    por_oc: dict[str, list[dict[str, str]]] = defaultdict(list)
    for fila in filas_db:
        por_contenedor[fila["n_contenedor"]].append(fila)
        por_oc[fila["oc"]].append(fila)

    contenedores = tuple(por_contenedor)
    ordenes_compra = tuple(por_oc)
    detalles = []
    con_contenedor_exacto = 0
    con_oc_exacta = 0
    con_alguna_exacta = 0
    con_coincidencia_fuerte = 0
    con_similitud_un_caracter = 0
    sin_coincidencia = 0

    for identificador in sorted(ids_faltantes):
        clave = _componentes_desde_id(identificador)
        exactos_contenedor = por_contenedor.get(clave["n_contenedor"], [])
        exactos_oc = por_oc.get(clave["oc"], [])
        if exactos_contenedor:
            con_contenedor_exacto += 1
        if exactos_oc:
            con_oc_exacta += 1
        if exactos_contenedor or exactos_oc:
            con_alguna_exacta += 1

        contenedores_similares = sorted(
            valor
            for valor in contenedores
            if valor != clave["n_contenedor"]
            and abs(len(valor) - len(clave["n_contenedor"])) <= 1
            and _distancia_damerau(valor, clave["n_contenedor"]) == 1
        )
        oc_similares = sorted(
            valor
            for valor in ordenes_compra
            if valor != clave["oc"]
            and abs(len(valor) - len(clave["oc"])) <= 1
            and _distancia_damerau(valor, clave["oc"]) == 1
        )
        if contenedores_similares or oc_similares:
            con_similitud_un_caracter += 1

        candidatos_por_id: dict[str, dict[str, str]] = {}
        for candidato in (*exactos_contenedor, *exactos_oc):
            candidatos_por_id[candidato["id_certificacion"]] = candidato
        for valor in contenedores_similares:
            for candidato in por_contenedor[valor]:
                candidatos_por_id[candidato["id_certificacion"]] = candidato
        for valor in oc_similares:
            for candidato in por_oc[valor]:
                candidatos_por_id[candidato["id_certificacion"]] = candidato

        candidatos_fuertes = []
        candidatos_relacionados = []
        for candidato in candidatos_por_id.values():
            mismo_gd = candidato["gd"] == clave["gd"]
            mismo_sku = candidato["sku"] == clave["sku"]
            mismo_contenedor = (
                candidato["n_contenedor"] == clave["n_contenedor"]
            )
            misma_oc = candidato["oc"] == clave["oc"]
            detalle_candidato = {
                "id_certificacion": candidato["id_certificacion"],
                "contenedor_exacto": mismo_contenedor,
                "oc_exacta": misma_oc,
                "gd_exacto": mismo_gd,
                "sku_exacto": mismo_sku,
            }
            if mismo_gd and mismo_sku and (mismo_contenedor or misma_oc):
                candidatos_fuertes.append(detalle_candidato)
            elif (mismo_gd or mismo_sku) and (mismo_contenedor or misma_oc):
                candidatos_relacionados.append(detalle_candidato)

        candidatos_fuertes.sort(key=lambda fila: fila["id_certificacion"])
        candidatos_relacionados.sort(key=lambda fila: fila["id_certificacion"])
        if candidatos_fuertes:
            con_coincidencia_fuerte += 1
        if not (
            exactos_contenedor
            or exactos_oc
            or contenedores_similares
            or oc_similares
        ):
            sin_coincidencia += 1

        detalles.append(
            {
                "id_certificacion_csv": identificador,
                "contenedor_exacto": len(exactos_contenedor),
                "oc_exacta": len(exactos_oc),
                "contenedores_similares_1_edicion": contenedores_similares,
                "oc_similares_1_edicion": oc_similares,
                "candidatos_fuertes": candidatos_fuertes[
                    :LIMITE_CANDIDATOS_POR_ID
                ],
                "candidatos_relacionados": candidatos_relacionados[
                    :LIMITE_CANDIDATOS_POR_ID
                ],
                "candidatos_omitidos": max(
                    0,
                    len(candidatos_fuertes)
                    + len(candidatos_relacionados)
                    - (2 * LIMITE_CANDIDATOS_POR_ID),
                ),
            }
        )

    return {
        "ids_analizados": len(detalles),
        "con_contenedor_exacto": con_contenedor_exacto,
        "con_oc_exacta": con_oc_exacta,
        "con_oc_o_contenedor_exacto": con_alguna_exacta,
        "con_similitud_de_una_edicion": con_similitud_un_caracter,
        "con_coincidencia_fuerte_gd_sku": con_coincidencia_fuerte,
        "sin_coincidencia_oc_contenedor": sin_coincidencia,
        "detalles": detalles,
    }
