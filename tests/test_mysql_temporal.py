"""Integración opcional contra tablas TEMPORARY; nunca toca tablas productivas."""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymysql

import certificacion.auditoria as modulo_auditoria
import certificacion.carga_historica as modulo_carga_historica
import certificacion.catalogos as modulo_catalogos
import certificacion.datos as modulo_datos
import certificacion.datos_productos as modulo_datos_productos
from certificacion.configuracion import crear_conexion
from certificacion.catalogos import RepositorioCatalogos
from certificacion.carga_historica import importar_carga_historica
from certificacion.constantes import CAMPOS_AUTOMATICOS
from certificacion.datos import RepositorioCertificacion
from certificacion.datos_productos import RepositorioProductos
from certificacion.gestion import (
    _actualizar_con_repositorio,
    _actualizar_masivo_con_repositorio,
    _cambiar_activo_con_repositorio,
)
from certificacion.sincronizacion import _sincronizar_con_repositorio
from certificacion.validaciones import construir_id_certificacion
from tests.fakes import fila_origen
from tests.test_csv_historico import ENCABEZADOS


EJECUTAR = os.environ.get("LOG_IMPORTADO_RUN_MYSQL_TESTS") == "1"
RAIZ = Path(__file__).resolve().parent.parent
TABLA_PRODUCTOS_TEMP = "tmp_test_certificacion_productos"
TABLA_AUDITORIA_TEMP = "tmp_test_certificacion_auditoria"
TABLA_CATALOGOS_TEMP = "tmp_test_certificacion_catalogos"
TABLA_CATALOGOS_AUDITORIA_TEMP = "tmp_test_certificacion_catalogos_auditoria"
TABLA_MIGRACION_006_TEMP = "tmp_test_migracion_006"


class RepositorioOrigenControlado(RepositorioCertificacion):
    def __init__(self, conexion, origen):
        super().__init__(conexion)
        self.origen = origen

    def obtener_origen(self):
        return list(self.origen)


class RepositorioConFalloAuditoria(RepositorioOrigenControlado):
    def auditar_creacion(self, id_certificacion, fila, usuario):
        raise RuntimeError("Fallo controlado después del INSERT principal")

    def auditar_creaciones(self, filas, usuario):
        raise RuntimeError("Fallo controlado después del INSERT principal")


class ConexionPrestada:
    """Delega todo salvo close para reutilizar la sesión de tablas TEMPORARY."""

    def __init__(self, conexion):
        self._conexion = conexion

    def __getattr__(self, nombre):
        return getattr(self._conexion, nombre)

    def close(self):
        return None


@unittest.skipUnless(
    EJECUTAR,
    "Defina LOG_IMPORTADO_RUN_MYSQL_TESTS=1 para usar tablas TEMPORARY",
)
class PruebasMySQLTemporales(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conexion = crear_conexion(os.environ.get("LOG_IMPORTADO_CONFIG"))
        ddl_principal = (
            RAIZ / "migraciones" / "001_crear_log_imp_certificacion_productos.sql"
        ).read_text(encoding="utf-8")
        ddl_auditoria = (
            RAIZ / "migraciones" / "002_crear_log_imp_certificacion_auditoria.sql"
        ).read_text(encoding="utf-8")
        ddl_catalogos = (
            RAIZ / "migraciones" / "003_crear_log_imp_certificacion_catalogos.sql"
        ).read_text(encoding="utf-8")
        ddl_catalogos_auditoria = (
            RAIZ
            / "migraciones"
            / "004_crear_log_imp_certificacion_catalogos_auditoria.sql"
        ).read_text(encoding="utf-8")
        dml_catalogos_iniciales = (
            RAIZ / "migraciones" / "005_cargar_catalogos_iniciales.sql"
        ).read_text(encoding="utf-8")
        ddl_principal = ddl_principal.replace(
            "CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Productos",
            f"CREATE TEMPORARY TABLE {TABLA_PRODUCTOS_TEMP}",
        )
        ddl_auditoria = ddl_auditoria.replace(
            "CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Auditoria",
            f"CREATE TEMPORARY TABLE {TABLA_AUDITORIA_TEMP}",
        )
        ddl_catalogos = ddl_catalogos.replace(
            "CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Catalogos",
            f"CREATE TEMPORARY TABLE {TABLA_CATALOGOS_TEMP}",
        )
        ddl_catalogos_auditoria = ddl_catalogos_auditoria.replace(
            "CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Catalogos_Auditoria",
            f"CREATE TEMPORARY TABLE {TABLA_CATALOGOS_AUDITORIA_TEMP}",
        )
        dml_catalogos_iniciales = dml_catalogos_iniciales.replace(
            "Log_Imp_Certificacion_Catalogos", TABLA_CATALOGOS_TEMP
        )

        with cls.conexion.cursor() as cursor:
            cursor.execute(ddl_principal)
            cursor.execute(ddl_auditoria)
            cursor.execute(ddl_catalogos)
            cursor.execute(ddl_catalogos_auditoria)
            cursor.execute(dml_catalogos_iniciales)
        cls.conexion.commit()

        cls.tabla_productos_original = modulo_datos.TABLA_PRODUCTOS
        cls.tabla_datos_catalogos_original = modulo_datos.TABLA_CATALOGOS
        cls.tabla_auditoria_original = modulo_auditoria.TABLA_AUDITORIA
        cls.tabla_gestion_productos_original = modulo_datos_productos.TABLA_PRODUCTOS
        cls.tabla_gestion_auditoria_original = modulo_datos_productos.TABLA_AUDITORIA
        cls.tabla_catalogos_original = modulo_catalogos.TABLA_CATALOGOS
        cls.tabla_catalogos_auditoria_original = (
            modulo_catalogos.TABLA_CATALOGOS_AUDITORIA
        )
        modulo_datos.TABLA_PRODUCTOS = TABLA_PRODUCTOS_TEMP
        modulo_datos.TABLA_CATALOGOS = TABLA_CATALOGOS_TEMP
        modulo_auditoria.TABLA_AUDITORIA = TABLA_AUDITORIA_TEMP
        modulo_datos_productos.TABLA_PRODUCTOS = TABLA_PRODUCTOS_TEMP
        modulo_datos_productos.TABLA_AUDITORIA = TABLA_AUDITORIA_TEMP
        modulo_catalogos.TABLA_CATALOGOS = TABLA_CATALOGOS_TEMP
        modulo_catalogos.TABLA_CATALOGOS_AUDITORIA = (
            TABLA_CATALOGOS_AUDITORIA_TEMP
        )

    @classmethod
    def tearDownClass(cls):
        modulo_datos.TABLA_PRODUCTOS = cls.tabla_productos_original
        modulo_datos.TABLA_CATALOGOS = cls.tabla_datos_catalogos_original
        modulo_auditoria.TABLA_AUDITORIA = cls.tabla_auditoria_original
        modulo_datos_productos.TABLA_PRODUCTOS = cls.tabla_gestion_productos_original
        modulo_datos_productos.TABLA_AUDITORIA = cls.tabla_gestion_auditoria_original
        modulo_catalogos.TABLA_CATALOGOS = cls.tabla_catalogos_original
        modulo_catalogos.TABLA_CATALOGOS_AUDITORIA = (
            cls.tabla_catalogos_auditoria_original
        )
        cls.conexion.close()  # El cierre elimina todas las tablas TEMPORARY.

    def setUp(self):
        with self.conexion.cursor() as cursor:
            cursor.execute(f"DELETE FROM {TABLA_AUDITORIA_TEMP}")
            cursor.execute(f"DELETE FROM {TABLA_PRODUCTOS_TEMP}")
            cursor.execute(f"DELETE FROM {TABLA_CATALOGOS_TEMP}")
            cursor.execute(f"DELETE FROM {TABLA_CATALOGOS_AUDITORIA_TEMP}")
        self.conexion.commit()

    def test_ddl_genera_id_impide_duplicado_y_preserva_campos_usuario(self):
        origen = fila_origen()
        repo = RepositorioOrigenControlado(self.conexion, [origen])
        resumen = _sincronizar_con_repositorio(repo, "integracion", aplicar=True)
        self.assertEqual(resumen["insertados"], 1)

        identificador = construir_id_certificacion(
            origen["n_contenedor"], origen["oc"], origen["gd"], origen["sku"]
        )
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"SELECT id_certificacion FROM {TABLA_PRODUCTOS_TEMP}"
            )
            self.assertEqual(cursor.fetchone()["id_certificacion"], identificador)
            cursor.execute(
                f"""
                UPDATE {TABLA_PRODUCTOS_TEMP}
                SET codigo = %s, comentarios = %s
                WHERE id_certificacion = %s
                """,
                ("COD-MANUAL", "NO MODIFICAR", identificador),
            )
        self.conexion.commit()

        cambiado = fila_origen(nave="NAVE DOS", unidades=25)
        repo = RepositorioOrigenControlado(self.conexion, [cambiado])
        resumen = _sincronizar_con_repositorio(repo, "integracion", aplicar=True)
        self.assertEqual(resumen["actualizados"], 1)

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT nave, unidades, codigo, comentarios
                FROM {TABLA_PRODUCTOS_TEMP}
                WHERE id_certificacion = %s
                """,
                (identificador,),
            )
            producto = cursor.fetchone()
            self.assertEqual(producto["nave"], "NAVE DOS")
            self.assertEqual(producto["unidades"], 25)
            self.assertEqual(producto["codigo"], "COD-MANUAL")
            self.assertEqual(producto["comentarios"], "NO MODIFICAR")

            cursor.execute(
                f"""
                SELECT accion, campo_modificado
                FROM {TABLA_AUDITORIA_TEMP}
                ORDER BY id_auditoria
                """
            )
            eventos = cursor.fetchall()
            self.assertEqual(
                [(e["accion"], e["campo_modificado"]) for e in eventos],
                [
                    ("SYNC_CREATE", "REGISTRO"),
                    ("SYNC_UPDATE", "nave"),
                    ("SYNC_UPDATE", "unidades"),
                ],
            )

    def test_migracion_006_genera_llave_sin_colisiones_por_separador(self):
        ddl = (
            RAIZ / "migraciones" / "006_agregar_clave_edicion_masiva.sql"
        ).read_text(encoding="utf-8").replace(
            "Log_Imp_Certificacion_Productos", TABLA_MIGRACION_006_TEMP
        )
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TEMPORARY TABLE {TABLA_MIGRACION_006_TEMP} (
                    nave VARCHAR(50) NULL,
                    oc VARCHAR(50) NOT NULL,
                    sku VARCHAR(11) NOT NULL,
                    unidades INT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_0900_ai_ci
                """
            )
            cursor.execute(ddl)
            cursor.executemany(
                f"""
                INSERT INTO {TABLA_MIGRACION_006_TEMP} (nave, oc, sku)
                VALUES (%s, %s, %s)
                """,
                (("A_B", "C", "D"), ("A", "B_C", "D")),
            )
            cursor.execute(
                f"""
                SELECT clave_edicion_masiva
                FROM {TABLA_MIGRACION_006_TEMP}
                ORDER BY nave
                """
            )
            claves = [fila["clave_edicion_masiva"] for fila in cursor.fetchall()]
        self.assertEqual(len(set(claves)), 2)

    def test_actualizacion_masiva_agrupa_filas_y_audita_cada_campo(self):
        origenes = [fila_origen(sku=70000 + indice) for indice in range(4)]
        repo = RepositorioOrigenControlado(self.conexion, origenes)
        creado = _sincronizar_con_repositorio(
            repo,
            "integracion",
            aplicar=True,
        )
        self.assertEqual(creado["insertados"], 4)

        modificados = [
            fila_origen(sku=70000, nave="NAVE MASIVA"),
            fila_origen(sku=70001, nave="NAVE MASIVA"),
            fila_origen(sku=70002, nave="NAVE DIFERENTE", unidades=33),
            fila_origen(sku=70003),
        ]
        actualizado = _sincronizar_con_repositorio(
            RepositorioOrigenControlado(self.conexion, modificados),
            "integracion",
            aplicar=True,
        )

        self.assertEqual(actualizado["actualizados"], 3)
        self.assertEqual(actualizado["sin_cambios"], 1)
        self.assertEqual(actualizado["auditorias_generadas"], 4)
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT sku, nave, unidades
                FROM {TABLA_PRODUCTOS_TEMP}
                ORDER BY sku
                """
            )
            self.assertEqual(
                [
                    (fila["sku"], fila["nave"], fila["unidades"])
                    for fila in cursor.fetchall()
                ],
                [
                    ("70000", "NAVE MASIVA", 10),
                    ("70001", "NAVE MASIVA", 10),
                    ("70002", "NAVE DIFERENTE", 33),
                    ("70003", "NAVE UNO", 10),
                ],
            )
            cursor.execute(
                f"""
                SELECT campo_modificado, COUNT(*) AS total
                FROM {TABLA_AUDITORIA_TEMP}
                WHERE accion = 'SYNC_UPDATE'
                GROUP BY campo_modificado
                ORDER BY campo_modificado
                """
            )
            self.assertEqual(
                [
                    (fila["campo_modificado"], fila["total"])
                    for fila in cursor.fetchall()
                ],
                [("nave", 3), ("unidades", 1)],
            )

    def test_duplicado_real_lanza_integrity_error(self):
        origen = fila_origen()
        repo = RepositorioOrigenControlado(self.conexion, [origen])
        _sincronizar_con_repositorio(repo, "integracion", aplicar=True)

        columnas = ", ".join(CAMPOS_AUTOMATICOS)
        with self.assertRaises(pymysql.err.IntegrityError):
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {TABLA_PRODUCTOS_TEMP} ({columnas}, creado_por)
                    VALUES ({", ".join(["%s"] * len(CAMPOS_AUTOMATICOS))}, %s)
                    """,
                    (
                        *(origen[campo] for campo in CAMPOS_AUTOMATICOS),
                        "DUPLICADO",
                    ),
                )
        self.conexion.rollback()

    def test_fallo_de_auditoria_revierte_insert_real(self):
        repo = RepositorioConFalloAuditoria(self.conexion, [fila_origen()])
        resumen = _sincronizar_con_repositorio(repo, "integracion", aplicar=True)
        self.assertFalse(resumen["confirmado"])

        with self.conexion.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM {TABLA_PRODUCTOS_TEMP}")
            self.assertEqual(cursor.fetchone()["total"], 0)
            cursor.execute(f"SELECT COUNT(*) AS total FROM {TABLA_AUDITORIA_TEMP}")
            self.assertEqual(cursor.fetchone()["total"], 0)

    def test_gestion_manual_y_vigencia_comparten_auditoria_real(self):
        origen = fila_origen()
        repo_sync = RepositorioOrigenControlado(self.conexion, [origen])
        creado = _sincronizar_con_repositorio(
            repo_sync, "integracion", aplicar=True
        )
        self.assertEqual(creado["insertados"], 1)
        identificador = construir_id_certificacion(
            origen["n_contenedor"],
            origen["oc"],
            origen["gd"],
            origen["sku"],
        )

        repo_gestion = RepositorioProductos(self.conexion)
        actualizado = _actualizar_con_repositorio(
            repo_gestion,
            identificador,
            {
                "estado_certificacion": "EN PROCESO",
                "laboratorio": "LAB TEST",
                "muestras_retiradas": "3",
            },
            "operador",
        )
        self.assertEqual(actualizado["actualizados"], 1)
        self.assertTrue(actualizado["reactivado"])

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    nave,
                    estado_certificacion,
                    laboratorio,
                    muestras_retiradas,
                    activo,
                    actualizado_por
                FROM {TABLA_PRODUCTOS_TEMP}
                WHERE id_certificacion = %s
                """,
                (identificador,),
            )
            producto = cursor.fetchone()
            self.assertEqual(producto["nave"], origen["nave"])
            self.assertEqual(producto["estado_certificacion"], "EN PROCESO")
            self.assertEqual(producto["laboratorio"], "LAB TEST")
            self.assertEqual(producto["muestras_retiradas"], 3)
            self.assertEqual(producto["activo"], 1)
            self.assertEqual(producto["actualizado_por"], "OPERADOR")

            cursor.execute(
                f"""
                SELECT accion, campo_modificado
                FROM {TABLA_AUDITORIA_TEMP}
                ORDER BY id_auditoria
                """
            )
            eventos = [
                (fila["accion"], fila["campo_modificado"])
                for fila in cursor.fetchall()
            ]
            self.assertEqual(
                eventos,
                [
                    ("SYNC_CREATE", "REGISTRO"),
                    ("USER_UPDATE", "estado_certificacion"),
                    ("USER_UPDATE", "laboratorio"),
                    ("USER_UPDATE", "muestras_retiradas"),
                    ("REACTIVATE", "activo"),
                ],
            )

    def test_edicion_masiva_real_usa_nave_oc_sku_y_audita_cada_fila(self):
        primero = fila_origen(n_contenedor="MSCU1234567", gd=654321)
        segundo = fila_origen(n_contenedor="MSCU7654321", gd=654322)
        fuera = fila_origen(
            n_contenedor="MSCU9999999",
            gd=654323,
            nave="OTRA NAVE",
        )
        creado = _sincronizar_con_repositorio(
            RepositorioOrigenControlado(
                self.conexion, [primero, segundo, fuera]
            ),
            "integracion",
            aplicar=True,
        )
        self.assertEqual(creado["insertados"], 3)
        identificador = construir_id_certificacion(
            primero["n_contenedor"], primero["oc"], primero["gd"], primero["sku"]
        )

        resultado = _actualizar_masivo_con_repositorio(
            RepositorioProductos(self.conexion),
            identificador,
            {"codigo": "MASIVO", "comentarios": "Aplicado al grupo"},
            "editor",
        )
        self.assertEqual(resultado["registros_grupo"], 2)
        self.assertEqual(resultado["actualizados"], 2)
        self.assertEqual(resultado["auditorias_generadas"], 6)
        self.assertEqual(resultado["reactivados"], 2)

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT nave, codigo, comentarios, activo, clave_edicion_masiva
                FROM {TABLA_PRODUCTOS_TEMP}
                ORDER BY n_contenedor
                """
            )
            filas = list(cursor.fetchall())
            dentro = [fila for fila in filas if fila["nave"] == "NAVE UNO"]
            externo = [fila for fila in filas if fila["nave"] == "OTRA NAVE"][0]
            self.assertEqual(len({fila["clave_edicion_masiva"] for fila in dentro}), 1)
            self.assertTrue(all(fila["codigo"] == "MASIVO" for fila in dentro))
            self.assertTrue(all(fila["activo"] == 1 for fila in dentro))
            self.assertIsNone(externo["codigo"])
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM {TABLA_AUDITORIA_TEMP}
                WHERE accion = 'USER_UPDATE'
                """
            )
            self.assertEqual(cursor.fetchone()["total"], 4)

    def test_error_auditoria_masiva_revierte_todos_los_productos(self):
        primero = fila_origen(n_contenedor="MSCU1234567", gd=654321)
        segundo = fila_origen(n_contenedor="MSCU7654321", gd=654322)
        _sincronizar_con_repositorio(
            RepositorioOrigenControlado(self.conexion, [primero, segundo]),
            "integracion",
            aplicar=True,
        )
        identificador = construir_id_certificacion(
            primero["n_contenedor"], primero["oc"], primero["gd"], primero["sku"]
        )
        repo = RepositorioProductos(self.conexion)
        with patch.object(
            repo,
            "auditar_cambios_masivos",
            side_effect=RuntimeError("Fallo controlado masivo"),
        ):
            with self.assertRaisesRegex(RuntimeError, "controlado masivo"):
                _actualizar_masivo_con_repositorio(
                    repo,
                    identificador,
                    {"codigo": "NO DEBE QUEDAR"},
                    "editor",
                )
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {TABLA_PRODUCTOS_TEMP} "
                "WHERE codigo IS NOT NULL"
            )
            self.assertEqual(cursor.fetchone()["total"], 0)
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {TABLA_PRODUCTOS_TEMP} "
                "WHERE activo <> 0"
            )
            self.assertEqual(cursor.fetchone()["total"], 0)
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {TABLA_AUDITORIA_TEMP} "
                "WHERE accion = 'USER_UPDATE'"
            )
            self.assertEqual(cursor.fetchone()["total"], 0)

    def test_metricas_solo_marcan_estados_terminales_como_gestionados(self):
        origenes = [fila_origen(sku=98765 + indice) for indice in range(4)]
        repo_sync = RepositorioOrigenControlado(self.conexion, origenes)
        resultado = _sincronizar_con_repositorio(
            repo_sync, "integracion", aplicar=True
        )
        self.assertEqual(resultado["insertados"], 4)
        estados = (
            "Liberado",
            "No necesita inspección",
            "Proceso de certificación",
            None,
        )
        with self.conexion.cursor() as cursor:
            for origen, estado in zip(origenes, estados):
                identificador = construir_id_certificacion(
                    origen["n_contenedor"],
                    origen["oc"],
                    origen["gd"],
                    origen["sku"],
                )
                cursor.execute(
                    f"UPDATE {TABLA_PRODUCTOS_TEMP} "
                    "SET estado_certificacion = %s, activo = 1 "
                    "WHERE id_certificacion = %s",
                    (estado, identificador),
                )
        self.conexion.commit()

        repo = RepositorioProductos(self.conexion)
        metricas = repo.obtener_metricas()
        gestionados = repo.listar(
            filtros={"gestion": "Gestionados"}, pagina=1, tamano_pagina=20
        )
        pendientes = repo.listar(
            filtros={"gestion": "Pendientes"}, pagina=1, tamano_pagina=20
        )
        self.assertEqual(metricas["gestionados"], 1)
        self.assertEqual(metricas["pendientes"], 3)
        self.assertEqual(gestionados["total"], 1)
        self.assertEqual(pendientes["total"], 3)

    def test_carga_historica_real_iguala_manuales_vigencia_y_auditoria(self):
        origenes = [fila_origen(sku=88001 + indice) for indice in range(3)]
        creado = _sincronizar_con_repositorio(
            RepositorioOrigenControlado(self.conexion, origenes),
            "integracion",
            aplicar=True,
        )
        self.assertEqual(creado["insertados"], 3)
        ids = [
            construir_id_certificacion(
                origen["n_contenedor"],
                origen["oc"],
                origen["gd"],
                origen["sku"],
            )
            for origen in origenes
        ]
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"UPDATE {TABLA_PRODUCTOS_TEMP} SET activo = 1 "
                "WHERE id_certificacion IN (%s, %s)",
                (ids[1], ids[2]),
            )
        self.conexion.commit()

        fila_liberada = {encabezado: "" for encabezado in ENCABEZADOS}
        fila_liberada.update(
            {
                "Container": origenes[0]["n_contenedor"],
                "OC": origenes[0]["oc"],
                "OP": origenes[0]["gd"],
                "Sku": origenes[0]["sku"],
                "Código": "HISTORICO",
                "ESTADO": "Liberado",
            }
        )
        fila_sin_inspeccion = {encabezado: "" for encabezado in ENCABEZADOS}
        fila_sin_inspeccion.update(
            {
                "Container": origenes[1]["n_contenedor"],
                "OC": origenes[1]["oc"],
                "OP": origenes[1]["gd"],
                "Sku": origenes[1]["sku"],
                "ESTADO": "No necesita inspección",
            }
        )

        with tempfile.TemporaryDirectory() as carpeta:
            ruta_csv = Path(carpeta) / "Certificacion.csv"
            with ruta_csv.open(
                "w", encoding="utf-8-sig", newline=""
            ) as archivo:
                escritor = csv.DictWriter(
                    archivo, fieldnames=ENCABEZADOS, delimiter=";"
                )
                escritor.writeheader()
                escritor.writerows((fila_liberada, fila_sin_inspeccion))
            with patch.object(
                modulo_carga_historica,
                "crear_conexion",
                return_value=ConexionPrestada(self.conexion),
            ):
                resultado = importar_carga_historica(
                    ruta_csv,
                    "historico",
                )

        self.assertTrue(resultado["confirmado"])
        self.assertEqual(resultado["auditorias_generadas"], 6)
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id_certificacion, codigo, estado_certificacion, activo
                FROM {TABLA_PRODUCTOS_TEMP}
                ORDER BY sku
                """
            )
            productos = list(cursor.fetchall())
            self.assertEqual(
                [producto["activo"] for producto in productos], [1, 0, 0]
            )
            self.assertEqual(productos[0]["codigo"], "HISTORICO")
            self.assertEqual(productos[0]["estado_certificacion"], "Liberado")
            self.assertEqual(
                productos[1]["estado_certificacion"],
                "No necesita inspección",
            )
            cursor.execute(
                f"""
                SELECT accion, COUNT(*) AS total
                FROM {TABLA_AUDITORIA_TEMP}
                WHERE accion <> 'SYNC_CREATE'
                GROUP BY accion
                ORDER BY accion
                """
            )
            self.assertEqual(
                [(fila["accion"], fila["total"]) for fila in cursor.fetchall()],
                [
                    ("DESACTIVATE", 2),
                    ("REACTIVATE", 1),
                    ("USER_UPDATE", 3),
                ],
            )

    def test_catalogos_crean_actualizan_y_desactivan_sin_borrado(self):
        repo = RepositorioCatalogos(self.conexion)
        self.conexion.begin()
        identificador = repo.crear(
            tipo="laboratorio",
            valor="LAB TEST",
            descripcion="Inicial",
            orden=10,
            usuario="OPERADOR",
        )
        repo.auditar_evento(
            id_catalogo=identificador,
            tipo="laboratorio",
            usuario="OPERADOR",
            accion="CATALOG_CREATE",
            campo_modificado="REGISTRO",
            valor_anterior=None,
            valor_nuevo={"valor": "LAB TEST"},
        )
        self.conexion.commit()

        self.conexion.begin()
        existente = repo.obtener_para_actualizar(identificador)
        self.assertEqual(existente["valor"], "LAB TEST")
        repo.actualizar(
            identificador,
            valor="LAB CONTROL",
            descripcion="Actualizado",
            orden=20,
            usuario="EDITOR",
        )
        repo.auditar_evento(
            id_catalogo=identificador,
            tipo="laboratorio",
            usuario="EDITOR",
            accion="CATALOG_UPDATE",
            campo_modificado="valor",
            valor_anterior="LAB TEST",
            valor_nuevo="LAB CONTROL",
        )
        repo.cambiar_activo(identificador, False, "EDITOR")
        repo.auditar_evento(
            id_catalogo=identificador,
            tipo="laboratorio",
            usuario="EDITOR",
            accion="CATALOG_DEACTIVATE",
            campo_modificado="activo",
            valor_anterior=1,
            valor_nuevo=0,
        )
        self.conexion.commit()

        filas = repo.listar("laboratorio")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["valor"], "LAB CONTROL")
        self.assertEqual(filas[0]["activo"], 0)
        self.assertEqual(filas[0]["actualizado_por"], "EDITOR")
        eventos = repo.listar_auditoria(identificador)
        self.assertEqual(
            [evento["accion"] for evento in reversed(eventos)],
            ["CATALOG_CREATE", "CATALOG_UPDATE", "CATALOG_DEACTIVATE"],
        )

    def test_error_auditoria_catalogo_revierte_alta(self):
        repo = RepositorioCatalogos(self.conexion)
        self.conexion.begin()
        identificador = repo.crear(
            tipo="laboratorio",
            valor="LAB ROLLBACK",
            descripcion=None,
            orden=99,
            usuario="OPERADOR",
        )
        with self.assertRaises(pymysql.err.IntegrityError):
            repo.auditar_evento(
                id_catalogo=identificador,
                tipo=None,
                usuario="OPERADOR",
                accion="CATALOG_CREATE",
                campo_modificado="REGISTRO",
                valor_anterior=None,
                valor_nuevo="NO DEBE QUEDAR",
            )
        self.conexion.rollback()
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {TABLA_CATALOGOS_TEMP} "
                "WHERE valor = %s",
                ("LAB ROLLBACK",),
            )
            self.assertEqual(cursor.fetchone()["total"], 0)

    def test_servicio_departamento_audita_alta_y_desactivacion(self):
        conexion_prestada = ConexionPrestada(self.conexion)
        with patch.object(
            modulo_catalogos, "crear_conexion", return_value=conexion_prestada
        ):
            creado = modulo_catalogos.guardar_catalogo(
                tipo="codigo_depto",
                valor="721",
                descripcion="Incluido por usuario",
                orden=15,
                usuario="operador",
            )
            self.assertTrue(creado["ok"])
            desactivado = modulo_catalogos.cambiar_estado_catalogo(
                creado["id_catalogo"], False, "operador"
            )
            self.assertTrue(desactivado["ok"])
            historial = modulo_catalogos.consultar_auditoria_catalogos(
                creado["id_catalogo"]
            )
        self.assertTrue(historial["ok"])
        self.assertEqual(
            [fila["accion"] for fila in reversed(historial["filas"])],
            ["CATALOG_CREATE", "CATALOG_DEACTIVATE"],
        )

    def test_servicio_catalogo_revierte_si_falla_su_auditoria(self):
        conexion_prestada = ConexionPrestada(self.conexion)
        with (
            patch.object(
                modulo_catalogos,
                "crear_conexion",
                return_value=conexion_prestada,
            ),
            patch.object(
                modulo_catalogos.RepositorioCatalogos,
                "auditar_evento",
                side_effect=RuntimeError("Fallo controlado de historial"),
            ),
        ):
            resultado = modulo_catalogos.guardar_catalogo(
                tipo="laboratorio",
                valor="LAB NO DEBE QUEDAR",
                descripcion=None,
                orden=99,
                usuario="operador",
            )
        self.assertFalse(resultado["ok"])
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS total FROM {TABLA_CATALOGOS_TEMP} "
                "WHERE valor = %s",
                ("LAB NO DEBE QUEDAR",),
            )
            self.assertEqual(cursor.fetchone()["total"], 0)


if __name__ == "__main__":
    unittest.main()
