# Decisiones de fase 12: identidad de Windows y rendimiento

## Ingreso sin login

La aplicación ya no presenta una pantalla de ingreso. El usuario de auditoría
se resuelve al iniciar con este orden:

1. Variable `USERNAME` de la sesión de Windows.
2. `getpass.getuser()` como respaldo.
3. `os.getlogin()` como último respaldo.

El nombre se limpia, se convierte a mayúsculas y conserva el límite de 100
caracteres usado por la auditoría. La opción `--usuario` continúa disponible
como reemplazo explícito para pruebas o soporte, pero no es necesaria para el
uso normal de la interfaz ni del ejecutor `python -m certificacion`.

Los comandos de carga histórica mantienen `--usuario` obligatorio porque son
herramientas administrativas excepcionales y potencialmente masivas, no rutas
de ingreso cotidiano a la aplicación.

La cuenta del equipo sirve para atribuir cambios. No constituye por sí sola un
mecanismo de autorización por roles; si posteriormente se necesitan permisos
diferenciados, deberán definirse sobre esta identidad o sobre el directorio
corporativo.

## Optimización de la carga inicial

La apertura anterior realizaba por separado la consulta del listado y la carga
de catálogos, creando dos conexiones consecutivas a RDS. Además consultaba una
vez los catálogos activos y ejecutaba cinco consultas para recuperar valores
históricos.

La fase 12 realiza el listado, métricas y catálogos con una sola conexión. Los
catálogos activos se consultan una sola vez y los cinco conjuntos históricos se
recuperan con una consulta `UNION ALL`. Después de editar, activar, desactivar o
sincronizar productos sólo se recargan el listado y sus métricas. Los catálogos
se vuelven a solicitar únicamente cuando el usuario los administra.

No se mantiene una conexión global abierta: PyMySQL no debe compartirse entre
los hilos de trabajo de la interfaz, y una conexión persistente sería más
propensa a caducar o quedar inválida. Cada operación sigue teniendo conexión,
transacción, commit/rollback y cierre propios.

La medición de sólo lectura realizada el 7 de septiembre de 2026 sobre la base
configurada fue:

- antes: 3,912 segundos;
- después: 2,148 segundos;
- reducción observada: aproximadamente 45 %.

Es una medición puntual y puede variar por latencia de red, estado de RDS,
filtros y volumen.

## Configuración del ejecutable

Cuando se instala mediante MSI, el programa utiliza primero la configuración
protegida con DPAPI en el perfil del usuario. Un `config.json` ubicado junto al
`.exe` se mantiene solamente como compatibilidad para distribuciones `onedir`
manuales. Los argumentos `--config` y `LOG_IMPORTADO_CONFIG` continúan siendo
reemplazos explícitos para desarrollo o soporte.

## Validación

- 80 pruebas aisladas aprobadas.
- 14 pruebas de integración MySQL aprobadas con tablas `TEMPORARY`.
- Validación real de la consulta optimizada realizada en modo de sólo lectura.

Esta fase no modifica tablas ni requiere una nueva migración SQL. Para publicar
el cambio sólo es necesario reconstruir el ejecutable.
