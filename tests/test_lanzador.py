from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.iniciar_interfaz as lanzador


class PruebasLanzador(unittest.TestCase):
    def test_aprovisionamiento_msi_protege_y_elimina_json(self):
        with tempfile.TemporaryDirectory() as directorio:
            origen = Path(directorio) / "config.install.json"
            destino = Path(directorio) / "config.dat"
            origen.write_text("{}", encoding="utf-8")
            with (
                patch.object(lanzador, "_configurar_logging"),
                patch.object(lanzador, "cargar_configuracion"),
                patch.object(
                    lanzador,
                    "ruta_configuracion_protegida",
                    return_value=destino,
                ),
                patch.object(lanzador, "proteger_archivo_configuracion") as proteger,
            ):
                codigo = lanzador.main(
                    ["--provision-config-and-delete", str(origen)]
                )

            self.assertEqual(codigo, 0)
            self.assertFalse(origen.exists())
            proteger.assert_called_once_with(origen, destino)


if __name__ == "__main__":
    unittest.main()
