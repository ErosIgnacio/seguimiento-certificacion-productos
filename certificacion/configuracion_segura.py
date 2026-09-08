"""Protección local de la configuración mediante Windows DPAPI."""

from __future__ import annotations

import ctypes
import json
import os
from collections.abc import Mapping
from ctypes import wintypes
from pathlib import Path
from typing import Any


PROVEEDOR_APLICACION = "Cencosud"
NOMBRE_APLICACION = "CertificacionCarga"
VARIABLE_DIRECTORIO_DATOS = "CERTIFICACION_DATA_DIR"

_MAGIC = b"CERTCFG1\0"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class ErrorConfiguracionProtegida(RuntimeError):
    """Error al cifrar o leer la configuración protegida."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def directorio_datos_locales() -> Path:
    """Directorio escribible y privado del usuario actual."""
    personalizado = os.environ.get(VARIABLE_DIRECTORIO_DATOS, "").strip()
    if personalizado:
        return Path(personalizado).expanduser()
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    return base / PROVEEDOR_APLICACION / NOMBRE_APLICACION


def ruta_configuracion_protegida() -> Path:
    return directorio_datos_locales() / "config.dat"


def ruta_log_aplicacion() -> Path:
    return directorio_datos_locales() / "logs" / "certificacion_carga.log"


def _blob(datos: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(datos)
    puntero = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(datos), puntero), buffer


def _apis_windows() -> tuple[Any, Any]:
    if os.name != "nt":
        raise ErrorConfiguracionProtegida(
            "La protección DPAPI sólo está disponible en Windows."
        )

    crypt32 = ctypes.WinDLL("crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _proteger(contenido: bytes) -> bytes:
    crypt32, kernel32 = _apis_windows()
    origen, buffer_origen = _blob(contenido)
    destino = _DataBlob()
    if not crypt32.CryptProtectData(
        ctypes.byref(origen),
        "CertificacionCarga",
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(destino),
    ):
        codigo = ctypes.get_last_error()
        raise ErrorConfiguracionProtegida(
            f"Windows no pudo proteger la configuración ({codigo})."
        )
    del buffer_origen
    try:
        return ctypes.string_at(destino.pbData, destino.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(destino.pbData, ctypes.c_void_p))


def _desproteger(contenido: bytes) -> bytes:
    crypt32, kernel32 = _apis_windows()
    origen, buffer_origen = _blob(contenido)
    destino = _DataBlob()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(origen),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(destino),
    ):
        codigo = ctypes.get_last_error()
        raise ErrorConfiguracionProtegida(
            f"Windows no pudo abrir la configuración protegida ({codigo})."
        )
    del buffer_origen
    try:
        return ctypes.string_at(destino.pbData, destino.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(destino.pbData, ctypes.c_void_p))


def proteger_configuracion(
    configuracion: Mapping[str, Any], destino: Path
) -> None:
    """Serializa y cifra la configuración para la cuenta de Windows actual."""
    try:
        contenido = json.dumps(
            dict(configuracion), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ErrorConfiguracionProtegida(
            "La configuración no contiene JSON válido."
        ) from exc

    cifrado = _MAGIC + _proteger(contenido)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_bytes(cifrado)
    temporal.replace(destino)


def proteger_archivo_configuracion(origen: Path, destino: Path) -> None:
    """Valida un JSON y lo guarda cifrado sin copiar el texto plano."""
    try:
        configuracion = json.loads(origen.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ErrorConfiguracionProtegida(
            f"No existe el archivo de configuración: {origen}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorConfiguracionProtegida(
            f"No se pudo leer un JSON válido desde {origen}."
        ) from exc
    if not isinstance(configuracion, dict):
        raise ErrorConfiguracionProtegida(
            "La configuración debe ser un objeto JSON."
        )
    proteger_configuracion(configuracion, destino)


def leer_configuracion_protegida(origen: Path) -> dict[str, Any]:
    """Descifra y deserializa una configuración vinculada al usuario actual."""
    try:
        contenido = origen.read_bytes()
    except OSError as exc:
        raise ErrorConfiguracionProtegida(
            f"No se pudo leer la configuración protegida: {origen}"
        ) from exc
    if not contenido.startswith(_MAGIC):
        raise ErrorConfiguracionProtegida(
            "El archivo de configuración protegida no es válido."
        )
    try:
        configuracion = json.loads(
            _desproteger(contenido[len(_MAGIC) :]).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErrorConfiguracionProtegida(
            "La configuración protegida está dañada."
        ) from exc
    if not isinstance(configuracion, dict):
        raise ErrorConfiguracionProtegida(
            "La configuración protegida debe contener un objeto JSON."
        )
    return configuracion
