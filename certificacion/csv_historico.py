"""Lectura y validación por streaming del histórico Certificacion.csv."""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .constantes import CAMPOS_USUARIO
from .gestion import normalizar_campos_usuario
from .validaciones import (
    ClaveIncompletaError,
    _clave_colacion_mysql,
    construir_id_certificacion,
    valores_equivalentes,
)


ENCABEZADOS_CLAVE = {
    "container": "n_contenedor",
    "oc": "oc",
    "op": "gd",
    "sku": "sku",
}

ENCABEZADOS_USUARIO = {
    "codigo": "codigo",
    "pegar etiquetas": "pegar_etiquetas",
    "numero de qr": "numero_qr",
    "estado": "estado_certificacion",
    "fecha inspeccion": "fecha_inspeccion",
    "fecha de certificacion": "fecha_certificacion",
    "nro de inspeccion": "nro_inspeccion",
    "laboratorio": "laboratorio",
    "nro de certificado": "nro_certificado",
    "nro de informe inspeccion": "nro_informe_inspeccion",
    "retiro de muestras": "muestras_retiradas",
    "recep de muestras": "muestras_recepcionadas",
    "numero de guia de despacho": "numero_guia_despacho",
    "numero de guia er": "numero_guia_er",
    "prioridad": "prioridad",
    "comentarios": "comentarios",
}

LIMITE_DETALLES = 100


@dataclass
class ResultadoCsvHistorico:
    ruta: str
    sha256: str
    encoding: str
    delimitador: str
    encabezados: list[str]
    registros: dict[str, dict[str, Any]] = field(default_factory=dict)
    filas_archivo: int = 0
    filas_vacias: int = 0
    filas_con_datos: int = 0
    filas_invalidas: int = 0
    omitidos_clave_incompleta: int = 0
    duplicados_consolidados: int = 0
    duplicados_conflictivos: int = 0
    errores: list[dict[str, Any]] = field(default_factory=list)
    advertencias: list[dict[str, Any]] = field(default_factory=list)
    detalles_omitidos: int = 0

    @property
    def bloquea_importacion(self) -> bool:
        return bool(self.filas_invalidas or self.duplicados_conflictivos)

    def resumen(self) -> dict[str, Any]:
        return {
            "ruta": self.ruta,
            "sha256": self.sha256,
            "encoding": self.encoding,
            "delimitador": self.delimitador,
            "encabezados": self.encabezados,
            "filas_archivo": self.filas_archivo,
            "filas_vacias": self.filas_vacias,
            "filas_con_datos": self.filas_con_datos,
            "registros_validos": len(self.registros),
            "filas_invalidas": self.filas_invalidas,
            "omitidos_clave_incompleta": self.omitidos_clave_incompleta,
            "duplicados_consolidados": self.duplicados_consolidados,
            "duplicados_conflictivos": self.duplicados_conflictivos,
            "errores": self.errores,
            "advertencias": self.advertencias,
            "detalles_omitidos": self.detalles_omitidos,
            "bloquea_importacion": self.bloquea_importacion,
        }


def normalizar_encabezado(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "").strip().casefold())
    sin_tildes = "".join(
        caracter for caracter in texto if not unicodedata.combining(caracter)
    )
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes).strip()


def _detectar_codificacion(ruta: Path) -> str:
    with ruta.open("rb") as archivo:
        muestra = archivo.read(65536)
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            muestra.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("El CSV no utiliza UTF-8 ni Windows-1252")


def _detectar_delimitador(ruta: Path, encoding: str) -> str:
    with ruta.open("r", encoding=encoding, newline="") as archivo:
        encabezado = archivo.readline()
    if encabezado.count(";") > encabezado.count(","):
        return ";"
    try:
        return csv.Sniffer().sniff(encabezado, delimiters=";,\t").delimiter
    except csv.Error as exc:
        raise ValueError("No se pudo detectar el delimitador del CSV") from exc


def _agregar_error(
    resultado: ResultadoCsvHistorico,
    *,
    tipo: str,
    mensaje: str,
    fila_csv: int | None = None,
    id_certificacion: str | None = None,
) -> None:
    if len(resultado.errores) < LIMITE_DETALLES:
        detalle: dict[str, Any] = {"tipo": tipo, "mensaje": mensaje}
        if fila_csv is not None:
            detalle["fila_csv"] = fila_csv
        if id_certificacion is not None:
            detalle["id_certificacion"] = id_certificacion
        resultado.errores.append(detalle)
    else:
        resultado.detalles_omitidos += 1


def _agregar_advertencia(
    resultado: ResultadoCsvHistorico,
    *,
    tipo: str,
    mensaje: str,
    fila_csv: int,
) -> None:
    if len(resultado.advertencias) < LIMITE_DETALLES:
        resultado.advertencias.append(
            {"tipo": tipo, "mensaje": mensaje, "fila_csv": fila_csv}
        )
    else:
        resultado.detalles_omitidos += 1


def _filas_usuario_equivalentes(
    anterior: dict[str, Any], nuevo: dict[str, Any]
) -> bool:
    return all(
        valores_equivalentes(anterior.get(campo), nuevo.get(campo))
        for campo in CAMPOS_USUARIO
    )


def leer_csv_historico(ruta_csv: str | Path) -> ResultadoCsvHistorico:
    """Valida el archivo completo sin modificarlo ni consultar la base."""
    import hashlib

    ruta = Path(ruta_csv).expanduser().resolve()
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el archivo CSV: {ruta}")

    encoding = _detectar_codificacion(ruta)
    delimitador = _detectar_delimitador(ruta, encoding)
    sha256 = hashlib.sha256()
    with ruta.open("rb") as archivo_binario:
        for bloque in iter(lambda: archivo_binario.read(1024 * 1024), b""):
            sha256.update(bloque)

    with ruta.open("r", encoding=encoding, newline="") as archivo:
        lector = csv.DictReader(archivo, delimiter=delimitador)
        encabezados = list(lector.fieldnames or [])
        normalizados = [normalizar_encabezado(nombre) for nombre in encabezados]
        if len(normalizados) != len(set(normalizados)):
            raise ValueError("El CSV contiene encabezados duplicados al normalizar")

        por_normalizado = dict(zip(normalizados, encabezados))
        requeridos = {*ENCABEZADOS_CLAVE, *ENCABEZADOS_USUARIO}
        faltantes = sorted(requeridos - set(por_normalizado))
        if faltantes:
            raise ValueError(
                "Faltan columnas requeridas en el CSV: " + ", ".join(faltantes)
            )

        resultado = ResultadoCsvHistorico(
            ruta=str(ruta),
            sha256=sha256.hexdigest().upper(),
            encoding=encoding,
            delimitador=delimitador,
            encabezados=encabezados,
        )
        ids_por_colacion: dict[str, str] = {}

        for numero_fila, fila in enumerate(lector, start=2):
            resultado.filas_archivo += 1
            valores = [valor for clave, valor in fila.items() if clave is not None]
            if not any(str(valor or "").strip() for valor in valores):
                resultado.filas_vacias += 1
                continue
            resultado.filas_con_datos += 1

            try:
                componentes = {
                    campo: fila[por_normalizado[encabezado]]
                    for encabezado, campo in ENCABEZADOS_CLAVE.items()
                }
                identificador = construir_id_certificacion(
                    componentes["n_contenedor"],
                    componentes["oc"],
                    componentes["gd"],
                    componentes["sku"],
                )
                datos_usuario = normalizar_campos_usuario(
                    {
                        campo: fila[por_normalizado[encabezado]]
                        for encabezado, campo in ENCABEZADOS_USUARIO.items()
                    }
                )
            except ClaveIncompletaError as exc:
                resultado.omitidos_clave_incompleta += 1
                _agregar_advertencia(
                    resultado,
                    tipo=type(exc).__name__,
                    mensaje=str(exc),
                    fila_csv=numero_fila,
                )
                continue
            except Exception as exc:
                resultado.filas_invalidas += 1
                _agregar_error(
                    resultado,
                    tipo=type(exc).__name__,
                    mensaje=str(exc),
                    fila_csv=numero_fila,
                )
                continue

            clave_colacion = _clave_colacion_mysql(identificador)
            id_colision = ids_por_colacion.get(clave_colacion)
            if id_colision is not None and id_colision != identificador:
                resultado.duplicados_conflictivos += 1
                _agregar_error(
                    resultado,
                    tipo="COLISION_COLLATION",
                    mensaje=f"Colisiona con {id_colision} bajo la collation MySQL",
                    fila_csv=numero_fila,
                    id_certificacion=identificador,
                )
                continue
            ids_por_colacion[clave_colacion] = identificador

            anterior = resultado.registros.get(identificador)
            if anterior is None:
                resultado.registros[identificador] = datos_usuario
            elif _filas_usuario_equivalentes(anterior, datos_usuario):
                resultado.duplicados_consolidados += 1
            else:
                resultado.duplicados_conflictivos += 1
                _agregar_error(
                    resultado,
                    tipo="DUPLICADO_CONFLICTIVO",
                    mensaje="La misma clave contiene campos de usuario diferentes",
                    fila_csv=numero_fila,
                    id_certificacion=identificador,
                )

    return resultado
