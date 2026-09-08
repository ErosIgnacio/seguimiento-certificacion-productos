# Preparación para publicación en GitHub

## Archivos publicables

El código, migraciones, pruebas, manifiesto WiX, especificación PyInstaller y
documentación técnica pueden incorporarse al repositorio.

Los siguientes elementos están excluidos mediante `.gitignore`:

- configuración y variables de entorno locales;
- datos y reportes operacionales;
- diagnósticos realizados contra producción;
- logs y cachés de Python;
- entornos virtuales;
- carpetas `build`, `dist` e `installer/output`;
- MSI, ZIP y archivos de hash generados.

## Verificación antes del primer push

Antes de confirmar el primer commit se debe revisar la lista completa de
archivos que Git incorporará. La revisión debe confirmar que no aparezcan:

```text
config.json
Certificacion.csv
reportes/
installer/output/
*.msi
*.zip
*.log
config.dat
```

También debe buscarse cualquier hostname real, usuario de base de datos,
contraseña, token, clave privada o identificador operacional dentro del diff.

## Decisiones pendientes

- Definir si el repositorio será público o privado.
- Elegir una licencia antes de crear `LICENSE`.
- Rotar las credenciales que hayan sido compartidas fuera de un gestor seguro.
- Definir el canal privado para reportes de seguridad.
- Firmar instaladores productivos con un certificado corporativo.

## Automatización

El workflow `.github/workflows/tests.yml` ejecuta las pruebas aisladas en
Windows con Python 3.11 y 3.14. No configura una conexión MySQL y, por lo tanto,
no requiere secretos de GitHub. Dependabot revisa semanalmente dependencias de
Python y acciones de GitHub.
