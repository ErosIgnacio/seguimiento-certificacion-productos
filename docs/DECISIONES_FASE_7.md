# Decisiones de implementación — sincronización por lotes

## Problema observado

La sincronización original ejecutaba una sentencia MySQL por cada producto sin
cambios y una sentencia adicional por cada evento de auditoría. Con 2.681
productos se estimaron 3.962 viajes de red. La latencia observada de 146 ms por
sentencia elevaba el tiempo base a aproximadamente 9,6 minutos.

## Persistencia optimizada

El servicio continúa validando y bloqueando los registros dentro de una sola
transacción, pero primero clasifica todo el origen en nuevos, actualizados y sin
cambios. Luego ejecuta:

- `INSERT` multi-fila para productos nuevos;
- verificación por lote de los IDs generados por MySQL;
- `UPDATE` con `CASE`, agrupado por la combinación de campos realmente distintos;
- `UPDATE ... WHERE id_certificacion IN (...)` para fechas de sincronización;
- `INSERT` multi-fila para auditorías de creación y actualización.

Los campos gestionados por usuarios no participan en los `UPDATE`. Cada cambio
automático conserva una fila de auditoría y cualquier fallo sigue provocando
rollback conjunto de productos y eventos.

Los SQL masivos utilizan exclusivamente marcadores `%s`, incluso para valores
nulos y fechas de control. Esto permite que `PyMySQL.executemany` construya
sentencias multi-fila reales en lugar de repetir una consulta por registro.

## Exclusión entre instancias

Antes de una sincronización real se adquiere el bloqueo nombrado MySQL
`log_imp_certificacion_sincronizacion`. Una segunda instancia recibe un error
controlado y no inicia otra transacción. El bloqueo se libera explícitamente y,
como protección adicional, MySQL también lo libera al cerrar la conexión.

La previsualización no adquiere este bloqueo ni utiliza `FOR UPDATE` porque no
escribe datos.

## Verificación de rendimiento

Benchmark ejecutado contra tablas `TEMPORARY` en MySQL 8.4.8:

- creación y auditoría de 2.681 productos: 6,97 segundos;
- segunda sincronización con 376 actualizados, 2.305 sin cambios y 576 eventos:
  4,16 segundos;
- una segunda sincronización simultánea fue rechazada correctamente.

El tiempo incluye la persistencia transaccional del conjunto controlado, pero no
la consulta operacional de origen. En la medición productiva de solo lectura,
consultar y validar el origen tardó aproximadamente 2,6 segundos.

## Otras oportunidades

No se modificaron las tablas operacionales. Su consulta continúa haciendo
escaneos completos; cualquier índice sobre las tablas de origen debe ser revisado
por el responsable de esas cargas. También puede reducirse el tiempo de apertura
reutilizando una sola conexión para listado, métricas y catálogos.
