# Decisiones de implementación — fase 1

## Reutilización del proyecto

Se revisaron por completo los archivos activos de la carpeta `Log_Imp`:
`crud_programacion_v12.py`, `crud_entregas.py`, `MASTER_ETL_V3.py`,
`ETL_entrega_v2.py`, `DownloadSC.py`, `config.json` y `README.TXT`, además de la
estructura y los usos de `Log_Imp_Auditoria`.

Patrones conservados:

- PyMySQL y consultas parametrizadas con `%s`.
- `config.json` existente, sin otra copia ni credenciales dentro del código.
- usuario capturado por login, con `strip()` y mayúsculas; el servicio recibe ese
  valor y no crea otro sistema de autenticación.
- commit/rollback explícitos, cursores acotados y cierre seguro de conexión.
- prefijo de tablas `Log_Imp_*`.
- auditoría por cada campo realmente cambiado.

Los `get_conn()` actuales están definidos dentro de scripts con efectos de
importación (inicialización Tk/ejecución de aplicación) y algunos conservan
configuración embebida; por eso no son módulos reutilizables con seguridad. El
nuevo backend tiene un único adaptador de conexión que lee el `config.json`
existente. No se importó un CRUD ni se creó otro archivo de credenciales.

`Log_Imp_Auditoria` no fue modificada ni utilizada. La nueva auditoría comparte
la conexión y la transacción del producto; no abre una conexión independiente.

## Clave y tipos

Los tipos reales observados fueron:

- `N_Contenedor VARCHAR(50)` y `OC VARCHAR(50)`.
- `GD INT` y `Articulo INT`; se reservaron 11 caracteres para los 10 dígitos y
  un posible signo, sin truncamiento.
- `Cant_GD INT`, por lo que `unidades` es `INT`.
- fechas operacionales son `DATE`.
- `Descripcion VARCHAR(50)`.
- `Destino MEDIUMTEXT`; `compartido` conserva `MEDIUMTEXT` para no introducir
  truncamientos.
- `prioridad` conserva `VARCHAR(267)`, longitud ya usada por el campo homónimo
  operativo; cantidades de muestras son `INT UNSIGNED` bajo el supuesto de que
  no existen cantidades negativas.

La longitud declarada del ID es `50 + 50 + 11 + 11 + 3 = 125`. Con `utf8mb4`, la
PK ocupa como máximo 500 bytes y la clave única compuesta 488 bytes, ambos bajo
el límite InnoDB detectado de 3.072 bytes. No existe un segundo índice sobre el
ID además de la PK.

MySQL calcula el ID con `UPPER(TRIM(...))`. Python calcula previamente el mismo
valor sólo para validar, agrupar y buscar; nunca incluye `id_certificacion` en
un `INSERT` o `UPDATE`. Los cuatro componentes se persisten normalizados y son
inmutables.

La DDL incorpora `CHECK` de claves no vacías/marcadores inválidos y sin `_` como
defensa adicional. El servicio detecta esos casos antes de cualquier escritura;
si hay `_`, detiene toda la sincronización y revierte.

## Origen y duplicados

Se mantuvo el `LEFT JOIN` solicitado. Esto conserva visibilidad de contenedores
del departamento que aún no poseen producto en flujo. Esas filas aparecen en el
resumen como claves incompletas y se omiten; funcionalmente sólo las filas con
contenedor, OC, GD y SKU válidos alcanzan la persistencia. `OP` sigue siendo
`lifc.GD`; `numero_guia_despacho` es un campo manual distinto.

Antes de escribir se normaliza todo el lote. Repeticiones con los 14 campos
automáticos equivalentes se consolidan. Si una clave repite con cualquier valor
automático distinto, no se elige una fila: se informa el campo y sus valores,
se detiene el lote y se hace rollback. También se anticipan colisiones por
mayúsculas/acentos compatibles con `utf8mb4_0900_ai_ci`.

## Persistencia y control de cambios

La implementación evita el `ON DUPLICATE KEY UPDATE ... VALUES()` obsoleto. Bajo
una única transacción carga los existentes con `FOR UPDATE` y decide:

- nuevo: inserta los 14 automáticos, controles de creación y deja los 16 campos
  manuales en `NULL`; después registra un `SYNC_CREATE` con snapshot JSON;
- existente: compara sólo los diez automáticos actualizables y genera un
  `UPDATE` dinámico con los que cambiaron, más la última sincronización;
- idéntico: sólo actualiza `fecha_ultima_sincronizacion`, sin auditoría;
- ausente del origen: no lo toca, elimina ni desactiva.

No se modifican claves, campos manuales, `activo`, `creado_por`,
`fecha_creacion`, `actualizado_por` ni `fecha_actualizacion` durante una
sincronización. Los dos últimos quedan disponibles para el futuro CRUD manual.

Cada cambio automático real genera un `SYNC_UPDATE`. Las acciones futuras
`USER_UPDATE`, `DESACTIVATE` y `REACTIVATE` están permitidas por la tabla y el
módulo de auditoría, pero esta fase no implementa todavía la GUI que las origina.
No hay borrado físico ni cascada sobre la auditoría.

## Manejo de errores

La función pública devuelve siempre un resumen estructurado. Las validaciones de
lote y excepciones MySQL producen rollback; si ya se contabilizaban operaciones,
se trasladan a `operaciones_revertidas` y los contadores confirmados vuelven a
cero. La salida `confirmado` evita interpretar intentos revertidos como éxito.

Se usa `logging` estándar y errores estructurados. La aplicación anfitriona puede
configurar su handler; el CLI muestra errores en consola sin registrar secretos.
