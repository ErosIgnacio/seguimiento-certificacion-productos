-- Fase 10: departamentos administrables incluidos en la sincronización.
-- INSERT IGNORE conserva la vigencia decidida por el usuario en ejecuciones futuras.

INSERT IGNORE INTO Log_Imp_Certificacion_Catalogos (
    tipo,
    valor,
    descripcion,
    orden,
    activo,
    creado_por,
    fecha_creacion
) VALUES
    ('codigo_depto', '700', 'Incluido en la sincronización', 10, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '701', 'Incluido en la sincronización', 20, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '702', 'Incluido en la sincronización', 30, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '703', 'Incluido en la sincronización', 40, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '720', 'Incluido en la sincronización', 50, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '726', 'Incluido en la sincronización', 60, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '727', 'Incluido en la sincronización', 70, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '730', 'Incluido en la sincronización', 80, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP),
    ('codigo_depto', '669', 'Incluido en la sincronización', 90, 1, 'MIGRACION_FASE_10', CURRENT_TIMESTAMP);
