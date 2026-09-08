"""Lanzador manual de la interfaz de certificación."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


if __package__ in (None, ""):
    raiz_proyecto = Path(__file__).resolve().parent.parent
    if str(raiz_proyecto) not in sys.path:
        sys.path.insert(0, str(raiz_proyecto))

from certificacion.configuracion import ErrorConfiguracion, cargar_configuracion
from certificacion.configuracion_segura import (
    ErrorConfiguracionProtegida,
    proteger_archivo_configuracion,
    ruta_configuracion_protegida,
    ruta_log_aplicacion,
)
from certificacion.interfaz import iniciar_interfaz_certificacion


def _configurar_logging() -> None:
    ruta = ruta_log_aplicacion()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        manejador = RotatingFileHandler(
            ruta,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[manejador],
            force=True,
        )
    except OSError:
        logging.basicConfig(level=logging.INFO, force=True)


def _aprovisionar_configuracion(
    origen: str, *, eliminar_origen: bool = False
) -> int:
    """Valida y protege la configuración temporal entregada por el MSI."""
    ruta_origen = Path(origen)
    try:
        cargar_configuracion(ruta_origen)
        proteger_archivo_configuracion(
            ruta_origen, ruta_configuracion_protegida()
        )
        if eliminar_origen:
            ruta_origen.unlink()
    except (ErrorConfiguracion, ErrorConfiguracionProtegida, OSError):
        logging.getLogger(__name__).exception(
            "No se pudo aprovisionar la configuración del MSI"
        )
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    _configurar_logging()
    argumentos_crudos = list(sys.argv[1:] if argv is None else argv)
    if len(argumentos_crudos) == 2 and argumentos_crudos[0] in {
        "--provision-config",
        "--provision-config-and-delete",
    }:
        return _aprovisionar_configuracion(
            argumentos_crudos[1],
            eliminar_origen=(
                argumentos_crudos[0] == "--provision-config-and-delete"
            ),
        )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--usuario",
        help=(
            "Usuario opcional para soporte o pruebas. Si se omite, se usa "
            "automáticamente la cuenta de Windows del equipo."
        ),
    )
    parser.add_argument("--config", help="Ruta opcional al config.json existente")
    argumentos = parser.parse_args(argumentos_crudos)
    if argumentos.config:
        os.environ["LOG_IMPORTADO_CONFIG"] = argumentos.config
    iniciar_interfaz_certificacion(argumentos.usuario)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
