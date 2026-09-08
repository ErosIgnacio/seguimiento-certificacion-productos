"""Carga la configuración existente y crea conexiones PyMySQL reutilizables."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pymysql

from .configuracion_segura import (
    ErrorConfiguracionProtegida,
    leer_configuracion_protegida,
    ruta_configuracion_protegida,
)


VARIABLE_RUTA_CONFIG = "LOG_IMPORTADO_CONFIG"


class ErrorConfiguracion(RuntimeError):
    """Configuración ausente o inválida."""


def buscar_ruta_config(ruta_config: str | Path | None = None) -> Path:
    """Localiza el config.json ya utilizado por Log_Importado."""
    candidatos: list[Path] = []

    if ruta_config:
        candidatos.append(Path(ruta_config))

    ruta_entorno = os.environ.get(VARIABLE_RUTA_CONFIG)
    if ruta_entorno:
        candidatos.append(Path(ruta_entorno))

    # En PyInstaller permite mantener un config.json editable junto al EXE.
    if getattr(sys, "frozen", False):
        candidatos.append(Path(sys.executable).resolve().parent / "config.json")

    raiz_proyecto = Path(__file__).resolve().parent.parent
    candidatos.extend(
        (
            raiz_proyecto / "config.json",
            raiz_proyecto.parent / "Log_Imp" / "config.json",
            Path.cwd() / "config.json",
        )
    )

    for candidato in candidatos:
        ruta = candidato.expanduser().resolve()
        if ruta.is_file():
            return ruta

    buscadas = ", ".join(str(path) for path in candidatos)
    raise ErrorConfiguracion(
        "No se encontró el config.json existente de Log_Importado. "
        f"Rutas revisadas: {buscadas}. También puede definir "
        f"{VARIABLE_RUTA_CONFIG}."
    )


def cargar_configuracion(
    ruta_config: str | Path | None = None,
) -> dict[str, Any]:
    """Lee las variables existentes sin incorporar credenciales al código."""
    usar_protegida = (
        bool(getattr(sys, "frozen", False))
        and ruta_config is None
        and not os.environ.get(VARIABLE_RUTA_CONFIG)
        and ruta_configuracion_protegida().is_file()
    )
    if usar_protegida:
        ruta = ruta_configuracion_protegida()
        try:
            configuracion = leer_configuracion_protegida(ruta)
        except ErrorConfiguracionProtegida as exc:
            raise ErrorConfiguracion(
                "No se pudo abrir la configuración protegida. Reinstale la "
                f"aplicación o contacte a soporte. Detalle: {exc}"
            ) from exc
    else:
        ruta = buscar_ruta_config(ruta_config)
        try:
            configuracion = json.loads(ruta.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ErrorConfiguracion(f"No se pudo leer {ruta}: {exc}") from exc

    if not isinstance(configuracion, dict):
        raise ErrorConfiguracion(
            f"La configuración de {ruta} debe contener un objeto JSON"
        )

    requeridas = ("host", "user", "password", "database")
    faltantes = [nombre for nombre in requeridas if not configuracion.get(nombre)]
    if faltantes:
        raise ErrorConfiguracion(
            "Faltan variables requeridas en config.json: " + ", ".join(faltantes)
        )

    # Se conservan las variables existentes y sólo se agregan opciones técnicas.
    configuracion.setdefault("port", 3306)
    configuracion.setdefault("charset", "utf8mb4")
    configuracion["cursorclass"] = pymysql.cursors.DictCursor
    configuracion["autocommit"] = False
    configuracion.setdefault("connect_timeout", 15)
    configuracion.setdefault("read_timeout", 120)
    configuracion.setdefault("write_timeout", 120)
    return configuracion


def crear_conexion(ruta_config: str | Path | None = None):
    """Crea una conexión PyMySQL con transacciones explícitas."""
    return pymysql.connect(**cargar_configuracion(ruta_config))
