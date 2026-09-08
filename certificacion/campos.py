"""Metadatos de campos compartidos por validaciones y la interfaz."""

from __future__ import annotations


ETIQUETAS_CAMPOS = {
    "id_certificacion": "ID certificación",
    "eta": "ETA",
    "fecha_liberacion": "Fecha liberación",
    "nave": "Nave",
    "n_contenedor": "Contenedor",
    "fecha_programacion": "Fecha programación",
    "status_carga": "Status carga",
    "compartido": "Compartido",
    "cd_destino": "CD destino",
    "codigo_depto": "Código depto.",
    "oc": "OC",
    "gd": "GD",
    "sku": "SKU",
    "descripcion": "Descripción",
    "unidades": "Unidades",
    "codigo": "Código",
    "pegar_etiquetas": "Pegar etiquetas",
    "numero_qr": "Número de QR",
    "estado_certificacion": "Estado certificación",
    "fecha_inspeccion": "Fecha inspección",
    "fecha_certificacion": "Fecha certificación",
    "nro_inspeccion": "Nro. inspección",
    "laboratorio": "Laboratorio",
    "nro_certificado": "Nro. certificado",
    "nro_informe_inspeccion": "Nro. informe inspección",
    "muestras_retiradas": "Muestras retiradas",
    "muestras_recepcionadas": "Muestras recepcionadas",
    "numero_guia_despacho": "Número guía despacho",
    "numero_guia_er": "Número guía ER",
    "prioridad": "Prioridad",
    "comentarios": "Comentarios",
    "activo": "Certificable",
    "creado_por": "Creado por",
    "fecha_creacion": "Fecha creación",
    "actualizado_por": "Actualizado por",
    "fecha_actualizacion": "Fecha actualización",
    "fecha_ultima_sincronizacion": "Última sincronización",
}

CAMPOS_FECHA_USUARIO = frozenset(
    {"fecha_inspeccion", "fecha_certificacion"}
)
CAMPOS_ENTEROS_USUARIO = frozenset(
    {"muestras_retiradas", "muestras_recepcionadas"}
)

LONGITUDES_CAMPOS_USUARIO = {
    "codigo": 100,
    "pegar_etiquetas": 50,
    "numero_qr": 150,
    "estado_certificacion": 100,
    "nro_inspeccion": 100,
    "laboratorio": 150,
    "nro_certificado": 150,
    "nro_informe_inspeccion": 150,
    "numero_guia_despacho": 100,
    "numero_guia_er": 100,
    "prioridad": 267,
    "comentarios": 65535,
}

COLUMNAS_LISTADO = (
    "nave",
    "eta",
    "n_contenedor",
    "oc",
    "gd",
    "sku",
    "descripcion",
    "unidades",
    "estado_certificacion",
    "laboratorio",
    "prioridad",
    "activo",
    "fecha_programacion",
)

ANCHOS_COLUMNAS = {
    "nave": 130,
    "eta": 85,
    "n_contenedor": 115,
    "oc": 95,
    "gd": 80,
    "sku": 85,
    "descripcion": 230,
    "unidades": 75,
    "estado_certificacion": 155,
    "laboratorio": 125,
    "prioridad": 105,
    "activo": 65,
    "fecha_programacion": 115,
}

ANCHOS_MINIMOS_COLUMNAS = {
    "nave": 90,
    "eta": 75,
    "n_contenedor": 100,
    "oc": 75,
    "gd": 65,
    "sku": 70,
    "descripcion": 150,
    "unidades": 70,
    "estado_certificacion": 120,
    "laboratorio": 90,
    "prioridad": 90,
    "activo": 60,
    "fecha_programacion": 105,
}
