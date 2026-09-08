-- Fase 1: auditoría independiente para certificaciones.
-- No posee borrado en cascada ni FK: la auditoría debe sobrevivir al registro.

CREATE TABLE IF NOT EXISTS Log_Imp_Certificacion_Auditoria (
    id_auditoria BIGINT NOT NULL AUTO_INCREMENT,
    id_certificacion VARCHAR(125)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    n_contenedor VARCHAR(50)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    oc VARCHAR(50)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    gd VARCHAR(11)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    sku VARCHAR(11)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    usuario VARCHAR(100) NOT NULL,
    accion VARCHAR(50) NOT NULL,
    campo_modificado VARCHAR(100) NOT NULL,
    valor_anterior MEDIUMTEXT NULL,
    valor_nuevo MEDIUMTEXT NULL,
    fecha_modificacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id_auditoria),
    INDEX idx_cert_auditoria_id (id_certificacion),
    INDEX idx_cert_auditoria_fecha (fecha_modificacion),
    INDEX idx_cert_auditoria_usuario (usuario),

    CONSTRAINT chk_certificacion_auditoria_accion CHECK (
        accion IN (
            'SYNC_CREATE',
            'SYNC_UPDATE',
            'USER_UPDATE',
            'DESACTIVATE',
            'REACTIVATE'
        )
    )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  ROW_FORMAT = DYNAMIC;
