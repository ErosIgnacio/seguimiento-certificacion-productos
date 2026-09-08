-- Ejecutar antes de las DDL. Este archivo no modifica datos.

SELECT
    VERSION() AS version_mysql,
    @@character_set_database AS character_set_database,
    @@collation_database AS collation_database,
    @@innodb_default_row_format AS innodb_default_row_format;

SELECT
    TABLE_NAME,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    CHARACTER_MAXIMUM_LENGTH,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
      (TABLE_NAME = 'Log_Imp_Programacion_Contenedores'
       AND COLUMN_NAME IN (
           'ETA', 'fecha_liberacion', 'Nave', 'N_Contenedor',
           'Fecha_Programacion', 'Status_Carga', 'Destino', 'CD_Destino',
           'Codigo_Depto', 'OC'
       ))
      OR
      (TABLE_NAME = 'Log_Imp_Flujo_Consolidado'
       AND COLUMN_NAME IN (
           'GD', 'Articulo', 'Descripcion', 'Cant_GD',
           'N_Container', 'Importacion'
       ))
  )
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT
    MAX(CHAR_LENGTH(n_contenedor)) AS max_n_contenedor,
    MAX(CHAR_LENGTH(oc)) AS max_oc,
    MAX(CHAR_LENGTH(gd)) AS max_gd,
    MAX(CHAR_LENGTH(sku)) AS max_sku,
    MAX(
        CHAR_LENGTH(n_contenedor) + CHAR_LENGTH(oc)
        + CHAR_LENGTH(gd) + CHAR_LENGTH(sku) + 3
    ) AS max_id_certificacion
FROM (
    SELECT
        UPPER(TRIM(lipc.N_Contenedor)) AS n_contenedor,
        UPPER(TRIM(lipc.OC)) AS oc,
        UPPER(TRIM(CAST(lifc.GD AS CHAR))) AS gd,
        UPPER(TRIM(CAST(lifc.Articulo AS CHAR))) AS sku
    FROM Log_Imp_Programacion_Contenedores lipc
    LEFT JOIN Log_Imp_Flujo_Consolidado lifc
        ON lipc.N_Contenedor = lifc.N_Container
        AND lipc.OC = lifc.Importacion
    WHERE lipc.Codigo_Depto IN (
        '700', '701', '702', '703', '720',
        '726', '727', '730', '669'
    )
) origen;
