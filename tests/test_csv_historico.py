from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from certificacion.csv_historico import leer_csv_historico


ENCABEZADOS = (
    "Container",
    "OC",
    "OP",
    "Sku",
    "Código",
    "Pegar Etiquetas",
    "Numero de QR",
    "ESTADO",
    "Fecha inspección",
    "Fecha de certificación",
    "Nro de inspección",
    "Laboratorio",
    "Nro de Certificado",
    "Nro de Informe Inspección",
    "Retiro de muestras",
    "Recep. de muestras",
    "Numero de Guía de Despacho",
    "Numero de Guía ER",
    "PRIORIDAD",
    "Comentarios",
)


def fila_csv(**cambios):
    fila = {
        "Container": "MSCU1234567",
        "OC": "123456789",
        "OP": "654321",
        "Sku": "98765",
        "Código": "COD-1",
        "Pegar Etiquetas": "Qr",
        "Numero de QR": "QR-1",
        "ESTADO": "Liberado",
        "Fecha inspección": "2026-08-20",
        "Fecha de certificación": "21-08-2026",
        "Nro de inspección": "INS-1",
        "Laboratorio": "CESMEC",
        "Nro de Certificado": "CERT-1",
        "Nro de Informe Inspección": "INF-1",
        "Retiro de muestras": "2",
        "Recep. de muestras": "1",
        "Numero de Guía de Despacho": "GD-1",
        "Numero de Guía ER": "ER-1",
        "PRIORIDAD": "PRIORIDAD",
        "Comentarios": "Carga histórica",
    }
    fila.update(cambios)
    return fila


class PruebasCsvHistorico(unittest.TestCase):
    def _crear_csv(self, filas):
        temporal = tempfile.TemporaryDirectory()
        ruta = Path(temporal.name) / "Certificacion.csv"
        with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.DictWriter(
                archivo, fieldnames=ENCABEZADOS, delimiter=";"
            )
            escritor.writeheader()
            escritor.writerows(filas)
        self.addCleanup(temporal.cleanup)
        return ruta

    def test_lee_y_normaliza_clave_fechas_y_cantidades(self):
        ruta = self._crear_csv([fila_csv(Container=" mscu1234567 ")])
        resultado = leer_csv_historico(ruta)

        self.assertFalse(resultado.bloquea_importacion)
        self.assertEqual(
            set(resultado.registros),
            {"MSCU1234567_123456789_654321_98765"},
        )
        datos = next(iter(resultado.registros.values()))
        self.assertEqual(datos["fecha_inspeccion"], date(2026, 8, 20))
        self.assertEqual(datos["fecha_certificacion"], date(2026, 8, 21))
        self.assertEqual(datos["muestras_retiradas"], 2)
        self.assertEqual(datos["muestras_recepcionadas"], 1)

    def test_omite_filas_vacias_e_incompletas_sin_bloquear(self):
        vacia = {encabezado: "" for encabezado in ENCABEZADOS}
        ruta = self._crear_csv([fila_csv(), vacia, fila_csv(Sku="")])
        resultado = leer_csv_historico(ruta)

        self.assertEqual(len(resultado.registros), 1)
        self.assertEqual(resultado.filas_vacias, 1)
        self.assertEqual(resultado.omitidos_clave_incompleta, 1)
        self.assertFalse(resultado.bloquea_importacion)

    def test_consolida_duplicado_identico(self):
        fila = fila_csv()
        resultado = leer_csv_historico(self._crear_csv([fila, dict(fila)]))

        self.assertEqual(len(resultado.registros), 1)
        self.assertEqual(resultado.duplicados_consolidados, 1)
        self.assertEqual(resultado.duplicados_conflictivos, 0)

    def test_bloquea_duplicado_conflictivo(self):
        resultado = leer_csv_historico(
            self._crear_csv([fila_csv(), fila_csv(**{"Código": "OTRO"})])
        )

        self.assertTrue(resultado.bloquea_importacion)
        self.assertEqual(resultado.duplicados_conflictivos, 1)
        self.assertEqual(resultado.errores[0]["tipo"], "DUPLICADO_CONFLICTIVO")

    def test_bloquea_guion_bajo_en_componente(self):
        resultado = leer_csv_historico(
            self._crear_csv([fila_csv(Container="MSCU_1234567")])
        )

        self.assertTrue(resultado.bloquea_importacion)
        self.assertEqual(resultado.filas_invalidas, 1)
        self.assertEqual(resultado.errores[0]["tipo"], "ClaveConSeparadorError")


if __name__ == "__main__":
    unittest.main()
