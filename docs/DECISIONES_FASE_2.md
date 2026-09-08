# Decisiones de implementación — interfaz y gestión manual

## Alcance implementado

La interfaz usa CustomTkinter 5.2.2 y Tk 8.6, manteniendo la estética y patrones
de los CRUD existentes. Incluye:

- usuario conectado visible en el encabezado;
- métricas de total, activos, pendientes, gestionados e inactivos;
- filtros parametrizados por búsqueda libre, estado, laboratorio y vigencia;
- tabla paginada de 100 filas por página;
- previsualización y sincronización con resumen completo;
- edición de los 16 campos gestionados por usuario;
- desactivación y reactivación lógica, sin eliminación física;
- consulta de auditoría con detalle de valores;
- consultas MySQL en hilos de trabajo para no bloquear Tkinter.

La tabla y el editor muestran claves y campos automáticos sólo como contexto. El
servicio rechaza cualquier campo fuera de `CAMPOS_USUARIO`, aunque una llamada
externa intente omitir la protección visual.

## Integración con login

No se creó otro login. La función:

```python
iniciar_interfaz_certificacion(usuario, parent=ventana_actual)
```

recibe el mismo `self.usuario` en mayúsculas que ya manejan los CRUD. El script
manual acepta `--usuario` sólo como mecanismo de prueba controlada.

Con `parent` crea un `CTkToplevel`, evitando una segunda raíz o un `mainloop`
anidado. Sin `parent` crea la aplicación independiente usada por el lanzador.

## Gestión y auditoría

Una edición manual bloquea el registro con `SELECT ... FOR UPDATE`, calcula los
cambios reales, actualiza sólo esos campos y registra una auditoría `USER_UPDATE`
por campo. Producto y eventos comparten conexión, commit y rollback.

`DESACTIVATE` y `REACTIVATE` cambian únicamente `activo` y los controles de
edición manual, con un evento de auditoría sobre el campo `activo`. No existen
acciones `DELETE`.

Las fechas aceptan `AAAA-MM-DD`; el servicio también reconoce `DD-MM-AAAA` para
compatibilidad con los CRUD actuales. Las cantidades de muestras deben ser
enteros no negativos. Vacíos se convierten a `NULL`. Los textos respetan las
longitudes de la migración y los comentarios se validan por bytes UTF-8 debido
al límite real del tipo `TEXT`.

## Próximos pasos sugeridos

1. Acordar catálogos formales para estado, laboratorio, prioridad y etiquetas.
2. Definir roles/permisos si algunos usuarios sólo deben consultar.
3. Integrar el botón que llama
   `iniciar_interfaz_certificacion(self.usuario, parent=self)` en la ventana
   principal de `Log_Imp`.
4. Validar con usuarios operativos los nombres, orden y filtros de columnas.
5. Incorporar exportación Excel y alertas de fechas sólo después de validar el
   flujo operativo y los catálogos.
