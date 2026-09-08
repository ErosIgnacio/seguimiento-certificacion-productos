# Decisiones de fase 11: reactivación automática al editar

Una modificación manual indica que el usuario comenzó a gestionar el producto.
Por ello, cada registro inactivo que reciba al menos un cambio real en sus
campos de usuario pasa automáticamente a `activo = 1` (Certificable).

La reactivación:

- funciona en edición individual y masiva;
- se evalúa por registro, por lo que una fila sin diferencias no se reactiva;
- genera una auditoría `REACTIVATE` sobre el campo `activo`, además de las
  auditorías `USER_UPDATE` correspondientes;
- comparte transacción, commit y rollback con los cambios manuales;
- no modifica productos fuera del grupo Nave-OC-SKU en la edición masiva.

La regla `No necesita inspección` tiene prioridad. Si ese es el estado
resultante del registro, permanece inactivo aunque se hayan modificado otros
campos. Si un usuario cambia dicho estado por otro valor y existe una diferencia
real, el registro vuelve a ser Certificable.

No se requiere una migración adicional: se reutilizan la columna `activo`, el
servicio de cambio de vigencia y las acciones de auditoría existentes.
