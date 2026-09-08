# Decisiones de implementación — catálogos, filtros y calidad

## Alcance implementado

La fase 3 agrega una tabla de catálogos administrables, nuevos filtros en la
interfaz y controles de calidad de solo lectura. No modifica el modelo de la
tabla principal ni ejecuta sincronizaciones automáticas.

## Catálogos

`Log_Imp_Certificacion_Catalogos` administra estos tipos:

- `estado_certificacion`;
- `laboratorio`;
- `prioridad`;
- `pegar_etiquetas`.

No se usa `ENUM`. La combinación `(tipo, valor)` es única y los registros se
desactivan mediante `activo`; no existe eliminación física. Cada alta, edición o
cambio de vigencia conserva usuario y fechas de control usando la conexión
PyMySQL existente con commit/rollback.

La migración no carga valores iniciales porque los catálogos deben ser definidos
por el negocio. Mientras un tipo no tenga valores activos, el editor mantiene
compatibilidad permitiendo texto. Desde el primer valor activo, el backend exige
que las nuevas ediciones seleccionen un valor activo. Los valores históricos
siguen visibles en filtros y en el registro que ya los contiene.

## Filtros

Además de búsqueda, estado, laboratorio y vigencia se incorporaron:

- prioridad;
- departamento;
- pendientes o gestionados;
- rango de ETA desde/hasta.

Las fechas se normalizan en el servicio y se rechaza un rango invertido. Los
valores nunca se interpolan en SQL; las columnas y reglas disponibles son listas
cerradas del código y todos los valores usan parámetros `%s`.

## Calidad de datos

La ventana Calidad ejecuta consultas `SELECT` y presenta conteos y hasta 200
ejemplos para estas reglas:

- fecha de certificación anterior a fecha de inspección;
- muestras recepcionadas superiores a muestras retiradas;
- número de certificado sin fecha de certificación;
- fecha de certificación sin estado.

Un mismo producto puede aparecer en más de una regla, por lo que el total es el
número de hallazgos y no necesariamente el número de productos diferentes. La
ventana no corrige ni elimina datos.

## Verificación

- 39 pruebas aisladas aprobadas; 5 de integración omitidas por defecto.
- 5 pruebas MySQL aprobadas usando exclusivamente tablas `TEMPORARY`.
- Smoke test aprobado para `CTk`, `CTkToplevel`, Catálogos y Calidad.
- MySQL detectado: 8.4.8, `utf8mb4_0900_ai_ci`, InnoDB DYNAMIC.
- Migración 003 aplicada y verificada el 13 de agosto de 2026.

Los comandos de desarrollo de esta fase no invocaron la sincronización real.
Al cierre, la base contenía 2.435 productos y 2.435 eventos `SYNC_CREATE`
atribuidos a `EROMOREN`, creados entre las 14:53 y 15:12 del 13 de agosto de
2026. El servicio de listado devolvió 2.435 filas, 100 visibles en la primera de
25 páginas.

## Decisiones pendientes

- Definir con negocio los valores y el orden inicial de cada catálogo.
- Definir roles antes de restringir administración de catálogos.
- Acordar columnas y formato antes de incorporar exportación Excel.
- Definir una fecha de vencimiento real antes de implementar alertas de vigencia.
