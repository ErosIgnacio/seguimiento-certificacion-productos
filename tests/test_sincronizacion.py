from __future__ import annotations

import unittest

from certificacion.constantes import CAMPOS_USUARIO
from certificacion.sincronizacion import _sincronizar_con_repositorio
from tests.fakes import RepositorioEnMemoria, fila_origen, producto_existente


class PruebasSincronizacion(unittest.TestCase):
    def test_inserta_registro_y_audita_snapshot(self):
        repo = RepositorioEnMemoria([fila_origen()])
        resumen = _sincronizar_con_repositorio(repo, " operador ", aplicar=True)

        self.assertTrue(resumen["confirmado"])
        self.assertEqual(resumen["insertados"], 1)
        self.assertEqual(len(repo.productos), 1)
        producto = next(iter(repo.productos.values()))
        self.assertEqual(producto["creado_por"], "OPERADOR")
        self.assertEqual(producto["activo"], 0)
        self.assertTrue(all(producto[campo] is None for campo in CAMPOS_USUARIO))
        self.assertEqual(len(repo.auditoria), 1)
        self.assertEqual(repo.auditoria[0]["accion"], "SYNC_CREATE")
        self.assertEqual(repo.auditoria[0]["campo_modificado"], "REGISTRO")

    def test_actualiza_solo_automaticos_y_conserva_todos_los_de_usuario(self):
        valores_usuario = {
            campo: (7 if campo.startswith("muestras_") else f"MANUAL-{campo}")
            for campo in CAMPOS_USUARIO
        }
        existente = producto_existente(**valores_usuario)
        repo = RepositorioEnMemoria(
            [fila_origen(descripcion="DESCRIPCION NUEVA", unidades=12)],
            [existente],
        )

        resumen = _sincronizar_con_repositorio(repo, "sincronizador", aplicar=True)
        producto = next(iter(repo.productos.values()))

        self.assertEqual(resumen["actualizados"], 1)
        self.assertEqual(producto["descripcion"], "DESCRIPCION NUEVA")
        self.assertEqual(producto["unidades"], 12)
        self.assertEqual(
            {campo: producto[campo] for campo in CAMPOS_USUARIO}, valores_usuario
        )
        # La sincronización tampoco toma propiedad de controles de edición manual.
        self.assertEqual(producto["creado_por"], "INICIAL")
        self.assertEqual(producto["actualizado_por"], "EDITOR")

    def test_audita_una_fila_por_modificacion_real(self):
        repo = RepositorioEnMemoria(
            [fila_origen(nave="NAVE DOS", unidades=20)],
            [producto_existente()],
        )
        resumen = _sincronizar_con_repositorio(repo, "sync", aplicar=True)

        self.assertEqual(resumen["actualizados"], 1)
        self.assertEqual(len(repo.auditoria), 2)
        self.assertEqual(
            {evento["campo_modificado"] for evento in repo.auditoria},
            {"nave", "unidades"},
        )
        self.assertTrue(
            all(evento["accion"] == "SYNC_UPDATE" for evento in repo.auditoria)
        )

    def test_datos_iguales_no_generan_auditoria(self):
        repo = RepositorioEnMemoria([fila_origen()], [producto_existente()])
        resumen = _sincronizar_con_repositorio(repo, "sync", aplicar=True)

        self.assertEqual(resumen["sin_cambios"], 1)
        self.assertEqual(resumen["actualizados"], 0)
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(len(repo.marcados_sincronizados), 1)

    def test_duplicado_conflictivo_revierte_y_no_elige_fila(self):
        existente = producto_existente(descripcion="SIN TOCAR")
        repo = RepositorioEnMemoria(
            [fila_origen(unidades=1), fila_origen(unidades=2)], [existente]
        )
        anterior = dict(repo.productos)

        resumen = _sincronizar_con_repositorio(repo, "sync", aplicar=True)

        self.assertEqual(resumen["duplicados_conflictivos"], 1)
        self.assertFalse(resumen["confirmado"])
        self.assertEqual(repo.productos, anterior)
        self.assertEqual(repo.rollbacks, 1)
        self.assertEqual(repo.commits, 0)

    def test_error_de_auditoria_revierte_principal_y_auditoria(self):
        repo = RepositorioEnMemoria(
            [fila_origen()], fallar_auditoria=True
        )
        resumen = _sincronizar_con_repositorio(repo, "sync", aplicar=True)

        self.assertFalse(resumen["confirmado"])
        self.assertEqual(resumen["insertados"], 0)
        self.assertEqual(resumen["operaciones_revertidas"]["insertados"], 1)
        self.assertEqual(repo.productos, {})
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(repo.rollbacks, 1)

    def test_repositorio_impide_insertar_dos_veces_misma_combinacion(self):
        fila = fila_origen()
        repo = RepositorioEnMemoria([])
        repo.iniciar_transaccion()
        repo.insertar_producto(fila, "SYNC")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            repo.insertar_producto(fila, "SYNC")
        repo.rollback()

    def test_no_desactiva_registro_ausente_del_origen(self):
        presente = producto_existente()
        ausente = producto_existente(
            n_contenedor="TGHU7654321",
            oc="999999999",
            gd="123456",
            sku="45678",
            activo=1,
        )
        repo = RepositorioEnMemoria([fila_origen()], [presente, ausente])

        resumen = _sincronizar_con_repositorio(repo, "sync", aplicar=True)

        self.assertEqual(resumen["sin_cambios"], 1)
        self.assertIn(ausente["id_certificacion"], repo.productos)
        self.assertEqual(repo.productos[ausente["id_certificacion"]]["activo"], 1)

    def test_previsualizacion_no_escribe_y_hace_rollback(self):
        repo = RepositorioEnMemoria([fila_origen()])
        resumen = _sincronizar_con_repositorio(repo, "sync", aplicar=False)

        self.assertEqual(resumen["modo"], "PREVISUALIZACION")
        self.assertEqual(resumen["insertados"], 1)
        self.assertFalse(resumen["confirmado"])
        self.assertEqual(repo.productos, {})
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(repo.rollbacks, 1)
        self.assertTrue(all(total == 0 for total in repo.llamadas_lote.values()))

    def test_aplica_cada_tipo_de_operacion_mediante_lotes(self):
        origen_nuevo = fila_origen(sku=11111)
        origen_actualizado = fila_origen(sku=22222, nave="NAVE ACTUALIZADA")
        origen_igual = fila_origen(sku=33333)
        repo = RepositorioEnMemoria(
            [origen_nuevo, origen_actualizado, origen_igual],
            [
                producto_existente(sku="22222"),
                producto_existente(sku="33333"),
            ],
        )

        resumen = _sincronizar_con_repositorio(repo, "sync", aplicar=True)

        self.assertTrue(resumen["confirmado"])
        self.assertEqual(resumen["insertados"], 1)
        self.assertEqual(resumen["actualizados"], 1)
        self.assertEqual(resumen["sin_cambios"], 1)
        self.assertEqual(resumen["auditorias_generadas"], 2)
        self.assertEqual(
            repo.llamadas_lote,
            {
                "insertar": 1,
                "actualizar": 1,
                "marcar": 1,
                "auditar_creaciones": 1,
                "auditar_cambios": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
