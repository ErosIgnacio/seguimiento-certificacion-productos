"""Repositorio transaccional en memoria para probar el servicio."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from certificacion.auditoria import serializar_snapshot_automatico
from certificacion.constantes import CAMPOS_AUTOMATICOS, CAMPOS_USUARIO
from certificacion.validaciones import construir_id_certificacion


def construir_clave_edicion_masiva(producto: Mapping[str, Any]) -> str | None:
    nave = str(producto.get("nave") or "").strip().upper()
    if nave.casefold() in {"", "nan", "none", "null"}:
        return None
    oc = str(producto["oc"]).strip().upper()
    sku = str(producto["sku"]).strip().upper()
    return f"{len(nave):03d}:{nave}{len(oc):03d}:{oc}{len(sku):03d}:{sku}"


class RepositorioEnMemoria:
    def __init__(
        self,
        origen: Iterable[Mapping[str, Any]],
        productos: Iterable[Mapping[str, Any]] = (),
        *,
        fallar_auditoria: bool = False,
    ):
        self.origen = deepcopy(list(origen))
        self.productos: dict[str, dict[str, Any]] = {}
        for producto in productos:
            copia = deepcopy(dict(producto))
            identificador = copia.get("id_certificacion") or construir_id_certificacion(
                copia["n_contenedor"], copia["oc"], copia["gd"], copia["sku"]
            )
            copia["id_certificacion"] = identificador
            self.productos[identificador] = copia

        self.auditoria: list[dict[str, Any]] = []
        self.fallar_auditoria = fallar_auditoria
        self._snapshot = None
        self.commits = 0
        self.rollbacks = 0
        self.marcados_sincronizados: list[str] = []
        self.llamadas_lote = {
            "insertar": 0,
            "actualizar": 0,
            "marcar": 0,
            "auditar_creaciones": 0,
            "auditar_cambios": 0,
        }

    def iniciar_transaccion(self) -> None:
        if self._snapshot is not None:
            raise RuntimeError("Ya existe una transacción")
        self._snapshot = (
            deepcopy(self.productos),
            deepcopy(self.auditoria),
            deepcopy(self.marcados_sincronizados),
        )

    def commit(self) -> None:
        self.commits += 1
        self._snapshot = None

    def rollback(self) -> None:
        self.rollbacks += 1
        if self._snapshot is not None:
            self.productos, self.auditoria, self.marcados_sincronizados = (
                deepcopy(self._snapshot[0]),
                deepcopy(self._snapshot[1]),
                deepcopy(self._snapshot[2]),
            )
        self._snapshot = None

    def obtener_origen(self):
        return deepcopy(self.origen)

    def obtener_existentes_para_actualizar(self, ids_certificacion):
        return {
            identificador: deepcopy(self.productos[identificador])
            for identificador in ids_certificacion
            if identificador in self.productos
        }

    def obtener_existentes(self, ids_certificacion):
        return self.obtener_existentes_para_actualizar(ids_certificacion)

    def insertar_producto(self, fila, usuario):
        identificador = construir_id_certificacion(
            fila["n_contenedor"], fila["oc"], fila["gd"], fila["sku"]
        )
        if identificador in self.productos:
            raise ValueError("Duplicate entry")
        producto = {campo: deepcopy(fila.get(campo)) for campo in CAMPOS_AUTOMATICOS}
        producto.update({campo: None for campo in CAMPOS_USUARIO})
        producto.update(
            {
                "id_certificacion": identificador,
                "activo": 0,
                "creado_por": usuario,
                "actualizado_por": usuario,
            }
        )
        self.productos[identificador] = producto
        return identificador

    def insertar_productos(self, filas, usuario):
        self.llamadas_lote["insertar"] += 1
        return [self.insertar_producto(fila, usuario) for fila in filas]

    def actualizar_campos_automaticos(self, id_certificacion, cambios):
        for campo, (_, nuevo) in cambios.items():
            self.productos[id_certificacion][campo] = deepcopy(nuevo)

    def actualizar_campos_automaticos_lote(self, operaciones):
        self.llamadas_lote["actualizar"] += 1
        operaciones = list(operaciones)
        for identificador, cambios in operaciones:
            self.actualizar_campos_automaticos(identificador, cambios)
        return len(operaciones)

    def marcar_sincronizado(self, id_certificacion):
        self.marcados_sincronizados.append(id_certificacion)

    def marcar_sincronizados(self, ids_certificacion):
        self.llamadas_lote["marcar"] += 1
        ids = list(ids_certificacion)
        for identificador in ids:
            self.marcar_sincronizado(identificador)
        return len(ids)

    def _comprobar_auditoria(self):
        if self.fallar_auditoria:
            raise RuntimeError("Fallo controlado de auditoría")

    def auditar_creacion(self, id_certificacion, fila, usuario):
        self._comprobar_auditoria()
        self.auditoria.append(
            {
                "id_certificacion": id_certificacion,
                "usuario": usuario,
                "accion": "SYNC_CREATE",
                "campo_modificado": "REGISTRO",
                "valor_anterior": None,
                "valor_nuevo": serializar_snapshot_automatico(fila),
            }
        )

    def auditar_creaciones(self, filas, usuario):
        self.llamadas_lote["auditar_creaciones"] += 1
        filas = list(filas)
        for fila in filas:
            self.auditar_creacion(fila["id_certificacion"], fila, usuario)
        return len(filas)

    def auditar_cambios(
        self, id_certificacion, fila_clave, usuario, accion, cambios
    ):
        self._comprobar_auditoria()
        for campo, (anterior, nuevo) in cambios.items():
            self.auditoria.append(
                {
                    "id_certificacion": id_certificacion,
                    "usuario": usuario,
                    "accion": accion,
                    "campo_modificado": campo,
                    "valor_anterior": anterior,
                    "valor_nuevo": nuevo,
                }
            )

    def auditar_cambios_lote(self, operaciones, usuario, accion):
        self.llamadas_lote["auditar_cambios"] += 1
        operaciones = list(operaciones)
        total = 0
        for identificador, fila_clave, cambios in operaciones:
            self.auditar_cambios(
                identificador,
                fila_clave,
                usuario,
                accion,
                cambios,
            )
            total += len(cambios)
        return total


def fila_origen(**cambios):
    fila = {
        "eta": None,
        "fecha_liberacion": None,
        "nave": "NAVE UNO",
        "n_contenedor": "MSCU1234567",
        "fecha_programacion": None,
        "status_carga": "EN TRANSITO",
        "compartido": "COMPARTIDO",
        "cd_destino": "CD01",
        "codigo_depto": "700",
        "oc": "123456789",
        "gd": 654321,
        "sku": 98765,
        "descripcion": "PRODUCTO CONTROLADO",
        "unidades": 10,
    }
    fila.update(cambios)
    return fila


def producto_existente(**cambios):
    producto = fila_origen()
    producto["gd"] = str(producto["gd"])
    producto["sku"] = str(producto["sku"])
    producto.update({campo: None for campo in CAMPOS_USUARIO})
    producto.update(
        {
            "activo": 1,
            "creado_por": "INICIAL",
            "actualizado_por": "EDITOR",
        }
    )
    producto.update(cambios)
    producto["id_certificacion"] = construir_id_certificacion(
        producto["n_contenedor"],
        producto["oc"],
        producto["gd"],
        producto["sku"],
    )
    producto["clave_edicion_masiva"] = construir_clave_edicion_masiva(producto)
    return producto


class RepositorioGestionEnMemoria:
    """Fake del CRUD manual con rollback de producto y auditoría."""

    def __init__(self, producto, *, fallar_auditoria=False):
        self.producto = deepcopy(producto)
        self.auditoria = []
        self.fallar_auditoria = fallar_auditoria
        self._snapshot = None
        self.commits = 0
        self.rollbacks = 0

    def iniciar_transaccion(self):
        self._snapshot = (deepcopy(self.producto), deepcopy(self.auditoria))

    def commit(self):
        self.commits += 1
        self._snapshot = None

    def rollback(self):
        self.rollbacks += 1
        if self._snapshot is not None:
            self.producto, self.auditoria = deepcopy(self._snapshot)
        self._snapshot = None

    def obtener_para_actualizar(self, identificador):
        if self.producto.get("id_certificacion") != identificador:
            return None
        return deepcopy(self.producto)

    def actualizar_campos_usuario(self, identificador, cambios, usuario):
        if identificador != self.producto["id_certificacion"]:
            raise LookupError(identificador)
        for campo, (_, nuevo) in cambios.items():
            self.producto[campo] = deepcopy(nuevo)
        self.producto["actualizado_por"] = usuario

    def cambiar_activo(self, identificador, activo, usuario):
        if identificador != self.producto["id_certificacion"]:
            raise LookupError(identificador)
        self.producto["activo"] = 1 if activo else 0
        self.producto["actualizado_por"] = usuario

    def auditar_cambios(
        self,
        *,
        id_certificacion,
        fila_clave,
        usuario,
        accion,
        cambios,
    ):
        if self.fallar_auditoria:
            raise RuntimeError("Fallo controlado de auditoría manual")
        for campo, (anterior, nuevo) in cambios.items():
            self.auditoria.append(
                {
                    "id_certificacion": id_certificacion,
                    "usuario": usuario,
                    "accion": accion,
                    "campo_modificado": campo,
                    "valor_anterior": anterior,
                    "valor_nuevo": nuevo,
                }
            )


class RepositorioGestionMasivaEnMemoria:
    """Fake transaccional para grupos Nave-OC-SKU."""

    def __init__(self, productos, *, fallar_auditoria=False):
        self.productos = {}
        for producto in productos:
            copia = deepcopy(producto)
            copia["clave_edicion_masiva"] = construir_clave_edicion_masiva(copia)
            self.productos[copia["id_certificacion"]] = copia
        self.auditoria = []
        self.fallar_auditoria = fallar_auditoria
        self._snapshot = None
        self.commits = 0
        self.rollbacks = 0

    def iniciar_transaccion(self):
        self._snapshot = (deepcopy(self.productos), deepcopy(self.auditoria))

    def edicion_masiva_disponible(self):
        return True

    def commit(self):
        self.commits += 1
        self._snapshot = None

    def rollback(self):
        self.rollbacks += 1
        if self._snapshot is not None:
            self.productos, self.auditoria = deepcopy(self._snapshot)
        self._snapshot = None

    def obtener(self, identificador):
        producto = self.productos.get(identificador)
        return deepcopy(producto) if producto else None

    def obtener_con_clave_masiva(self, identificador):
        return self.obtener(identificador)

    def obtener_resumen_grupo_masivo(self, clave):
        filas = [
            fila
            for fila in self.productos.values()
            if fila["clave_edicion_masiva"] == clave
        ]
        return {
            "total": len(filas),
            "activos": sum(bool(fila["activo"]) for fila in filas),
            "inactivos": sum(not bool(fila["activo"]) for fila in filas),
        }

    def obtener_grupo_masivo_para_actualizar(self, clave):
        return deepcopy(
            sorted(
                (
                    fila
                    for fila in self.productos.values()
                    if fila["clave_edicion_masiva"] == clave
                ),
                key=lambda fila: fila["id_certificacion"],
            )
        )

    def actualizar_campos_usuario_masivo(self, operaciones, usuario):
        for identificador, cambios in operaciones:
            for campo, (_anterior, nuevo) in cambios.items():
                self.productos[identificador][campo] = deepcopy(nuevo)
            self.productos[identificador]["actualizado_por"] = usuario
        return len(operaciones)

    def cambiar_activos_masivo(self, operaciones, usuario):
        for identificador, activo in operaciones:
            self.productos[identificador]["activo"] = 1 if activo else 0
            self.productos[identificador]["actualizado_por"] = usuario
        return len(operaciones)

    def auditar_cambios_masivos(self, *, operaciones, usuario, accion):
        if self.fallar_auditoria:
            raise RuntimeError("Fallo controlado de auditoría masiva")
        total = 0
        for identificador, _fila_clave, cambios in operaciones:
            for campo, (anterior, nuevo) in cambios.items():
                self.auditoria.append(
                    {
                        "id_certificacion": identificador,
                        "usuario": usuario,
                        "accion": accion,
                        "campo_modificado": campo,
                        "valor_anterior": anterior,
                        "valor_nuevo": nuevo,
                    }
                )
                total += 1
        return total
