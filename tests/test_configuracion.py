from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import certificacion.configuracion as modulo_configuracion


class PruebasConfiguracion(unittest.TestCase):
    def test_exe_prioriza_config_editable_junto_al_ejecutable(self):
        with tempfile.TemporaryDirectory() as carpeta:
            directorio = Path(carpeta)
            ejecutable = directorio / "certificacion_carga.exe"
            configuracion = directorio / "config.json"
            configuracion.write_text("{}", encoding="utf-8")

            entorno = dict(os.environ)
            entorno.pop("LOG_IMPORTADO_CONFIG", None)
            with (
                patch.dict(os.environ, entorno, clear=True),
                patch.object(
                    modulo_configuracion.sys, "frozen", True, create=True
                ),
                patch.object(
                    modulo_configuracion.sys,
                    "executable",
                    str(ejecutable),
                ),
            ):
                encontrada = modulo_configuracion.buscar_ruta_config()

        self.assertEqual(encontrada, configuracion.resolve())

    def test_exe_usa_configuracion_dpapi_si_esta_disponible(self):
        configuracion = {
            "host": "servidor",
            "user": "usuario",
            "password": "secreto",
            "database": "base",
        }
        with tempfile.TemporaryDirectory() as directorio:
            protegida = Path(directorio) / "config.dat"
            protegida.touch()
            entorno = dict(os.environ)
            entorno.pop("LOG_IMPORTADO_CONFIG", None)
            with (
                patch.dict(os.environ, entorno, clear=True),
                patch.object(
                    modulo_configuracion.sys, "frozen", True, create=True
                ),
                patch.object(
                    modulo_configuracion,
                    "ruta_configuracion_protegida",
                    return_value=protegida,
                ),
                patch.object(
                    modulo_configuracion,
                    "leer_configuracion_protegida",
                    return_value=configuracion,
                ) as leer,
            ):
                resultado = modulo_configuracion.cargar_configuracion()

            leer.assert_called_once_with(protegida)
            self.assertEqual(resultado["host"], "servidor")
            self.assertFalse(resultado["autocommit"])


if __name__ == "__main__":
    unittest.main()
