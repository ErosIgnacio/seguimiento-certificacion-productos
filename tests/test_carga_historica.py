from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import patch

import certificacion.carga_historica as modulo_carga
from certificacion.constantes import CAMPOS_USUARIO
from certificacion.csv_historico import ResultadoCsvHistorico
from tests.fakes import (
    RepositorioGestionMasivaEnMemoria,
    producto_existente,
)


def datos_usuario(**cambios):
    datos = {campo: None for campo in CAMPOS_USUARIO}
    datos.update(cambios)
    return datos


def resultado_csv(registros):
    return ResultadoCsvHistorico(
        ruta="Certificacion.csv",
        sha256="ABC123",
        encoding="utf-8-sig",
        delimitador=";",
        encabezados=[],
        registros=registros,
        filas_archivo=len(registros),
        filas_con_datos=len(registros),
    )


class RepositorioCargaEnMemoria(RepositorioGestionMasivaEnMemoria):
    def obtener_todos(self):
        return deepcopy(list(self.productos.values()))

    def obtener_todos_para_actualizar(self):
        return self.obtener_todos()

    def obtener_catalogos_activos(self):
        return {}


class BloqueoEnMemoria:
    def __init__(self):
        self.adquirido = 0
        self.liberado = 0

    def adquirir_bloqueo_sincronizacion(self):
        self.adquirido += 1

    def liberar_bloqueo_sincronizacion(self):
        self.liberado += 1


class ConexionCargaEnMemoria:
    def __init__(self, repositorio):
        self.repositorio = repositorio
        self.cerrada = False

    def rollback(self):
        self.repositorio.rollback()

    def close(self):
        self.cerrada = True


class PruebasCargaHistorica(unittest.TestCase):
    def setUp(self):
        self.primero = producto_existente(
            sku="10001",
            codigo="ANTERIOR",
            activo=0,
        )
        self.segundo = producto_existente(
            sku="10002",
            estado_certificacion="Proceso de certificación",
            activo=1,
        )
        self.ausente = producto_existente(sku="10003", activo=1)

    def _ejecutar(self, csv, repositorio, **opciones):
        conexion = ConexionCargaEnMemoria(repositorio)
        bloqueo = BloqueoEnMemoria()
        with (
            patch.object(modulo_carga, "leer_csv_historico", return_value=csv),
            patch.object(modulo_carga, "crear_conexion", return_value=conexion),
            patch.object(
                modulo_carga,
                "RepositorioProductos",
                return_value=repositorio,
            ),
            patch.object(
                modulo_carga,
                "RepositorioCertificacion",
                return_value=bloqueo,
            ),
        ):
            resultado = modulo_carga.importar_carga_historica(
                "Certificacion.csv", " operador ", **opciones
            )
        return resultado, conexion, bloqueo

    def test_importa_manuales_y_define_vigencia_con_auditoria(self):
        repo = RepositorioCargaEnMemoria(
            [self.primero, self.segundo, self.ausente]
        )
        csv = resultado_csv(
            {
                self.primero["id_certificacion"]: datos_usuario(
                    codigo="CERTIFICADO", estado_certificacion="Liberado"
                ),
                self.segundo["id_certificacion"]: datos_usuario(
                    estado_certificacion="No necesita inspección"
                ),
            }
        )

        resultado, conexion, bloqueo = self._ejecutar(csv, repo)

        self.assertTrue(resultado["ok"])
        self.assertTrue(resultado["confirmado"])
        self.assertEqual(resultado["actualizados_campos_usuario"], 2)
        self.assertEqual(resultado["reactivados_por_csv"], 1)
        self.assertEqual(resultado["desactivados_no_requiere_inspeccion"], 1)
        self.assertEqual(resultado["desactivados_ausentes_csv"], 1)
        self.assertEqual(resultado["auditorias_generadas"], 6)
        self.assertEqual(
            repo.productos[self.primero["id_certificacion"]]["codigo"],
            "CERTIFICADO",
        )
        self.assertEqual(
            repo.productos[self.primero["id_certificacion"]]["activo"], 1
        )
        self.assertEqual(
            repo.productos[self.segundo["id_certificacion"]]["activo"], 0
        )
        self.assertEqual(
            repo.productos[self.ausente["id_certificacion"]]["activo"], 0
        )
        self.assertEqual(repo.commits, 1)
        self.assertEqual(bloqueo.adquirido, 1)
        self.assertEqual(bloqueo.liberado, 1)
        self.assertTrue(conexion.cerrada)

    def test_bloquea_por_defecto_si_el_csv_contiene_ids_ausentes(self):
        repo = RepositorioCargaEnMemoria([self.primero])
        csv = resultado_csv(
            {
                self.primero["id_certificacion"]: datos_usuario(),
                "MSCU9999999_999_999_999": datos_usuario(),
            }
        )

        resultado, _, _ = self._ejecutar(csv, repo)

        self.assertFalse(resultado["ok"])
        self.assertFalse(resultado["confirmado"])
        self.assertEqual(resultado["modo"], "IMPORTACION_BLOQUEADA")
        self.assertEqual(resultado["csv_sin_registro_db"], 1)
        self.assertEqual(resultado["errores"][-1]["tipo"], "CSV_SIN_REGISTRO_DB")
        self.assertEqual(repo.commits, 0)
        self.assertEqual(repo.rollbacks, 1)

    def test_error_de_auditoria_revierte_principal_y_auditoria(self):
        repo = RepositorioCargaEnMemoria(
            [self.primero, self.ausente], fallar_auditoria=True
        )
        antes = deepcopy(repo.productos)
        csv = resultado_csv(
            {
                self.primero["id_certificacion"]: datos_usuario(
                    codigo="NO DEBE QUEDAR", estado_certificacion="Liberado"
                )
            }
        )

        resultado, _, _ = self._ejecutar(csv, repo)

        self.assertFalse(resultado["ok"])
        self.assertFalse(resultado["confirmado"])
        self.assertEqual(repo.productos, antes)
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(repo.commits, 0)
        self.assertEqual(repo.rollbacks, 1)


if __name__ == "__main__":
    unittest.main()
