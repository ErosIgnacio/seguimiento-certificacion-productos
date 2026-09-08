# Decisiones de implementación — ingreso sin contraseña

## Comportamiento

La ejecución independiente muestra una pantalla con un solo campo **Nombre de
usuario** y el botón **Ingresar**. También permite continuar con la tecla Enter.
No existe campo de contraseña y no se consulta una tabla de credenciales.

El nombre es obligatorio, admite hasta 100 caracteres y se normaliza con
`TRIM` y mayúsculas. Ese valor se muestra en el encabezado y se reutiliza en las
auditorías, sincronizaciones y cambios manuales.

## Formas de apertura

Sin argumentos, abre el ingreso:

```powershell
python -m scripts.iniciar_interfaz
```

Para pruebas controladas puede omitirse la pantalla:

```powershell
python -m scripts.iniciar_interfaz --usuario EROMOREN
```

Cuando otra ventana de Log_Importado ya conoce al usuario, debe entregarlo:

```python
iniciar_interfaz_certificacion(self.usuario, parent=self)
```

La integración con `parent` rechaza aperturas sin usuario para evitar un segundo
login dentro del sistema existente.

## Límite de seguridad

Este mecanismo identifica al responsable para efectos operativos y de
auditoría, pero no autentica su identidad. Al no existir contraseña, cualquier
persona con acceso al programa puede escribir otro nombre. Si posteriormente se
requieren permisos o trazabilidad con identidad verificada, deberá reutilizarse
una sesión autenticada de Log_Importado o un directorio corporativo.

## Verificación

- 52 pruebas aisladas aprobadas; 9 MySQL se omiten por defecto.
- Smoke test gráfico aprobado: entrada visible sin máscara de contraseña,
  normalización a `EROMOREN` y transición a la aplicación principal.
- No fue necesaria una migración ni se modificaron datos MySQL.
