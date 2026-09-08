from __future__ import annotations

import unittest

from certificacion.coincidencias_historicas import (
    analizar_coincidencias_faltantes,
)
from tests.fakes import producto_existente


class PruebasCoincidenciasHistoricas(unittest.TestCase):
    def test_detecta_contenedor_mal_escrito_con_oc_gd_sku_iguales(self):
        existente = producto_existente(
            n_contenedor="MSCU1234567",
            oc="PCL2500000001",
            gd="123456",
            sku="98765999",
        )
        faltante = "MSCU1234568_PCL2500000001_123456_98765999"

        resultado = analizar_coincidencias_faltantes([faltante], [existente])

        self.assertEqual(resultado["con_oc_exacta"], 1)
        self.assertEqual(resultado["con_similitud_de_una_edicion"], 1)
        self.assertEqual(resultado["con_coincidencia_fuerte_gd_sku"], 1)
        self.assertEqual(
            resultado["detalles"][0]["candidatos_fuertes"][0][
                "id_certificacion"
            ],
            existente["id_certificacion"],
        )

    def test_detecta_oc_mal_escrita_con_contenedor_gd_sku_iguales(self):
        existente = producto_existente(
            n_contenedor="MSCU1234567",
            oc="PCL2500000001",
            gd="123456",
            sku="98765999",
        )
        faltante = "MSCU1234567_PCL2500000002_123456_98765999"

        resultado = analizar_coincidencias_faltantes([faltante], [existente])

        self.assertEqual(resultado["con_contenedor_exacto"], 1)
        self.assertEqual(resultado["con_similitud_de_una_edicion"], 1)
        self.assertEqual(resultado["con_coincidencia_fuerte_gd_sku"], 1)

    def test_informa_id_sin_coincidencia(self):
        existente = producto_existente()
        faltante = "ABCD9999999_OC999999999_111111_222222"

        resultado = analizar_coincidencias_faltantes([faltante], [existente])

        self.assertEqual(resultado["sin_coincidencia_oc_contenedor"], 1)
        self.assertEqual(resultado["con_coincidencia_fuerte_gd_sku"], 0)
        self.assertEqual(resultado["detalles"][0]["candidatos_fuertes"], [])


if __name__ == "__main__":
    unittest.main()
