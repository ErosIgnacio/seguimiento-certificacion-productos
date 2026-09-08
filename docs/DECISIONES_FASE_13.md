# Decisiones de fase 13: instalador MSI

## Modelo replicado

Se adaptó el proceso utilizado por `ProgramacionContenedores`:

- PyInstaller 6.22.2 en modo `onedir` y `windowed`.
- WiX Toolset 5.0.2 fijado mediante `.config/dotnet-tools.json`.
- MSI x64 por usuario, sin requerir permisos administrativos.
- Instalación en `%LOCALAPPDATA%\Programs\Cencosud\certificacion_carga`.
- Acceso directo en Escritorio y menú Inicio `Cencosud`.
- Construcción en una ruta temporal única y limpieza segura al terminar.
- Hash SHA-256 junto al MSI.
- `UpgradeCode` estable y bloqueo de downgrade mediante `MajorUpgrade`.

La versión inicial del paquete es `1.0.0` y se mantiene en
`certificacion/version.py`. Antes de publicar una actualización debe cambiarse a
una versión superior de tres componentes.

## Configuración y logs

El `config.json` no se incorpora al `onedir`. El MSI lo transporta temporalmente
como `config.install.json`, invoca el ejecutable en modo de aprovisionamiento y
lo elimina después de cifrarlo con Windows DPAPI. La aplicación instalada lee:

```text
%LOCALAPPDATA%\Cencosud\CertificacionCarga\config.dat
```

El cifrado está vinculado a la cuenta de Windows que ejecuta la instalación. Los
logs rotativos se escriben en:

```text
%LOCALAPPDATA%\Cencosud\CertificacionCarga\logs\certificacion_carga.log
```

DPAPI protege la copia instalada, pero el MSI contiene el JSON necesario para el
aprovisionamiento. Por ello el instalador debe tratarse como confidencial y no
publicarse fuera de canales corporativos.

## Construcción

Desde la raíz del proyecto:

```powershell
.\scripts\build_msi.ps1
```

El script valida Python/Tk de 64 bits, dependencias, pruebas, ausencia de un
`config.json` en el `onedir`, creación del ejecutable, restauración de WiX,
creación del MSI y cálculo del hash.

Archivos generados:

```text
installer\output\CertificacionCarga-1.0.0.msi
installer\output\CertificacionCarga-1.0.0.msi.sha256
```

## Validación realizada

- 101 pruebas descubiertas: 87 aisladas aprobadas y 14 MySQL omitidas en la
  ejecución normal; las 14 pruebas MySQL ya se validaron separadamente.
- Cifrado y descifrado DPAPI real aprobado en Windows.
- Ejecutable `onedir` generado correctamente.
- MSI generado correctamente y tablas internas inspeccionadas.
- Accesos `DesktopShortcut` y `StartMenuShortcut` presentes.
- Acción `ProvisionProtectedConfig` presente y con parámetros ocultos.
- SHA-256 generado y coincidente.

El MSI no tiene todavía firma Authenticode. Debe firmarse con un certificado de
código aprobado por Cencosud antes de una distribución productiva.

## Validación ICE

El patrón heredado instala un árbol grande de archivos `onedir` dentro del perfil
del usuario. La validación ICE reporta `ICE38`, `ICE43`, `ICE64`, `ICE60` e
`ICE91`; son las mismas categorías observadas en el MSI de referencia. WiX
advierte expresamente que el cosechado `Files` dentro de paquetes por usuario no
supera estas reglas ICE.

Si Ciberseguridad exige un MSI sin esos hallazgos, la siguiente iteración deberá
cambiar el alcance a instalación por equipo o generar componentes con claves
HKCU individuales. Esa modificación puede requerir permisos administrativos y
debe acordarse antes de reemplazar el modelo solicitado.
