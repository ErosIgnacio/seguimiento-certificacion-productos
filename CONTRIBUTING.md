# Contribución

## Preparación local

1. Cree un entorno virtual de Python 3.11 o superior.
2. Instale `requirements-dev.txt`.
3. Copie `config.example.json` como `config.json` y complete únicamente su copia
   local.
4. Aplique las migraciones solamente contra un entorno autorizado.

## Validación

Antes de proponer cambios ejecute:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Las pruebas MySQL están desactivadas por defecto y sólo deben ejecutarse contra
una conexión autorizada; crean tablas `TEMPORARY`.

## Reglas de publicación

- No incorpore credenciales ni datos productivos.
- Use consultas parametrizadas.
- Mantenga auditoría y escritura principal en la misma transacción.
- Agregue pruebas para cambios de comportamiento.
- Actualice `certificacion/version.py` antes de publicar una nueva versión del
  MSI.
