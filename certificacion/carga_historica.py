"""Importación controlada de campos manuales desde Certificacion.csv."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .configuracion import crear_conexion
from .coincidencias_historicas import analizar_coincidencias_faltantes
from .constantes import (
    CAMPOS_CATALOGO,
    ESTADO_NO_REQUIERE_INSPECCION,
)
from .csv_historico import ResultadoCsvHistorico, leer_csv_historico
from .datos import RepositorioCertificacion
from .datos_productos import RepositorioProductos
from .gestion import _calcular_cambios_usuario
from .usuarios import normalizar_usuario


LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())
LIMITE_IDS_RESUMEN = 100


@dataclass
class PlanCargaHistorica:
    resumen: dict[str, Any]
    actualizaciones_usuario: list[
        tuple[str, Mapping[str, Any], Mapping[str, tuple[Any, Any]]]
    ] = field(default_factory=list)
    cambios_vigencia: list[
        tuple[str, Mapping[str, Any], Mapping[str, tuple[Any, Any]], bool, str]
    ] = field(default_factory=list)


def _es_no_requiere_inspeccion(valor: Any) -> bool:
    return (
        valor is not None
        and str(valor).strip().casefold()
        == ESTADO_NO_REQUIERE_INSPECCION.casefold()
    )


def _valores_fuera_catalogo(
    csv: ResultadoCsvHistorico,
    catalogos_activos: Mapping[str, list[str]],
) -> dict[str, list[str]]:
    resultado: dict[str, list[str]] = {}
    for campo in CAMPOS_CATALOGO:
        permitidos = {
            str(valor).strip().casefold()
            for valor in catalogos_activos.get(campo, [])
        }
        historicos = sorted(
            {
                str(datos[campo]).strip()
                for datos in csv.registros.values()
                if datos.get(campo) is not None
                and str(datos[campo]).strip().casefold() not in permitidos
            },
            key=str.casefold,
        )
        if historicos:
            resultado[campo] = historicos
    return resultado


def _construir_plan(
    csv: ResultadoCsvHistorico,
    registros_db: list[Mapping[str, Any]],
    catalogos_activos: Mapping[str, list[str]],
) -> PlanCargaHistorica:
    por_id = {fila["id_certificacion"]: fila for fila in registros_db}
    ids_csv = set(csv.registros)
    ids_db = set(por_id)
    ids_coincidentes = ids_csv & ids_db
    ids_csv_sin_db = sorted(ids_csv - ids_db)
    ids_db_sin_csv = ids_db - ids_csv

    manuales = []
    vigencias = []
    ids_con_cambio: set[str] = set()
    desactivados_ausentes = 0
    desactivados_no_inspeccion = 0
    reactivados = 0

    for identificador in sorted(ids_coincidentes):
        existente = por_id[identificador]
        datos_csv = csv.registros[identificador]
        cambios = _calcular_cambios_usuario(existente, datos_csv)
        if cambios:
            manuales.append((identificador, existente, cambios))
            ids_con_cambio.add(identificador)

        activo_objetivo = not _es_no_requiere_inspeccion(
            datos_csv.get("estado_certificacion")
        )
        activo_anterior = bool(existente["activo"])
        if activo_anterior != activo_objetivo:
            cambios_activo = {
                "activo": (
                    1 if activo_anterior else 0,
                    1 if activo_objetivo else 0,
                )
            }
            motivo = "CSV_NO_REQUIERE_INSPECCION"
            if activo_objetivo:
                motivo = "CSV_PRESENTE"
                reactivados += 1
            else:
                desactivados_no_inspeccion += 1
            vigencias.append(
                (
                    identificador,
                    existente,
                    cambios_activo,
                    activo_objetivo,
                    motivo,
                )
            )
            ids_con_cambio.add(identificador)

    for identificador in sorted(ids_db_sin_csv):
        existente = por_id[identificador]
        if not bool(existente["activo"]):
            continue
        cambios_activo = {"activo": (1, 0)}
        vigencias.append(
            (
                identificador,
                existente,
                cambios_activo,
                False,
                "AUSENTE_CSV",
            )
        )
        desactivados_ausentes += 1
        ids_con_cambio.add(identificador)

    auditorias_manuales = sum(len(cambios) for _, _, cambios in manuales)
    auditorias_vigencia = len(vigencias)
    resumen = {
        **csv.resumen(),
        "registros_db": len(registros_db),
        "coincidentes": len(ids_coincidentes),
        "csv_sin_registro_db": len(ids_csv_sin_db),
        "detalle_csv_sin_registro_db": ids_csv_sin_db[:LIMITE_IDS_RESUMEN],
        "detalle_csv_sin_registro_db_omitidos": max(
            0, len(ids_csv_sin_db) - LIMITE_IDS_RESUMEN
        ),
        "diagnostico_csv_sin_registro_db": analizar_coincidencias_faltantes(
            ids_csv_sin_db, registros_db
        ),
        "db_ausentes_del_csv": len(ids_db_sin_csv),
        "actualizados_campos_usuario": len(manuales),
        "registros_con_cambio": len(ids_con_cambio),
        "sin_cambios": len(registros_db) - len(ids_con_cambio),
        "reactivados_por_csv": reactivados,
        "desactivados_ausentes_csv": desactivados_ausentes,
        "desactivados_no_requiere_inspeccion": desactivados_no_inspeccion,
        "valores_historicos_fuera_catalogo": _valores_fuera_catalogo(
            csv, catalogos_activos
        ),
        "auditorias_estimadas": auditorias_manuales + auditorias_vigencia,
        "auditorias_generadas": 0,
        "confirmado": False,
        "modo": "PREVISUALIZACION",
    }
    return PlanCargaHistorica(
        resumen=resumen,
        actualizaciones_usuario=manuales,
        cambios_vigencia=vigencias,
    )


def _ejecutar_carga_historica(
    ruta_csv: str | Path,
    usuario: str,
    *,
    aplicar: bool,
    ruta_config: str | Path | None = None,
    permitir_csv_sin_db: bool = False,
) -> dict[str, Any]:
    try:
        usuario_normalizado = normalizar_usuario(usuario)
        csv = leer_csv_historico(ruta_csv)
    except Exception as exc:
        LOGGER.exception("No se pudo leer el histórico de certificación")
        return {
            "ok": False,
            "confirmado": False,
            "modo": "IMPORTACION" if aplicar else "PREVISUALIZACION",
            "errores": [{"tipo": type(exc).__name__, "mensaje": str(exc)}],
        }

    resumen_csv = csv.resumen()
    if not csv.registros:
        resumen_csv.update(
            {
                "ok": False,
                "confirmado": False,
                "modo": "IMPORTACION" if aplicar else "PREVISUALIZACION",
                "errores": [
                    {
                        "tipo": "CSV_SIN_PRODUCTOS",
                        "mensaje": "El CSV no contiene productos válidos",
                    }
                ],
            }
        )
        return resumen_csv
    if csv.bloquea_importacion:
        resumen_csv.update(
            {
                "ok": False,
                "confirmado": False,
                "modo": "IMPORTACION" if aplicar else "PREVISUALIZACION",
            }
        )
        return resumen_csv

    conexion = None
    repositorio_bloqueo = None
    bloqueo_adquirido = False
    transaccion_iniciada = False
    plan = None
    try:
        conexion = crear_conexion(ruta_config)
        repositorio = RepositorioProductos(conexion)
        repositorio_bloqueo = RepositorioCertificacion(conexion)
        if aplicar:
            repositorio_bloqueo.adquirir_bloqueo_sincronizacion()
            bloqueo_adquirido = True
            repositorio.iniciar_transaccion()
            transaccion_iniciada = True
            registros_db = repositorio.obtener_todos_para_actualizar()
        else:
            registros_db = repositorio.obtener_todos()

        plan = _construir_plan(
            csv,
            registros_db,
            repositorio.obtener_catalogos_activos(),
        )
        plan.resumen["ok"] = True

        if not aplicar:
            return plan.resumen

        if (
            plan.resumen["csv_sin_registro_db"]
            and not permitir_csv_sin_db
        ):
            repositorio.rollback()
            transaccion_iniciada = False
            plan.resumen.update(
                {
                    "ok": False,
                    "confirmado": False,
                    "modo": "IMPORTACION_BLOQUEADA",
                }
            )
            plan.resumen.setdefault("errores", []).append(
                {
                    "tipo": "CSV_SIN_REGISTRO_DB",
                    "mensaje": (
                        "Existen productos del CSV sin coincidencia en MySQL. "
                        "Revise el detalle o autorice explícitamente una carga "
                        "parcial con permitir_csv_sin_db=True."
                    ),
                }
            )
            return plan.resumen

        if plan.actualizaciones_usuario:
            repositorio.actualizar_campos_usuario_masivo(
                [
                    (identificador, cambios)
                    for identificador, _, cambios in plan.actualizaciones_usuario
                ],
                usuario_normalizado,
            )
        if plan.cambios_vigencia:
            repositorio.cambiar_activos_masivo(
                [
                    (identificador, activo)
                    for identificador, _, _, activo, _ in plan.cambios_vigencia
                ],
                usuario_normalizado,
            )

        auditorias = 0
        if plan.actualizaciones_usuario:
            auditorias += repositorio.auditar_cambios_masivos(
                operaciones=plan.actualizaciones_usuario,
                usuario=usuario_normalizado,
                accion="USER_UPDATE",
            )
        for activo_objetivo, accion in (
            (False, "DESACTIVATE"),
            (True, "REACTIVATE"),
        ):
            operaciones = [
                (identificador, fila, cambios)
                for identificador, fila, cambios, activo, _
                in plan.cambios_vigencia
                if activo == activo_objetivo
            ]
            if operaciones:
                auditorias += repositorio.auditar_cambios_masivos(
                    operaciones=operaciones,
                    usuario=usuario_normalizado,
                    accion=accion,
                )

        repositorio.commit()
        transaccion_iniciada = False
        plan.resumen.update(
            {
                "confirmado": True,
                "modo": "IMPORTACION",
                "auditorias_generadas": auditorias,
            }
        )
        return plan.resumen
    except Exception as exc:
        if transaccion_iniciada and conexion is not None:
            try:
                conexion.rollback()
            except Exception:
                LOGGER.exception("También falló el rollback de la carga histórica")
        LOGGER.exception("Falló la carga histórica de certificación")
        resumen = plan.resumen if plan is not None else resumen_csv
        resumen.update(
            {
                "ok": False,
                "confirmado": False,
                "modo": "IMPORTACION" if aplicar else "PREVISUALIZACION",
            }
        )
        resumen.setdefault("errores", []).append(
            {"tipo": type(exc).__name__, "mensaje": str(exc)}
        )
        return resumen
    finally:
        if bloqueo_adquirido and repositorio_bloqueo is not None:
            try:
                repositorio_bloqueo.liberar_bloqueo_sincronizacion()
            except Exception:
                LOGGER.exception("No se pudo liberar el bloqueo de la importación")
        if conexion is not None:
            try:
                conexion.close()
            except Exception:
                LOGGER.exception("No se pudo cerrar la conexión de la carga histórica")


def previsualizar_carga_historica(
    ruta_csv: str | Path,
    usuario: str,
    *,
    ruta_config: str | Path | None = None,
) -> dict[str, Any]:
    """Compara CSV y MySQL sin escribir ni bloquear registros."""
    return _ejecutar_carga_historica(
        ruta_csv,
        usuario,
        aplicar=False,
        ruta_config=ruta_config,
    )


def importar_carga_historica(
    ruta_csv: str | Path,
    usuario: str,
    *,
    ruta_config: str | Path | None = None,
    permitir_csv_sin_db: bool = False,
) -> dict[str, Any]:
    """Iguala campos manuales y vigencia en una transacción auditada."""
    return _ejecutar_carga_historica(
        ruta_csv,
        usuario,
        aplicar=True,
        ruta_config=ruta_config,
        permitir_csv_sin_db=permitir_csv_sin_db,
    )
