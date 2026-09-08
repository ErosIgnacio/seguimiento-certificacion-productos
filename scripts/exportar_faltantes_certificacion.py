"""Exporta un reporte HTML o CSV de IDs históricos ausentes."""

from __future__ import annotations

import argparse
import csv
import html
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from certificacion.carga_historica import previsualizar_carga_historica
from certificacion.configuracion import crear_conexion
from certificacion.datos import RepositorioCertificacion
from certificacion.validaciones import preparar_filas_origen


def _texto(valor) -> str:
    return html.escape("" if valor is None else str(valor))


def _obtener_filas_reporte(
    ruta_csv: str | Path,
    usuario: str,
    *,
    ruta_config: str | Path | None = None,
) -> list[dict[str, str]]:
    resultado = previsualizar_carga_historica(
        ruta_csv,
        usuario,
        ruta_config=ruta_config,
    )
    if not resultado.get("ok"):
        raise RuntimeError(f"No se pudo previsualizar la carga: {resultado['errores']}")
    ids_faltantes = resultado.get("detalle_csv_sin_registro_db", [])
    if len(ids_faltantes) != resultado.get("csv_sin_registro_db"):
        raise RuntimeError("El resumen limitó IDs y no permite exportarlos todos")

    componentes = [identificador.split("_") for identificador in ids_faltantes]
    conexion = crear_conexion(ruta_config)
    try:
        origen = RepositorioCertificacion(
            conexion
        ).obtener_origen_por_contenedor_oc(
            (valores[0] for valores in componentes),
            (valores[1] for valores in componentes),
        )
    finally:
        conexion.close()
    validadas = preparar_filas_origen(origen)
    ids_faltantes_set = set(ids_faltantes)
    por_id_origen = {
        fila["id_certificacion"]: fila
        for fila in validadas.filas
        if fila["id_certificacion"] in ids_faltantes_set
    }

    filas = []
    for identificador in sorted(ids_faltantes):
        n_contenedor, oc, gd, sku = identificador.split("_")
        encontrado = por_id_origen.get(identificador)
        if encontrado:
            clasificacion = "ENCONTRADO EN ORIGEN"
            observacion = (
                "ID completo encontrado en tablas operacionales; no fue "
                "sincronizado porque el departamento no está en el filtro actual."
            )
            encontrado_otras_tablas = "SI"
        else:
            clasificacion = "SIN COINCIDENCIA EXACTA"
            observacion = (
                "No existe una equivalencia segura por ID completo; se omite "
                "de la carga histórica."
            )
            encontrado_otras_tablas = "NO"
        filas.append(
            {
                "id_certificacion": identificador,
                "n_contenedor": n_contenedor,
                "oc": oc,
                "gd": gd,
                "sku": sku,
                "encontrado_en_otras_tablas": encontrado_otras_tablas,
                "codigo_depto_encontrado": (
                    str(encontrado.get("codigo_depto") or "")
                    if encontrado
                    else ""
                ),
                "eta_encontrada": (
                    str(encontrado.get("eta") or "") if encontrado else ""
                ),
                "nave_encontrada": (
                    str(encontrado.get("nave") or "") if encontrado else ""
                ),
                "clasificacion": clasificacion,
                "observacion": observacion,
            }
        )
    return filas


def generar_reporte(
    ruta_csv: str | Path,
    usuario: str,
    ruta_salida: str | Path,
    *,
    ruta_config: str | Path | None = None,
) -> Path:
    filas = _obtener_filas_reporte(
        ruta_csv,
        usuario,
        ruta_config=ruta_config,
    )
    filas_html = []
    for fila in filas:
        clase = (
            "encontrado"
            if fila["encontrado_en_otras_tablas"] == "SI"
            else ""
        )
        valores = (
            fila["id_certificacion"],
            fila["n_contenedor"],
            fila["oc"],
            fila["gd"],
            fila["sku"],
            fila["clasificacion"],
            fila["codigo_depto_encontrado"],
            fila["eta_encontrada"],
            fila["nave_encontrada"],
            fila["observacion"],
        )
        celdas = "".join(f"<td>{_texto(valor)}</td>" for valor in valores)
        filas_html.append(f'<tr class="{clase}">{celdas}</tr>')

    documento = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Registros históricos sin coincidencia</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; color: #172033; }}
    h1 {{ margin-bottom: 6px; color: #12325b; }}
    .resumen {{ margin: 16px 0 20px; padding: 14px 16px; background: #eef4fb;
               border-left: 5px solid #2563eb; border-radius: 4px; }}
    .leyenda {{ display: inline-block; padding: 6px 10px; margin-bottom: 14px;
                background: #fff2b2; border: 1px solid #d9b300; }}
    .tabla {{ overflow-x: auto; border: 1px solid #ccd5e1; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 1450px; }}
    th {{ position: sticky; top: 0; background: #17365d; color: white;
          text-align: left; padding: 9px; white-space: nowrap; }}
    td {{ padding: 8px 9px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
    tr.encontrado, tr.encontrado:nth-child(even) {{ background: #fff2b2; font-weight: 600; }}
    td:first-child {{ font-family: Consolas, monospace; white-space: nowrap; }}
  </style>
</head>
<body>
  <h1>46 registros históricos sin coincidencia en certificación</h1>
  <div class="resumen">
    Se importaron por separado los 162 IDs coincidentes. Este reporte desglosa
    las 46 claves omitidas. Los 3 registros encontrados exactamente en el origen
    operacional están resaltados en amarillo; pertenecen al departamento 721.
    Generado: {_texto(datetime.now().isoformat(timespec='seconds'))}.
  </div>
  <div class="leyenda">Amarillo: ID completo encontrado en otro departamento.</div>
  <div class="tabla">
    <table>
      <thead><tr>
        <th>id_certificacion</th><th>n_contenedor</th><th>oc</th><th>gd</th>
        <th>sku</th><th>clasificacion</th><th>codigo_depto</th><th>eta</th>
        <th>nave</th><th>observacion</th>
      </tr></thead>
      <tbody>{''.join(filas_html)}</tbody>
    </table>
  </div>
</body>
</html>
"""
    salida = Path(ruta_salida).expanduser().resolve()
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(documento, encoding="utf-8")
    return salida


def generar_reporte_csv(
    ruta_csv: str | Path,
    usuario: str,
    ruta_salida: str | Path,
    *,
    ruta_config: str | Path | None = None,
) -> Path:
    """Genera UTF-8 con BOM y separador punto y coma para Excel regional."""
    filas = _obtener_filas_reporte(
        ruta_csv,
        usuario,
        ruta_config=ruta_config,
    )
    salida = Path(ruta_salida).expanduser().resolve()
    salida.parent.mkdir(parents=True, exist_ok=True)
    encabezados = (
        "id_certificacion",
        "n_contenedor",
        "oc",
        "gd",
        "sku",
        "encontrado_en_otras_tablas",
        "codigo_depto_encontrado",
        "eta_encontrada",
        "nave_encontrada",
        "clasificacion",
        "observacion",
    )
    with salida.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=encabezados,
            delimiter=";",
            lineterminator="\n",
        )
        escritor.writeheader()
        escritor.writerows(filas)
    return salida


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archivo", default="Certificacion.csv")
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--config")
    parser.add_argument(
        "--salida",
        default="reportes/Certificacion_46_ids_no_coincidentes.html",
    )
    argumentos = parser.parse_args()
    funcion = (
        generar_reporte_csv
        if Path(argumentos.salida).suffix.casefold() == ".csv"
        else generar_reporte
    )
    salida = funcion(
        argumentos.archivo,
        argumentos.usuario,
        argumentos.salida,
        ruta_config=argumentos.config,
    )
    print(salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
