from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from certificacion.configuracion_segura import (
    leer_configuracion_protegida,
    proteger_configuracion,
)


class PruebasConfiguracionSegura(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "DPAPI sólo está disponible en Windows")
    def test_protege_y_recupera_configuracion_para_usuario_actual(self):
        datos = {
            "host": "servidor",
            "user": "usuario",
            "password": "secreto",
            "database": "base",
            "port": 3306,
        }
        with tempfile.TemporaryDirectory() as directorio:
            destino = Path(directorio) / "config.dat"
            proteger_configuracion(datos, destino)

            self.assertNotIn(b"secreto", destino.read_bytes())
            self.assertEqual(leer_configuracion_protegida(destino), datos)


if __name__ == "__main__":
    unittest.main()
