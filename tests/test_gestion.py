from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import Mock, patch

import certificacion.gestion as modulo_gestion

from certificacion.gestion import (
    _actualizar_con_repositorio,
    _actualizar_masivo_con_repositorio,
    cargar_datos_iniciales,
    _cambiar_activo_con_repositorio,
    _normalizar_filtros_listado,
    _obtener_contexto_masivo_con_repositorio,
    _validar_valores_catalogados,
    normalizar_campos_usuario,
)
from tests.fakes import (
    RepositorioGestionEnMemoria,
    RepositorioGestionMasivaEnMemoria,
    producto_existente,
)


class PruebasGestionManual(unittest.TestCase):
    def setUp(self):
        self.existente = producto_existente(
            codigo="COD-1",
            comentarios="Original",
            muestras_retiradas=2,
        )

    def test_normaliza_fechas_enteros_y_vacios(self):
        resultado = normalizar_campos_usuario(
            {
                "fecha_inspeccion": "2026-08-13",
                "fecha_certificacion": "14-08-2026",
                "muestras_retiradas": " 5 ",
                "muestras_recepcionadas": "",
                "laboratorio": "  LAB UNO  ",
            }
        )
        self.assertEqual(resultado["fecha_inspeccion"], date(2026, 8, 13))
        self.assertEqual(resultado["fecha_certificacion"], date(2026, 8, 14))
        self.assertEqual(resultado["muestras_retiradas"], 5)
        self.assertIsNone(resultado["muestras_recepcionadas"])
        self.assertEqual(resultado["laboratorio"], "LAB UNO")

    def test_rechaza_campos_automaticos_y_cantidades_invalidas(self):
        with self.assertRaisesRegex(ValueError, "no gestionados"):
            normalizar_campos_usuario({"nave": "NAVE MODIFICADA"})
        with self.assertRaisesRegex(ValueError, "no puede ser negativo"):
            normalizar_campos_usuario({"muestras_retiradas": -1})
        with self.assertRaisesRegex(ValueError, "AAAA-MM-DD"):
            normalizar_campos_usuario({"fecha_inspeccion": "13/08/2026"})
        with self.assertRaisesRegex(ValueError, "bytes UTF-8"):
            normalizar_campos_usuario({"comentarios": "á" * 40_000})

    def test_actualiza_solo_manual_y_audita_cada_cambio(self):
        automaticos_antes = {
            campo: self.existente[campo]
            for campo in ("nave", "n_contenedor", "oc", "gd", "sku", "unidades")
        }
        repo = RepositorioGestionEnMemoria(self.existente)
        resultado = _actualizar_con_repositorio(
            repo,
            self.existente["id_certificacion"],
            {"codigo": "COD-2", "comentarios": "Nuevo"},
            " operador ",
        )

        self.assertTrue(resultado["ok"])
        self.assertEqual(set(resultado["campos_modificados"]), {"codigo", "comentarios"})
        self.assertEqual(repo.producto["codigo"], "COD-2")
        self.assertEqual(repo.producto["comentarios"], "Nuevo")
        self.assertEqual(
            {campo: repo.producto[campo] for campo in automaticos_antes},
            automaticos_antes,
        )
        self.assertEqual(len(repo.auditoria), 2)
        self.assertTrue(
            all(evento["accion"] == "USER_UPDATE" for evento in repo.auditoria)
        )
        self.assertEqual(repo.producto["actualizado_por"], "OPERADOR")
        self.assertEqual(repo.commits, 1)

    def test_carga_inicial_reutiliza_una_conexion_y_un_catalogo_activo(self):
        conexion = Mock()
        repositorio = Mock()
        repositorio.listar.return_value = {
            "total": 1,
            "filas": [{"id_certificacion": "ID-1"}],
        }
        repositorio.obtener_metricas.return_value = {
            "total": 1,
            "activos": 1,
            "inactivos": 0,
            "pendientes": 1,
            "gestionados": 0,
        }
        activos = {"laboratorio": ["CESMEC"]}
        repositorio.obtener_catalogos_activos.return_value = activos
        repositorio.obtener_catalogos.return_value = activos

        with (
            patch.object(
                modulo_gestion, "crear_conexion", return_value=conexion
            ) as crear,
            patch.object(
                modulo_gestion,
                "RepositorioProductos",
                return_value=repositorio,
            ) as construir_repositorio,
        ):
            resultado = cargar_datos_iniciales()

        self.assertTrue(resultado["ok"])
        self.assertEqual(resultado["listado"]["total_filtrado"], 1)
        crear.assert_called_once_with()
        construir_repositorio.assert_called_once_with(conexion)
        repositorio.obtener_catalogos_activos.assert_called_once_with()
        repositorio.obtener_catalogos.assert_called_once_with(activos)
        conexion.close.assert_called_once_with()

    def test_sin_cambios_no_escribe_auditoria(self):
        repo = RepositorioGestionEnMemoria(self.existente)
        resultado = _actualizar_con_repositorio(
            repo,
            self.existente["id_certificacion"],
            {"codigo": "COD-1", "comentarios": "Original"},
            "operador",
        )
        self.assertEqual(resultado["actualizados"], 0)
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(repo.rollbacks, 1)

    def test_desactiva_y_reactiva_con_auditoria(self):
        repo = RepositorioGestionEnMemoria(self.existente)
        desactivado = _cambiar_activo_con_repositorio(
            repo, self.existente["id_certificacion"], False, "operador"
        )
        self.assertTrue(desactivado["ok"])
        self.assertEqual(repo.producto["activo"], 0)
        self.assertEqual(repo.auditoria[-1]["accion"], "DESACTIVATE")

        reactivado = _cambiar_activo_con_repositorio(
            repo, self.existente["id_certificacion"], True, "operador"
        )
        self.assertTrue(reactivado["ok"])
        self.assertEqual(repo.producto["activo"], 1)
        self.assertEqual(repo.auditoria[-1]["accion"], "REACTIVATE")

    def test_no_necesita_inspeccion_desactiva_en_la_misma_transaccion(self):
        repo = RepositorioGestionEnMemoria(self.existente)
        resultado = _actualizar_con_repositorio(
            repo,
            self.existente["id_certificacion"],
            {"estado_certificacion": "No necesita inspección"},
            "operador",
        )

        self.assertEqual(resultado["actualizados"], 1)
        self.assertFalse(resultado["activo"])
        self.assertEqual(repo.producto["activo"], 0)
        self.assertEqual(
            [evento["accion"] for evento in repo.auditoria],
            ["USER_UPDATE", "DESACTIVATE"],
        )
        self.assertEqual(repo.commits, 1)

    def test_editar_inactivo_lo_convierte_en_certificable_y_audita(self):
        inactivo = producto_existente(
            activo=0,
            comentarios="Pendiente de revisión",
        )
        repo = RepositorioGestionEnMemoria(inactivo)

        resultado = _actualizar_con_repositorio(
            repo,
            inactivo["id_certificacion"],
            {"comentarios": "Requiere certificación"},
            "operador",
        )

        self.assertTrue(resultado["activo"])
        self.assertTrue(resultado["reactivado"])
        self.assertEqual(repo.producto["activo"], 1)
        self.assertEqual(
            [evento["accion"] for evento in repo.auditoria],
            ["USER_UPDATE", "REACTIVATE"],
        )
        self.assertEqual(repo.auditoria[-1]["campo_modificado"], "activo")

    def test_inactivo_sin_cambios_no_se_convierte_en_certificable(self):
        inactivo = producto_existente(activo=0, codigo="SIN CAMBIOS")
        repo = RepositorioGestionEnMemoria(inactivo)

        resultado = _actualizar_con_repositorio(
            repo,
            inactivo["id_certificacion"],
            {"codigo": "SIN CAMBIOS"},
            "operador",
        )

        self.assertEqual(resultado["actualizados"], 0)
        self.assertFalse(resultado["activo"])
        self.assertFalse(resultado["reactivado"])
        self.assertEqual(repo.producto["activo"], 0)
        self.assertEqual(repo.auditoria, [])

    def test_editar_inactivo_no_necesita_inspeccion_lo_mantiene_inactivo(self):
        inactivo = producto_existente(
            activo=0,
            estado_certificacion="No necesita inspección",
            comentarios="Anterior",
        )
        repo = RepositorioGestionEnMemoria(inactivo)

        resultado = _actualizar_con_repositorio(
            repo,
            inactivo["id_certificacion"],
            {"comentarios": "Corregido"},
            "operador",
        )

        self.assertFalse(resultado["activo"])
        self.assertFalse(resultado["reactivado"])
        self.assertEqual(repo.producto["activo"], 0)
        self.assertEqual(
            [evento["accion"] for evento in repo.auditoria],
            ["USER_UPDATE"],
        )

    def test_fallo_auditoria_revierte_edicion_manual(self):
        repo = RepositorioGestionEnMemoria(
            self.existente, fallar_auditoria=True
        )
        with self.assertRaisesRegex(RuntimeError, "Fallo controlado"):
            _actualizar_con_repositorio(
                repo,
                self.existente["id_certificacion"],
                {"codigo": "NO DEBE QUEDAR"},
                "operador",
            )
        self.assertEqual(repo.producto["codigo"], "COD-1")
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(repo.rollbacks, 1)

    def test_normaliza_rango_eta_y_rechaza_rango_invertido(self):
        filtros = _normalizar_filtros_listado(
            {"eta_desde": "2026-08-01", "eta_hasta": "31-08-2026"}
        )
        self.assertEqual(filtros["eta_desde"], date(2026, 8, 1))
        self.assertEqual(filtros["eta_hasta"], date(2026, 8, 31))
        with self.assertRaisesRegex(ValueError, "posterior"):
            _normalizar_filtros_listado(
                {"eta_desde": "2026-09-01", "eta_hasta": "2026-08-31"}
            )

    def test_catalogo_activo_restringe_valores_sin_alterar_presentacion(self):
        normalizados = normalizar_campos_usuario(
            {"estado_certificacion": " en proceso "}
        )
        self.assertEqual(normalizados["estado_certificacion"], "en proceso")
        _validar_valores_catalogados(
            normalizados, {"estado_certificacion": ["EN PROCESO"]}
        )
        with self.assertRaisesRegex(ValueError, "catálogo activo"):
            _validar_valores_catalogados(
                {"estado_certificacion": "OTRO"},
                {"estado_certificacion": ["EN PROCESO"]},
            )

    def test_valor_historico_inactivo_no_bloquea_otro_cambio(self):
        existente = producto_existente(
            estado_certificacion="ESTADO HISTORICO", comentarios="Antes"
        )
        repo = RepositorioGestionEnMemoria(existente)
        resultado = _actualizar_con_repositorio(
            repo,
            existente["id_certificacion"],
            {
                "estado_certificacion": "ESTADO HISTORICO",
                "comentarios": "Después",
            },
            "operador",
            catalogos_activos={"estado_certificacion": ["EN PROCESO"]},
        )
        self.assertEqual(resultado["campos_modificados"], ["comentarios"])
        self.assertEqual(repo.producto["estado_certificacion"], "ESTADO HISTORICO")

    def test_guarda_presentacion_oficial_del_catalogo(self):
        repo = RepositorioGestionEnMemoria(self.existente)
        resultado = _actualizar_con_repositorio(
            repo,
            self.existente["id_certificacion"],
            {"estado_certificacion": "proceso de certificación"},
            "operador",
            catalogos_activos={
                "estado_certificacion": ["Proceso de certificación"]
            },
        )
        self.assertEqual(resultado["actualizados"], 1)
        self.assertEqual(
            repo.producto["estado_certificacion"], "Proceso de certificación"
        )


class PruebasGestionMasiva(unittest.TestCase):
    def setUp(self):
        self.primero = producto_existente(
            n_contenedor="CONTENEDOR-1",
            gd="1001",
            codigo="OBJETIVO",
            comentarios="Comentario uno",
        )
        self.segundo = producto_existente(
            n_contenedor="CONTENEDOR-2",
            gd="1002",
            codigo="ANTERIOR",
            comentarios="Comentario dos",
            activo=0,
        )
        self.otro_grupo = producto_existente(
            n_contenedor="CONTENEDOR-3",
            gd="1003",
            nave="OTRA NAVE",
            codigo="NO TOCAR",
            comentarios="Fuera del grupo",
        )

    def _repositorio(self, **opciones):
        return RepositorioGestionMasivaEnMemoria(
            [self.primero, self.segundo, self.otro_grupo], **opciones
        )

    def test_contexto_cuenta_activos_e_inactivos_del_grupo(self):
        resultado = _obtener_contexto_masivo_con_repositorio(
            self._repositorio(), self.primero["id_certificacion"]
        )
        self.assertEqual(resultado["grupo"]["total"], 2)
        self.assertEqual(resultado["grupo"]["activos"], 1)
        self.assertEqual(resultado["grupo"]["inactivos"], 1)

    def test_edita_solo_grupo_y_campos_ingresados(self):
        repo = self._repositorio()
        resultado = _actualizar_masivo_con_repositorio(
            repo,
            self.primero["id_certificacion"],
            {"codigo": "OBJETIVO", "comentarios": ""},
            " editor ",
        )

        self.assertEqual(resultado["registros_grupo"], 2)
        self.assertEqual(resultado["actualizados"], 2)
        self.assertEqual(resultado["auditorias_generadas"], 4)
        self.assertEqual(resultado["reactivados"], 1)
        primero = repo.productos[self.primero["id_certificacion"]]
        segundo = repo.productos[self.segundo["id_certificacion"]]
        otro = repo.productos[self.otro_grupo["id_certificacion"]]
        self.assertEqual(primero["codigo"], "OBJETIVO")
        self.assertIsNone(primero["comentarios"])
        self.assertEqual(segundo["codigo"], "OBJETIVO")
        self.assertIsNone(segundo["comentarios"])
        self.assertEqual(segundo["activo"], 1)
        self.assertEqual(otro["codigo"], "NO TOCAR")
        self.assertEqual(otro["comentarios"], "Fuera del grupo")
        self.assertEqual(
            [evento["accion"] for evento in repo.auditoria].count("USER_UPDATE"),
            3,
        )
        self.assertEqual(
            [evento["accion"] for evento in repo.auditoria].count("REACTIVATE"),
            1,
        )
        self.assertEqual(repo.commits, 1)

    def test_sin_diferencias_no_escribe_auditoria(self):
        segundo_igual = producto_existente(
            n_contenedor="CONTENEDOR-2",
            gd="1002",
            codigo="OBJETIVO",
            comentarios="Comentario uno",
        )
        repo = RepositorioGestionMasivaEnMemoria([self.primero, segundo_igual])
        resultado = _actualizar_masivo_con_repositorio(
            repo,
            self.primero["id_certificacion"],
            {"codigo": "OBJETIVO", "comentarios": "Comentario uno"},
            "editor",
        )
        self.assertEqual(resultado["actualizados"], 0)
        self.assertEqual(resultado["sin_cambios"], 2)
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(repo.rollbacks, 1)

    def test_fallo_auditoria_revierte_todo_el_grupo(self):
        repo = self._repositorio(fallar_auditoria=True)
        with self.assertRaisesRegex(RuntimeError, "auditoría masiva"):
            _actualizar_masivo_con_repositorio(
                repo,
                self.primero["id_certificacion"],
                {"codigo": "NO DEBE QUEDAR"},
                "editor",
            )
        self.assertEqual(
            repo.productos[self.primero["id_certificacion"]]["codigo"],
            "OBJETIVO",
        )
        self.assertEqual(
            repo.productos[self.segundo["id_certificacion"]]["codigo"],
            "ANTERIOR",
        )
        self.assertEqual(
            repo.productos[self.segundo["id_certificacion"]]["activo"],
            0,
        )
        self.assertEqual(repo.auditoria, [])
        self.assertEqual(repo.rollbacks, 1)

    def test_rechaza_edicion_masiva_sin_campos_ingresados(self):
        with self.assertRaisesRegex(ValueError, "al menos un campo"):
            _actualizar_masivo_con_repositorio(
                self._repositorio(),
                self.primero["id_certificacion"],
                {},
                "editor",
            )

    def test_no_necesita_inspeccion_desactiva_todo_el_grupo(self):
        segundo_activo = producto_existente(
            n_contenedor="CONTENEDOR-2",
            gd="1002",
            estado_certificacion="Proceso de certificación",
        )
        repo = RepositorioGestionMasivaEnMemoria(
            [self.primero, segundo_activo]
        )
        resultado = _actualizar_masivo_con_repositorio(
            repo,
            self.primero["id_certificacion"],
            {"estado_certificacion": "No necesita inspección"},
            "editor",
        )

        self.assertEqual(resultado["actualizados"], 2)
        self.assertEqual(resultado["auditorias_generadas"], 4)
        self.assertTrue(
            all(producto["activo"] == 0 for producto in repo.productos.values())
        )
        self.assertEqual(
            [evento["accion"] for evento in repo.auditoria].count("DESACTIVATE"),
            2,
        )

    def test_masivo_mantiene_inactivo_si_no_necesita_inspeccion(self):
        inactivo = producto_existente(
            n_contenedor="CONTENEDOR-2",
            gd="1002",
            activo=0,
            estado_certificacion="No necesita inspección",
            comentarios="Anterior",
        )
        repo = RepositorioGestionMasivaEnMemoria([self.primero, inactivo])

        resultado = _actualizar_masivo_con_repositorio(
            repo,
            self.primero["id_certificacion"],
            {"comentarios": "Actualizado"},
            "editor",
        )

        self.assertEqual(resultado["reactivados"], 0)
        self.assertEqual(
            repo.productos[inactivo["id_certificacion"]]["activo"],
            0,
        )
        self.assertNotIn(
            "REACTIVATE", [evento["accion"] for evento in repo.auditoria]
        )


if __name__ == "__main__":
    unittest.main()
