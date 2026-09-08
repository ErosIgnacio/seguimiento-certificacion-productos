from __future__ import annotations

import unittest

from certificacion.datos import RepositorioCertificacion


class CursorFalso:
    def __init__(self, conexion):
        self.conexion = conexion
        self.filas = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, consulta, parametros=()):
        self.conexion.consultas.append((consulta, tuple(parametros)))
        if "FROM Log_Imp_Certificacion_Catalogos" in consulta:
            self.filas = [
                {"valor": codigo} for codigo in self.conexion.departamentos
            ]
        else:
            self.filas = list(self.conexion.origen)

    def fetchall(self):
        return list(self.filas)


class ConexionFalsa:
    def __init__(self, departamentos, origen=()):
        self.departamentos = list(departamentos)
        self.origen = list(origen)
        self.consultas = []

    def cursor(self):
        return CursorFalso(self)


class PruebasDepartamentosSincronizacion(unittest.TestCase):
    def test_origen_usa_solo_catalogo_activo_y_parametros(self):
        conexion = ConexionFalsa(
            ["700", "721"],
            [{"codigo_depto": "721", "sku": 123}],
        )

        filas = RepositorioCertificacion(conexion).obtener_origen()

        self.assertEqual(filas, [{"codigo_depto": "721", "sku": 123}])
        consulta_catalogo, parametros_catalogo = conexion.consultas[0]
        consulta_origen, parametros_origen = conexion.consultas[1]
        self.assertIn("activo = 1", consulta_catalogo)
        self.assertEqual(parametros_catalogo, ("codigo_depto",))
        self.assertIn("Codigo_Depto IN (%s, %s)", consulta_origen)
        self.assertNotIn("'700'", consulta_origen)
        self.assertEqual(parametros_origen, ("700", "721"))

    def test_sin_departamentos_activos_detiene_antes_de_consultar_origen(self):
        conexion = ConexionFalsa([])

        with self.assertRaisesRegex(RuntimeError, "departamentos activos"):
            RepositorioCertificacion(conexion).obtener_origen()

        self.assertEqual(len(conexion.consultas), 1)


if __name__ == "__main__":
    unittest.main()
