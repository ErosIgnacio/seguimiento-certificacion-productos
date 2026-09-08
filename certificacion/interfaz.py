"""Interfaz CustomTkinter para seguimiento de certificaciones."""

from __future__ import annotations

import json
import threading
import calendar
from datetime import date, datetime
from typing import Any, Callable, Mapping

import customtkinter as ctk
from tkinter import messagebox, ttk

from .catalogos import (
    cambiar_estado_catalogo,
    consultar_auditoria_catalogos,
    guardar_catalogo,
    listar_catalogos,
)
from .campos import (
    ANCHOS_COLUMNAS,
    ANCHOS_MINIMOS_COLUMNAS,
    COLUMNAS_LISTADO,
    ETIQUETAS_CAMPOS,
)
from .constantes import CAMPOS_AUTOMATICOS, CAMPOS_CATALOGO, CAMPOS_USUARIO
from .gestion import (
    actualizar_certificacion,
    actualizar_certificaciones_masivo,
    cargar_datos_iniciales,
    cambiar_estado_certificacion,
    consultar_auditoria_certificacion,
    listar_certificaciones,
    obtener_certificacion,
    obtener_contexto_edicion_masiva,
)
from .sincronizacion import (
    previsualizar_certificaciones,
    sincronizar_certificaciones,
)
from .usuarios import normalizar_usuario, resolver_usuario


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

COLOR_PRIMARIO = "#1464F4"
COLOR_PRIMARIO_HOVER = "#0F4FC2"
COLOR_PELIGRO = "#C62828"
COLOR_EXITO = "#2E7D32"
COLOR_FONDO = "#F3F6FA"

ETIQUETAS_CATALOGOS = {
    "estado_certificacion": "Estado certificación",
    "laboratorio": "Laboratorio",
    "prioridad": "Prioridad",
    "pegar_etiquetas": "Pegar etiquetas",
    "codigo_depto": "Departamento de sincronización",
}

def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def _resumir(valor: Any, limite: int = 90) -> str:
    texto = _texto(valor).replace("\n", " ")
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def _campo_masivo_ingresado(valor: Any) -> bool:
    """Vacío significa conservar; cualquier contenido se aplica al grupo."""
    return valor is not None and bool(str(valor).strip())


def _mensajes_error(resultado: Mapping[str, Any]) -> str:
    errores = resultado.get("errores") or []
    if not errores:
        return "Ocurrió un error no informado."
    return "\n".join(
        f"• {error.get('mensaje', str(error))}" if isinstance(error, dict)
        else f"• {error}"
        for error in errores
    )


def _dimensiones_adaptadas(
    ancho_pantalla: int,
    alto_pantalla: int,
    ancho_deseado: int,
    alto_deseado: int,
) -> tuple[int, int, int, int]:
    """Calcula una geometría centrada que respeta barra de tareas y bordes."""
    ancho_disponible = max(320, ancho_pantalla - 60)
    alto_disponible = max(320, alto_pantalla - 120)
    ancho = min(ancho_deseado, ancho_disponible)
    alto = min(alto_deseado, alto_disponible)
    x = max(0, (ancho_pantalla - ancho) // 2)
    y = max(0, (alto_pantalla - alto) // 2 - 15)
    return ancho, alto, x, y


def _ajustar_ventana(
    ventana,
    ancho_deseado: int,
    alto_deseado: int,
    *,
    ancho_minimo: int = 760,
    alto_minimo: int = 520,
) -> None:
    ancho, alto, x, y = _dimensiones_adaptadas(
        ventana.winfo_screenwidth(),
        ventana.winfo_screenheight(),
        ancho_deseado,
        alto_deseado,
    )
    ventana.geometry(f"{ancho}x{alto}+{x}+{y}")
    ventana.minsize(min(ancho_minimo, ancho), min(alto_minimo, alto))


class CampoFecha(ctk.CTkFrame):
    """Entrada de fecha manual con calendario y operaciones básicas de Entry."""

    def __init__(self, parent, valor: Any = None, *, ancho_entrada: int = 140):
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.entrada = ctk.CTkEntry(
            self,
            width=ancho_entrada,
            height=34,
            placeholder_text="AAAA-MM-DD",
        )
        self.entrada.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.boton = ctk.CTkButton(
            self,
            text="📅",
            width=42,
            height=34,
            command=self.abrir_calendario,
        )
        self.boton.grid(row=0, column=1)
        self.establecer(valor)

    def get(self) -> str:
        return self.entrada.get()

    def delete(self, primero: Any, ultimo: Any = None) -> None:
        """Permite limpiar el control igual que un CTkEntry."""
        self.entrada.delete(primero, ultimo)

    def insert(self, indice: Any, texto: Any) -> None:
        """Permite ingresar texto manualmente o desde código."""
        self.entrada.insert(indice, texto)

    def establecer(self, valor: Any) -> None:
        self.entrada.delete(0, "end")
        if valor not in (None, ""):
            self.entrada.insert(0, _texto(valor))

    def abrir_calendario(self) -> None:
        VentanaSelectorFecha(
            self.winfo_toplevel(), self.get(), self.establecer
        )


class VentanaSelectorFecha(ctk.CTkToplevel):
    """Calendario mensual sin dependencias externas."""

    MESES = (
        "",
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    )

    def __init__(self, parent, valor_actual: str, al_seleccionar):
        super().__init__(parent)
        self.al_seleccionar = al_seleccionar
        try:
            inicial = datetime.strptime(valor_actual.strip(), "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            inicial = date.today()
        self.anio = inicial.year
        self.mes = inicial.month
        self.title("Seleccionar fecha")
        self.configure(fg_color=COLOR_FONDO)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        _ajustar_ventana(
            self, 390, 430, ancho_minimo=360, alto_minimo=400
        )

        cabecera = ctk.CTkFrame(self, fg_color="white")
        cabecera.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        cabecera.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            cabecera, text="◀", width=38, command=lambda: self._mover(-1)
        ).grid(row=0, column=0, padx=6, pady=8)
        self.etiqueta_mes = ctk.CTkLabel(
            cabecera, text="", font=("Segoe UI", 15, "bold")
        )
        self.etiqueta_mes.grid(row=0, column=1, padx=8)
        ctk.CTkButton(
            cabecera, text="▶", width=38, command=lambda: self._mover(1)
        ).grid(row=0, column=2, padx=6, pady=8)

        self.cuerpo = ctk.CTkFrame(self, fg_color="white")
        self.cuerpo.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        for columna in range(7):
            self.cuerpo.grid_columnconfigure(columna, weight=1)

        acciones = ctk.CTkFrame(self, fg_color="white")
        acciones.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 12))
        acciones.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            acciones, text="Limpiar", width=90, command=self._limpiar
        ).grid(row=0, column=1, padx=5, pady=8)
        ctk.CTkButton(
            acciones, text="Hoy", width=90, command=self._hoy
        ).grid(row=0, column=2, padx=(5, 8), pady=8)
        self._dibujar()

    def _dibujar(self) -> None:
        for widget in self.cuerpo.winfo_children():
            widget.destroy()
        self.etiqueta_mes.configure(text=f"{self.MESES[self.mes]} {self.anio}")
        for columna, texto in enumerate(("Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do")):
            ctk.CTkLabel(
                self.cuerpo,
                text=texto,
                font=("Segoe UI", 10, "bold"),
                text_color="#667085",
            ).grid(row=0, column=columna, padx=3, pady=5)
        semanas = calendar.Calendar(firstweekday=0).monthdayscalendar(
            self.anio, self.mes
        )
        hoy = date.today()
        for fila, semana in enumerate(semanas, start=1):
            for columna, dia in enumerate(semana):
                if not dia:
                    continue
                seleccionado_hoy = date(self.anio, self.mes, dia) == hoy
                boton = ctk.CTkButton(
                    self.cuerpo,
                    text=str(dia),
                    width=40,
                    height=34,
                    fg_color=COLOR_EXITO if seleccionado_hoy else "#E8EEF8",
                    text_color="white" if seleccionado_hoy else "#172033",
                    hover_color="#BFD1EE",
                    command=lambda d=dia: self._elegir(d),
                )
                boton.grid(row=fila, column=columna, padx=3, pady=3)

    def _mover(self, desplazamiento: int) -> None:
        indice = self.anio * 12 + (self.mes - 1) + desplazamiento
        self.anio, resto = divmod(indice, 12)
        self.mes = resto + 1
        self._dibujar()

    def _elegir(self, dia: int) -> None:
        self.al_seleccionar(date(self.anio, self.mes, dia).isoformat())
        self.destroy()

    def _hoy(self) -> None:
        self.al_seleccionar(date.today().isoformat())
        self.destroy()

    def _limpiar(self) -> None:
        self.al_seleccionar("")
        self.destroy()


class _BaseCertificacion:
    """Comportamiento compartido entre la aplicación y la ventana integrada."""

    def _inicializar(self, usuario: str) -> None:
        self.usuario = normalizar_usuario(usuario)
        self.title("Seguimiento de Certificación de Productos")
        self.geometry("1550x900")
        self.minsize(1180, 720)
        self.configure(fg_color=COLOR_FONDO)
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.pagina = 1
        self.paginas = 1
        self.tamano_pagina = 100
        self.seleccion_id: str | None = None
        self.seleccion_activo: bool | None = None
        self.catalogos: dict[str, list[str]] = {
            campo: [] for campo in CAMPOS_CATALOGO
        }
        self.catalogos_filtros = dict(self.catalogos)
        self.en_proceso = False
        self.botones_operacion: list[Any] = []

        self._configurar_estilos()
        self._construir_interfaz()
        self.after(150, self.cargar_inicial)

    def _configurar_estilos(self) -> None:
        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure(
            "Treeview",
            background="white",
            fieldbackground="white",
            foreground="#1F2937",
            rowheight=30,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        estilo.configure(
            "Treeview.Heading",
            background="#E8EEF8",
            foreground="#1F2937",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        estilo.map(
            "Treeview",
            background=[("selected", COLOR_PRIMARIO)],
            foreground=[("selected", "white")],
        )

    def _construir_interfaz(self) -> None:
        for fila in range(5):
            self.grid_rowconfigure(fila, weight=1 if fila == 3 else 0)
        self.grid_columnconfigure(0, weight=1)
        self._construir_encabezado()
        self._construir_metricas()
        self._construir_filtros()
        self._construir_tabla()
        self._construir_pie()

    def _construir_encabezado(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0, height=68)
        frame.grid(row=0, column=0, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame,
            text="Certificación de Productos",
            font=("Segoe UI", 23, "bold"),
            text_color="#172033",
        ).grid(row=0, column=0, padx=(22, 12), pady=16, sticky="w")
        ctk.CTkLabel(
            frame,
            text=f"Usuario: {self.usuario}",
            font=("Segoe UI", 12, "bold"),
            text_color="#526076",
        ).grid(row=0, column=1, padx=10, pady=16, sticky="w")

        self.btn_previsualizar = ctk.CTkButton(
            frame,
            text="Previsualizar",
            width=125,
            fg_color="#667085",
            hover_color="#4B5565",
            command=self.previsualizar_sincronizacion,
        )
        self.btn_previsualizar.grid(row=0, column=2, padx=5, pady=14)
        self.btn_sincronizar = ctk.CTkButton(
            frame,
            text="Sincronizar datos",
            width=150,
            fg_color=COLOR_PRIMARIO,
            hover_color=COLOR_PRIMARIO_HOVER,
            command=self.sincronizar_datos,
        )
        self.btn_sincronizar.grid(row=0, column=3, padx=(5, 20), pady=14)
        self.botones_operacion.extend(
            (self.btn_previsualizar, self.btn_sincronizar)
        )

    def _construir_metricas(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", padx=18, pady=(14, 8))
        for columna in range(5):
            frame.grid_columnconfigure(columna, weight=1)

        definiciones = (
            ("total", "Total", "#344054"),
            ("activos", "Certificables", COLOR_EXITO),
            ("pendientes", "Pendientes", "#D97706"),
            ("gestionados", "Gestionados", COLOR_PRIMARIO),
            ("inactivos", "Inactivos", "#667085"),
        )
        self.labels_metricas: dict[str, ctk.CTkLabel] = {}
        for columna, (campo, etiqueta, color) in enumerate(definiciones):
            tarjeta = ctk.CTkFrame(frame, fg_color="white", corner_radius=10)
            tarjeta.grid(
                row=0,
                column=columna,
                sticky="ew",
                padx=(0 if columna == 0 else 5, 0 if columna == 4 else 5),
            )
            ctk.CTkLabel(
                tarjeta,
                text=etiqueta,
                font=("Segoe UI", 11, "bold"),
                text_color="#667085",
            ).pack(anchor="w", padx=15, pady=(10, 0))
            valor = ctk.CTkLabel(
                tarjeta,
                text="0",
                font=("Segoe UI", 25, "bold"),
                text_color=color,
            )
            valor.pack(anchor="w", padx=15, pady=(0, 10))
            self.labels_metricas[campo] = valor

    def _construir_filtros(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="white", corner_radius=10)
        frame.grid(row=2, column=0, sticky="ew", padx=18, pady=6)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Buscar", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, padx=(14, 5), pady=12
        )
        self.entrada_buscar = ctk.CTkEntry(
            frame,
            placeholder_text="Contenedor, OC, GD, SKU, descripción, código, QR…",
            height=34,
        )
        self.entrada_buscar.grid(row=0, column=1, sticky="ew", padx=5, pady=12)
        self.entrada_buscar.bind("<Return>", lambda _evento: self.aplicar_filtros())

        self.combo_estado = self._crear_filtro_combo(frame, "Estado", 2, 3)
        self.combo_laboratorio = self._crear_filtro_combo(
            frame, "Laboratorio", 4, 5
        )
        self.combo_activo = self._crear_filtro_combo(
            frame,
            "Vigencia",
            6,
            7,
            valores=["Certificables", "Todos", "Inactivos"],
        )
        self.combo_activo.set("Certificables")

        self.btn_buscar = ctk.CTkButton(
            frame,
            text="Aplicar",
            width=85,
            command=self.aplicar_filtros,
        )
        self.btn_buscar.grid(row=0, column=8, padx=(8, 4), pady=12)
        self.btn_limpiar = ctk.CTkButton(
            frame,
            text="Limpiar",
            width=80,
            fg_color="#667085",
            hover_color="#4B5565",
            command=self.limpiar_filtros,
        )
        self.btn_limpiar.grid(row=0, column=9, padx=(4, 14), pady=12)

        self.combo_prioridad = self._crear_filtro_combo(
            frame, "Prioridad", 0, 1, fila=1
        )
        self.combo_gestion = self._crear_filtro_combo(
            frame,
            "Gestión",
            2,
            3,
            valores=["Todos", "Pendientes", "Gestionados"],
            fila=1,
        )
        ctk.CTkLabel(
            frame, text="Depto.", font=("Segoe UI", 11, "bold")
        ).grid(row=1, column=4, padx=(10, 4), pady=(0, 12))
        self.entrada_depto = ctk.CTkEntry(
            frame, width=100, height=34, placeholder_text="700"
        )
        self.entrada_depto.grid(row=1, column=5, padx=4, pady=(0, 12))
        ctk.CTkLabel(
            frame, text="ETA desde", font=("Segoe UI", 11, "bold")
        ).grid(row=1, column=6, padx=(10, 4), pady=(0, 12))
        self.entrada_eta_desde = CampoFecha(frame, ancho_entrada=105)
        self.entrada_eta_desde.grid(
            row=1, column=7, sticky="ew", padx=4, pady=(0, 12)
        )
        ctk.CTkLabel(
            frame, text="ETA hasta", font=("Segoe UI", 11, "bold")
        ).grid(row=1, column=8, padx=(10, 4), pady=(0, 12))
        self.entrada_eta_hasta = CampoFecha(frame, ancho_entrada=105)
        self.entrada_eta_hasta.grid(
            row=1, column=9, sticky="ew", padx=(4, 14), pady=(0, 12)
        )
        self.entrada_depto.bind(
            "<Return>", lambda _evento: self.aplicar_filtros()
        )
        for campo_fecha in (self.entrada_eta_desde, self.entrada_eta_hasta):
            campo_fecha.entrada.bind(
                "<Return>", lambda _evento: self.aplicar_filtros()
            )
        self.botones_operacion.extend((self.btn_buscar, self.btn_limpiar))

    @staticmethod
    def _crear_filtro_combo(
        frame,
        texto: str,
        columna_label: int,
        columna_combo: int,
        valores: list[str] | None = None,
        fila: int = 0,
    ):
        ctk.CTkLabel(frame, text=texto, font=("Segoe UI", 11, "bold")).grid(
            row=fila,
            column=columna_label,
            padx=(10, 4),
            pady=12 if fila == 0 else (0, 12),
        )
        combo = ctk.CTkComboBox(
            frame,
            values=valores or ["Todos"],
            width=155,
            height=34,
            state="readonly",
        )
        combo.grid(
            row=fila,
            column=columna_combo,
            padx=4,
            pady=12 if fila == 0 else (0, 12),
        )
        combo.set((valores or ["Todos"])[0])
        return combo

    def _construir_tabla(self) -> None:
        contenedor = ctk.CTkFrame(self, fg_color="white", corner_radius=10)
        contenedor.grid(row=3, column=0, sticky="nsew", padx=18, pady=6)
        contenedor.grid_columnconfigure(0, weight=1)
        contenedor.grid_rowconfigure(0, weight=1)

        self.tabla = ttk.Treeview(
            contenedor,
            columns=COLUMNAS_LISTADO,
            show="headings",
            selectmode="browse",
        )
        for campo in COLUMNAS_LISTADO:
            self.tabla.heading(campo, text=ETIQUETAS_CAMPOS.get(campo, campo))
            ancla = "center" if campo in {
                "eta", "unidades", "activo", "fecha_programacion"
            } else "w"
            self.tabla.column(
                campo,
                width=ANCHOS_COLUMNAS.get(campo, 120),
                minwidth=ANCHOS_MINIMOS_COLUMNAS.get(campo, 60),
                anchor=ancla,
                # El espacio libre se reparte entre todas las columnas y no se
                # concentra únicamente en Nave y Descripción.
                stretch=True,
            )
        self.tabla.tag_configure("inactivo", foreground="#8B95A7")
        self.tabla.tag_configure("activo", foreground="#172033")
        self.tabla.grid(row=0, column=0, sticky="nsew")
        self.tabla.bind("<<TreeviewSelect>>", self._al_seleccionar)
        self.tabla.bind("<Double-1>", lambda _evento: self.editar_seleccion())

        scroll_y = ttk.Scrollbar(
            contenedor, orient="vertical", command=self.tabla.yview
        )
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(
            contenedor, orient="horizontal", command=self.tabla.xview
        )
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.tabla.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )

    def _construir_pie(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        frame.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        frame.grid_columnconfigure(6, weight=1)

        self.btn_editar = ctk.CTkButton(
            frame,
            text="Editar seguimiento",
            width=145,
            state="disabled",
            command=self.editar_seleccion,
        )
        self.btn_editar.grid(row=0, column=0, padx=(18, 5), pady=10)
        self.btn_editar_masivo = ctk.CTkButton(
            frame,
            text="Editar masivo",
            width=120,
            state="disabled",
            fg_color="#475467",
            hover_color="#344054",
            command=self.editar_masivo_seleccion,
        )
        self.btn_editar_masivo.grid(row=0, column=1, padx=5, pady=10)
        self.btn_auditoria = ctk.CTkButton(
            frame,
            text="Ver auditoría",
            width=120,
            state="disabled",
            fg_color="#667085",
            hover_color="#4B5565",
            command=self.ver_auditoria,
        )
        self.btn_auditoria.grid(row=0, column=2, padx=5, pady=10)
        self.btn_estado = ctk.CTkButton(
            frame,
            text="Desactivar",
            width=110,
            state="disabled",
            fg_color=COLOR_PELIGRO,
            hover_color="#992020",
            command=self.cambiar_activo_seleccion,
        )
        self.btn_estado.grid(row=0, column=3, padx=5, pady=10)
        self.btn_recargar = ctk.CTkButton(
            frame,
            text="Recargar",
            width=100,
            fg_color="#667085",
            hover_color="#4B5565",
            command=self.cargar_datos,
        )
        self.btn_recargar.grid(row=0, column=4, padx=5, pady=10)
        self.btn_catalogos = ctk.CTkButton(
            frame,
            text="Catálogos",
            width=100,
            fg_color="#475467",
            hover_color="#344054",
            command=self.abrir_catalogos,
        )
        self.btn_catalogos.grid(row=0, column=5, padx=5, pady=10)
        self.botones_operacion.extend(
            (
                self.btn_editar,
                self.btn_editar_masivo,
                self.btn_auditoria,
                self.btn_estado,
                self.btn_recargar,
                self.btn_catalogos,
            )
        )

        self.label_estado = ctk.CTkLabel(
            frame,
            text="Preparando…",
            font=("Segoe UI", 11),
            text_color="#667085",
        )
        self.label_estado.grid(row=0, column=6, padx=15, pady=10, sticky="e")
        self.barra_progreso = ctk.CTkProgressBar(
            frame, mode="indeterminate", width=110
        )
        self.barra_progreso.grid(row=0, column=7, padx=8, pady=10)
        self.barra_progreso.grid_remove()

        self.btn_anterior = ctk.CTkButton(
            frame, text="◀", width=38, command=self.pagina_anterior
        )
        self.btn_anterior.grid(row=0, column=8, padx=(5, 2), pady=10)
        self.label_pagina = ctk.CTkLabel(
            frame, text="Página 1 de 1", width=110, font=("Segoe UI", 11, "bold")
        )
        self.label_pagina.grid(row=0, column=9, padx=4, pady=10)
        self.btn_siguiente = ctk.CTkButton(
            frame, text="▶", width=38, command=self.pagina_siguiente
        )
        self.btn_siguiente.grid(row=0, column=10, padx=(2, 18), pady=10)
        self.botones_operacion.extend((self.btn_anterior, self.btn_siguiente))

    def _ejecutar_async(
        self,
        trabajo: Callable[[], Any],
        al_terminar: Callable[[Any], None],
        mensaje: str,
    ) -> None:
        if self.en_proceso:
            return
        self._establecer_ocupado(True, mensaje)

        def ejecutar():
            try:
                resultado = trabajo()
            except Exception as exc:
                resultado = {
                    "ok": False,
                    "errores": [
                        {"tipo": type(exc).__name__, "mensaje": str(exc)}
                    ],
                }
            try:
                self.after(0, lambda: finalizar(resultado))
            except Exception:
                return

        def finalizar(resultado):
            self._establecer_ocupado(False, "Listo")
            al_terminar(resultado)

        threading.Thread(target=ejecutar, daemon=True).start()

    def _establecer_ocupado(self, ocupado: bool, mensaje: str) -> None:
        self.en_proceso = ocupado
        self.label_estado.configure(text=mensaje)
        if ocupado:
            self.barra_progreso.grid()
            self.barra_progreso.start()
        else:
            self.barra_progreso.stop()
            self.barra_progreso.grid_remove()
        self._actualizar_botones()

    def _actualizar_botones(self) -> None:
        estado_general = "disabled" if self.en_proceso else "normal"
        for boton in (
            self.btn_previsualizar,
            self.btn_sincronizar,
            self.btn_buscar,
            self.btn_limpiar,
            self.btn_recargar,
            self.btn_catalogos,
        ):
            boton.configure(state=estado_general)
        hay_seleccion = bool(self.seleccion_id) and not self.en_proceso
        estado_seleccion = "normal" if hay_seleccion else "disabled"
        self.btn_editar.configure(state=estado_seleccion)
        self.btn_editar_masivo.configure(state=estado_seleccion)
        self.btn_auditoria.configure(state=estado_seleccion)
        self.btn_estado.configure(state=estado_seleccion)
        self.btn_anterior.configure(
            state="normal" if not self.en_proceso and self.pagina > 1 else "disabled"
        )
        self.btn_siguiente.configure(
            state=(
                "normal"
                if not self.en_proceso and self.pagina < self.paginas
                else "disabled"
            )
        )

    def cargar_inicial(self) -> None:
        filtros = self._obtener_filtros()

        def terminado(resultado):
            catalogos = resultado.get("catalogos", {})
            if catalogos.get("ok"):
                self.catalogos_filtros = catalogos["catalogos"]
                activos = catalogos.get("catalogos_activos", {})
                self.catalogos = {
                    campo: activos.get(campo) or valores
                    for campo, valores in self.catalogos_filtros.items()
                }
                self._aplicar_catalogos()
            listado = resultado.get("listado", {})
            self._aplicar_listado(listado)

        self._ejecutar_async(
            lambda: cargar_datos_iniciales(
                filtros=filtros,
                pagina=self.pagina,
                tamano_pagina=self.tamano_pagina,
            ),
            terminado,
            "Cargando certificaciones…",
        )

    def cargar_datos(self) -> None:
        filtros = self._obtener_filtros()
        self._ejecutar_async(
            lambda: listar_certificaciones(
                filtros=filtros,
                pagina=self.pagina,
                tamano_pagina=self.tamano_pagina,
            ),
            self._aplicar_listado,
            "Consultando certificaciones…",
        )

    def _aplicar_catalogos(self) -> None:
        estado_actual = self.combo_estado.get()
        laboratorio_actual = self.combo_laboratorio.get()
        prioridad_actual = self.combo_prioridad.get()
        self.combo_estado.configure(
            values=[
                "Todos",
                *self.catalogos_filtros.get("estado_certificacion", []),
            ]
        )
        self.combo_laboratorio.configure(
            values=["Todos", *self.catalogos_filtros.get("laboratorio", [])]
        )
        self.combo_prioridad.configure(
            values=["Todos", *self.catalogos_filtros.get("prioridad", [])]
        )
        self.combo_estado.set(
            estado_actual if estado_actual in self.combo_estado.cget("values") else "Todos"
        )
        self.combo_laboratorio.set(
            laboratorio_actual
            if laboratorio_actual in self.combo_laboratorio.cget("values")
            else "Todos"
        )
        self.combo_prioridad.set(
            prioridad_actual
            if prioridad_actual in self.combo_prioridad.cget("values")
            else "Todos"
        )

    def _aplicar_listado(self, resultado: Mapping[str, Any]) -> None:
        if not resultado.get("ok"):
            messagebox.showerror(
                "Error de consulta", _mensajes_error(resultado), parent=self
            )
            self.label_estado.configure(text="No se pudieron cargar los datos")
            return

        self.tabla.delete(*self.tabla.get_children())
        for fila in resultado["filas"]:
            activo = bool(fila["activo"])
            valores = []
            for campo in COLUMNAS_LISTADO:
                if campo == "activo":
                    valores.append("Sí" if activo else "No")
                else:
                    valores.append(_texto(fila.get(campo)))
            self.tabla.insert(
                "",
                "end",
                iid=fila["id_certificacion"],
                values=valores,
                tags=("activo" if activo else "inactivo",),
            )

        for campo, etiqueta in self.labels_metricas.items():
            etiqueta.configure(text=str(resultado["metricas"].get(campo, 0)))
        self.pagina = resultado["pagina"]
        self.paginas = resultado["paginas"]
        self.label_pagina.configure(text=f"Página {self.pagina} de {self.paginas}")
        self.label_estado.configure(
            text=(
                f"{resultado['total_filtrado']} registros encontrados · "
                f"{len(resultado['filas'])} visibles"
            )
        )
        self.seleccion_id = None
        self.seleccion_activo = None
        self._actualizar_botones()

    def _obtener_filtros(self) -> dict[str, Any]:
        activo_texto = (
            self.combo_activo.get()
            if hasattr(self, "combo_activo")
            else "Certificables"
        )
        activo = {"Certificables": True, "Inactivos": False}.get(activo_texto)
        estado = self.combo_estado.get() if hasattr(self, "combo_estado") else "Todos"
        laboratorio = (
            self.combo_laboratorio.get()
            if hasattr(self, "combo_laboratorio")
            else "Todos"
        )
        prioridad = (
            self.combo_prioridad.get()
            if hasattr(self, "combo_prioridad")
            else "Todos"
        )
        gestion = (
            self.combo_gestion.get()
            if hasattr(self, "combo_gestion")
            else "Todos"
        )
        return {
            "buscar": self.entrada_buscar.get() if hasattr(self, "entrada_buscar") else "",
            "estado_certificacion": "" if estado == "Todos" else estado,
            "laboratorio": "" if laboratorio == "Todos" else laboratorio,
            "prioridad": "" if prioridad == "Todos" else prioridad,
            "codigo_depto": self.entrada_depto.get().strip(),
            "gestion": "" if gestion == "Todos" else gestion,
            "eta_desde": self.entrada_eta_desde.get().strip(),
            "eta_hasta": self.entrada_eta_hasta.get().strip(),
            "activo": activo,
        }

    def aplicar_filtros(self) -> None:
        self.pagina = 1
        self.cargar_datos()

    def limpiar_filtros(self) -> None:
        self.entrada_buscar.delete(0, "end")
        self.combo_estado.set("Todos")
        self.combo_laboratorio.set("Todos")
        self.combo_prioridad.set("Todos")
        self.combo_gestion.set("Todos")
        self.combo_activo.set("Certificables")
        for entrada in (
            self.entrada_depto,
            self.entrada_eta_desde,
            self.entrada_eta_hasta,
        ):
            entrada.delete(0, "end")
        self.aplicar_filtros()

    def pagina_anterior(self) -> None:
        if self.pagina > 1:
            self.pagina -= 1
            self.cargar_datos()

    def pagina_siguiente(self) -> None:
        if self.pagina < self.paginas:
            self.pagina += 1
            self.cargar_datos()

    def _al_seleccionar(self, _evento=None) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            self.seleccion_id = None
            self.seleccion_activo = None
        else:
            self.seleccion_id = seleccion[0]
            valores = self.tabla.item(seleccion[0], "values")
            indice_activo = COLUMNAS_LISTADO.index("activo")
            self.seleccion_activo = valores[indice_activo] == "Sí"
            if self.seleccion_activo:
                self.btn_estado.configure(
                    text="Desactivar",
                    fg_color=COLOR_PELIGRO,
                    hover_color="#992020",
                )
            else:
                self.btn_estado.configure(
                    text="Reactivar",
                    fg_color=COLOR_EXITO,
                    hover_color="#236428",
                )
        self._actualizar_botones()

    def editar_seleccion(self) -> None:
        if not self.seleccion_id:
            return
        identificador = self.seleccion_id

        def terminado(resultado):
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudo abrir", _mensajes_error(resultado), parent=self
                )
                return
            VentanaEdicion(
                self,
                resultado["registro"],
                self.catalogos,
            )

        self._ejecutar_async(
            lambda: obtener_certificacion(identificador),
            terminado,
            "Cargando detalle…",
        )

    def editar_masivo_seleccion(self) -> None:
        if not self.seleccion_id:
            return
        identificador = self.seleccion_id

        def terminado(resultado):
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudo abrir la edición masiva",
                    _mensajes_error(resultado),
                    parent=self,
                )
                return
            VentanaEdicion(
                self,
                resultado["registro"],
                self.catalogos,
                modo_masivo=True,
                grupo=resultado["grupo"],
            )

        self._ejecutar_async(
            lambda: obtener_contexto_edicion_masiva(identificador),
            terminado,
            "Preparando grupo Nave-OC-SKU…",
        )

    def guardar_edicion(
        self,
        ventana,
        id_certificacion: str,
        datos: Mapping[str, Any],
    ) -> None:
        ventana.establecer_guardando(True)

        def terminado(resultado):
            if not resultado.get("ok"):
                ventana.establecer_guardando(False)
                messagebox.showerror(
                    "No se pudo guardar", _mensajes_error(resultado), parent=ventana
                )
                return
            messagebox.showinfo(
                "Seguimiento",
                resultado.get("mensaje", "Cambios guardados"),
                parent=ventana,
            )
            ventana.destroy()
            self.cargar_datos()

        self._ejecutar_async(
            lambda: actualizar_certificacion(
                id_certificacion, datos, self.usuario
            ),
            terminado,
            "Guardando seguimiento…",
        )

    def guardar_edicion_masiva(
        self,
        ventana,
        id_certificacion: str,
        datos: Mapping[str, Any],
    ) -> None:
        grupo = ventana.grupo
        etiquetas = ", ".join(
            ETIQUETAS_CAMPOS.get(campo, campo) for campo in datos
        )
        detalle_inactivos = (
            f" (incluye {grupo['inactivos']} inactivo(s))"
            if grupo.get("inactivos")
            else ""
        )
        if not messagebox.askyesno(
            "Confirmar edición masiva",
            f"Se aplicarán los campos: {etiquetas}\n\n"
            f"A {grupo['total']} registro(s){detalle_inactivos} con:\n"
            f"Nave: {_texto(grupo['nave'])}\n"
            f"OC: {_texto(grupo['oc'])}\n"
            f"SKU: {_texto(grupo['sku'])}\n\n"
            "Solo se escribirán y auditarán valores realmente diferentes. "
            "Cada registro inactivo modificado pasará a Certificable, salvo "
            "si su estado resultante es 'No necesita inspección'. "
            "¿Desea continuar?",
            parent=ventana,
        ):
            return

        ventana.establecer_guardando(True)

        def terminado(resultado):
            if not resultado.get("ok"):
                ventana.establecer_guardando(False)
                messagebox.showerror(
                    "No se pudo aplicar la edición masiva",
                    _mensajes_error(resultado),
                    parent=ventana,
                )
                return
            messagebox.showinfo(
                "Edición masiva",
                f"{resultado['mensaje']}\n\n"
                f"Grupo actual: {resultado['registros_grupo']}\n"
                f"Sin cambios: {resultado['sin_cambios']}\n"
                f"Convertidos en certificables: {resultado['reactivados']}\n"
                f"Desactivados por estado: {resultado['desactivados']}\n"
                f"Eventos de auditoría: {resultado['auditorias_generadas']}",
                parent=ventana,
            )
            ventana.destroy()
            self.cargar_datos()

        self._ejecutar_async(
            lambda: actualizar_certificaciones_masivo(
                id_certificacion, datos, self.usuario
            ),
            terminado,
            "Aplicando edición masiva…",
        )

    def cambiar_activo_seleccion(self) -> None:
        if not self.seleccion_id or self.seleccion_activo is None:
            return
        nuevo_estado = not self.seleccion_activo
        verbo = "reactivar" if nuevo_estado else "desactivar"
        if not messagebox.askyesno(
            "Confirmar",
            f"¿Desea {verbo} el registro seleccionado?\n\n"
            f"{self.seleccion_id}",
            parent=self,
        ):
            return
        identificador = self.seleccion_id

        def terminado(resultado):
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudo cambiar el estado",
                    _mensajes_error(resultado),
                    parent=self,
                )
                return
            messagebox.showinfo(
                "Vigencia", resultado["mensaje"], parent=self
            )
            self.cargar_datos()

        self._ejecutar_async(
            lambda: cambiar_estado_certificacion(
                identificador, nuevo_estado, self.usuario
            ),
            terminado,
            f"Cambiando vigencia de {identificador}…",
        )

    def ver_auditoria(self) -> None:
        if not self.seleccion_id:
            return
        identificador = self.seleccion_id

        def terminado(resultado):
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudo consultar la auditoría",
                    _mensajes_error(resultado),
                    parent=self,
                )
                return
            VentanaAuditoria(self, identificador, resultado["filas"])

        self._ejecutar_async(
            lambda: consultar_auditoria_certificacion(identificador),
            terminado,
            "Consultando auditoría…",
        )

    def abrir_catalogos(self) -> None:
        def terminado(resultado):
            if not resultado.get("ok"):
                messagebox.showerror(
                    "Catálogos no disponibles",
                    _mensajes_error(resultado)
                    + "\n\nAplique primero la migración 003.",
                    parent=self,
                )
                return
            VentanaCatalogos(self, resultado["filas"])

        self._ejecutar_async(
            listar_catalogos,
            terminado,
            "Consultando catálogos…",
        )

    def guardar_catalogo_interfaz(
        self, ventana, datos: Mapping[str, Any]
    ) -> None:
        ventana.establecer_ocupado(True)

        def terminado(resultado):
            if not ventana.winfo_exists():
                return
            ventana.establecer_ocupado(False)
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudo guardar",
                    _mensajes_error(resultado),
                    parent=ventana,
                )
                return
            messagebox.showinfo(
                "Catálogos", resultado["mensaje"], parent=ventana
            )
            self._recargar_catalogos_ventana(ventana)

        self._ejecutar_async(
            lambda: guardar_catalogo(usuario=self.usuario, **datos),
            terminado,
            "Guardando catálogo…",
        )

    def cambiar_catalogo_interfaz(
        self, ventana, id_catalogo: int, activo: bool
    ) -> None:
        ventana.establecer_ocupado(True)

        def terminado(resultado):
            if not ventana.winfo_exists():
                return
            ventana.establecer_ocupado(False)
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudo cambiar la vigencia",
                    _mensajes_error(resultado),
                    parent=ventana,
                )
                return
            self._recargar_catalogos_ventana(ventana)

        self._ejecutar_async(
            lambda: cambiar_estado_catalogo(
                id_catalogo, activo, self.usuario
            ),
            terminado,
            "Actualizando catálogo…",
        )

    def ver_auditoria_catalogo(
        self, ventana, id_catalogo: int | None = None
    ) -> None:
        ventana.establecer_ocupado(True)

        def terminado(resultado):
            if not ventana.winfo_exists():
                return
            ventana.establecer_ocupado(False)
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudo consultar el historial",
                    _mensajes_error(resultado),
                    parent=ventana,
                )
                return
            VentanaAuditoriaCatalogos(
                ventana, resultado["filas"], id_catalogo=id_catalogo
            )

        self._ejecutar_async(
            lambda: consultar_auditoria_catalogos(id_catalogo),
            terminado,
            "Consultando historial de catálogos…",
        )

    def _recargar_catalogos_ventana(self, ventana) -> None:
        def terminado(resultado):
            if not ventana.winfo_exists():
                return
            if not resultado.get("ok"):
                messagebox.showerror(
                    "No se pudieron recargar los catálogos",
                    _mensajes_error(resultado),
                    parent=ventana,
                )
                return
            ventana.aplicar_filas(resultado["filas"])
            self.cargar_inicial()

        self._ejecutar_async(
            listar_catalogos,
            terminado,
            "Recargando catálogos…",
        )

    def previsualizar_sincronizacion(self) -> None:
        self._ejecutar_async(
            lambda: previsualizar_certificaciones(self.usuario),
            lambda resultado: self._mostrar_resumen_sincronizacion(
                resultado, "Previsualización"
            ),
            "Validando origen sin escribir…",
        )

    def sincronizar_datos(self) -> None:
        if not messagebox.askyesno(
            "Sincronizar datos",
            "Se consultará el origen y se aplicarán inserciones/actualizaciones "
            "automáticas. Los campos gestionados por usuarios se conservarán.\n\n"
            "¿Desea continuar?",
            parent=self,
        ):
            return

        def terminado(resultado):
            self._mostrar_resumen_sincronizacion(resultado, "Sincronización")
            if resultado.get("confirmado"):
                self.cargar_datos()

        self._ejecutar_async(
            lambda: sincronizar_certificaciones(self.usuario),
            terminado,
            "Sincronizando productos…",
        )

    def _mostrar_resumen_sincronizacion(
        self,
        resultado: Mapping[str, Any],
        titulo: str,
    ) -> None:
        es_previsualizacion = resultado.get("modo") == "PREVISUALIZACION"
        if es_previsualizacion:
            encabezado = "PREVISUALIZACIÓN — NO SE ESCRIBIERON DATOS"
            etiqueta_insertados = "Se insertarían"
            etiqueta_actualizados = "Se actualizarían"
            etiqueta_sin_cambios = "Permanecerían sin cambios"
        else:
            encabezado = (
                "SINCRONIZACIÓN CONFIRMADA — COMMIT EJECUTADO"
                if resultado.get("confirmado")
                else "SINCRONIZACIÓN NO CONFIRMADA — SIN COMMIT"
            )
            etiqueta_insertados = "Insertados"
            etiqueta_actualizados = "Actualizados"
            etiqueta_sin_cambios = "Sin cambios"

        auditorias = (
            resultado.get("auditorias_estimadas", 0)
            if es_previsualizacion
            else resultado.get("auditorias_generadas", 0)
        )
        etiqueta_auditorias = (
            "Se generarían auditorías"
            if es_previsualizacion
            else "Auditorías generadas"
        )

        lineas = [
            encabezado,
            "",
            f"Origen: {resultado.get('origen', 0)}",
            f"{etiqueta_insertados}: {resultado.get('insertados', 0)}",
            f"{etiqueta_actualizados}: {resultado.get('actualizados', 0)}",
            f"{etiqueta_sin_cambios}: {resultado.get('sin_cambios', 0)}",
            (
                "Claves incompletas omitidas: "
                f"{resultado.get('omitidos_clave_incompleta', 0)}"
            ),
            (
                "Duplicados idénticos consolidados: "
                f"{resultado.get('duplicados_consolidados', 0)}"
            ),
            (
                "Duplicados conflictivos: "
                f"{resultado.get('duplicados_conflictivos', 0)}"
            ),
            f"Claves con '_': {resultado.get('claves_con_separador', 0)}",
            f"{etiqueta_auditorias}: {auditorias}",
            (
                "Duración del proceso: "
                f"{float(resultado.get('duracion_segundos', 0) or 0):.2f} s"
            ),
        ]
        if resultado.get("errores"):
            lineas.extend(("", "Errores:", _mensajes_error(resultado)))
            messagebox.showerror(titulo, "\n".join(lineas), parent=self)
        else:
            estado = (
                "Los registros ya están disponibles en la tabla."
                if resultado.get("confirmado")
                else "Para cargarlos use el botón azul «Sincronizar datos»."
            )
            lineas.extend(("", estado))
            messagebox.showinfo(titulo, "\n".join(lineas), parent=self)


class AppCertificacion(ctk.CTk, _BaseCertificacion):
    """Aplicación independiente identificada por la sesión de Windows."""

    def __init__(self, usuario: str | None = None):
        ctk.CTk.__init__(self)
        self._inicializar(resolver_usuario(usuario))


class VentanaCertificacion(ctk.CTkToplevel, _BaseCertificacion):
    """Versión integrada dentro de un CRUD Tk/CustomTkinter ya activo."""

    def __init__(self, parent, usuario: str):
        ctk.CTkToplevel.__init__(self, parent)
        self._inicializar(usuario)
        self.transient(parent)


class VentanaEdicion(ctk.CTkToplevel):
    """Editor individual o masivo de campos gestionados por usuarios."""

    def __init__(
        self,
        parent: AppCertificacion,
        registro: Mapping[str, Any],
        catalogos: Mapping[str, list[str]],
        *,
        modo_masivo: bool = False,
        grupo: Mapping[str, Any] | None = None,
    ):
        super().__init__(parent)
        self.parent = parent
        self.registro = dict(registro)
        self.catalogos = catalogos
        self.modo_masivo = modo_masivo
        self.grupo = dict(grupo or {})
        self.widgets: dict[str, Any] = {}
        self.texto_boton_guardar = (
            f"Aplicar a {self.grupo.get('total', 0)} registros"
            if modo_masivo
            else "Guardar cambios"
        )
        self.title(
            "Edición masiva de certificaciones"
            if modo_masivo
            else "Editar seguimiento de certificación"
        )
        self.geometry("1050x800")
        self.minsize(900, 650)
        self.configure(fg_color=COLOR_FONDO)
        self.transient(parent)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._construir_encabezado()
        self._construir_automaticos()
        self._construir_formulario()
        self._construir_acciones()
        _ajustar_ventana(self, 1100, 850, ancho_minimo=820, alto_minimo=600)

    def _construir_encabezado(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        frame.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            frame,
            text="Edición masiva" if self.modo_masivo else "Editar seguimiento",
            font=("Segoe UI", 21, "bold"),
            text_color="#172033",
        ).pack(anchor="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(
            frame,
            text=(
                f"Nave: {_texto(self.grupo.get('nave'))} · "
                f"OC: {_texto(self.grupo.get('oc'))} · "
                f"SKU: {_texto(self.grupo.get('sku'))} · "
                f"{self.grupo.get('total', 0)} registros"
                if self.modo_masivo
                else self.registro["id_certificacion"]
            ),
            font=("Consolas", 11),
            text_color="#667085",
        ).pack(anchor="w", padx=20, pady=(0, 4 if self.modo_masivo else 14))
        if self.modo_masivo:
            ctk.CTkLabel(
                frame,
                text=(
                    "Complete únicamente los campos que desea cambiar. Todo "
                    "valor ingresado se aplicará al grupo y los campos vacíos "
                    "se conservarán sin cambios."
                ),
                text_color="#B54708",
                justify="left",
            ).pack(anchor="w", padx=20, pady=(0, 14))

    def _construir_automaticos(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="white", corner_radius=10)
        frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(12, 6))
        for columna in range(4):
            frame.grid_columnconfigure(columna, weight=1)
        ctk.CTkLabel(
            frame,
            text="Datos automáticos (solo lectura)",
            font=("Segoe UI", 12, "bold"),
            text_color="#344054",
        ).grid(row=0, column=0, columnspan=4, padx=14, pady=(10, 5), sticky="w")

        campos_contexto = (
            "n_contenedor", "oc", "gd", "sku",
            "descripcion", "unidades", "eta", "nave",
        )
        for indice, campo in enumerate(campos_contexto):
            fila = 1 + indice // 4
            columna = indice % 4
            celda = ctk.CTkFrame(frame, fg_color="transparent")
            celda.grid(row=fila, column=columna, sticky="ew", padx=12, pady=6)
            ctk.CTkLabel(
                celda,
                text=ETIQUETAS_CAMPOS[campo],
                font=("Segoe UI", 10, "bold"),
                text_color="#667085",
            ).pack(anchor="w")
            ctk.CTkLabel(
                celda,
                text=_resumir(self.registro.get(campo), 45) or "—",
                font=("Segoe UI", 11),
                text_color="#172033",
                wraplength=225,
                justify="left",
            ).pack(anchor="w", pady=(1, 3))

    def _construir_formulario(self) -> None:
        scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="white",
            corner_radius=10,
            label_text=(
                "Campos gestionados por el usuario · complete solo los cambios"
                if self.modo_masivo
                else "Campos gestionados por el usuario"
            ),
            label_font=("Segoe UI", 12, "bold"),
        )
        scroll.grid(row=2, column=0, sticky="nsew", padx=16, pady=6)
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        for indice, campo in enumerate(CAMPOS_USUARIO):
            columna = indice % 2
            fila = indice // 2
            grupo = ctk.CTkFrame(scroll, fg_color="transparent")
            grupo.grid(row=fila, column=columna, sticky="ew", padx=8, pady=6)
            grupo.grid_columnconfigure(0, weight=1)
            etiqueta = ETIQUETAS_CAMPOS.get(campo, campo)
            if campo in {"fecha_inspeccion", "fecha_certificacion"}:
                etiqueta += " (AAAA-MM-DD)"
            ctk.CTkLabel(
                grupo,
                text=etiqueta,
                font=("Segoe UI", 10, "bold"),
                text_color="#475467",
            ).grid(row=0, column=0, sticky="w", pady=(0, 3))
            valor_inicial = None if self.modo_masivo else self.registro.get(campo)

            if campo in {"fecha_inspeccion", "fecha_certificacion"}:
                widget = CampoFecha(grupo, valor_inicial)
                widget.grid(row=1, column=0, columnspan=2, sticky="ew")
            elif campo == "comentarios":
                widget = ctk.CTkTextbox(grupo, height=90)
                widget.grid(row=1, column=0, columnspan=2, sticky="ew")
                widget.insert("1.0", _texto(valor_inicial))
            elif campo in {"estado_certificacion", "laboratorio", "prioridad"}:
                valores = [""]
                valores.extend(self.catalogos.get(campo, []))
                actual = _texto(valor_inicial)
                if actual and actual not in valores:
                    valores.append(actual)
                widget = ctk.CTkComboBox(grupo, values=valores, height=34)
                widget.grid(row=1, column=0, columnspan=2, sticky="ew")
                widget.set(actual)
            elif campo == "pegar_etiquetas":
                valores = [""]
                valores.extend(
                    self.catalogos.get(campo) or ["SI", "NO", "PENDIENTE"]
                )
                actual = _texto(valor_inicial)
                if actual and actual not in valores:
                    valores.append(actual)
                widget = ctk.CTkComboBox(grupo, values=valores, height=34)
                widget.grid(row=1, column=0, columnspan=2, sticky="ew")
                widget.set(actual)
            else:
                widget = ctk.CTkEntry(grupo, height=34)
                widget.grid(row=1, column=0, columnspan=2, sticky="ew")
                widget.insert(0, _texto(valor_inicial))
            self.widgets[campo] = widget

    def _construir_acciones(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        frame.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        frame.grid_columnconfigure(0, weight=1)
        self.btn_cancelar = ctk.CTkButton(
            frame,
            text="Cancelar",
            width=110,
            fg_color="#667085",
            hover_color="#4B5565",
            command=self.destroy,
        )
        self.btn_cancelar.grid(row=0, column=1, padx=5, pady=12)
        self.btn_guardar = ctk.CTkButton(
            frame,
            text=self.texto_boton_guardar,
            width=175 if self.modo_masivo else 145,
            command=self.guardar,
        )
        self.btn_guardar.grid(row=0, column=2, padx=(5, 16), pady=12)

    def obtener_datos(self) -> dict[str, str]:
        datos = {}
        for campo, widget in self.widgets.items():
            if campo == "comentarios":
                valor = widget.get("1.0", "end-1c")
            else:
                valor = widget.get()
            if self.modo_masivo and not _campo_masivo_ingresado(valor):
                continue
            datos[campo] = valor
        return datos

    def guardar(self) -> None:
        datos = self.obtener_datos()
        if self.modo_masivo:
            if not datos:
                messagebox.showwarning(
                    "Edición masiva",
                    "Ingrese un valor en al menos un campo.",
                    parent=self,
                )
                return
            self.parent.guardar_edicion_masiva(
                self,
                self.registro["id_certificacion"],
                datos,
            )
        else:
            self.parent.guardar_edicion(
                self,
                self.registro["id_certificacion"],
                datos,
            )

    def establecer_guardando(self, guardando: bool) -> None:
        self.btn_guardar.configure(
            state="disabled" if guardando else "normal",
            text="Guardando…" if guardando else self.texto_boton_guardar,
        )
        self.btn_cancelar.configure(state="disabled" if guardando else "normal")


class VentanaCatalogos(ctk.CTkToplevel):
    """Alta, edición y vigencia de valores configurables; nunca elimina."""

    COLUMNAS = ("tipo", "valor", "descripcion", "orden", "activo")

    def __init__(self, parent, filas: list[dict[str, Any]]):
        super().__init__(parent)
        self.parent = parent
        self.filas_por_id: dict[str, dict[str, Any]] = {}
        self.id_seleccionado: int | None = None
        self.title("Catálogos de certificación")
        self.geometry("1050x680")
        self.minsize(850, 560)
        self.configure(fg_color=COLOR_FONDO)
        self.transient(parent)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        encabezado = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            encabezado,
            text="Catálogos administrables",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w", padx=18, pady=(12, 2))
        ctk.CTkLabel(
            encabezado,
            text=(
                "Estados, laboratorios, prioridades, etiquetas y departamentos "
                "incluidos en la sincronización. "
                "Los valores se desactivan; no se eliminan."
            ),
            text_color="#667085",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        cuerpo = ctk.CTkFrame(self, fg_color="white", corner_radius=10)
        cuerpo.grid(row=1, column=0, sticky="nsew", padx=16, pady=10)
        cuerpo.grid_columnconfigure(0, weight=1)
        cuerpo.grid_rowconfigure(0, weight=1)
        self.tabla = ttk.Treeview(
            cuerpo, columns=self.COLUMNAS, show="headings", selectmode="browse"
        )
        encabezados = {
            "tipo": "Tipo",
            "valor": "Valor",
            "descripcion": "Descripción",
            "orden": "Orden",
            "activo": "Activo",
        }
        anchos = (180, 220, 330, 70, 70)
        for campo, ancho in zip(self.COLUMNAS, anchos):
            self.tabla.heading(campo, text=encabezados[campo])
            self.tabla.column(campo, width=ancho, minwidth=60, anchor="w")
        self.tabla.grid(row=0, column=0, sticky="nsew")
        self.tabla.bind("<<TreeviewSelect>>", self._seleccionar)
        scroll = ttk.Scrollbar(cuerpo, orient="vertical", command=self.tabla.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tabla.configure(yscrollcommand=scroll.set)

        formulario = ctk.CTkFrame(self, fg_color="white", corner_radius=10)
        formulario.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        formulario.grid_columnconfigure(3, weight=1)
        self.combo_tipo = self._campo_combo(
            formulario,
            "Tipo",
            0,
            [*ETIQUETAS_CATALOGOS.values()],
            width=180,
        )
        self.entrada_valor = self._campo_entrada(formulario, "Valor", 1, 220)
        self.entrada_descripcion = self._campo_entrada(
            formulario, "Descripción", 2, 300
        )
        self.entrada_orden = self._campo_entrada(formulario, "Orden", 3, 80)
        self.entrada_orden.insert(0, "0")

        acciones = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        acciones.grid(row=3, column=0, sticky="ew")
        acciones.grid_columnconfigure(0, weight=1)
        self.label_estado = ctk.CTkLabel(
            acciones, text="Nuevo valor", text_color="#667085"
        )
        self.label_estado.grid(row=0, column=0, padx=16, pady=12, sticky="w")
        self.btn_nuevo = ctk.CTkButton(
            acciones, text="Nuevo", width=90, command=self.limpiar
        )
        self.btn_historial = ctk.CTkButton(
            acciones,
            text="Ver historial",
            width=110,
            fg_color="#667085",
            hover_color="#4B5565",
            command=self.ver_historial,
        )
        self.btn_historial.grid(row=0, column=1, padx=5, pady=12)
        self.btn_nuevo.grid(row=0, column=2, padx=5, pady=12)
        self.btn_vigencia = ctk.CTkButton(
            acciones,
            text="Desactivar",
            width=100,
            state="disabled",
            fg_color=COLOR_PELIGRO,
            hover_color="#992020",
            command=self.cambiar_vigencia,
        )
        self.btn_vigencia.grid(row=0, column=3, padx=5, pady=12)
        self.btn_guardar = ctk.CTkButton(
            acciones, text="Guardar", width=110, command=self.guardar
        )
        self.btn_guardar.grid(row=0, column=4, padx=(5, 16), pady=12)
        self.aplicar_filas(filas)
        _ajustar_ventana(self, 1100, 760, ancho_minimo=820, alto_minimo=560)

    @staticmethod
    def _campo_entrada(frame, etiqueta: str, columna: int, ancho: int):
        grupo = ctk.CTkFrame(frame, fg_color="transparent")
        grupo.grid(row=0, column=columna, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(
            grupo, text=etiqueta, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")
        entrada = ctk.CTkEntry(grupo, width=ancho, height=34)
        entrada.pack(fill="x")
        return entrada

    @staticmethod
    def _campo_combo(frame, etiqueta, columna, valores, width):
        grupo = ctk.CTkFrame(frame, fg_color="transparent")
        grupo.grid(row=0, column=columna, sticky="ew", padx=10, pady=10)
        ctk.CTkLabel(
            grupo, text=etiqueta, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")
        combo = ctk.CTkComboBox(
            grupo, values=valores, width=width, height=34, state="readonly"
        )
        combo.pack(fill="x")
        combo.set(valores[0])
        return combo

    def aplicar_filas(self, filas: list[dict[str, Any]]) -> None:
        self.filas_por_id = {str(f["id_catalogo"]): dict(f) for f in filas}
        self.tabla.delete(*self.tabla.get_children())
        for iid, fila in self.filas_por_id.items():
            self.tabla.insert(
                "",
                "end",
                iid=iid,
                values=(
                    ETIQUETAS_CATALOGOS.get(fila["tipo"], fila["tipo"]),
                    fila["valor"],
                    _texto(fila.get("descripcion")),
                    fila["orden"],
                    "Sí" if fila["activo"] else "No",
                ),
            )
        self.limpiar()

    def _seleccionar(self, _evento=None) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        fila = self.filas_por_id[seleccion[0]]
        self.id_seleccionado = int(fila["id_catalogo"])
        self.combo_tipo.set(ETIQUETAS_CATALOGOS[fila["tipo"]])
        self.combo_tipo.configure(state="disabled")
        for entrada, valor in (
            (self.entrada_valor, fila["valor"]),
            (self.entrada_descripcion, fila.get("descripcion")),
            (self.entrada_orden, fila["orden"]),
        ):
            entrada.delete(0, "end")
            entrada.insert(0, _texto(valor))
        activo = bool(fila["activo"])
        self.btn_vigencia.configure(
            state="normal",
            text="Desactivar" if activo else "Reactivar",
            fg_color=COLOR_PELIGRO if activo else COLOR_EXITO,
            hover_color="#992020" if activo else "#236428",
        )
        self.label_estado.configure(text=f"Editando ID {self.id_seleccionado}")

    def limpiar(self) -> None:
        self.id_seleccionado = None
        self.tabla.selection_remove(*self.tabla.selection())
        self.combo_tipo.configure(state="readonly")
        self.combo_tipo.set(next(iter(ETIQUETAS_CATALOGOS.values())))
        for entrada in (self.entrada_valor, self.entrada_descripcion):
            entrada.delete(0, "end")
        self.entrada_orden.delete(0, "end")
        self.entrada_orden.insert(0, "0")
        self.btn_vigencia.configure(state="disabled", text="Desactivar")
        self.label_estado.configure(text="Nuevo valor")

    def guardar(self) -> None:
        tipo_por_etiqueta = {
            etiqueta: tipo for tipo, etiqueta in ETIQUETAS_CATALOGOS.items()
        }
        self.parent.guardar_catalogo_interfaz(
            self,
            {
                "id_catalogo": self.id_seleccionado,
                "tipo": tipo_por_etiqueta[self.combo_tipo.get()],
                "valor": self.entrada_valor.get(),
                "descripcion": self.entrada_descripcion.get(),
                "orden": self.entrada_orden.get(),
            },
        )

    def cambiar_vigencia(self) -> None:
        if self.id_seleccionado is None:
            return
        fila = self.filas_por_id[str(self.id_seleccionado)]
        objetivo = not bool(fila["activo"])
        verbo = "reactivar" if objetivo else "desactivar"
        if not messagebox.askyesno(
            "Confirmar vigencia",
            f"¿Desea {verbo} este valor?\n\n{fila['valor']}\n\n"
            "El historial y los productos existentes se conservarán.",
            parent=self,
        ):
            return
        self.parent.cambiar_catalogo_interfaz(
            self, self.id_seleccionado, objetivo
        )

    def ver_historial(self) -> None:
        self.parent.ver_auditoria_catalogo(self, self.id_seleccionado)

    def establecer_ocupado(self, ocupado: bool) -> None:
        estado = "disabled" if ocupado else "normal"
        self.btn_guardar.configure(state=estado)
        self.btn_nuevo.configure(state=estado)
        self.btn_historial.configure(state=estado)
        if self.id_seleccionado is not None:
            self.btn_vigencia.configure(state=estado)


class VentanaAuditoriaCatalogos(ctk.CTkToplevel):
    """Historial inmutable de altas y cambios en las opciones."""

    COLUMNAS = (
        "fecha_modificacion",
        "tipo",
        "usuario",
        "accion",
        "campo_modificado",
        "valor_anterior",
        "valor_nuevo",
    )

    def __init__(self, parent, filas: list[dict[str, Any]], *, id_catalogo=None):
        super().__init__(parent)
        self.filas_por_id = {str(f["id_auditoria"]): f for f in filas}
        self.title("Historial de catálogos")
        self.configure(fg_color=COLOR_FONDO)
        self.transient(parent)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        encabezado = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew")
        alcance = f"Catálogo ID {id_catalogo}" if id_catalogo else "Todos los catálogos"
        ctk.CTkLabel(
            encabezado,
            text="Historial de opciones",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w", padx=18, pady=(12, 2))
        ctk.CTkLabel(
            encabezado,
            text=f"{alcance} · {len(filas)} eventos",
            text_color="#667085",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        cuerpo = ctk.CTkFrame(self, fg_color="white", corner_radius=10)
        cuerpo.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        cuerpo.grid_columnconfigure(0, weight=1)
        cuerpo.grid_rowconfigure(0, weight=1)
        self.tabla = ttk.Treeview(
            cuerpo, columns=self.COLUMNAS, show="headings", selectmode="browse"
        )
        encabezados = (
            "Fecha",
            "Tipo",
            "Usuario",
            "Acción",
            "Campo",
            "Valor anterior",
            "Valor nuevo",
        )
        anchos = (145, 155, 110, 155, 120, 250, 250)
        for campo, texto, ancho in zip(self.COLUMNAS, encabezados, anchos):
            self.tabla.heading(campo, text=texto)
            self.tabla.column(campo, width=ancho, minwidth=75, anchor="w")
        self.tabla.grid(row=0, column=0, sticky="nsew")
        self.tabla.bind("<<TreeviewSelect>>", self._mostrar_detalle)
        scroll_y = ttk.Scrollbar(cuerpo, orient="vertical", command=self.tabla.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(cuerpo, orient="horizontal", command=self.tabla.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.tabla.configure(
            yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set
        )
        for iid, fila in self.filas_por_id.items():
            self.tabla.insert(
                "",
                "end",
                iid=iid,
                values=(
                    _texto(fila["fecha_modificacion"]),
                    ETIQUETAS_CATALOGOS.get(fila["tipo"], fila["tipo"]),
                    fila["usuario"],
                    fila["accion"],
                    fila["campo_modificado"],
                    _resumir(fila["valor_anterior"]),
                    _resumir(fila["valor_nuevo"]),
                ),
            )
        self.detalle = ctk.CTkTextbox(self, height=125, wrap="word")
        self.detalle.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.detalle.insert("1.0", "Seleccione un evento para ver el detalle.")
        self.detalle.configure(state="disabled")
        _ajustar_ventana(self, 1350, 780, ancho_minimo=850, alto_minimo=560)

    def _mostrar_detalle(self, _evento=None) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        fila = self.filas_por_id[seleccion[0]]
        self.detalle.configure(state="normal")
        self.detalle.delete("1.0", "end")
        self.detalle.insert(
            "1.0", json.dumps(fila, ensure_ascii=False, indent=2, default=str)
        )
        self.detalle.configure(state="disabled")


class VentanaAuditoria(ctk.CTkToplevel):
    """Consulta visual, sin edición ni eliminación de eventos."""

    COLUMNAS = (
        "fecha_modificacion",
        "usuario",
        "accion",
        "campo_modificado",
        "valor_anterior",
        "valor_nuevo",
    )

    def __init__(self, parent, id_certificacion: str, filas: list[dict[str, Any]]):
        super().__init__(parent)
        self.filas_por_id = {str(fila["id_auditoria"]): fila for fila in filas}
        self.title("Auditoría de certificación")
        self.geometry("1200x700")
        self.minsize(900, 540)
        self.configure(fg_color=COLOR_FONDO)
        self.transient(parent)
        self.grab_set()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        encabezado = ctk.CTkFrame(self, fg_color="white", corner_radius=0)
        encabezado.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(
            encabezado,
            text="Historial de auditoría",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w", padx=18, pady=(12, 2))
        ctk.CTkLabel(
            encabezado,
            text=f"{id_certificacion} · {len(filas)} eventos",
            font=("Consolas", 10),
            text_color="#667085",
        ).pack(anchor="w", padx=18, pady=(0, 12))

        cuerpo = ctk.CTkFrame(self, fg_color="white", corner_radius=10)
        cuerpo.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        cuerpo.grid_columnconfigure(0, weight=1)
        cuerpo.grid_rowconfigure(0, weight=1)

        self.tabla = ttk.Treeview(
            cuerpo, columns=self.COLUMNAS, show="headings", selectmode="browse"
        )
        encabezados = {
            "fecha_modificacion": "Fecha",
            "usuario": "Usuario",
            "accion": "Acción",
            "campo_modificado": "Campo",
            "valor_anterior": "Valor anterior",
            "valor_nuevo": "Valor nuevo",
        }
        anchos = (145, 115, 115, 170, 290, 290)
        for campo, ancho in zip(self.COLUMNAS, anchos):
            self.tabla.heading(campo, text=encabezados[campo])
            self.tabla.column(campo, width=ancho, minwidth=80, anchor="w")
        self.tabla.grid(row=0, column=0, sticky="nsew")
        self.tabla.bind("<<TreeviewSelect>>", self._mostrar_detalle)
        scroll_y = ttk.Scrollbar(cuerpo, orient="vertical", command=self.tabla.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(cuerpo, orient="horizontal", command=self.tabla.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.tabla.configure(
            yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set
        )

        for fila in filas:
            self.tabla.insert(
                "",
                "end",
                iid=str(fila["id_auditoria"]),
                values=(
                    _texto(fila["fecha_modificacion"]),
                    _texto(fila["usuario"]),
                    _texto(fila["accion"]),
                    ETIQUETAS_CAMPOS.get(
                        fila["campo_modificado"], fila["campo_modificado"]
                    ),
                    _resumir(fila["valor_anterior"]),
                    _resumir(fila["valor_nuevo"]),
                ),
            )

        self.detalle = ctk.CTkTextbox(self, height=130, wrap="word")
        self.detalle.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.detalle.insert("1.0", "Seleccione un evento para ver el detalle completo.")
        self.detalle.configure(state="disabled")
        _ajustar_ventana(self, 1250, 760, ancho_minimo=850, alto_minimo=540)

    def _mostrar_detalle(self, _evento=None) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        fila = self.filas_por_id[seleccion[0]]
        contenido = {
            "fecha": _texto(fila["fecha_modificacion"]),
            "usuario": fila["usuario"],
            "accion": fila["accion"],
            "campo": fila["campo_modificado"],
            "valor_anterior": fila["valor_anterior"],
            "valor_nuevo": fila["valor_nuevo"],
        }
        self.detalle.configure(state="normal")
        self.detalle.delete("1.0", "end")
        self.detalle.insert(
            "1.0", json.dumps(contenido, ensure_ascii=False, indent=2, default=str)
        )
        self.detalle.configure(state="disabled")


def iniciar_interfaz_certificacion(usuario: str | None = None, parent=None):
    """Abre la interfaz usando el usuario indicado o la sesión de Windows."""
    usuario_resuelto = resolver_usuario(usuario)
    if parent is not None:
        return VentanaCertificacion(parent, usuario_resuelto)
    app = AppCertificacion(usuario_resuelto)
    app.mainloop()
    return app
