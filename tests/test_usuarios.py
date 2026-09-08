from __future__ import annotations

import inspect
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import certificacion.__main__ as modulo_principal
from certificacion.interfaz import AppCertificacion, iniciar_interfaz_certificacion
from certificacion.usuarios import (
    normalizar_usuario,
    obtener_usuario_equipo,
    resolver_usuario,
)


class PruebasIngresoUsuario(unittest.TestCase):
    def test_usuario_se_normaliza_sin_validar_contrasena(self):
        self.assertEqual(normalizar_usuario("  eromoren  "), "EROMOREN")

    def test_rechaza_usuario_vacio_y_mayor_a_cien_caracteres(self):
        with self.assertRaisesRegex(ValueError, "obligatorio"):
            normalizar_usuario("   ")
        with self.assertRaisesRegex(ValueError, "100"):
            normalizar_usuario("U" * 101)

    def test_usuario_es_opcional_en_lanzadores(self):
        firma_app = inspect.signature(AppCertificacion)
        firma_lanzador = inspect.signature(iniciar_interfaz_certificacion)
        self.assertIsNone(firma_app.parameters["usuario"].default)
        self.assertIsNone(firma_lanzador.parameters["usuario"].default)

    def test_obtiene_usuario_de_windows_sin_login(self):
        with patch.dict(os.environ, {"USERNAME": " eromoren "}):
            self.assertEqual(obtener_usuario_equipo(), "EROMOREN")
            self.assertEqual(resolver_usuario(), "EROMOREN")

    def test_override_explicito_se_conserva_para_soporte(self):
        with patch.dict(os.environ, {"USERNAME": "EQUIPO"}):
            self.assertEqual(resolver_usuario(" operador "), "OPERADOR")

    def test_ejecutor_manual_usa_windows_si_no_recibe_usuario(self):
        resumen = {"errores": [], "confirmado": False}
        with (
            patch.object(modulo_principal.sys, "argv", ["certificacion"]),
            patch.object(
                modulo_principal,
                "resolver_usuario",
                return_value="EROMOREN",
            ) as resolver,
            patch.object(
                modulo_principal,
                "_ejecutar_con_nueva_conexion",
                return_value=resumen,
            ) as ejecutar,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(modulo_principal.main(), 0)

        resolver.assert_called_once_with(None)
        ejecutar.assert_called_once_with(
            "EROMOREN",
            aplicar=False,
            ruta_config=None,
        )


if __name__ == "__main__":
    unittest.main()
