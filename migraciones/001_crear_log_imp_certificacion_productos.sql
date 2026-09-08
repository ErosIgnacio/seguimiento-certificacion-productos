-- Fase 1: tabla principal de certificación de productos.
-- Verificado contra MySQL 8.4.8 / InnoDB DYNAMIC / utf8mb4_0900_ai_ci.
-- Longitud de clave: 50 + 50 + 11 + 11 + 3 separadores = 125 caracteres.
-- Índice máximo de la PK: 125 * 4 = 500 bytes (< 3072 bytes).

CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Productos (
    n_contenedor VARCHAR(50)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    oc VARCHAR(50)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    gd VARCHAR(11)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    sku VARCHAR(11)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,

    id_certificacion VARCHAR(125)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
        GENERATED ALWAYS AS (
            CONCAT(
                UPPER(TRIM(n_contenedor)), '_',
                UPPER(TRIM(oc)), '_',
                UPPER(TRIM(gd)), '_',
                UPPER(TRIM(sku))
            )
        ) STORED,

    eta DATE NULL,
    fecha_liberacion DATE NULL,
    nave VARCHAR(50) NULL,
    fecha_programacion DATE NULL,
    status_carga VARCHAR(50) NULL,
    -- Destino es MEDIUMTEXT en el origen; se conserva para evitar truncamientos.
    compartido MEDIUMTEXT NULL,
    cd_destino VARCHAR(50) NULL,
    codigo_depto VARCHAR(50) NULL,
    descripcion VARCHAR(50) NULL,
    unidades INT NULL,

    -- Llave interna para ediciones por Nave-OC-SKU. Los prefijos de longitud
    -- vuelven inequívoca la combinación aunque aparezcan separadores internos.
    clave_edicion_masiva VARCHAR(123)
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
        ) STORED,

    codigo VARCHAR(100) NULL,
    pegar_etiquetas VARCHAR(50) NULL,
    numero_qr VARCHAR(150) NULL,
    estado_certificacion VARCHAR(100) NULL,
    fecha_inspeccion DATE NULL,
    fecha_certificacion DATE NULL,
    nro_inspeccion VARCHAR(100) NULL,
    laboratorio VARCHAR(150) NULL,
    nro_certificado VARCHAR(150) NULL,
    nro_informe_inspeccion VARCHAR(150) NULL,
    muestras_retiradas INT UNSIGNED NULL,
    muestras_recepcionadas INT UNSIGNED NULL,
    numero_guia_despacho VARCHAR(100) NULL,
    numero_guia_er VARCHAR(100) NULL,
    prioridad VARCHAR(267) NULL,
    comentarios TEXT NULL,

    activo TINYINT(1) NOT NULL DEFAULT 1,
    creado_por VARCHAR(100) NOT NULL,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_por VARCHAR(100) NULL,
    fecha_actualizacion DATETIME NULL,
    fecha_ultima_sincronizacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id_certificacion),
    UNIQUE KEY uq_certificacion_clave (n_contenedor, oc, gd, sku),
    KEY idx_certificacion_clave_masiva (clave_edicion_masiva),

    CONSTRAINT chk_certificacion_activo CHECK (activo IN (0, 1)),
    CONSTRAINT chk_certificacion_clave_no_vacia CHECK (
        LOWER(TRIM(n_contenedor)) NOT IN ('', 'nan', 'none', 'null')
        AND LOWER(TRIM(oc)) NOT IN ('', 'nan', 'none', 'null')
        AND LOWER(TRIM(gd)) NOT IN ('', 'nan', 'none', 'null')
        AND LOWER(TRIM(sku)) NOT IN ('', 'nan', 'none', 'null')
    ),
    CONSTRAINT chk_certificacion_clave_sin_separador CHECK (
        INSTR(n_contenedor, '_') = 0
        AND INSTR(oc, '_') = 0
        AND INSTR(gd, '_') = 0
        AND INSTR(sku, '_') = 0
    )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  ROW_FORMAT = DYNAMIC;
