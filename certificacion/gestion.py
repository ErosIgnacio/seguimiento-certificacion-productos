"""Servicios de consulta y edición manual para la interfaz de certificación."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from .campos import (
    CAMPOS_ENTEROS_USUARIO,
    CAMPOS_FECHA_USUARIO,
    LONGITUDES_CAMPOS_USUARIO,
)
from .configuracion import crear_conexion
from .constantes import (
    CAMPO_CLAVE_EDICION_MASIVA,
    CAMPOS_CATALOGO,
    CAMPOS_USUARIO,
    ESTADO_NO_REQUIERE_INSPECCION,
)
from .datos_productos import RepositorioProductos
from .usuarios import normalizar_usuario
from .validaciones import valores_equivalentes


LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

TAMANO_PAGINA_MAXIMO = 500
LIMITE_AUDITORIA_MAXIMO = 2000
LIMITE_CALIDAD_MAXIMO = 1000


def _error(exc: Exception) -> dict[str, Any]:
    LOGGER.exception("Operación de gestión de certificaciones fallida")
    return {
        "ok": False,
        "errores": [{"tipo": type(exc).__name__, "mensaje": str(exc)}],
    }


def _validar_id(id_certificacion: str) -> str:
    if not isinstance(id_certificacion, str) or not id_certificacion.strip():
        raise ValueError("Debe seleccionar un registro de certificación")
    return id_certificacion.strip()


def _normalizar_filtros_listado(
    filtros: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalizados = dict(filtros or {})
    for nombre, etiqueta in (
        ("eta_desde", "ETA desde"),
        ("eta_hasta", "ETA hasta"),
    ):
        valor = normalizados.get(nombre)
        if valor not in (None, ""):
            normalizados[nombre] = _normalizar_fecha(etiqueta, valor)
    desde = normalizados.get("eta_desde")
    hasta = normalizados.get("eta_hasta")
    if desde and hasta and desde > hasta:
        raise ValueError("ETA desde no puede ser posterior a ETA hasta")
    return normalizados


def _normalizar_fecha(campo: str, valor: Any) -> date | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"{campo} debe usar formato AAAA-MM-DD")


def _normalizar_entero(campo: str, valor: Any) -> int | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{campo} debe ser un número entero")
    if isinstance(valor, float):
        if math.isnan(valor) or not valor.is_integer():
            raise ValueError(f"{campo} debe ser un número entero")
        entero = int(valor)
    elif isinstance(valor, Decimal):
        if valor != valor.to_integral_value():
            raise ValueError(f"{campo} debe ser un número entero")
        entero = int(valor)
    else:
        try:
            entero = int(str(valor).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{campo} debe ser un número entero") from exc
    if entero < 0:
        raise ValueError(f"{campo} no puede ser negativo")
    if entero > 4_294_967_295:
        raise ValueError(f"{campo} excede el máximo permitido")
    return entero


def normalizar_campos_usuario(
    datos: Mapping[str, Any],
) -> dict[str, Any]:
    """Valida una edición parcial y convierte vacíos a NULL."""
    no_permitidos = set(datos) - set(CAMPOS_USUARIO)
    if no_permitidos:
        raise ValueError(
            "Se intentó editar campos no gestionados por el usuario: "
            + ", ".join(sorted(no_permitidos))
        )

    normalizados: dict[str, Any] = {}
    for campo, valor in datos.items():
        if campo in CAMPOS_FECHA_USUARIO:
            normalizados[campo] = _normalizar_fecha(campo, valor)
            continue
        if campo in CAMPOS_ENTEROS_USUARIO:
            normalizados[campo] = _normalizar_entero(campo, valor)
            continue

        if valor is None:
            normalizados[campo] = None
            continue
        texto = str(valor).strip()
        if not texto:
            normalizados[campo] = None
            continue
        longitud_maxima = LONGITUDES_CAMPOS_USUARIO.get(campo)
        longitud_real = (
            len(texto.encode("utf-8")) if campo == "comentarios" else len(texto)
        )
        unidad = "bytes UTF-8" if campo == "comentarios" else "caracteres"
        if longitud_maxima and longitud_real > longitud_maxima:
            raise ValueError(
                f"{campo} usa {longitud_real} {unidad} y admite {longitud_maxima}"
            )
        normalizados[campo] = texto

    return normalizados


def _calcular_cambios_usuario(
    existente: Mapping[str, Any],
    normalizados: Mapping[str, Any],
) -> dict[str, tuple[Any, Any]]:
    return {
        campo: (existente.get(campo), valor)
        for campo, valor in normalizados.items()
        if not valores_equivalentes(existente.get(campo), valor)
    }


def _es_estado_no_requiere_inspeccion(valor: Any) -> bool:
    return (
        valor is not None
        and str(valor).strip().casefold()
        == ESTADO_NO_REQUIERE_INSPECCION.casefold()
    )


def _validar_valores_catalogados(
    normalizados: Mapping[str, Any],
    catalogos: Mapping[str, list[str]],
) -> None:
    for campo in CAMPOS_CATALOGO:
        valor = normalizados.get(campo)
        valores_permitidos = catalogos.get(campo, [])
        permitidos_normalizados = {
            str(item).strip().casefold() for item in valores_permitidos
        }
        if (
            valor is not None
            and valores_permitidos
            and str(valor).strip().casefold() not in permitidos_normalizados
        ):
            raise ValueError(
                f"{campo} debe seleccionarse desde el catálogo activo"
            )


def _aplicar_presentacion_catalogos(
    normalizados: dict[str, Any],
    catalogos: Mapping[str, list[str]],
) -> None:
    """Reemplaza variantes de mayúsculas por la escritura oficial activa."""
    for campo in CAMPOS_CATALOGO:
        valor = normalizados.get(campo)
        if valor is None:
            continue
        canonicos = {
            str(item).strip().casefold(): item
            for item in catalogos.get(campo, [])
        }
        canonico = canonicos.get(str(valor).strip().casefold())
        if canonico is not None:
            normalizados[campo] = canonico


def _actualizar_con_repositorio(
    repositorio,
    id_certificacion: str,
    datos: Mapping[str, Any],
    usuario: str,
    catalogos_activos: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    identificador = _validar_id(id_certificacion)
    usuario_normalizado = normalizar_usuario(usuario)
    normalizados = normalizar_campos_usuario(datos)
    if catalogos_activos is not None:
        _aplicar_presentacion_catalogos(normalizados, catalogos_activos)
    transaccion_iniciada = False
    try:
        repositorio.iniciar_transaccion()
        transaccion_iniciada = True
        existente = repositorio.obtener_para_actualizar(identificador)
        if existente is None:
            raise LookupError(f"No existe la certificación {identificador}")

        cambios = _calcular_cambios_usuario(existente, normalizados)
        estado_resultante = normalizados.get(
            "estado_certificacion", existente.get("estado_certificacion")
        )
        no_requiere_inspeccion = _es_estado_no_requiere_inspeccion(
            estado_resultante
        )
        debe_desactivar = (
            no_requiere_inspeccion and bool(existente["activo"])
        )
        debe_reactivar = (
            bool(cambios)
            and not bool(existente["activo"])
            and not no_requiere_inspeccion
        )
        if not cambios and not debe_desactivar and not debe_reactivar:
            repositorio.rollback()
            return {
                "ok": True,
                "id_certificacion": identificador,
                "actualizados": 0,
                "campos_modificados": [],
                "activo": bool(existente["activo"]),
                "reactivado": False,
                "mensaje": "No existen cambios para guardar",
            }
        if catalogos_activos is not None:
            _validar_valores_catalogados(
                {campo: nuevo for campo, (_anterior, nuevo) in cambios.items()},
                catalogos_activos,
            )

        if cambios:
            repositorio.actualizar_campos_usuario(
                identificador, cambios, usuario_normalizado
            )
            repositorio.auditar_cambios(
                id_certificacion=identificador,
                fila_clave=existente,
                usuario=usuario_normalizado,
                accion="USER_UPDATE",
                cambios=cambios,
            )
        if debe_desactivar or debe_reactivar:
            activo_objetivo = debe_reactivar
            cambio_activo = {
                "activo": (
                    1 if existente["activo"] else 0,
                    1 if activo_objetivo else 0,
                )
            }
            repositorio.cambiar_activo(
                identificador, activo_objetivo, usuario_normalizado
            )
            repositorio.auditar_cambios(
                id_certificacion=identificador,
                fila_clave=existente,
                usuario=usuario_normalizado,
                accion="REACTIVATE" if debe_reactivar else "DESACTIVATE",
                cambios=cambio_activo,
            )
        repositorio.commit()
        campos_modificados = list(cambios)
        if debe_desactivar or debe_reactivar:
            campos_modificados.append("activo")
        activo_resultante = (
            True
            if debe_reactivar
            else False
            if debe_desactivar
            else bool(existente["activo"])
        )
        return {
            "ok": True,
            "id_certificacion": identificador,
            "actualizados": 1,
            "campos_modificados": campos_modificados,
            "activo": activo_resultante,
            "reactivado": debe_reactivar,
            "mensaje": (
                "Cambios guardados; el registro ahora es certificable"
                if debe_reactivar
                else "Cambios guardados correctamente"
            ),
        }
    except Exception:
        if transaccion_iniciada:
            repositorio.rollback()
        raise


def _clave_masiva_de_registro(registro: Mapping[str, Any]) -> str:
    clave = registro.get(CAMPO_CLAVE_EDICION_MASIVA)
    if clave is None or not str(clave).strip():
        raise RuntimeError(
            "El registro no tiene llave Nave-OC-SKU disponible. "
            "Aplique la migración 006 y verifique que Nave sea válida."
        )
    return str(clave)


def _verificar_soporte_edicion_masiva(repositorio) -> None:
    if not repositorio.edicion_masiva_disponible():
        raise RuntimeError(
            "La edición masiva requiere aplicar la migración "
            "006_agregar_clave_edicion_masiva.sql"
        )


def _obtener_contexto_masivo_con_repositorio(
    repositorio,
    id_certificacion: str,
) -> dict[str, Any]:
    identificador = _validar_id(id_certificacion)
    _verificar_soporte_edicion_masiva(repositorio)
    registro = repositorio.obtener_con_clave_masiva(identificador)
    if registro is None:
        raise LookupError(f"No existe la certificación {identificador}")
    clave = _clave_masiva_de_registro(registro)
    resumen = repositorio.obtener_resumen_grupo_masivo(clave)
    if resumen["total"] < 1:
        raise RuntimeError("No se encontró el grupo Nave-OC-SKU seleccionado")
    return {
        "ok": True,
        "registro": registro,
        "grupo": {
            "clave_edicion_masiva": clave,
            "nave": registro["nave"],
            "oc": registro["oc"],
            "sku": registro["sku"],
            **resumen,
        },
        "errores": [],
    }


def _actualizar_masivo_con_repositorio(
    repositorio,
    id_certificacion: str,
    datos: Mapping[str, Any],
    usuario: str,
    catalogos_activos: Mapping[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Aplica una edición parcial a todo el grupo Nave-OC-SKU."""
    identificador = _validar_id(id_certificacion)
    usuario_normalizado = normalizar_usuario(usuario)
    normalizados = normalizar_campos_usuario(datos)
    if not normalizados:
        raise ValueError("Seleccione al menos un campo para la edición masiva")
    if catalogos_activos is not None:
        _aplicar_presentacion_catalogos(normalizados, catalogos_activos)
    _verificar_soporte_edicion_masiva(repositorio)

    transaccion_iniciada = False
    try:
        repositorio.iniciar_transaccion()
        transaccion_iniciada = True

        referencia = repositorio.obtener_con_clave_masiva(identificador)
        if referencia is None:
            raise LookupError(f"No existe la certificación {identificador}")
        clave = _clave_masiva_de_registro(referencia)
        registros = repositorio.obtener_grupo_masivo_para_actualizar(clave)
        if not any(
            fila["id_certificacion"] == identificador for fila in registros
        ):
            raise RuntimeError(
                "El grupo Nave-OC-SKU cambió mientras se abría la edición; "
                "recargue los datos e inténtelo nuevamente"
            )

        operaciones_auditoria = []
        operaciones_actualizacion = []
        operaciones_vigencia_auditoria = {
            "DESACTIVATE": [],
            "REACTIVATE": [],
        }
        operaciones_vigencia = []
        for registro in registros:
            cambios = _calcular_cambios_usuario(registro, normalizados)
            if cambios:
                operaciones_auditoria.append(
                    (registro["id_certificacion"], registro, cambios)
                )
                operaciones_actualizacion.append(
                    (registro["id_certificacion"], cambios)
                )
            estado_resultante = normalizados.get(
                "estado_certificacion", registro.get("estado_certificacion")
            )
            no_requiere_inspeccion = _es_estado_no_requiere_inspeccion(
                estado_resultante
            )
            activo_anterior = bool(registro["activo"])
            activo_objetivo = activo_anterior
            if no_requiere_inspeccion:
                activo_objetivo = False
            elif cambios and not activo_anterior:
                activo_objetivo = True
            if activo_objetivo != activo_anterior:
                cambio_activo = {
                    "activo": (
                        1 if activo_anterior else 0,
                        1 if activo_objetivo else 0,
                    )
                }
                accion = "REACTIVATE" if activo_objetivo else "DESACTIVATE"
                operaciones_vigencia_auditoria[accion].append(
                    (registro["id_certificacion"], registro, cambio_activo)
                )
                operaciones_vigencia.append(
                    (registro["id_certificacion"], activo_objetivo)
                )

        if not operaciones_actualizacion and not operaciones_vigencia:
            repositorio.rollback()
            return {
                "ok": True,
                "id_certificacion": identificador,
                "registros_grupo": len(registros),
                "actualizados": 0,
                "sin_cambios": len(registros),
                "auditorias_generadas": 0,
                "reactivados": 0,
                "desactivados": 0,
                "campos_aplicados": list(normalizados),
                "mensaje": "Todos los registros del grupo ya tenían esos valores",
            }

        if catalogos_activos is not None:
            _validar_valores_catalogados(normalizados, catalogos_activos)

        if operaciones_actualizacion:
            repositorio.actualizar_campos_usuario_masivo(
                operaciones_actualizacion,
                usuario_normalizado,
            )
        if operaciones_vigencia:
            repositorio.cambiar_activos_masivo(
                operaciones_vigencia,
                usuario_normalizado,
            )
        auditorias_generadas = 0
        if operaciones_auditoria:
            auditorias_generadas += repositorio.auditar_cambios_masivos(
                operaciones=operaciones_auditoria,
                usuario=usuario_normalizado,
                accion="USER_UPDATE",
            )
        for accion, operaciones in operaciones_vigencia_auditoria.items():
            if operaciones:
                auditorias_generadas += repositorio.auditar_cambios_masivos(
                    operaciones=operaciones,
                    usuario=usuario_normalizado,
                    accion=accion,
                )
        ids_actualizados = {
            identificador for identificador, _ in operaciones_actualizacion
        } | {identificador for identificador, _ in operaciones_vigencia}
        actualizados = len(ids_actualizados)
        repositorio.commit()
        return {
            "ok": True,
            "id_certificacion": identificador,
            "registros_grupo": len(registros),
            "actualizados": actualizados,
            "sin_cambios": len(registros) - actualizados,
            "auditorias_generadas": auditorias_generadas,
            "reactivados": len(
                operaciones_vigencia_auditoria["REACTIVATE"]
            ),
            "desactivados": len(
                operaciones_vigencia_auditoria["DESACTIVATE"]
            ),
            "campos_aplicados": list(normalizados),
            "mensaje": (
                f"Edición masiva aplicada a {actualizados} "
                f"registro{'s' if actualizados != 1 else ''}"
            ),
        }
    except Exception:
        if transaccion_iniciada:
            repositorio.rollback()
        raise


def _cambiar_activo_con_repositorio(
    repositorio,
    id_certificacion: str,
    activo: bool,
    usuario: str,
) -> dict[str, Any]:
    identificador = _validar_id(id_certificacion)
    usuario_normalizado = normalizar_usuario(usuario)
    if not isinstance(activo, bool):
        raise ValueError("El estado activo debe ser verdadero o falso")
    objetivo = activo
    transaccion_iniciada = False
    try:
        repositorio.iniciar_transaccion()
        transaccion_iniciada = True
        existente = repositorio.obtener_para_actualizar(identificador)
        if existente is None:
            raise LookupError(f"No existe la certificación {identificador}")
        anterior = bool(existente["activo"])
        if anterior == objetivo:
            repositorio.rollback()
            return {
                "ok": True,
                "id_certificacion": identificador,
                "actualizados": 0,
                "activo": objetivo,
                "mensaje": "El registro ya tenía el estado solicitado",
            }

        accion = "REACTIVATE" if objetivo else "DESACTIVATE"
        cambios = {"activo": (1 if anterior else 0, 1 if objetivo else 0)}
        repositorio.cambiar_activo(
            identificador, objetivo, usuario_normalizado
        )
        repositorio.auditar_cambios(
            id_certificacion=identificador,
            fila_clave=existente,
            usuario=usuario_normalizado,
            accion=accion,
            cambios=cambios,
        )
        repositorio.commit()
        return {
            "ok": True,
            "id_certificacion": identificador,
            "actualizados": 1,
            "activo": objetivo,
            "mensaje": "Registro reactivado" if objetivo else "Registro desactivado",
        }
    except Exception:
        if transaccion_iniciada:
            repositorio.rollback()
        raise


def listar_certificaciones(
    *,
    filtros: Mapping[str, Any] | None = None,
    pagina: int = 1,
    tamano_pagina: int = 100,
) -> dict[str, Any]:
    conexion = None
    try:
        conexion = crear_conexion()
        return _listar_con_repositorio(
            RepositorioProductos(conexion),
            filtros=filtros,
            pagina=pagina,
            tamano_pagina=tamano_pagina,
        )
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def _listar_con_repositorio(
    repositorio,
    *,
    filtros: Mapping[str, Any] | None,
    pagina: int,
    tamano_pagina: int,
) -> dict[str, Any]:
    pagina = max(1, int(pagina))
    tamano_pagina = max(1, min(TAMANO_PAGINA_MAXIMO, int(tamano_pagina)))
    filtros = _normalizar_filtros_listado(filtros)
    listado = repositorio.listar(
        filtros=filtros,
        pagina=pagina,
        tamano_pagina=tamano_pagina,
    )
    metricas = repositorio.obtener_metricas()
    paginas = max(1, math.ceil(listado["total"] / tamano_pagina))
    if pagina > paginas:
        pagina = paginas
        listado = repositorio.listar(
            filtros=filtros,
            pagina=pagina,
            tamano_pagina=tamano_pagina,
        )
    return {
        "ok": True,
        "filas": listado["filas"],
        "total_filtrado": listado["total"],
        "metricas": metricas,
        "pagina": pagina,
        "paginas": paginas,
        "tamano_pagina": tamano_pagina,
        "errores": [],
    }


def _cargar_inicial_con_repositorio(
    repositorio,
    *,
    filtros: Mapping[str, Any] | None,
    pagina: int,
    tamano_pagina: int,
) -> dict[str, Any]:
    listado = _listar_con_repositorio(
        repositorio,
        filtros=filtros,
        pagina=pagina,
        tamano_pagina=tamano_pagina,
    )
    activos = repositorio.obtener_catalogos_activos()
    catalogos = repositorio.obtener_catalogos(activos)
    return {
        "ok": True,
        "listado": listado,
        "catalogos": {
            "ok": True,
            "catalogos": catalogos,
            "catalogos_activos": activos,
            "errores": [],
        },
        "errores": [],
    }


def cargar_datos_iniciales(
    *,
    filtros: Mapping[str, Any] | None = None,
    pagina: int = 1,
    tamano_pagina: int = 100,
) -> dict[str, Any]:
    """Carga listado, métricas y catálogos usando una sola conexión."""
    conexion = None
    try:
        conexion = crear_conexion()
        return _cargar_inicial_con_repositorio(
            RepositorioProductos(conexion),
            filtros=filtros,
            pagina=pagina,
            tamano_pagina=tamano_pagina,
        )
    except Exception as exc:
        error = _error(exc)
        return {
            "ok": False,
            "listado": error,
            "catalogos": error,
            "errores": error["errores"],
        }
    finally:
        if conexion is not None:
            conexion.close()


def obtener_catalogos_certificacion() -> dict[str, Any]:
    conexion = None
    try:
        conexion = crear_conexion()
        repositorio = RepositorioProductos(conexion)
        activos = repositorio.obtener_catalogos_activos()
        catalogos = repositorio.obtener_catalogos(activos)
        return {
            "ok": True,
            "catalogos": catalogos,
            "catalogos_activos": activos,
            "errores": [],
        }
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def consultar_calidad_certificaciones(
    *, limite: int = 200
) -> dict[str, Any]:
    conexion = None
    try:
        limite = max(1, min(LIMITE_CALIDAD_MAXIMO, int(limite)))
        conexion = crear_conexion()
        calidad = RepositorioProductos(conexion).obtener_calidad(limite=limite)
        return {"ok": True, **calidad, "errores": []}
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def obtener_certificacion(id_certificacion: str) -> dict[str, Any]:
    conexion = None
    try:
        identificador = _validar_id(id_certificacion)
        conexion = crear_conexion()
        registro = RepositorioProductos(conexion).obtener(identificador)
        if registro is None:
            raise LookupError(f"No existe la certificación {identificador}")
        return {"ok": True, "registro": registro, "errores": []}
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def obtener_contexto_edicion_masiva(
    id_certificacion: str,
) -> dict[str, Any]:
    conexion = None
    try:
        conexion = crear_conexion()
        return _obtener_contexto_masivo_con_repositorio(
            RepositorioProductos(conexion), id_certificacion
        )
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def actualizar_certificacion(
    id_certificacion: str,
    datos: Mapping[str, Any],
    usuario: str,
) -> dict[str, Any]:
    conexion = None
    try:
        conexion = crear_conexion()
        repositorio = RepositorioProductos(conexion)
        return _actualizar_con_repositorio(
            repositorio,
            id_certificacion,
            datos,
            usuario,
            catalogos_activos=repositorio.obtener_catalogos_activos(),
        )
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def actualizar_certificaciones_masivo(
    id_certificacion: str,
    datos: Mapping[str, Any],
    usuario: str,
) -> dict[str, Any]:
    conexion = None
    try:
        conexion = crear_conexion()
        repositorio = RepositorioProductos(conexion)
        return _actualizar_masivo_con_repositorio(
            repositorio,
            id_certificacion,
            datos,
            usuario,
            catalogos_activos=repositorio.obtener_catalogos_activos(),
        )
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def cambiar_estado_certificacion(
    id_certificacion: str,
    activo: bool,
    usuario: str,
) -> dict[str, Any]:
    conexion = None
    try:
        conexion = crear_conexion()
        return _cambiar_activo_con_repositorio(
            RepositorioProductos(conexion), id_certificacion, activo, usuario
        )
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()


def consultar_auditoria_certificacion(
    id_certificacion: str,
    *,
    limite: int = 500,
) -> dict[str, Any]:
    conexion = None
    try:
        identificador = _validar_id(id_certificacion)
        limite = max(1, min(LIMITE_AUDITORIA_MAXIMO, int(limite)))
        conexion = crear_conexion()
        filas = RepositorioProductos(conexion).listar_auditoria(
            identificador, limite=limite
        )
        return {"ok": True, "filas": filas, "errores": []}
    except Exception as exc:
        return _error(exc)
    finally:
        if conexion is not None:
            conexion.close()
