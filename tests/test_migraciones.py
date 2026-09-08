from __future__ import annotations

import re
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent


class PruebasMigraciones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.principal = (
            RAIZ / "migraciones" / "001_crear_log_imp_certificacion_productos.sql"
        ).read_text(encoding="utf-8")
        cls.auditoria = (
            RAIZ / "migraciones" / "002_crear_log_imp_certificacion_auditoria.sql"
        ).read_text(encoding="utf-8")
        cls.catalogos = (
            RAIZ / "migraciones" / "003_crear_log_imp_certificacion_catalogos.sql"
        ).read_text(encoding="utf-8")
        cls.catalogos_auditoria = (
            RAIZ
            / "migraciones"
            / "004_crear_log_imp_certificacion_catalogos_auditoria.sql"
        ).read_text(encoding="utf-8")
        cls.catalogos_iniciales = (
            RAIZ / "migraciones" / "005_cargar_catalogos_iniciales.sql"
        ).read_text(encoding="utf-8")
        cls.clave_masiva = (
            RAIZ / "migraciones" / "006_agregar_clave_edicion_masiva.sql"
        ).read_text(encoding="utf-8")
        cls.departamentos = (
            RAIZ
            / "migraciones"
            / "007_cargar_departamentos_sincronizacion.sql"
        ).read_text(encoding="utf-8")

    def test_id_es_generado_textual_y_primary_key_sin_indice_duplicado(self):
        self.assertRegex(
            self.principal,
            r"id_certificacion\s+VARCHAR\(125\)[\s\S]*?GENERATED ALWAYS AS",
        )
        self.assertIn("STORED", self.principal)
        self.assertIn("PRIMARY KEY (id_certificacion)", self.principal)
        self.assertNotIn("AUTO_INCREMENT", self.principal)
        self.assertEqual(
            len(re.findall(r"(?:KEY|INDEX)\s+\w+\s*\(id_certificacion\)", self.principal)),
            0,
        )

    def test_combinacion_tiene_restriccion_unica(self):
        self.assertIn(
            "UNIQUE KEY uq_certificacion_clave (n_contenedor, oc, gd, sku)",
            self.principal,
        )

    def test_clave_masiva_es_generada_no_visible_e_indexada(self):
        for contenido in (self.principal, self.clave_masiva):
            self.assertRegex(
                contenido,
                r"clave_edicion_masiva\s+VARCHAR\(123\)[\s\S]*?"
                r"GENERATED ALWAYS AS",
            )
            self.assertIn("idx_certificacion_clave_masiva", contenido)
            self.assertIn("CHAR_LENGTH(UPPER(TRIM(nave)))", contenido)
            self.assertIn("CHAR_LENGTH(UPPER(TRIM(oc)))", contenido)
            self.assertIn("CHAR_LENGTH(UPPER(TRIM(sku)))", contenido)

    def test_auditoria_tiene_tipo_y_collation_identicos_e_indices(self):
        patron = (
            r"id_certificacion\s+VARCHAR\(125\)\s+"
            r"CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
        self.assertRegex(self.principal, patron)
        self.assertRegex(self.auditoria, patron)
        for indice in (
            "idx_cert_auditoria_id",
            "idx_cert_auditoria_fecha",
            "idx_cert_auditoria_usuario",
        ):
            self.assertIn(indice, self.auditoria)

    def test_no_hay_enum_ni_borrado_fisico(self):
        contenido = (
            self.principal
            + self.auditoria
            + self.catalogos
            + self.catalogos_auditoria
            + self.catalogos_iniciales
            + self.departamentos
        ).upper()
        self.assertNotIn("ENUM(", contenido)
        self.assertNotIn("DELETE FROM", contenido)

    def test_catalogos_son_unicos_y_se_desactivan_sin_borrado(self):
        self.assertIn(
            "UNIQUE KEY uq_certificacion_catalogo_tipo_valor (tipo, valor)",
            self.catalogos,
        )
        self.assertIn("activo TINYINT(1) NOT NULL DEFAULT 1", self.catalogos)
        self.assertIn("creado_por VARCHAR(100) NOT NULL", self.catalogos)

    def test_auditoria_catalogos_tiene_acciones_e_indices(self):
        for accion in (
            "CATALOG_CREATE",
            "CATALOG_UPDATE",
            "CATALOG_DEACTIVATE",
            "CATALOG_REACTIVATE",
        ):
            self.assertIn(accion, self.catalogos_auditoria)
        for indice in (
            "idx_cert_catalogo_aud_id",
            "idx_cert_catalogo_aud_fecha",
            "idx_cert_catalogo_aud_usuario",
        ):
            self.assertIn(indice, self.catalogos_auditoria)

    def test_carga_inicial_contiene_todos_los_valores_oficiales(self):
        self.assertEqual(
            self.catalogos_iniciales.count("('estado_certificacion',"), 13
        )
        self.assertEqual(self.catalogos_iniciales.count("('pegar_etiquetas',"), 5)
        self.assertEqual(self.catalogos_iniciales.count("('prioridad',"), 4)
        self.assertEqual(self.catalogos_iniciales.count("('laboratorio',"), 4)
        for valor in (
            "Liberado",
            "Pendiente DI",
            "Qr, Placa caracteristica y advertencias",
            "SIN PRIORIDAD",
            "GASEI-ARBA-INGCER",
        ):
            self.assertIn(valor, self.catalogos_iniciales)

    def test_departamentos_iniciales_son_catalogo_idempotente(self):
        self.assertIn("INSERT IGNORE", self.departamentos)
        self.assertEqual(self.departamentos.count("('codigo_depto',"), 9)
        for codigo in ("700", "701", "702", "703", "720", "726", "727", "730", "669"):
            self.assertIn(f"'codigo_depto', '{codigo}'", self.departamentos)


if __name__ == "__main__":
    unittest.main()
