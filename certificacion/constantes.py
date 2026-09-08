"""Constantes compartidas por el backend de certificación."""

TABLA_PRODUCTOS = "Log_Imp_Certificacion_Productos"
TABLA_AUDITORIA = "Log_Imp_Certificacion_Auditoria"
TABLA_CATALOGOS = "Log_Imp_Certificacion_Catalogos"
TABLA_CATALOGOS_AUDITORIA = "Log_Imp_Certificacion_Catalogos_Auditoria"
CAMPO_CLAVE_EDICION_MASIVA = "clave_edicion_masiva"

# Nave (50) + OC (50) + SKU (11), con un prefijo "NNN:" por componente.
# El formato por longitud evita colisiones aunque un valor contenga separadores.
LONGITUD_CLAVE_EDICION_MASIVA = 50 + 50 + 11 + (4 * 3)

CAMPOS_CATALOGO = (
    "estado_certificacion",
    "laboratorio",
    "prioridad",
    "pegar_etiquetas",
    "codigo_depto",
)

# Un producto se considera gestionado solamente al alcanzar uno de estos
# estados terminales. Los demás estados representan gestión todavía pendiente.
ESTADOS_GESTIONADOS = (
    "Liberado",
)

ESTADO_NO_REQUIERE_INSPECCION = "No necesita inspección"

CAMPOS_CLAVE = (
    "n_contenedor",
    "oc",
    "gd",
    "sku",
)

CAMPOS_AUTOMATICOS = (
    "eta",
    "fecha_liberacion",
    "nave",
    "n_contenedor",
    "fecha_programacion",
    "status_carga",
    "compartido",
    "cd_destino",
    "codigo_depto",
    "oc",
    "gd",
    "sku",
    "descripcion",
    "unidades",
)

# Los componentes de la clave son inmutables y no pertenecen a este conjunto.
CAMPOS_AUTOMATICOS_ACTUALIZABLES = (
    "eta",
    "fecha_liberacion",
    "nave",
    "fecha_programacion",
    "status_carga",
    "compartido",
    "cd_destino",
    "codigo_depto",
    "descripcion",
    "unidades",
)

CAMPOS_USUARIO = (
    "codigo",
    "pegar_etiquetas",
    "numero_qr",
    "estado_certificacion",
    "fecha_inspeccion",
    "fecha_certificacion",
    "nro_inspeccion",
    "laboratorio",
    "nro_certificado",
    "nro_informe_inspeccion",
    "muestras_retiradas",
    "muestras_recepcionadas",
    "numero_guia_despacho",
    "numero_guia_er",
    "prioridad",
    "comentarios",
)

LONGITUDES_CLAVE = {
    "n_contenedor": 50,
    "oc": 50,
    # GD y Articulo son INT en el origen. Once caracteres cubren INT con signo.
    "gd": 11,
    "sku": 11,
}

LONGITUD_ID_CERTIFICACION = sum(LONGITUDES_CLAVE.values()) + 3

ACCIONES_AUDITORIA = frozenset(
    {
        "SYNC_CREATE",
        "SYNC_UPDATE",
        "USER_UPDATE",
        "DESACTIVATE",
        "REACTIVATE",
    }
)

CONSULTA_ORIGEN = """
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
WHERE lipc.Codigo_Depto IN ({marcadores_departamentos})
ORDER BY lipc.ETA ASC
"""
