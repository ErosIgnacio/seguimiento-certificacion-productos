-- Fase 4: auditoría transaccional e independiente de los catálogos.

CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Catalogos_Auditoria (
    id_auditoria BIGINT NOT NULL AUTO_INCREMENT,
    id_catalogo BIGINT NOT NULL,
    tipo VARCHAR(50)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    usuario VARCHAR(100) NOT NULL,
    accion VARCHAR(30) NOT NULL,
    campo_modificado VARCHAR(100) NOT NULL,
    valor_anterior TEXT NULL,
    valor_nuevo TEXT NULL,
    fecha_modificacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id_auditoria),
    INDEX idx_cert_catalogo_aud_id (id_catalogo),
    INDEX idx_cert_catalogo_aud_fecha (fecha_modificacion),
    INDEX idx_cert_catalogo_aud_usuario (usuario),

    CONSTRAINT chk_cert_catalogo_aud_accion CHECK (
        accion IN (
            'CATALOG_CREATE',
            'CATALOG_UPDATE',
            'CATALOG_DEACTIVATE',
            'CATALOG_REACTIVATE'
        )
    )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  ROW_FORMAT = DYNAMIC;
