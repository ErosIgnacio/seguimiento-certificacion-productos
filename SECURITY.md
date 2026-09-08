# Seguridad

## Información sensible

Este repositorio no debe contener credenciales, archivos de configuración
reales, exportaciones de productos, reportes operacionales ni instaladores que
incorporen secretos.

No publique:

- `config.json`, variantes locales o archivos `.env`;
- `config.dat` o sus temporales;
- `Certificacion.csv` y archivos de `reportes/`;
- instaladores de `installer/output/`, porque pueden transportar configuración
  de aprovisionamiento;
- logs, volcados de base de datos o capturas con datos reales.

Use `config.example.json` únicamente como plantilla. Nunca sustituya sus valores
de ejemplo por credenciales reales dentro del repositorio.

## Reporte de vulnerabilidades

No abra un issue público con contraseñas, datos operacionales o detalles que
permitan acceder a infraestructura. Informe el problema por el canal privado de
soporte o seguridad definido por la organización propietaria del repositorio.

Si una credencial llega a publicarse, elimínela del historial y rótela de
inmediato. Quitar solamente el archivo en un commit posterior no elimina el
secreto de los commits anteriores.
