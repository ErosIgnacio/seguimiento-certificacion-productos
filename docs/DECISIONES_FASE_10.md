# Decisiones de fase 10: certificables y departamentos configurables

## Terminología visible

La columna MySQL `activo` y las claves internas `activos`/`inactivos` se
conservan para no alterar el esquema ni los contratos del backend. En la
interfaz, `activo = 1` se presenta como **Certificable** o **Certificables**.
Los registros con `activo = 0` continúan presentándose como **Inactivos**.

## Alcance de departamentos

Los departamentos dejan de estar escritos como literales en la consulta de
origen. Se reutilizan las tablas:

- `Log_Imp_Certificacion_Catalogos`, con tipo `codigo_depto`;
- `Log_Imp_Certificacion_Catalogos_Auditoria`, para altas, cambios,
  desactivaciones y reactivaciones.

La migración `007_cargar_departamentos_sincronizacion.sql` registra como alcance
inicial los códigos `700`, `701`, `702`, `703`, `720`, `726`, `727`, `730` y
`669`. Usa `INSERT IGNORE`, por lo que una ejecución posterior no reactiva un
valor que el usuario haya desactivado.

Cada sincronización consulta los valores `codigo_depto` activos y construye la
cantidad necesaria de marcadores `%s`; los códigos se envían como parámetros
PyMySQL. Si no existe ningún departamento activo, se produce un error antes de
consultar productos y la transacción se revierte.

Desactivar un departamento modifica solamente el alcance de sincronizaciones
futuras. No elimina ni desactiva automáticamente productos previamente cargados.
Los códigos se validan como texto compuesto solo por dígitos y conservan ceros
iniciales.
