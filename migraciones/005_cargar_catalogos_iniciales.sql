-- Fase 4: valores oficiales informados por el negocio.
-- INSERT IGNORE hace la carga idempotente y no reactiva valores desactivados.

INSERT IGNORE INTO Log_Imp_Certificacion_Catalogos (
    tipo,
    valor,
    descripcion,
    orden,
    activo,
    creado_por,
    fecha_creacion
) VALUES
    ('estado_certificacion', 'Liberado', NULL, 10, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Pendiente DI', NULL, 20, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Pendiente entrega de Etiquetas', NULL, 30, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Proceso pegado de etiqueta', NULL, 40, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Proceso de certificación', NULL, 50, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Espera resultado laboratorio tipo', NULL, 60, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Espera resultado laboratorio', NULL, 70, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Espera de la Liberación', NULL, 80, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Solicitud de inspección enviada', NULL, 90, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Productos no llegaron', NULL, 100, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Inspección confirmada', NULL, 110, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'No necesita inspección', NULL, 120, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('estado_certificacion', 'Sin certificar', NULL, 130, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),

    ('pegar_etiquetas', 'No', NULL, 10, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('pegar_etiquetas', 'Qr', NULL, 20, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('pegar_etiquetas', 'Qr, Placa advertencias', NULL, 30, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('pegar_etiquetas', 'Qr, Placa caracteristica', NULL, 40, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('pegar_etiquetas', 'Qr, Placa caracteristica y advertencias', NULL, 50, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),

    ('prioridad', 'PRIORIDAD', NULL, 10, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('prioridad', 'VENTILACION', NULL, 20, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('prioridad', 'CALEFACCION', NULL, 30, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('prioridad', 'SIN PRIORIDAD', NULL, 40, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),

    ('laboratorio', 'INGCER', NULL, 10, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('laboratorio', 'GASEI-ARBA-INGCER', NULL, 20, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('laboratorio', 'LENOR', NULL, 30, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP),
    ('laboratorio', 'CESMEC', NULL, 40, 1, 'MIGRACION_FASE_4', CURRENT_TIMESTAMP);
