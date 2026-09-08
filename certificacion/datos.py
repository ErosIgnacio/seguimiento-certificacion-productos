"""Acceso a MySQL para la sincronización de certificaciones."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from . import auditoria
from .constantes import (
    CAMPOS_AUTOMATICOS,
    CAMPOS_AUTOMATICOS_ACTUALIZABLES,
    CAMPOS_CLAVE,
    CAMPOS_USUARIO,
    CONSULTA_ORIGEN,
    TABLA_CATALOGOS,
    TABLA_PRODUCTOS,
)


class RepositorioCertificacion:
    """Unidad de trabajo sobre una única conexión/transacción PyMySQL."""

    def __init__(self, conexion):
        self.conexion = conexion

    def iniciar_transaccion(self) -> None:
        self.conexion.begin()

    def commit(self) -> None:
        self.conexion.commit()

    def rollback(self) -> None:
        self.conexion.rollback()

    def adquirir_bloqueo_sincronizacion(self, espera_segundos: int = 0) -> None:
        """Impide dos sincronizaciones simultáneas entre distintas instancias."""
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "SELECT GET_LOCK(%s, %s) AS adquirido",
                ("log_imp_certificacion_sincronizacion", espera_segundos),
            )
            resultado = cursor.fetchone()
        if not resultado or int(resultado["adquirido"] or 0) != 1:
            raise RuntimeError(
                "Ya existe otra sincronización de certificaciones en ejecución"
            )

    def liberar_bloqueo_sincronizacion(self) -> None:
        """Libera el bloqueo nombrado; el cierre de conexión también lo libera."""
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "SELECT RELEASE_LOCK(%s) AS liberado",
                ("log_imp_certificacion_sincronizacion",),
            )

    def obtener_departamentos_sincronizacion(self) -> list[str]:
        """Obtiene el alcance vigente configurado por los usuarios."""
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT valor
                FROM {TABLA_CATALOGOS}
                WHERE tipo = %s
                  AND activo = 1
                ORDER BY orden, valor
                """,
                ("codigo_depto",),
            )
            filas = cursor.fetchall()

        departamentos = []
        vistos = set()
        for fila in filas:
            codigo = str(fila.get("valor") or "").strip()
            if codigo and codigo not in vistos:
                departamentos.append(codigo)
                vistos.add(codigo)
        return departamentos

    def obtener_origen(self) -> list[dict[str, Any]]:
        departamentos = self.obtener_departamentos_sincronizacion()
        if not departamentos:
            raise RuntimeError(
                "No existen departamentos activos para la sincronización. "
                "Aplique la migración 007 o active al menos uno desde Catálogos."
            )
        marcadores = ", ".join(["%s"] * len(departamentos))
        consulta = CONSULTA_ORIGEN.format(
            marcadores_departamentos=marcadores
        )
        with self.conexion.cursor() as cursor:
            cursor.execute(consulta, tuple(departamentos))
            return list(cursor.fetchall())

    def obtener_origen_por_contenedor_oc(
        self,
        contenedores: Iterable[str],
        ordenes_compra: Iterable[str],
    ) -> list[dict[str, Any]]:
        """Busca claves históricas en el origen sin filtrar departamentos."""
        contenedores = sorted({str(valor).strip().upper() for valor in contenedores})
        ordenes_compra = sorted(
            {str(valor).strip().upper() for valor in ordenes_compra}
        )
        condiciones = []
        parametros: list[str] = []
        if contenedores:
            condiciones.append(
                "UPPER(TRIM(lipc.N_Contenedor)) IN ("
                + ", ".join(["%s"] * len(contenedores))
                + ")"
            )
            parametros.extend(contenedores)
        if ordenes_compra:
            condiciones.append(
                "UPPER(TRIM(lipc.OC)) IN ("
                + ", ".join(["%s"] * len(ordenes_compra))
                + ")"
            )
            parametros.extend(ordenes_compra)
        if not condiciones:
            return []

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    lipc.ETA AS eta,
                    lipc.fecha_liberacion AS fecha_liberacion,
                    lipc.Nave AS nave,
                    lipc.N_Contenedor AS n_contenedor,
                    lipc.Fecha_Programacion AS fecha_programacion,
                    lipc.Status_Carga AS status_carga,
                    lipc.Destino AS compartido,
                    lipc.CD_Destino AS cd_destino,
                    lipc.Codigo_Depto AS codigo_depto,
                    lipc.OC AS oc,
                    lifc.GD AS gd,
                    lifc.Articulo AS sku,
                    lifc.Descripcion AS descripcion,
                    lifc.Cant_GD AS unidades
                FROM Log_Imp_Programacion_Contenedores lipc
                LEFT JOIN Log_Imp_Flujo_Consolidado lifc
                    ON lipc.N_Contenedor = lifc.N_Container
                    AND lipc.OC = lifc.Importacion
                WHERE {" OR ".join(condiciones)}
                ORDER BY lipc.N_Contenedor, lipc.OC, lifc.GD, lifc.Articulo
                """,
                parametros,
            )
            return list(cursor.fetchall())

    def obtener_existentes_para_actualizar(
        self,
        ids_certificacion: Iterable[str],
        tamano_lote: int = 500,
    ) -> dict[str, dict[str, Any]]:
        return self._obtener_existentes(
            ids_certificacion,
            tamano_lote=tamano_lote,
            bloquear=True,
        )

    def obtener_existentes(
        self,
        ids_certificacion: Iterable[str],
        tamano_lote: int = 500,
    ) -> dict[str, dict[str, Any]]:
        """Consulta para previsualización sin bloquear productos."""
        return self._obtener_existentes(
            ids_certificacion,
            tamano_lote=tamano_lote,
            bloquear=False,
        )

    def _obtener_existentes(
        self,
        ids_certificacion: Iterable[str],
        *,
        tamano_lote: int,
        bloquear: bool,
    ) -> dict[str, dict[str, Any]]:
        ids = list(ids_certificacion)
        existentes: dict[str, dict[str, Any]] = {}
        columnas = ", ".join(("id_certificacion", *CAMPOS_AUTOMATICOS))
        sufijo_bloqueo = "FOR UPDATE" if bloquear else ""

        with self.conexion.cursor() as cursor:
            for inicio in range(0, len(ids), tamano_lote):
                lote = ids[inicio : inicio + tamano_lote]
                marcadores = ", ".join(["%s"] * len(lote))
                cursor.execute(
                    f"""
                    SELECT {columnas}
                    FROM {TABLA_PRODUCTOS}
                    WHERE id_certificacion IN ({marcadores})
                    {sufijo_bloqueo}
                    """,
                    lote,
                )
                for fila in cursor.fetchall():
                    existentes[fila["id_certificacion"]] = fila

        return existentes

    def insertar_producto(self, fila: Mapping[str, Any], usuario: str) -> str:
        """Inserción individual conservada para usos puntuales y compatibilidad."""
        with self.conexion.cursor() as cursor:
            cursor.execute(
                self._sql_insertar_producto(),
                self._parametros_insertar_producto(fila, usuario),
            )
            cursor.execute(
                f"""
                SELECT id_certificacion
                FROM {TABLA_PRODUCTOS}
                WHERE n_contenedor = %s
                  AND oc = %s
                  AND gd = %s
                  AND sku = %s
                """,
                tuple(fila[campo] for campo in CAMPOS_CLAVE),
            )
            insertado = cursor.fetchone()

        if not insertado:
            raise RuntimeError("MySQL insertó el registro pero no devolvió su clave generada")
        return insertado["id_certificacion"]

    @staticmethod
    def _sql_insertar_producto() -> str:
        columnas = ", ".join(CAMPOS_AUTOMATICOS)
        marcadores = ", ".join(["%s"] * len(CAMPOS_AUTOMATICOS))
        columnas_usuario = ", ".join(CAMPOS_USUARIO)
        nulos_usuario = ", ".join(["NULL"] * len(CAMPOS_USUARIO))
        return f"""
                INSERT INTO {TABLA_PRODUCTOS} (
                    {columnas},
                    {columnas_usuario},
                    activo,
                    creado_por,
                    fecha_creacion,
                    actualizado_por,
                    fecha_actualizacion,
                    fecha_ultima_sincronizacion
                ) VALUES (
                    {marcadores},
                    {nulos_usuario},
                    0,
                    %s,
                    CURRENT_TIMESTAMP,
                    %s,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """

    @staticmethod
    def _parametros_insertar_producto(
        fila: Mapping[str, Any], usuario: str
    ) -> tuple[Any, ...]:
        return (
            *(fila[campo] for campo in CAMPOS_AUTOMATICOS),
            usuario,
            usuario,
        )

    @staticmethod
    def _sql_insertar_productos_masivo() -> str:
        columnas = (
            *CAMPOS_AUTOMATICOS,
            *CAMPOS_USUARIO,
            "activo",
            "creado_por",
            "fecha_creacion",
            "actualizado_por",
            "fecha_actualizacion",
            "fecha_ultima_sincronizacion",
        )
        return f"""
            INSERT INTO {TABLA_PRODUCTOS} ({", ".join(columnas)})
            VALUES ({", ".join(["%s"] * len(columnas))})
        """

    @staticmethod
    def _parametros_insertar_producto_masivo(
        fila: Mapping[str, Any],
        usuario: str,
        fecha_control: Any,
    ) -> tuple[Any, ...]:
        return (
            *(fila[campo] for campo in CAMPOS_AUTOMATICOS),
            *(None for _ in CAMPOS_USUARIO),
            0,
            usuario,
            fecha_control,
            usuario,
            fecha_control,
            fecha_control,
        )

    def insertar_productos(
        self,
        filas: Iterable[Mapping[str, Any]],
        usuario: str,
        *,
        tamano_lote: int = 250,
    ) -> list[str]:
        """Inserta productos en lotes y verifica sus IDs generados por MySQL."""
        filas = list(filas)
        if not filas:
            return []
        if tamano_lote < 1:
            raise ValueError("El tamaño de lote de productos debe ser positivo")

        identificadores = [fila["id_certificacion"] for fila in filas]
        if len(set(identificadores)) != len(identificadores):
            raise ValueError("El lote contiene identificadores duplicados")

        verificados: set[str] = set()
        with self.conexion.cursor() as cursor:
            cursor.execute("SELECT CURRENT_TIMESTAMP AS fecha_control")
            fecha_control = cursor.fetchone()["fecha_control"]
            for inicio in range(0, len(filas), tamano_lote):
                lote = filas[inicio : inicio + tamano_lote]
                cursor.executemany(
                    self._sql_insertar_productos_masivo(),
                    [
                        self._parametros_insertar_producto_masivo(
                            fila,
                            usuario,
                            fecha_control,
                        )
                        for fila in lote
                    ],
                )

                ids_lote = [fila["id_certificacion"] for fila in lote]
                marcadores = ", ".join(["%s"] * len(ids_lote))
                cursor.execute(
                    f"""
                    SELECT id_certificacion
                    FROM {TABLA_PRODUCTOS}
                    WHERE id_certificacion IN ({marcadores})
                    """,
                    ids_lote,
                )
                verificados.update(
                    fila["id_certificacion"] for fila in cursor.fetchall()
                )

        faltantes = set(identificadores) - verificados
        if faltantes:
            ejemplos = ", ".join(sorted(faltantes)[:5])
            raise RuntimeError(
                "MySQL no generó los identificadores esperados para el lote: "
                + ejemplos
            )
        return identificadores

    def actualizar_campos_automaticos(
        self,
        id_certificacion: str,
        cambios: Mapping[str, tuple[Any, Any]],
    ) -> None:
        campos_no_permitidos = set(cambios) - set(CAMPOS_AUTOMATICOS_ACTUALIZABLES)
        if campos_no_permitidos:
            raise ValueError(
                "Se intentó modificar campos no actualizables: "
                + ", ".join(sorted(campos_no_permitidos))
            )
        if not cambios:
            return

        asignaciones = [f"{campo} = %s" for campo in cambios]
        asignaciones.append("fecha_ultima_sincronizacion = CURRENT_TIMESTAMP")
        parametros = [cambios[campo][1] for campo in cambios]
        parametros.append(id_certificacion)

        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {TABLA_PRODUCTOS}
                SET {", ".join(asignaciones)}
                WHERE id_certificacion = %s
                """,
                parametros,
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"No se pudo actualizar exactamente una fila: {id_certificacion}"
                )

    def actualizar_campos_automaticos_lote(
        self,
        operaciones: Iterable[
            tuple[str, Mapping[str, tuple[Any, Any]]]
        ],
        *,
        tamano_lote: int = 100,
    ) -> int:
        """Agrupa por campos modificados y actualiza cada grupo con CASE."""
        operaciones = list(operaciones)
        if not operaciones:
            return 0
        if tamano_lote < 1:
            raise ValueError("El tamaño de lote de actualización debe ser positivo")

        grupos: dict[
            tuple[str, ...],
            list[tuple[str, Mapping[str, tuple[Any, Any]]]],
        ] = defaultdict(list)
        identificadores: set[str] = set()

        for identificador, cambios in operaciones:
            no_permitidos = set(cambios) - set(CAMPOS_AUTOMATICOS_ACTUALIZABLES)
            if no_permitidos:
                raise ValueError(
                    "Se intentó modificar campos no actualizables: "
                    + ", ".join(sorted(no_permitidos))
                )
            if not cambios:
                continue
            if identificador in identificadores:
                raise ValueError(
                    f"El lote contiene dos actualizaciones para {identificador}"
                )
            identificadores.add(identificador)
            campos = tuple(
                campo
                for campo in CAMPOS_AUTOMATICOS_ACTUALIZABLES
                if campo in cambios
            )
            grupos[campos].append((identificador, cambios))

        with self.conexion.cursor() as cursor:
            for campos, grupo in grupos.items():
                for inicio in range(0, len(grupo), tamano_lote):
                    lote = grupo[inicio : inicio + tamano_lote]
                    asignaciones: list[str] = []
                    parametros: list[Any] = []

                    for campo in campos:
                        casos = []
                        for identificador, cambios in lote:
                            casos.append("WHEN %s THEN %s")
                            parametros.extend(
                                (identificador, cambios[campo][1])
                            )
                        asignaciones.append(
                            f"{campo} = CASE id_certificacion "
                            + " ".join(casos)
                            + f" ELSE {campo} END"
                        )

                    ids_lote = [identificador for identificador, _ in lote]
                    marcadores = ", ".join(["%s"] * len(ids_lote))
                    parametros.extend(ids_lote)
                    cursor.execute(
                        f"""
                        UPDATE {TABLA_PRODUCTOS}
                        SET
                            {", ".join(asignaciones)},
                            fecha_ultima_sincronizacion = CURRENT_TIMESTAMP
                        WHERE id_certificacion IN ({marcadores})
                        """,
                        parametros,
                    )
        return len(identificadores)

    def marcar_sincronizado(self, id_certificacion: str) -> None:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {TABLA_PRODUCTOS}
                SET fecha_ultima_sincronizacion = CURRENT_TIMESTAMP
                WHERE id_certificacion = %s
                """,
                (id_certificacion,),
            )

    def marcar_sincronizados(
        self,
        ids_certificacion: Iterable[str],
        *,
        tamano_lote: int = 500,
    ) -> int:
        """Actualiza la fecha de sincronización con un UPDATE por lote."""
        ids = list(ids_certificacion)
        if not ids:
            return 0
        if tamano_lote < 1:
            raise ValueError("El tamaño de lote de sincronización debe ser positivo")
        if len(set(ids)) != len(ids):
            raise ValueError("El lote contiene identificadores duplicados")

        with self.conexion.cursor() as cursor:
            for inicio in range(0, len(ids), tamano_lote):
                lote = ids[inicio : inicio + tamano_lote]
                marcadores = ", ".join(["%s"] * len(lote))
                cursor.execute(
                    f"""
                    UPDATE {TABLA_PRODUCTOS}
                    SET fecha_ultima_sincronizacion = CURRENT_TIMESTAMP
                    WHERE id_certificacion IN ({marcadores})
                    """,
                    lote,
                )
        return len(ids)

    def auditar_creacion(
        self,
        id_certificacion: str,
        fila: Mapping[str, Any],
        usuario: str,
    ) -> None:
        with self.conexion.cursor() as cursor:
            auditoria.insertar_creacion(
                cursor,
                id_certificacion=id_certificacion,
                fila=fila,
                usuario=usuario,
            )

    def auditar_creaciones(
        self,
        filas: Iterable[Mapping[str, Any]],
        usuario: str,
    ) -> int:
        """Registra los snapshots iniciales mediante INSERT multi-fila."""
        filas = list(filas)
        with self.conexion.cursor() as cursor:
            return auditoria.insertar_creaciones_masivas(
                cursor,
                filas=(
                    (fila["id_certificacion"], fila) for fila in filas
                ),
                usuario=usuario,
            )

    def auditar_cambios(
        self,
        id_certificacion: str,
        fila_clave: Mapping[str, Any],
        usuario: str,
        accion: str,
        cambios: Mapping[str, tuple[Any, Any]],
    ) -> None:
        with self.conexion.cursor() as cursor:
            auditoria.insertar_cambios(
                cursor,
                id_certificacion=id_certificacion,
                fila_clave=fila_clave,
                usuario=usuario,
                accion=accion,
                cambios=cambios,
            )

    def auditar_cambios_lote(
        self,
        operaciones: Iterable[
            tuple[
                str,
                Mapping[str, Any],
                Mapping[str, tuple[Any, Any]],
            ]
        ],
        usuario: str,
        accion: str,
    ) -> int:
        """Registra todos los campos modificados mediante INSERT multi-fila."""
        with self.conexion.cursor() as cursor:
            return auditoria.insertar_cambios_masivos(
                cursor,
                operaciones=operaciones,
                usuario=usuario,
                accion=accion,
            )
