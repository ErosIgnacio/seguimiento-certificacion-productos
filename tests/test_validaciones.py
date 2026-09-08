from __future__ import annotations

import unittest

from certificacion.validaciones import (
    ClaveConSeparadorError,
    ClaveIncompletaError,
    construir_id_certificacion,
    preparar_filas_origen,
)
from tests.fakes import fila_origen


class PruebasValidaciones(unittest.TestCase):
    def test_construye_id_normalizado(self):
        resultado = construir_id_certificacion(
            "  mscu1234567 ", " 123456789 ", 654321, " sku98765 "
        )
        self.assertEqual(
            resultado, "MSCU1234567_123456789_654321_SKU98765"
        )

    def test_rechaza_cada_forma_de_clave_incompleta(self):
        invalidos = (None, "", "   ", "nan", "NaN", "none", "NONE", "null")
        for valor in invalidos:
            with self.subTest(valor=valor):
                with self.assertRaises(ClaveIncompletaError):
                    construir_id_certificacion(valor, "OC", "GD", "SKU")

        filas = [fila_origen(sku=valor) for valor in invalidos]
        resultado = preparar_filas_origen(filas)
        self.assertEqual(resultado.omitidos_clave_incompleta, len(invalidos))
        self.assertEqual(resultado.filas, [])

    def test_detecta_guion_bajo_y_bloquea(self):
        with self.assertRaises(ClaveConSeparadorError):
            construir_id_certificacion("MSCU_1234567", "OC", "GD", "SKU")
        resultado = preparar_filas_origen(
            [fila_origen(n_contenedor="MSCU_1234567")]
        )
        self.assertEqual(resultado.claves_con_separador, 1)
        self.assertTrue(resultado.bloquea_sincronizacion)
        self.assertEqual(resultado.errores[0]["tipo"], "CLAVE_CON_SEPARADOR")

    def test_duplica_identico_se_consolida(self):
        fila = fila_origen()
        resultado = preparar_filas_origen([fila, dict(fila)])
        self.assertEqual(len(resultado.filas), 1)
        self.assertEqual(resultado.duplicados_consolidados, 1)
        self.assertEqual(resultado.duplicados_conflictivos, 0)

    def test_duplicado_conflictivo_detalla_campo(self):
        resultado = preparar_filas_origen(
            [fila_origen(unidades=10), fila_origen(unidades=11)]
        )
        self.assertEqual(resultado.duplicados_conflictivos, 1)
        self.assertTrue(resultado.bloquea_sincronizacion)
        self.assertIn(
            "unidades", resultado.detalles_duplicados_conflictivos[0]["campos"]
        )


if __name__ == "__main__":
    unittest.main()
