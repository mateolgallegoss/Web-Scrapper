#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
interfaz.py
===========
Interfaz gráfica con tkinter para configurar los parámetros del scraper.py.

Permite editar visualmente la SECCIÓN DE CONFIGURACIÓN de scraper.py
sin tener que abrir el código manualmente.

Parámetros editables:
    - URL_INICIAL
    - RETARDO_ENTRE_PETICIONES
    - PROFUNDIDAD_MAXIMA
    - MAX_PAGINAS
    - RUTA_BASE_DATOS
    - RUTA_DIRECTORIO_ARCHIVOS
    - TIEMPO_ESPERA_NAVEGACION
    - DOMINIO_PERMITIDO
    - USER_AGENT

Uso:
    python programas/interfaz.py
"""

import re
import sys
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Ruta al scraper.py (mismo directorio que esta interfaz)
RUTA_SCRAPER = Path(__file__).parent / "scraper.py"
# Directorio base del proyecto (raíz, un nivel arriba de programas/)
DIRECTORIO_PROYECTO = Path(__file__).resolve().parent.parent


def leer_configuracion() -> dict:
    """Lee scraper.py y extrae los valores de configuración."""
    if not RUTA_SCRAPER.exists():
        raise FileNotFoundError(f"No se encontró {RUTA_SCRAPER}")

    contenido = RUTA_SCRAPER.read_text(encoding="utf-8")

    def buscar_str(nombre: str) -> str:
        m = re.search(rf'^{nombre}:\s*str\s*=\s*"(.*?)"', contenido, re.MULTILINE)
        return m.group(1) if m else ""

    def buscar_int(nombre: str) -> str:
        m = re.search(rf'^{nombre}:\s*int\s*=\s*(\d+)', contenido, re.MULTILINE)
        return m.group(1) if m else "0"

    def buscar_float(nombre: str) -> str:
        m = re.search(rf'^{nombre}:\s*float\s*=\s*([0-9.]+)', contenido, re.MULTILINE)
        return m.group(1) if m else "0"

    def buscar_bool(nombre: str) -> str:
        m = re.search(rf'^{nombre}:\s*bool\s*=\s*(True|False)', contenido, re.MULTILINE)
        return m.group(1) if m else "True"

    # USER_AGENT es multilínea: USER_AGENT: str = ( "part1 " "part2" )
    # Nota: no usar \(.*?\) porque el UA contiene paréntesis ) dentro de las comillas
    # y el *? no codicioso cortaría antes. Usamos patrón que busca strings entre comillas.
    m_ua = re.search(r'USER_AGENT:\s*str\s*=\s*\(\s*((?:"[^"]*"\s*)+)\s*\)', contenido, re.DOTALL)
    if m_ua:
        # extrae todos los strings entre comillas dobles y los concatena
        partes = re.findall(r'"(.*?)"', m_ua.group(1), re.DOTALL)
        user_agent = "".join(partes)
    else:
        # fallback por si se guarda en una sola línea o archivo corrupto previo
        m_ua_old = re.search(r'USER_AGENT:\s*str\s*=\s*\((.*?)\)', contenido, re.DOTALL)
        if m_ua_old:
            partes = re.findall(r'"(.*?)"', m_ua_old.group(1), re.DOTALL)
            user_agent = "".join(partes)
        else:
            m_ua2 = re.search(r'^USER_AGENT:\s*str\s*=\s*"(.*?)"', contenido, re.MULTILINE)
            user_agent = m_ua2.group(1) if m_ua2 else ""

    return {
        "URL_INICIAL": buscar_str("URL_INICIAL"),
        "DOMINIO_PERMITIDO": buscar_str("DOMINIO_PERMITIDO"),
        "RUTA_BASE_DATOS": buscar_str("RUTA_BASE_DATOS"),
        "RUTA_DIRECTORIO_ARCHIVOS": buscar_str("RUTA_DIRECTORIO_ARCHIVOS"),
        "RETARDO_ENTRE_PETICIONES": buscar_float("RETARDO_ENTRE_PETICIONES"),
        "TIEMPO_ESPERA_NAVEGACION": buscar_float("TIEMPO_ESPERA_NAVEGACION"),
        "PROFUNDIDAD_MAXIMA": buscar_int("PROFUNDIDAD_MAXIMA"),
        "MAX_PAGINAS": buscar_int("MAX_PAGINAS"),
        "MODO_INCREMENTAL": buscar_bool("MODO_INCREMENTAL"),
        "USER_AGENT": user_agent,
    }


def guardar_configuracion(valores: dict) -> None:
    """Reescribe scraper.py actualizando solo la sección de configuración."""
    contenido = RUTA_SCRAPER.read_text(encoding="utf-8")

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    # Strings con comillas
    contenido = re.sub(
        r'^URL_INICIAL:\s*str\s*=\s*".*?"',
        f'URL_INICIAL: str = "{esc(valores["URL_INICIAL"])}"',
        contenido,
        flags=re.MULTILINE,
    )
    contenido = re.sub(
        r'^DOMINIO_PERMITIDO:\s*str\s*=\s*".*?"',
        f'DOMINIO_PERMITIDO: str = "{esc(valores["DOMINIO_PERMITIDO"])}"',
        contenido,
        flags=re.MULTILINE,
    )
    contenido = re.sub(
        r'^RUTA_BASE_DATOS:\s*str\s*=\s*".*?"',
        f'RUTA_BASE_DATOS: str = "{esc(valores["RUTA_BASE_DATOS"])}"',
        contenido,
        flags=re.MULTILINE,
    )
    contenido = re.sub(
        r'^RUTA_DIRECTORIO_ARCHIVOS:\s*str\s*=\s*".*?"',
        f'RUTA_DIRECTORIO_ARCHIVOS: str = "{esc(valores["RUTA_DIRECTORIO_ARCHIVOS"])}"',
        contenido,
        flags=re.MULTILINE,
    )

    # Numéricos (sin comillas)
    contenido = re.sub(
        r'^RETARDO_ENTRE_PETICIONES:\s*float\s*=\s*[0-9.]+',
        f'RETARDO_ENTRE_PETICIONES: float = {valores["RETARDO_ENTRE_PETICIONES"]}',
        contenido,
        flags=re.MULTILINE,
    )
    contenido = re.sub(
        r'^TIEMPO_ESPERA_NAVEGACION:\s*float\s*=\s*[0-9.]+',
        f'TIEMPO_ESPERA_NAVEGACION: float = {valores["TIEMPO_ESPERA_NAVEGACION"]}',
        contenido,
        flags=re.MULTILINE,
    )
    contenido = re.sub(
        r'^PROFUNDIDAD_MAXIMA:\s*int\s*=\s*\d+',
        f'PROFUNDIDAD_MAXIMA: int = {valores["PROFUNDIDAD_MAXIMA"]}',
        contenido,
        flags=re.MULTILINE,
    )
    contenido = re.sub(
        r'^MAX_PAGINAS:\s*int\s*=\s*\d+',
        f'MAX_PAGINAS: int = {valores["MAX_PAGINAS"]}',
        contenido,
        flags=re.MULTILINE,
    )

    # Bool MODO_INCREMENTAL
    if "MODO_INCREMENTAL" in valores:
        if re.search(r'^MODO_INCREMENTAL:\s*bool\s*=\s*(True|False)', contenido, re.MULTILINE):
            contenido = re.sub(
                r'^MODO_INCREMENTAL:\s*bool\s*=\s*(True|False)',
                f'MODO_INCREMENTAL: bool = {valores["MODO_INCREMENTAL"]}',
                contenido,
                flags=re.MULTILINE,
            )
        else:
            # Insertar antes de USER_AGENT si no existe (archivos antiguos)
            contenido = contenido.replace(
                "USER_AGENT: str = (",
                f'MODO_INCREMENTAL: bool = {valores["MODO_INCREMENTAL"]}\n\nUSER_AGENT: str = (',
            )

    # USER_AGENT multilínea
    # Usar patrón robusto que no se corta con paréntesis dentro de comillas
    ua = esc(valores["USER_AGENT"].strip())
    nuevo_bloque_ua = f'USER_AGENT: str = (\n    "{ua}"\n)'
    # patrón robusto: uno o más strings entre comillas dentro de paréntesis
    nuevo_contenido, n = re.subn(
        r'USER_AGENT:\s*str\s*=\s*\(\s*(?:"[^"]*"\s*)+\)',
        nuevo_bloque_ua,
        contenido,
        flags=re.DOTALL,
    )
    if n == 0:
        # fallback para archivos antiguos/corruptos (patrón no codicioso)
        contenido = re.sub(
            r'USER_AGENT:\s*str\s*=\s*\(.*?\)',
            nuevo_bloque_ua,
            contenido,
            flags=re.DOTALL,
        )
        # limpiar posible resto corrupto dejado por el bug anterior:
        # ej: ) AppleWebKit/537.36 " \n    "(KHTML... -> eliminar
        contenido = re.sub(
            r'USER_AGENT:\s*str\s*=\s*\(\s*"[^"]*"\s*\)\s*AppleWebKit.*?"\)',
            nuevo_bloque_ua,
            contenido,
            flags=re.DOTALL,
        )
    else:
        contenido = nuevo_contenido
    # también soporta caso de una sola línea USER_AGENT: str = "..."
    if 'USER_AGENT: str = (' not in contenido:
        contenido = re.sub(
            r'^USER_AGENT:\s*str\s*=\s*".*?"',
            nuevo_bloque_ua,
            contenido,
            flags=re.MULTILINE,
        )

    RUTA_SCRAPER.write_text(contenido, encoding="utf-8")


class InterfazScraper(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Configurador Scraper — scraper.py")
        self.geometry("780x720")
        self.minsize(720, 640)

        # Estilo
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TLabel", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))

        self._crear_widgets()
        self.cargar_valores()

    def _crear_widgets(self):
        # Contenedor principal con scroll
        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Permitir scroll con rueda
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        main = ttk.Frame(scrollable_frame, padding=20)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Configuración del Scraper", style="Header.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(main, text="Modifica los parámetros y guarda directamente en scraper.py", foreground="#555").pack(anchor="w", pady=(0, 15))
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=(0, 15))

        # --- Formulario ---
        form = ttk.Frame(main)
        form.pack(fill="x", expand=True)
        form.columnconfigure(1, weight=1)

        row = 0

        # URL Inicial
        ttk.Label(form, text="URL inicial *").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        self.var_url = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_url).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(form, text="Ej: https://ejemplo.com", foreground="#777", font=("Segoe UI", 8)).grid(row=row, column=1, sticky="w")
        row += 1

        # Dominio permitido
        ttk.Label(form, text="Dominio permitido").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        self.var_dominio = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_dominio).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1
        ttk.Label(form, text="Vacío = se deriva de la URL inicial", foreground="#777", font=("Segoe UI", 8)).grid(row=row, column=1, sticky="w")
        row += 1

        # Retardo
        ttk.Label(form, text="Retardo entre peticiones (s)").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        self.var_retardo = tk.StringVar()
        ttk.Spinbox(form, textvariable=self.var_retardo, from_=0, to=60, increment=0.5, wrap=True).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1

        # Profundidad
        ttk.Label(form, text="Profundidad máxima").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        self.var_profundidad = tk.StringVar()
        ttk.Spinbox(form, textvariable=self.var_profundidad, from_=0, to=20, increment=1, wrap=True).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1

        # Max páginas
        ttk.Label(form, text="Máx. páginas").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        self.var_max_paginas = tk.StringVar()
        ttk.Spinbox(form, textvariable=self.var_max_paginas, from_=1, to=10000, increment=1, wrap=True).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1

        # Modo incremental
        ttk.Label(form, text="Modo incremental").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        self.var_incremental = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Solo URLs nuevas (desmarcado = forzar re-scrapeo)", variable=self.var_incremental).grid(row=row, column=1, sticky="w", pady=6)
        row += 1
        ttk.Label(form, text="Activado: respeta BD y descubre hijos nuevos sin re-guardar", foreground="#777", font=("Segoe UI", 8)).grid(row=row, column=1, sticky="w")
        row += 1

        # Timeout
        ttk.Label(form, text="Timeout navegación (ms)").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        self.var_timeout = tk.StringVar()
        ttk.Spinbox(form, textvariable=self.var_timeout, from_=1000, to=120000, increment=1000, wrap=True).grid(row=row, column=1, sticky="ew", pady=6)
        row += 1

        # Ruta BD
        ttk.Label(form, text="Ruta base de datos").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        frame_bd = ttk.Frame(form)
        frame_bd.grid(row=row, column=1, sticky="ew", pady=6)
        frame_bd.columnconfigure(0, weight=1)
        self.var_ruta_bd = tk.StringVar()
        ttk.Entry(frame_bd, textvariable=self.var_ruta_bd).grid(row=0, column=0, sticky="ew")
        ttk.Button(frame_bd, text="…", width=3, command=lambda: self._elegir_archivo(self.var_ruta_bd, save=True)).grid(row=0, column=1, padx=(6, 0))
        row += 1

        # Ruta archivos
        ttk.Label(form, text="Directorio archivos").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        frame_dir = ttk.Frame(form)
        frame_dir.grid(row=row, column=1, sticky="ew", pady=6)
        frame_dir.columnconfigure(0, weight=1)
        self.var_ruta_dir = tk.StringVar()
        ttk.Entry(frame_dir, textvariable=self.var_ruta_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(frame_dir, text="…", width=3, command=lambda: self._elegir_directorio(self.var_ruta_dir)).grid(row=0, column=1, padx=(6, 0))
        row += 1

        # User Agent
        ttk.Label(form, text="User-Agent").grid(row=row, column=0, sticky="nw", pady=6, padx=(0, 10))
        frame_ua = ttk.Frame(form)
        frame_ua.grid(row=row, column=1, sticky="ew", pady=6)
        frame_ua.columnconfigure(0, weight=1)
        self.txt_user_agent = tk.Text(frame_ua, height=4, wrap="word", font=("Segoe UI", 9), relief="solid", bd=1)
        self.txt_user_agent.grid(row=0, column=0, sticky="ew")
        scroll_ua = ttk.Scrollbar(frame_ua, orient="vertical", command=self.txt_user_agent.yview)
        scroll_ua.grid(row=0, column=1, sticky="ns")
        self.txt_user_agent.configure(yscrollcommand=scroll_ua.set)
        row += 1
        ttk.Label(form, text="Se usa para evadir detección de bots", foreground="#777", font=("Segoe UI", 8)).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=15)

        # Botones
        btns = ttk.Frame(main)
        btns.pack(fill="x")

        ttk.Button(btns, text="Recargar", command=self.cargar_valores).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Guardar cambios", command=self.guardar).pack(side="left", padx=6)
        ttk.Button(btns, text="Guardar y ejecutar scraper", command=self.guardar_y_ejecutar).pack(side="left", padx=6)
        ttk.Button(btns, text="Salir", command=self.destroy).pack(side="right")

        # Barra de estado
        self.var_estado = tk.StringVar(value="Listo")
        ttk.Label(main, textvariable=self.var_estado, foreground="#444", font=("Segoe UI", 8)).pack(anchor="w", pady=(12, 0))

    def _elegir_archivo(self, var: tk.StringVar, save: bool = False):
        if save:
            path = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite", "*.db"), ("Todos", "*.*")])
        else:
            path = filedialog.askopenfilename(filetypes=[("SQLite", "*.db"), ("Todos", "*.*")])
        if path:
            # guardar relativo al proyecto si está dentro de él
            try:
                rel = Path(path).resolve().relative_to(DIRECTORIO_PROYECTO.resolve())
                var.set(str(rel))
            except ValueError:
                var.set(path)

    def _elegir_directorio(self, var: tk.StringVar):
        path = filedialog.askdirectory()
        if path:
            try:
                rel = Path(path).resolve().relative_to(DIRECTORIO_PROYECTO.resolve())
                var.set(str(rel))
            except ValueError:
                var.set(path)

    def cargar_valores(self):
        try:
            cfg = leer_configuracion()
            self.var_url.set(cfg["URL_INICIAL"])
            self.var_dominio.set(cfg["DOMINIO_PERMITIDO"])
            self.var_ruta_bd.set(cfg["RUTA_BASE_DATOS"])
            self.var_ruta_dir.set(cfg["RUTA_DIRECTORIO_ARCHIVOS"])
            self.var_retardo.set(cfg["RETARDO_ENTRE_PETICIONES"])
            self.var_timeout.set(cfg["TIEMPO_ESPERA_NAVEGACION"])
            self.var_profundidad.set(cfg["PROFUNDIDAD_MAXIMA"])
            self.var_max_paginas.set(cfg["MAX_PAGINAS"])
            # MODO_INCREMENTAL es nuevo, puede no existir en archivos antiguos
            try:
                self.var_incremental.set(cfg.get("MODO_INCREMENTAL", "True") == "True")
            except Exception:
                pass
            self.txt_user_agent.delete("1.0", "end")
            self.txt_user_agent.insert("1.0", cfg["USER_AGENT"])
            self.var_estado.set(f"Cargado desde {RUTA_SCRAPER.name}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer {RUTA_SCRAPER}:\n{e}")
            self.var_estado.set("Error al cargar")

    def _validar(self) -> bool:
        url = self.var_url.get().strip()
        if url and not url.startswith(("http://", "https://")):
            messagebox.showwarning("Validación", "La URL inicial debe empezar por http:// o https://")
            return False
        try:
            float(self.var_retardo.get())
            float(self.var_timeout.get())
            int(self.var_profundidad.get())
            int(self.var_max_paginas.get())
        except ValueError:
            messagebox.showwarning("Validación", "Retardo, timeout, profundidad y máx. páginas deben ser numéricos")
            return False
        if not self.var_ruta_bd.get().strip():
            messagebox.showwarning("Validación", "La ruta de la base de datos no puede estar vacía")
            return False
        if not self.var_ruta_dir.get().strip():
            messagebox.showwarning("Validación", "El directorio de archivos no puede estar vacío")
            return False
        return True

    def _recolectar(self) -> dict:
        return {
            "URL_INICIAL": self.var_url.get().strip(),
            "DOMINIO_PERMITIDO": self.var_dominio.get().strip(),
            "RUTA_BASE_DATOS": self.var_ruta_bd.get().strip(),
            "RUTA_DIRECTORIO_ARCHIVOS": self.var_ruta_dir.get().strip(),
            "RETARDO_ENTRE_PETICIONES": self.var_retardo.get().strip() or "2.0",
            "TIEMPO_ESPERA_NAVEGACION": self.var_timeout.get().strip() or "30000",
            "PROFUNDIDAD_MAXIMA": self.var_profundidad.get().strip() or "3",
            "MAX_PAGINAS": self.var_max_paginas.get().strip() or "100",
            "MODO_INCREMENTAL": "True" if getattr(self, "var_incremental", None) and self.var_incremental.get() else "False",
            "USER_AGENT": self.txt_user_agent.get("1.0", "end-1c").strip(),
        }

    def guardar(self):
        if not self._validar():
            return
        try:
            guardar_configuracion(self._recolectar())
            messagebox.showinfo("Guardado", f"Configuración guardada en {RUTA_SCRAPER}")
            self.var_estado.set("Guardado correctamente ✓")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")
            self.var_estado.set("Error al guardar")

    def guardar_y_ejecutar(self):
        if not self._validar():
            return
        try:
            guardar_configuracion(self._recolectar())
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")
            return

        # Validar sintaxis antes de lanzar para avisar de corrupciones
        try:
            import py_compile
            py_compile.compile(str(RUTA_SCRAPER), doraise=True)
        except Exception as e:
            messagebox.showerror("Error", f"scraper.py tiene error de sintaxis y no se puede ejecutar:\n{e}")
            self.var_estado.set("Error de sintaxis en scraper.py")
            return

        self.var_estado.set("Ejecutando scraper… revisa la terminal")
        # Ejecutar en hilo para no congelar la UI

        def _encontrar_python() -> str:
            """Busca un intérprete con bs4+playwright instalados."""
            candidatos = [sys.executable, "python", "python3", "py"]
            for cand in candidatos:
                if not cand:
                    continue
                try:
                    # comprueba que bs4 y playwright importan
                    r = subprocess.run(
                        [cand, "-c", "import bs4, playwright"],
                        capture_output=True,
                        timeout=3,
                    )
                    if r.returncode == 0:
                        return cand
                except Exception:
                    continue
            return sys.executable

        def _run():
            try:
                python_bin = _encontrar_python()
                # En Windows usar cmd /k para que la ventana NO se cierre al terminar
                # y el usuario pueda ver logs/errores.
                if sys.platform == "win32":
                    # -u = stdout no bufferizado para ver logs en tiempo real
                    cmd = ["cmd.exe", "/k", python_bin, "-u", str(RUTA_SCRAPER)]
                    kwargs = {"cwd": str(DIRECTORIO_PROYECTO), "creationflags": subprocess.CREATE_NEW_CONSOLE}
                else:
                    cmd = [python_bin, "-u", str(RUTA_SCRAPER)]
                    kwargs = {"cwd": str(DIRECTORIO_PROYECTO)}
                logger_cmd = " ".join(cmd)
                print(f"[interfaz] lanzando: {logger_cmd}")
                subprocess.Popen(cmd, **kwargs)
                self.after(0, lambda: self.var_estado.set(f"Scraper lanzado en nueva ventana ({python_bin}) - no se cerrará sola"))
            except Exception as e:
                self.after(0, lambda ex=e: messagebox.showerror("Error", f"No se pudo ejecutar scraper.py:\n{ex}"))
                self.after(0, lambda: self.var_estado.set("Error al lanzar scraper"))

        threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    app = InterfazScraper()
    app.mainloop()
