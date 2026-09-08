# Seguimiento de Certificación de Productos

Aplicación de escritorio en Python para sincronizar y gestionar la certificación
de productos importados. Incluye interfaz CustomTkinter, persistencia MySQL con
PyMySQL, auditoría transaccional, edición masiva, catálogos configurables e
instalador MSI para Windows.

El backend puede integrarse en `Log_Imp` o ejecutarse de manera independiente.
En ambos casos utiliza automáticamente el usuario de la sesión de Windows, sin
mostrar una pantalla de login.

## Componentes

- `certificacion/configuracion.py`: localiza la configuración JSON en desarrollo,
  lee la configuración DPAPI del MSI y crea la conexión PyMySQL.
- `certificacion/configuracion_segura.py`: protege credenciales instaladas con
  Windows DPAPI y define las rutas de datos y logs por usuario.
- `certificacion/validaciones.py`: normalización de claves, construcción esperada
  del ID, claves incompletas, `_`, duplicados idénticos/conflictivos y colisiones
  compatibles con la collation del proyecto.
- `certificacion/datos.py`: consulta de origen y operaciones de sincronización.
- `certificacion/datos_productos.py`: consultas y persistencia del CRUD manual.
- `certificacion/gestion.py`: validación y transacciones de edición individual,
  masiva y vigencia.
- `certificacion/catalogos.py`: administración transaccional de catálogos.
- `certificacion/interfaz.py`: interfaz CustomTkinter integrada al usuario.
- `certificacion/sincronizacion.py`: servicio transaccional independiente de GUI.
- `certificacion/csv_historico.py`: lectura por streaming y validación del CSV.
- `certificacion/carga_historica.py`: comparación e importación histórica auditada.
- `certificacion/auditoria.py`: auditoría en la misma transacción que el producto.
- `certificacion/migraciones.py`: prevalidación y runner controlado de las DDL.
- `migraciones/`: preconsulta y las siete migraciones SQL completas.
- `scripts/`: diagnóstico del origen y aplicación controlada de migraciones.
- `tests/`: pruebas unitarias y pruebas MySQL con tablas `TEMPORARY`.

## Ejecución

Todos los ejemplos deben ejecutarse desde la raíz que contiene las carpetas
`certificacion`, `migraciones`, `scripts` y `tests`.

### Preparación del entorno

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .\config.example.json .\config.json
```

Complete únicamente el `config.json` local. Este archivo está excluido de Git y
nunca debe incorporarse al repositorio.

El módulo localiza primero el argumento `--config`, luego la variable
`LOG_IMPORTADO_CONFIG`. La instalación MSI usa la configuración DPAPI del perfil
de Windows. Como compatibilidad para un `onedir` manual, el EXE también puede
leer un `config.json` junto al ejecutable; en desarrollo revisa la raíz del
proyecto y el directorio actual. Puede apuntarse al archivo existente con:

```powershell
$env:LOG_IMPORTADO_CONFIG = "C:\ruta\Log_Imp\config.json"
```

La aplicación no imprime credenciales. Consulte `SECURITY.md` antes de crear un
commit o distribuir un instalador.

### 1. Prevalidar y aplicar migraciones

La primera orden sólo lee metadatos y no crea tablas:

```powershell
python -m scripts.aplicar_migraciones
```

Después de revisar el resultado, la creación explícita es:

```powershell
python -m scripts.aplicar_migraciones --confirmar
```

Las migraciones se ejecutan en orden: tabla principal, auditoría de productos,
catálogos, auditoría de catálogos, carga inicial, llave de edición masiva y
departamentos iniciales de sincronización. En
MySQL cada DDL es atómica, pero varias DDL no forman una transacción conjunta.
El runner omite la migración 006 cuando ya detecta su columna e índice completos,
y verifica los IDs, índices, tablas, los 26 valores operacionales y los 9
departamentos iniciales.

### 2. Previsualizar y sincronizar

La previsualización consulta y valida todo, calcula inserciones/actualizaciones y
hace rollback sin escribir:

```powershell
python -m certificacion
```

Los contadores de este modo significan **se insertarían/se actualizarían**. Sólo
`confirmado=true` identifica una sincronización con commit.

También puede ejecutarse directamente desde el botón **Run Python File** del
editor o por ruta:

```powershell
python certificacion\__main__.py
```

La sincronización real requiere una confirmación explícita:

```powershell
python -m certificacion --aplicar
```

Desde la interfaz se llama directamente con el usuario ya resuelto:

```python
from certificacion import sincronizar_certificaciones

resumen = sincronizar_certificaciones(self.usuario)
```

El servicio captura las excepciones, ejecuta rollback, cierra la conexión y las
reporta en `resumen["errores"]`. Sólo `confirmado=True` significa que hubo commit.

### 3. Diagnóstico del origen

```powershell
python -m scripts.diagnosticar_origen
```

Es una operación de sólo lectura. Los detalles se limitan a 100 ejemplos en la
salida para que un problema masivo no desborde el reporte.

### 4. Previsualizar la carga histórica

La carga de `Certificacion.csv` siempre se debe previsualizar primero:

```powershell
python -m scripts.importar_certificacion_csv --archivo .\Certificacion.csv --usuario OPERADOR --config .\config.json
```

El comando compara el archivo completo con MySQL sin escribir. Reconstruye
`id_certificacion` desde `Container`, `OC`, `OP` y `Sku`, porque el CSV no trae
una columna física con ese identificador.

La aplicación real requiere `--aplicar`. Además, si existen claves del CSV que
no están en MySQL, se bloquea por defecto. Sólo después de revisar y aceptar una
carga parcial se puede añadir `--permitir-csv-sin-db`:

```powershell
python -m scripts.importar_certificacion_csv --archivo .\Certificacion.csv --usuario OPERADOR --config .\config.json --aplicar --permitir-csv-sin-db
```

Los campos manuales, la vigencia y sus auditorías se escriben en una sola
transacción. La carga no modifica campos automáticos ni crea productos faltantes.
Los resultados y diagnósticos generados por este proceso son información
operacional y deben permanecer fuera del repositorio.

### 5. Abrir la interfaz

Primero deben existir las tablas de las migraciones. Sin argumentos abre la
aplicación directamente y obtiene el usuario de la sesión de Windows:

```powershell
python -m scripts.iniciar_interfaz
```

También funciona por ruta directa:

```powershell
python scripts\iniciar_interfaz.py
```

`--usuario OPERADOR` sigue disponible únicamente como reemplazo explícito para
pruebas o soporte.

Para integrarla en el CRUD que ya conoce al usuario:

```python
from certificacion.interfaz import iniciar_interfaz_certificacion

iniciar_interfaz_certificacion(self.usuario, parent=self)
```

Si la integración no entrega un usuario, también se obtiene automáticamente de
Windows. Este valor identifica al responsable en la auditoría, pero no reemplaza
un sistema de autorización por roles ni constituye una autenticación adicional.

### 6. Construir el instalador MSI

La versión se define en `certificacion/version.py`. El proceso completo ejecuta
las pruebas, crea el `onedir` en una carpeta temporal, restaura WiX Toolset 5.0.2,
construye el MSI y calcula su hash SHA-256:

```powershell
.\scripts\build_msi.ps1
```

El resultado se guarda en:

```text
installer\output\CertificacionCarga-<version>.msi
installer\output\CertificacionCarga-<version>.msi.sha256
```

La instalación es por usuario y no requiere permisos de administrador. Instala
la carpeta completa en:

```text
%LOCALAPPDATA%\Programs\Cencosud\certificacion_carga
```

Crea accesos directos **Certificación de Productos** en el Escritorio y en el
menú Inicio, dentro de `Cencosud`. Durante la instalación, el JSON temporal se
valida, cifra para la cuenta actual mediante Windows DPAPI y elimina. La
aplicación utiliza luego:

```text
%LOCALAPPDATA%\Cencosud\CertificacionCarga\config.dat
%LOCALAPPDATA%\Cencosud\CertificacionCarga\logs\certificacion_carga.log
```

El MSI contiene la configuración de aprovisionamiento antes de instalarse. Debe
tratarse como archivo confidencial y distribuirse sólo por canales corporativos.
DPAPI protege la copia instalada, no el contenido del MSI original.

## Pruebas

Pruebas predeterminadas, totalmente en memoria y sin conexión a producción:

```powershell
python -m unittest discover -s tests -v
```

Pruebas de integración de DDL, clave generada, restricciones, preservación de
campos manuales y rollback conjunto. Sólo crean tablas `TEMPORARY` en la sesión y
éstas desaparecen al cerrarse la conexión:

```powershell
$env:LOG_IMPORTADO_RUN_MYSQL_TESTS = "1"
python -m unittest tests.test_mysql_temporal -v
```

## Estado de la entrega

- MySQL detectado: `8.4.8`.
- Base: `utf8mb4`, collation `utf8mb4_0900_ai_ci`.
- InnoDB: `DYNAMIC`, página de 16 KiB, índice máximo de 3.072 bytes.
- Longitudes declaradas: contenedor 50, OC 50, GD 11 y SKU 11.
- `id_certificacion`: `VARCHAR(125)` generado y almacenado; máximo 500 bytes.
- Las cuatro tablas destino quedaron creadas y verificadas. Se cargaron 13
  estados, 5 opciones de etiquetas, 4 prioridades y 4 laboratorios.
- La tabla visual muestra `nave` y `fecha_programacion`; conserva el ID como
  identificador interno de la fila, sin mostrar el ID ni la última sincronización.
- La interfaz denomina **Certificables** a los productos con `activo = 1` e
  **Inactivos** a los que aún no se revisan o no requieren certificación.
- La interfaz incorpora filtros avanzados, paginación, edición individual,
  edición masiva Nave-OC-SKU, vigencia lógica, auditoría, catálogos y
  sincronización sin bloquear el hilo gráfico.
- La edición masiva abre los campos vacíos: todo valor que el usuario ingrese se
  aplica al grupo y los campos que deje vacíos se conservan. Incluye registros
  activos e inactivos y audita cada diferencia por producto dentro de la misma
  transacción.
- Los cambios de catálogos tienen auditoría transaccional independiente. Quitar
  una opción la desactiva sin borrar productos ni historial.
- Los departamentos incluidos en la sincronización se administran como el
  catálogo `codigo_depto`. Solo sus valores activos forman el `IN` parametrizado
  de la consulta de origen; sin departamentos activos la sincronización se
  detiene y revierte.
- Los dos campos de fecha tienen calendario y las ventanas secundarias se
  adaptan al tamaño de la pantalla manteniendo visibles sus botones.
- Sólo `Liberado` clasifica un producto activo como gestionado. Al asignar
  `No necesita inspección`, la misma transacción deja el producto inactivo y lo
  excluye de gestionados.
- Los productos nuevos creados por una sincronización nacen inactivos. El
  usuario activa explícitamente sólo aquellos que requieren certificación.
- Una edición individual o masiva con cambios reales convierte automáticamente
  cada producto inactivo afectado en certificable y registra `REACTIVATE` en la
  misma transacción. Si el estado resultante es `No necesita inspección`, el
  producto permanece inactivo.
- El botón **Revisar calidad** fue retirado del flujo de la interfaz.
- La ejecución independiente e integrada omite el login y utiliza la cuenta de
  Windows. El argumento `--usuario` se conserva como reemplazo de soporte.
- La carga inicial reutiliza una única conexión, obtiene una sola vez los
  catálogos activos y consolida en una consulta los cinco catálogos históricos.
  Las ediciones recargan sólo listado y métricas; los catálogos se recargan
  únicamente después de administrarlos.
- En la medición de lectura del 7 de septiembre de 2026, la carga inicial pasó
  de 3,91 a 2,15 segundos (aproximadamente 45 % menos). El tiempo final depende
  de la red, latencia de RDS, filtros y volumen de datos.
- La sincronización persiste productos, fechas de última sincronización y
  auditorías mediante lotes. Un bloqueo nombrado de MySQL impide que dos
  instancias sincronicen simultáneamente.
- Un benchmark con tablas temporales y 2.681 productos tardó 6,97 segundos para
  crearlos y 4,16 segundos para procesar 376 actualizaciones, 2.305 registros
  sin cambios y 576 eventos de auditoría.
- Estado de pruebas de la fase 13: 90 pruebas aisladas aprobadas y 14 pruebas
  MySQL temporales aprobadas.
- Instalador generado: `CertificacionCarga-1.0.0.msi`, 22,98 MB, con accesos
  directos de Escritorio y menú Inicio verificados en sus tablas internas.
- El MSI sigue el modelo `perUser` de `ProgramacionContenedores`. La validación
  ICE informa las mismas categorías conocidas (`ICE38`, `ICE43`, `ICE64`,
  `ICE60` e `ICE91`) por instalar el árbol `onedir` bajo el perfil del usuario.
  El paquete aún no tiene firma digital corporativa.
Las decisiones técnicas están en
`docs/DECISIONES_FASE_1.md`, `docs/DECISIONES_FASE_2.md`,
`docs/DECISIONES_FASE_3.md`, `docs/DECISIONES_FASE_4.md`,
`docs/DECISIONES_FASE_5.md`, `docs/DECISIONES_FASE_6.md`,
`docs/DECISIONES_FASE_7.md`, `docs/DECISIONES_FASE_8.md`,
`docs/DECISIONES_FASE_10.md`, `docs/DECISIONES_FASE_11.md`,
`docs/DECISIONES_FASE_12.md` y `docs/DECISIONES_FASE_13.md`.

Los diagnósticos, cargas históricas, reportes e instaladores con configuración
real permanecen excluidos de Git por contener información operacional.
