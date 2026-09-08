-- Fase 3: catálogos administrables. No usa ENUM ni elimina valores físicamente.

CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Catalogos (
    id_catalogo BIGINT NOT NULL AUTO_INCREMENT,
    tipo VARCHAR(50)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    valor VARCHAR(267)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    descripcion VARCHAR(255) NULL,
    orden INT UNSIGNED NOT NULL DEFAULT 0,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    creado_por VARCHAR(100) NOT NULL,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_por VARCHAR(100) NULL,
    fecha_actualizacion DATETIME NULL,

    PRIMARY KEY (id_catalogo),
    UNIQUE KEY uq_certificacion_catalogo_tipo_valor (tipo, valor),
    INDEX idx_cert_catalogo_tipo_activo_orden (tipo, activo, orden),

    CONSTRAINT chk_certificacion_catalogo_activo CHECK (activo IN (0, 1)),
    CONSTRAINT chk_certificacion_catalogo_tipo CHECK (
        TRIM(tipo) <> '' AND INSTR(tipo, ' ') = 0
    ),
    CONSTRAINT chk_certificacion_catalogo_valor CHECK (TRIM(valor) <> '')
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  ROW_FORMAT = DYNAMIC;
