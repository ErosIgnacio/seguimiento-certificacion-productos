# Decisiones de implementación — catálogos oficiales y usabilidad

## Catálogos oficiales

La migración 005 carga, de forma idempotente, 26 valores entregados por el
negocio:

- 13 estados de certificación;
- 5 opciones de pegar etiquetas;
- 4 prioridades;
- 4 laboratorios.

La escritura se conserva como fue informada; por ejemplo, `Liberado`, `Qr` y
`Proceso de certificación`. Las comparaciones ignoran mayúsculas y minúsculas,
pero una edición guarda la presentación oficial del catálogo.

`INSERT IGNORE` evita duplicar valores al volver a ejecutar el runner y no
reactiva opciones que un usuario haya quitado posteriormente.

## Agregar y quitar laboratorios

La ventana Catálogos permite crear laboratorios y administrar también los otros
tipos. La acción visible **Quitar opción** cambia `activo` a cero:

- no ejecuta `DELETE`;
- no borra el valor de productos existentes;
- impide seleccionarlo en nuevas ediciones;
- permite reactivarlo posteriormente.

## Auditoría independiente

La migración 004 crea
`Log_Imp_Certificacion_Catalogos_Auditoria`. Registra:

- `CATALOG_CREATE` con snapshot inicial;
- `CATALOG_UPDATE`, una fila por campo realmente cambiado;
- `CATALOG_DEACTIVATE`;
- `CATALOG_REACTIVATE`.

La escritura del catálogo y su auditoría usa la misma conexión y transacción.
Si el evento falla, el cambio del catálogo se revierte. El botón **Ver
historial** muestra el registro seleccionado o todo el historial si no hay una
selección.

La carga inicial de la migración se identifica mediante
`creado_por = MIGRACION_FASE_4`; no genera eventos que aparenten una acción de
usuario.

## Ingreso de fechas

`fecha_inspeccion` y `fecha_certificacion` incorporan un botón de calendario.
Permite:

- navegar por mes;
- seleccionar un día;
- usar la fecha actual;
- limpiar el valor.

El resultado se escribe como `AAAA-MM-DD`. Se mantiene la posibilidad de
escribir manualmente para no limitar a usuarios de teclado. El selector fue
implementado con Tk/CustomTkinter y biblioteca estándar, sin dependencias nuevas.

## Ventanas y scroll

Editor, Catálogos, Calidad y ambas auditorías calculan su geometría usando el
tamaño real de la pantalla y reservan espacio inferior para la barra de tareas.
Los botones permanecen fuera del área desplazable. El formulario de seguimiento
continúa dentro de `CTkScrollableFrame`, por lo que las 16 casillas pueden
recorrerse sin ocultar Guardar o Cancelar.

## Verificación

- 46 pruebas aisladas aprobadas; 8 de MySQL se omiten por defecto.
- 8 pruebas MySQL aprobadas con tablas `TEMPORARY`.
- Se comprobó el servicio exacto usado por Agregar y Quitar opción.
- Se comprobó rollback conjunto ante un fallo de auditoría.
- Smoke test gráfico aprobado para calendario y todas las ventanas secundarias.
- Migraciones 004 y 005 aplicadas y verificadas en MySQL 8.4.8.
