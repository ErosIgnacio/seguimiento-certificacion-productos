# Decisiones de implementación — edición masiva Nave-OC-SKU

## Listado principal

La tabla de la interfaz ya no presenta `id_certificacion` ni
`fecha_ultima_sincronizacion`. En sus posiciones se muestran `nave` y
`fecha_programacion`. El ID continúa llegando en la consulta y se usa únicamente
como `iid` interno del `Treeview`, por lo que seleccionar, editar, auditar y
cambiar vigencia no dependen de una columna visible.

## Llave de agrupación

La migración 006 agrega `clave_edicion_masiva VARCHAR(123)` como columna
`GENERATED ALWAYS ... STORED` e índice no único. Se deriva de Nave, OC y SKU
normalizados con `UPPER(TRIM(...))`.

La representación usa un prefijo de longitud `NNN:` antes de cada componente.
Así, dos combinaciones distintas no colisionan aunque en el futuro aparezcan
guiones bajos, barras u otros separadores. La longitud máxima es:

- Nave: 50;
- OC: 50;
- SKU: 11;
- tres prefijos de cuatro caracteres: 12;
- total: 123 caracteres, hasta 492 bytes con `utf8mb4`.

La columna no se muestra en el listado. Al ser generada, cambia automáticamente
si una sincronización actualiza `nave`; OC y SKU siguen siendo componentes
inmutables de la clave primaria del producto.

## Operación masiva segura

El usuario abre **Editar masivo** desde un producto seleccionado. El backend
obtiene el grupo actual mediante la llave generada y cuenta activos e inactivos.
El formulario masivo abre todos los campos vacíos y no exige selectores
adicionales: cada valor ingresado se aplica al grupo y cada campo vacío conserva
el dato que tenga cada producto. En esta modalidad un campo vacío no se utiliza
para limpiar valores a `NULL`.

Al confirmar, el backend vuelve a resolver la llave, bloquea todas las filas del
grupo con `FOR UPDATE` en orden de ID, calcula diferencias por producto y:

- actualiza solo campos gestionados por el usuario;
- conserva campos automáticos, claves, vigencia y campos manuales no marcados;
- incluye los productos inactivos que pertenezcan al mismo grupo;
- registra `USER_UPDATE` por cada campo realmente modificado y producto;
- hace commit conjunto o rollback conjunto de productos y auditoría.

## Cambio de navegación

Se agregó **Editar masivo** junto a **Editar seguimiento** y se retiró el botón
**Revisar calidad**. El servicio de diagnóstico de calidad se conserva en el
backend por compatibilidad, pero ya no forma parte del flujo visible.

Los anchos del listado se compactaron a 1.460 píxeles base y todas las columnas
pueden estirarse. Así el espacio adicional se reparte entre ellas en lugar de
concentrarse en Nave y Descripción; cada una conserva además un ancho mínimo.

## Verificación

Los datos reales inspeccionados tenían una longitud máxima de Nave de 22
caracteres, sin nulos, vacíos, `_` ni `|`. En los 2.681 productos existentes se
detectaron 2.612 grupos Nave-OC-SKU.

La fase agrega pruebas unitarias para selección parcial, conservación de otros
grupos, inclusión de inactivos, ausencia de cambios y rollback. Las pruebas
MySQL usan tablas `TEMPORARY` y verifican la columna generada, el agrupamiento,
la auditoría por fila/campo y el rollback real.
