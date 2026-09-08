# Decisiones de implementación — clasificación de gestión

> Regla histórica reemplazada en la carga histórica del 25 de agosto de 2026.
> La regla vigente considera gestionado únicamente `Liberado`; al seleccionar
> `No necesita inspección`, el registro pasa a inactivo. La regla vigente está
> resumida en la sección «Estado de la entrega» del `README.md`.

## Estados terminales

Un producto activo se considera **Gestionado** solamente cuando
`estado_certificacion` corresponde, ignorando mayúsculas, minúsculas y espacios
exteriores, a uno de estos valores:

- `Liberado`;
- `No necesita inspección`.

Todo producto activo con estado vacío o con cualquier estado intermedio se
considera **Pendiente**. La misma definición se usa en las tarjetas superiores y
en el filtro Gestión, evitando diferencias entre el resumen y el listado.

La regla está centralizada en `ESTADOS_GESTIONADOS`; no se agregó una columna
redundante ni se actualizaron productos. La clasificación se calcula al consultar.

## Control de Calidad

> Nota de fase 8: este botón fue retirado de la interfaz por decisión funcional.
> La descripción siguiente se conserva únicamente como antecedente histórico.

El botón **Revisar calidad** era opcional para el flujo diario. Ejecutaba consultas
de solo lectura para detectar fechas invertidas, cantidades de muestras
inconsistentes y datos de certificación incompletos. No cambia estados, no marca
un producto como gestionado y no impide guardar.

Se mantiene como control preventivo porque puede detectar errores cuando los
usuarios comiencen a completar información. Puede ocultarse en una etapa
posterior sin afectar sincronización, edición ni auditoría.

## Verificación

- 48 pruebas aisladas aprobadas; 9 MySQL se omiten por defecto.
- 9 pruebas MySQL aprobadas usando tablas `TEMPORARY`.
- Estado productivo consultado sin escrituras: 2.435 activos, 2.435 pendientes,
  0 gestionados y 0 hallazgos de calidad al 25 de agosto de 2026.
