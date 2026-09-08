from __future__ import annotations

import unittest

from certificacion.catalogos import (
    normalizar_codigo_departamento,
    normalizar_valor_catalogo,
    validar_tipo_catalogo,
)


class PruebasCatalogos(unittest.TestCase):
    def test_tipo_y_valor_se_normalizan(self):
        self.assertEqual(validar_tipo_catalogo(" Laboratorio "), "laboratorio")
        self.assertEqual(normalizar_valor_catalogo(" Lab Uno "), "Lab Uno")

    def test_rechaza_tipo_valor_vacio_y_valor_extenso(self):
        with self.assertRaisesRegex(ValueError, "no permitido"):
            validar_tipo_catalogo("estado_inventado")
        with self.assertRaisesRegex(ValueError, "obligatorio"):
            normalizar_valor_catalogo("   ")
        with self.assertRaisesRegex(ValueError, "267"):
            normalizar_valor_catalogo("X" * 268)

    def test_departamento_es_catalogo_y_solo_admite_digitos(self):
        self.assertEqual(
            validar_tipo_catalogo("codigo_depto"), "codigo_depto"
        )
        self.assertEqual(normalizar_codigo_departamento(" 0721 "), "0721")
        with self.assertRaisesRegex(ValueError, "solo dígitos"):
            normalizar_codigo_departamento("DEP-721")


if __name__ == "__main__":
    unittest.main()
