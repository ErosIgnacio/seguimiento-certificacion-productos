"""Servicio transaccional e independiente de la interfaz gráfica."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Mapping

from .configuracion import crear_conexion
from .constantes import CAMPOS_AUTOMATICOS_ACTUALIZABLES, CAMPOS_CLAVE
from .datos import RepositorioCertificacion
from .usuarios import normalizar_usuario
from .validaciones import preparar_filas_origen, valores_equivalentes


LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


def crear_resumen() -> dict[str, Any]:
    return {
        "origen": 0,
        "insertados": 0,
        "actualizados": 0,
        "sin_cambios": 0,
        "omitidos_clave_incompleta": 0,
        "duplicados_consolidados": 0,
        "duplicados_conflictivos": 0,
        "claves_con_separador": 0,
        "errores": [],
        "confirmado": False,
        "modo": "SINCRONIZACION",
        "estrategia_persistencia": "LOTES",
        "duracion_segundos": 0.0,
        "auditorias_estimadas": 0,
        "auditorias_generadas": 0,
    }


def _calcular_cambios(
    existente: Mapping[str, Any],
    fila_origen: Mapping[str, Any],
) -> dict[str, tuple[Any, Any]]:
    return {
        campo: (existente.get(campo), fila_origen.get(campo))
        for campo in CAMPOS_AUTOMATICOS_ACTUALIZABLES
        if not valores_equivalentes(existente.get(campo), fila_origen.get(campo))
    }


def _validar_clave_inmutable(
    existente: Mapping[str, Any],
    fila_origen: Mapping[str, Any],
) -> None:
    diferentes = [
        campo
        for campo in CAMPOS_CLAVE
        if not valores_equivalentes(existente.get(campo), fila_origen.get(campo))
    ]
    if diferentes:
        raise RuntimeError(
            "Colisión de id_certificacion con componentes inmutables diferentes: "
            + ", ".join(diferentes)
        )


def _sincronizar_con_repositorio(
    repositorio,
    usuario: str,
    *,
    aplicar: bool,
) -> dict[str, Any]:
    """Motor inyectable; permite pruebas sin tocar MySQL productivo."""
    resumen = crear_resumen()
    resumen["modo"] = "SINCRONIZACION" if aplicar else "PREVISUALIZACION"
    usuario_normalizado = normalizar_usuario(usuario)
    transaccion_iniciada = False
    inicio = time.perf_counter()

    try:
        repositorio.iniciar_transaccion()
        transaccion_iniciada = True
        filas_origen = repositorio.obtener_origen()
        resumen["origen"] = len(filas_origen)

        validacion = preparar_filas_origen(filas_origen)
        resumen.update(
            {
                "omitidos_clave_incompleta": validacion.omitidos_clave_incompleta,
                "duplicados_consolidados": validacion.duplicados_consolidados,
                "duplicados_conflictivos": validacion.duplicados_conflictivos,
                "claves_con_separador": validacion.claves_con_separador,
                "errores": validacion.errores,
                "detalle_claves_incompletas": (
                    validacion.detalles_clave_incompleta
                ),
                "detalle_claves_con_separador": (
                    validacion.detalles_claves_con_separador
                ),
                "detalle_duplicados_conflictivos": (
                    validacion.detalles_duplicados_conflictivos
                ),
            }
        )

        if validacion.bloquea_sincronizacion:
            repositorio.rollback()
            return resumen

        obtener_existentes = (
            repositorio.obtener_existentes_para_actualizar
            if aplicar
            else repositorio.obtener_existentes
        )
        existentes = obtener_existentes(
            fila["id_certificacion"] for fila in validacion.filas
        )

        nuevos: list[Mapping[str, Any]] = []
        actualizaciones: list[
            tuple[
                str,
                Mapping[str, Any],
                Mapping[str, tuple[Any, Any]],
            ]
        ] = []
        sin_cambios: list[str] = []

        for fila in validacion.filas:
            identificador = fila["id_certificacion"]
            existente = existentes.get(identificador)

            if existente is None:
                nuevos.append(fila)
                continue

            _validar_clave_inmutable(existente, fila)
            cambios = _calcular_cambios(existente, fila)
            if cambios:
                actualizaciones.append((identificador, fila, cambios))
            else:
                sin_cambios.append(identificador)

        resumen["insertados"] = len(nuevos)
        resumen["actualizados"] = len(actualizaciones)
        resumen["sin_cambios"] = len(sin_cambios)
        resumen["auditorias_estimadas"] = len(nuevos) + sum(
            len(cambios) for _, _, cambios in actualizaciones
        )

        if aplicar:
            repositorio.insertar_productos(nuevos, usuario_normalizado)
            repositorio.actualizar_campos_automaticos_lote(
                [
                    (identificador, cambios)
                    for identificador, _, cambios in actualizaciones
                ]
            )
            repositorio.marcar_sincronizados(sin_cambios)
            repositorio.auditar_creaciones(nuevos, usuario_normalizado)
            repositorio.auditar_cambios_lote(
                actualizaciones,
                usuario_normalizado,
                "SYNC_UPDATE",
            )
            resumen["auditorias_generadas"] = resumen["auditorias_estimadas"]

        if aplicar:
            repositorio.commit()
            resumen["confirmado"] = True
        else:
            # La previsualización no ejecuta INSERT/UPDATE; se cierra su lectura.
            repositorio.rollback()
        return resumen

    except Exception as exc:  # El contrato devuelve el error y garantiza rollback.
        if transaccion_iniciada:
            try:
                repositorio.rollback()
            except Exception:
                LOGGER.exception("También falló el rollback de certificaciones")

        intentos = {
            "insertados": resumen["insertados"],
            "actualizados": resumen["actualizados"],
            "auditorias": resumen["auditorias_generadas"],
        }
        if aplicar and any(intentos.values()):
            resumen["operaciones_revertidas"] = intentos
            resumen["insertados"] = 0
            resumen["actualizados"] = 0
            resumen["auditorias_generadas"] = 0

        resumen["errores"].append(
            {
                "tipo": type(exc).__name__,
                "mensaje": str(exc),
            }
        )
        LOGGER.exception("Falló la sincronización de certificaciones")
        return resumen
    finally:
        resumen["duracion_segundos"] = round(
            time.perf_counter() - inicio,
            3,
        )


def _ejecutar_con_nueva_conexion(
    usuario: str,
    *,
    aplicar: bool,
    ruta_config: str | Path | None = None,
) -> dict[str, Any]:
    conexion = None
    repositorio = None
    bloqueo_adquirido = False
    try:
        conexion = crear_conexion(ruta_config)
        repositorio = RepositorioCertificacion(conexion)
        if aplicar:
            repositorio.adquirir_bloqueo_sincronizacion()
            bloqueo_adquirido = True
        return _sincronizar_con_repositorio(
            repositorio,
            usuario,
            aplicar=aplicar,
        )
    except Exception as exc:
        resumen = crear_resumen()
        resumen["modo"] = "SINCRONIZACION" if aplicar else "PREVISUALIZACION"
        resumen["errores"].append(
            {"tipo": type(exc).__name__, "mensaje": str(exc)}
        )
        LOGGER.exception("No se pudo iniciar la sincronización")
        return resumen
    finally:
        if bloqueo_adquirido and repositorio is not None:
            try:
                repositorio.liberar_bloqueo_sincronizacion()
            except Exception:
                LOGGER.exception("No se pudo liberar el bloqueo de sincronización")
        if conexion is not None:
            try:
                conexion.close()
            except Exception:
                LOGGER.exception("No se pudo cerrar la conexión de certificaciones")


def sincronizar_certificaciones(usuario: str) -> dict:
    """
    Sincroniza los productos sujetos a certificación y devuelve
    el resumen completo del proceso.

    La interfaz futura debe pasar directamente su ``self.usuario``.
    """
    return _ejecutar_con_nueva_conexion(usuario, aplicar=True)


def previsualizar_certificaciones(
    usuario: str,
    *,
    ruta_config: str | Path | None = None,
) -> dict:
    """Calcula el resultado esperado sin escribir tabla ni auditoría."""
    return _ejecutar_con_nueva_conexion(
        usuario,
        aplicar=False,
        ruta_config=ruta_config,
    )
