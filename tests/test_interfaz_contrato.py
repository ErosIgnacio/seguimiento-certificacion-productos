from __future__ import annotations

import unittest
from unittest.mock import patch

import customtkinter as ctk

from certificacion.campos import (
    ANCHOS_COLUMNAS,
    ANCHOS_MINIMOS_COLUMNAS,
    COLUMNAS_LISTADO,
)
from certificacion.constantes import (
    CAMPOS_AUTOMATICOS,
    CAMPOS_CLAVE,
    CAMPOS_USUARIO,
    ESTADOS_GESTIONADOS,
)
from certificacion.datos_productos import RepositorioProductos
from certificacion.interfaz import (
    AppCertificacion,
    CampoFecha,
    ETIQUETAS_CATALOGOS,
    VentanaCertificacion,
    _campo_masivo_ingresado,
    _dimensiones_adaptadas,
    iniciar_interfaz_certificacion,
)


class PruebasContratoInterfaz(unittest.TestCase):
    def test_interfaz_es_customtkinter_y_tiene_lanzador_integrable(self):
        self.assertTrue(issubclass(AppCertificacion, ctk.CTk))
        self.assertTrue(issubclass(VentanaCertificacion, ctk.CTkToplevel))
        self.assertTrue(callable(iniciar_interfaz_certificacion))

    def test_integracion_sin_usuario_tambien_usa_cuenta_de_windows(self):
        parent = object()
        with (
            patch(
                "certificacion.interfaz.resolver_usuario",
                return_value="USUARIO_WINDOWS",
            ),
            patch(
                "certificacion.interfaz.VentanaCertificacion",
                return_value="VENTANA",
            ) as ventana,
        ):
            resultado = iniciar_interfaz_certificacion(parent=parent)
        self.assertEqual(resultado, "VENTANA")
        ventana.assert_called_once_with(parent, "USUARIO_WINDOWS")

    def test_campos_manual_automaticos_y_clave_no_se_superponen(self):
        self.assertFalse(set(CAMPOS_USUARIO) & set(CAMPOS_AUTOMATICOS))
        self.assertTrue(set(CAMPOS_CLAVE) <= set(CAMPOS_AUTOMATICOS))
        self.assertNotIn("id_certificacion", COLUMNAS_LISTADO)
        self.assertNotIn("fecha_ultima_sincronizacion", COLUMNAS_LISTADO)
        self.assertIn("nave", COLUMNAS_LISTADO)
        self.assertIn("fecha_programacion", COLUMNAS_LISTADO)
        self.assertIn("activo", COLUMNAS_LISTADO)

    def test_filtros_generan_sql_parametrizado(self):
        where, parametros = RepositorioProductos._construir_filtros(
            {
                "buscar": "MSCU",
                "estado_certificacion": "EN PROCESO",
                "laboratorio": "LAB",
                "prioridad": "ALTA",
                "gestion": "Gestionados",
                "eta_desde": "2026-08-01",
                "eta_hasta": "2026-08-31",
                "activo": True,
            }
        )
        self.assertNotIn("MSCU", where)
        self.assertNotIn("EN PROCESO", where)
        self.assertNotIn("LAB", where)
        self.assertNotIn("ALTA", where)
        self.assertEqual(where.count("%s"), len(parametros))
        self.assertIn("%MSCU%", parametros)
        self.assertEqual(parametros[-1], 1)

    def test_rechaza_filtro_gestion_fuera_de_catalogo(self):
        with self.assertRaisesRegex(ValueError, "gestión"):
            RepositorioProductos._construir_filtros({"gestion": "CUALQUIERA"})

    def test_gestionados_solo_considera_liberado(self):
        where_gestionados, parametros_gestionados = (
            RepositorioProductos._construir_filtros({"gestion": "Gestionados"})
        )
        where_pendientes, parametros_pendientes = (
            RepositorioProductos._construir_filtros({"gestion": "Pendientes"})
        )
        esperados = [estado.upper() for estado in ESTADOS_GESTIONADOS]
        self.assertEqual(esperados, ["LIBERADO"])
        self.assertEqual(parametros_gestionados, esperados)
        self.assertEqual(parametros_pendientes, esperados)
        self.assertIn("activo = 1", where_gestionados)
        self.assertIn("activo = 1", where_pendientes)
        self.assertIn(" IN (", where_gestionados)
        self.assertIn("NOT (", where_pendientes)
        for estado in ESTADOS_GESTIONADOS:
            self.assertNotIn(estado, where_gestionados)

    def test_ventanas_se_adaptan_a_pantalla_sin_ocultar_borde_inferior(self):
        ancho, alto, x, y = _dimensiones_adaptadas(1366, 768, 1200, 850)
        self.assertLessEqual(ancho + x, 1366)
        self.assertLessEqual(alto + y, 768)
        self.assertLessEqual(alto, 648)

    def test_filtros_eta_reutilizan_entrada_con_calendario(self):
        import inspect

        fuente = inspect.getsource(AppCertificacion._construir_filtros)
        self.assertGreaterEqual(fuente.count("CampoFecha("), 2)
        self.assertTrue(callable(CampoFecha.get))
        self.assertTrue(callable(CampoFecha.delete))
        self.assertTrue(callable(CampoFecha.insert))

    def test_interfaz_denomina_certificables_y_administra_departamentos(self):
        import inspect

        fuente_metricas = inspect.getsource(AppCertificacion._construir_metricas)
        fuente_filtros = inspect.getsource(AppCertificacion._construir_filtros)
        self.assertIn('"Certificables"', fuente_metricas)
        self.assertIn('"Certificables"', fuente_filtros)
        self.assertEqual(
            ETIQUETAS_CATALOGOS["codigo_depto"],
            "Departamento de sincronización",
        )

    def test_edicion_masiva_aplica_contenido_sin_selector_adicional(self):
        for valor in (None, "", "   "):
            self.assertFalse(_campo_masivo_ingresado(valor))
        for valor in ("Liberado", "0", 0, "  comentario  "):
            self.assertTrue(_campo_masivo_ingresado(valor))

    def test_anchos_del_listado_son_compactos_y_tienen_minimos(self):
        self.assertEqual(set(ANCHOS_COLUMNAS), set(COLUMNAS_LISTADO))
        self.assertEqual(set(ANCHOS_MINIMOS_COLUMNAS), set(COLUMNAS_LISTADO))
        self.assertLessEqual(sum(ANCHOS_COLUMNAS.values()), 1500)
        self.assertTrue(
            all(
                ANCHOS_MINIMOS_COLUMNAS[campo] <= ANCHOS_COLUMNAS[campo]
                for campo in COLUMNAS_LISTADO
            )
        )


if __name__ == "__main__":
    unittest.main()
