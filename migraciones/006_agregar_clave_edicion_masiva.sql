-- Llave interna, generada e indexada, para editar todos los productos que
-- comparten Nave-OC-SKU. No se presenta como columna visible en la interfaz.
-- Longitud: Nave (50) + OC (50) + SKU (11) + tres prefijos "NNN:" = 123.

ALTER TABLE Log_Imp_Certificacion_Productos
    ADD COLUMN clave_edicion_masiva VARCHAR(123)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
        GENERATED ALWAYS AS (
            CASE
                WHEN nave IS NULL
                  OR LOWER(TRIM(nave)) IN ('', 'nan', 'none', 'null')
                THEN NULL
                ELSE CONCAT(
                    LPAD(CHAR_LENGTH(UPPER(TRIM(nave))), 3, '0'), ':',
                    UPPER(TRIM(nave)),
                    LPAD(CHAR_LENGTH(UPPER(TRIM(oc))), 3, '0'), ':',
                    UPPER(TRIM(oc)),
                    LPAD(CHAR_LENGTH(UPPER(TRIM(sku))), 3, '0'), ':',
                    UPPER(TRIM(sku))
                )
            END
        ) STORED AFTER unidades,
    ADD INDEX idx_certificacion_clave_masiva (clave_edicion_masiva);
