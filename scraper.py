#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scraper.py
==========
Scraper web profesional, asíncrono y altamente resiliente.

Características principales:
    * Rastreo recursivo (BFS iterativo, sin llamadas recursivas) desde una URL
      inicial, restringido estrictamente al dominio de origen.
    * Límite configurable de profundidad (max_depth) y de páginas procesadas.
    * Extracción por página de: URL, título, HTML completo (DOM renderizado),
      texto visible limpio y todo el código JavaScript (etiquetas <script>).
    * Persistencia segura en SQLite con transacciones y `INSERT OR REPLACE`
      indexado por URL.
    * Guardado en disco de cada página rastreada en una carpeta individual con
      sus archivos (HTML, texto limpio y JavaScript), registrando las rutas en
      la base de datos. Cada ejecución crea una carpeta nueva con marca de
      tiempo.
    * Evasión básica de bloqueos: user_agent realista, flag
      `--disable-blink-features=AutomationControlled`, retardo configurable
      entre peticiones y manejo robusto de errores de navegación.

Requisitos de instalación:
    pip install playwright beautifulsoup4
    playwright install chromium

Uso:
    python scraper.py
"""

import asyncio
import hashlib
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse, urldefrag
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page
from playwright.async_api import Error as PlaywrightError


# ============================================================================
# SECCIÓN DE CONFIGURACIÓN
# ----------------------------------------------------------------------------
# Ajusta estos valores para adaptar el scraper a tu caso de uso.
# ============================================================================

# URL inicial desde la que comenzará el rastreo recursivo.
URL_INICIAL: str = "https://www.reddit.com/r/golang/"

# Retardo (en segundos) entre cada petición HTTP para simular comportamiento
# humano y no saturar el servidor objetivo.
RETARDO_ENTRE_PETICIONES: float = 2.0

# Nivel máximo de profundidad del rastreo (0 = solo la URL inicial).
PROFUNDIDAD_MAXIMA: int = 3

# Límite máximo de páginas a procesar durante la ejecución.
MAX_PAGINAS: int = 100

# Ruta del archivo de base de datos SQLite donde se guardarán los resultados.
RUTA_BASE_DATOS: str = "scrapeo.db"

# Directorio raíz donde se creará una carpeta nueva por cada ejecución del
# scraper (con marca de tiempo). Dentro, cada página rastreada tendrá su
# carpeta individual con: pagina.html, texto.txt y javascript.js.
RUTA_DIRECTORIO_ARCHIVOS: str = "archivos_scrapeados"

# Tiempo máximo de espera (en ms) para la carga de cada página.
TIEMPO_ESPERA_NAVEGACION: float = 30_000

# Dominio permitido. Si se deja vacío, se deriva automáticamente de URL_INICIAL.
# Útil para restringir el rastreo a un subdominio específico.
DOMINIO_PERMITIDO: str = ""

# User agent realista y moderno para evitar ser detectado como bot.
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scraper")


# ============================================================================
# FUNCIONES AUXILIARES DE PROCESAMIENTO
# ============================================================================

def normalizar_url(url: str) -> str:
    """Normaliza una URL para evitar duplicados.

    Elimina fragmentos tipo `#seccion`, normaliza las barras inclinadas de
    cierre al final de la ruta y descarta esquemas no http(s). Devuelve una
    cadena vacía si la URL no es procesable.
    """
    url = url.strip()
    # Elimina el fragmento (#seccion) de la URL.
    url_sin_fragmento, _ = urldefrag(url)
    url_parseada = urlparse(url_sin_fragmento)

    # Solo se aceptan esquemas http/https.
    if url_parseada.scheme not in ("http", "https"):
        return ""

    # Normaliza las barras de cierre duplicadas al final de la ruta.
    ruta = url_parseada.path
    if len(ruta) > 1 and ruta.endswith("/"):
        ruta = ruta.rstrip("/")

    return urlunparse(
        (
            url_parseada.scheme,
            url_parseada.netloc,
            ruta,
            url_parseada.params,
            url_parseada.query,
            "",  # sin fragmento
        )
    )


def obtener_dominio(url: str) -> str:
    """Devuelve el dominio (host) en minúsculas de una URL."""
    return urlparse(url).netloc.lower()


def generar_slug(url: str) -> str:
    """Genera un nombre de carpeta único y legible a partir de una URL.

    Combina la ruta de la URL (sanitizada) con un hash corto de la URL
    completa para garantizar unicidad y evitar colisiones entre páginas.
    """
    url_parseada = urlparse(url)
    ruta = url_parseada.path.strip("/") or "inicio"
    ruta = ruta.replace("/", "_")
    ruta = re.sub(r"[^A-Za-z0-9_.\-]", "_", ruta)[:80]
    hash_corto = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    return f"{ruta}_{hash_corto}"


def extraer_texto_limpio(html: str) -> str:
    """Extrae el texto visible limpio del HTML renderizado.

    Utiliza BeautifulSoup para eliminar scripts, estilos y los bloques
    considerados navegación (cabeceras, menús y pies de página), dejando
    únicamente el contenido textual legible por el usuario.
    """
    sopa = BeautifulSoup(html, "html.parser")

    # Elimina elementos que no aportan texto visible.
    for etiqueta in sopa(["script", "style", "noscript", "template"]):
        etiqueta.decompose()

    # Elimina bloques de navegación: cabeceras, menús y pies de página.
    for etiqueta in sopa.find_all(["header", "nav", "footer", "aside"]):
        etiqueta.decompose()

    texto = sopa.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", texto)


def extraer_javascript(html: str) -> str:
    """Extrae y concatena todo el código JavaScript inline de la página.

    Recoge el contenido textual de todas las etiquetas `<script>` y lo
    devuelve concatenado en un único campo de texto para su posterior
    análisis o indexación.
    """
    sopa = BeautifulSoup(html, "html.parser")
    fragmentos: list[str] = []
    for script in sopa.find_all("script"):
        contenido = script.get_text()
        if contenido.strip():
            fragmentos.append(contenido)
    return "\n".join(fragmentos)


def extraer_enlaces(html: str, url_base: str, dominio: str) -> list[str]:
    """Extrae los enlaces internos de la página.

    Resuelve cada enlace relativo a una URL absoluta, la normaliza y la
    conserva únicamente si pertenece al mismo dominio que la URL semilla.
    """
    sopa = BeautifulSoup(html, "html.parser")
    enlaces: list[str] = []
    for ancla in sopa.find_all("a", href=True):
        href: str = ancla["href"].strip()
        # Omite enlaces no navegables o enlaces externos.
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url_absoluta = urljoin(url_base, href)
        url_normalizada = normalizar_url(url_absoluta)
        if not url_normalizada:
            continue
        if obtener_dominio(url_normalizada) != dominio:
            continue
        enlaces.append(url_normalizada)
    return enlaces


# ============================================================================
# CAPA DE PERSISTENCIA (SQLITE)
# ============================================================================

class BaseDatos:
    """Gestiona la conexión y las operaciones sobre la base de datos SQLite."""

    def __init__(self, ruta: str) -> None:
        self.conexion = sqlite3.connect(ruta)
        # Modo WAL para mayor robustez ante accesos concurrentes.
        self.conexion.execute("PRAGMA journal_mode=WAL;")
        self.conexion.execute("PRAGMA busy_timeout = 5000;")
        self._crear_tabla()

    def _crear_tabla(self) -> None:
        """Crea las tablas (si no existen) y migra esquemas antiguos."""
        self.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS paginas_scrapeadas (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                url              TEXT UNIQUE,
                dominio          TEXT,
                titulo           TEXT,
                html_completo    TEXT,
                texto_limpio     TEXT,
                javascript_codigo TEXT,
                ruta_carpeta     TEXT,
                fecha_escrapeo   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS archivos_guardados (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                pagina_id    INTEGER NOT NULL,
                tipo         TEXT NOT NULL,
                ruta_archivo TEXT NOT NULL,
                UNIQUE (pagina_id, tipo),
                FOREIGN KEY (pagina_id)
                    REFERENCES paginas_scrapeadas (id) ON DELETE CASCADE
            );
            """
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_dominio "
            "ON paginas_scrapeadas (dominio);"
        )
        self.conexion.execute(
            "CREATE INDEX IF NOT EXISTS idx_archivos_pagina "
            "ON archivos_guardados (pagina_id);"
        )
        self._migrar_esquema()
        self.conexion.commit()

    def _migrar_esquema(self) -> None:
        """Añade columnas nuevas a bases de datos creadas con versiones previas."""
        columnas = [
            fila[1]
            for fila in self.conexion.execute("PRAGMA table_info(paginas_scrapeadas)")
        ]
        if "ruta_carpeta" not in columnas:
            self.conexion.execute(
                "ALTER TABLE paginas_scrapeadas ADD COLUMN ruta_carpeta TEXT;"
            )

    def url_existe(self, url: str) -> bool:
        """Comprueba si una URL ya está indexada en la base de datos."""
        cursor = self.conexion.execute(
            "SELECT 1 FROM paginas_scrapeadas WHERE url = ? LIMIT 1;",
            (url,),
        )
        return cursor.fetchone() is not None

    def guardar_pagina(
        self,
        url: str,
        dominio: str,
        titulo: Optional[str],
        html_completo: str,
        texto_limpio: str,
        javascript_codigo: str,
        ruta_carpeta: Optional[str] = None,
    ) -> int:
        """Guarda (o actualiza) una página rastreada mediante INSERT OR REPLACE.

        Devuelve el identificador (`id`) de la fila resultante.
        """
        with self.conexion:
            cursor = self.conexion.execute(
                """
                INSERT OR REPLACE INTO paginas_scrapeadas
                    (url, dominio, titulo, html_completo, texto_limpio,
                     javascript_codigo, ruta_carpeta)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    url,
                    dominio,
                    titulo,
                    html_completo,
                    texto_limpio,
                    javascript_codigo,
                    ruta_carpeta,
                ),
            )
        return int(cursor.lastrowid)

    def guardar_archivo(self, pagina_id: int, tipo: str, ruta_archivo: str) -> None:
        """Registra un archivo guardado en disco asociado a una página."""
        with self.conexion:
            self.conexion.execute(
                """
                INSERT OR REPLACE INTO archivos_guardados
                    (pagina_id, tipo, ruta_archivo)
                VALUES (?, ?, ?);
                """,
                (pagina_id, tipo, ruta_archivo),
            )

    def cerrar(self) -> None:
        """Cierra la conexión con la base de datos."""
        self.conexion.close()


# ============================================================================
# CRAWLER ASÍNCRONO
# ============================================================================

class Crawler:
    """Rastreador asíncrono (BFS iterativo) restringido a un único dominio.

    Gestiona una cola de URLs pendientes con su nivel de profundidad. El bucle
    principal consume la cola sin realizar llamadas recursivas, controlando el
    límite de profundidad y el número máximo de páginas a procesar.
    """

    def __init__(
        self,
        url_inicial: str,
        dominio: str,
        max_depth: int,
        max_paginas: int,
        delay: float,
        timeout: float,
        base_datos: BaseDatos,
        ruta_directorio_archivos: str,
    ) -> None:
        self.url_inicial = url_inicial
        self.dominio = dominio
        self.max_depth = max_depth
        self.max_paginas = max_paginas
        self.delay = delay
        self.timeout = timeout
        self.base_datos = base_datos
        self.ruta_directorio_archivos = ruta_directorio_archivos
        self.urls_procesadas: set[str] = set()
        self.cola: "asyncio.Queue[tuple[str, int]]" = asyncio.Queue()
        self.paginas_procesadas: int = 0

    async def iniciar(self) -> None:
        """Lanza el navegador y ejecuta el rastreo completo."""
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                user_agent=USER_AGENT,
                locale="es-ES",
                viewport={"width": 1366, "height": 768},
            )
            pagina = await context.new_page()
            try:
                await self._ejecutar_crawl(pagina)
            finally:
                await context.close()
                await browser.close()

    async def _ejecutar_crawl(self, pagina: Page) -> None:
        """Bucle principal del rastreo: consume la cola de URLs pendientes."""
        url_inicial_normalizada = normalizar_url(self.url_inicial)
        if not url_inicial_normalizada:
            logger.error("La URL inicial no es válida: %s", self.url_inicial)
            return

        await self.cola.put((url_inicial_normalizada, 0))

        while not self.cola.empty():
            # Control del límite máximo de páginas a procesar.
            if self.paginas_procesadas >= self.max_paginas:
                logger.info(
                    "Se alcanzó el límite máximo de páginas (%d).", self.max_paginas
                )
                break

            url, profundidad = await self.cola.get()
            await self._procesar_url(pagina, url, profundidad)

            # Retardo configurable entre peticiones para no saturar el servidor.
            if not self.cola.empty():
                await asyncio.sleep(self.delay)

    async def _procesar_url(self, pagina: Page, url: str, profundidad: int) -> None:
        """Procesa una única URL: la visita, extrae datos y encola sus enlaces."""
        # Evita duplicados y bucles infinitos (memoria + base de datos).
        if url in self.urls_procesadas or self.base_datos.url_existe(url):
            return
        # Filtro estricto de dominio.
        if obtener_dominio(url) != self.dominio:
            return
        # Control de profundidad máxima.
        if profundidad > self.max_depth:
            return

        self.urls_procesadas.add(url)
        logger.info("Procesando (nivel %d): %s", profundidad, url)

        # Navegación con manejo robusto de errores (timeouts, DNS, SSL, etc.).
        try:
            await pagina.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout al cargar la página: %s", url)
            return
        except PlaywrightError as error:
            logger.warning("Error de navegación en %s: %s", url, error)
            return
        except Exception as error:
            logger.warning("Error inesperado al navegar a %s: %s", url, error)
            return

        try:
            # Extracción de datos: HTML renderizado, título, texto y JS.
            html_completo: str = await pagina.content()
            titulo: Optional[str] = await pagina.title()
            texto_limpio: str = extraer_texto_limpio(html_completo)
            javascript_codigo: str = extraer_javascript(html_completo)

            # Guarda los archivos de la página en una carpeta individual.
            ruta_carpeta, rutas_archivos = self._guardar_archivos_en_disco(
                url=url,
                html_completo=html_completo,
                texto_limpio=texto_limpio,
                javascript_codigo=javascript_codigo,
            )

            # Persistencia segura en SQLite (página + referencias a sus archivos).
            pagina_id = self.base_datos.guardar_pagina(
                url=url,
                dominio=self.dominio,
                titulo=titulo,
                html_completo=html_completo,
                texto_limpio=texto_limpio,
                javascript_codigo=javascript_codigo,
                ruta_carpeta=ruta_carpeta,
            )
            for tipo, ruta_archivo in rutas_archivos:
                self.base_datos.guardar_archivo(pagina_id, tipo, ruta_archivo)

            self.paginas_procesadas += 1

            # Encola los enlaces internos para continuar el rastreo.
            if profundidad < self.max_depth:
                for enlace in extraer_enlaces(html_completo, url, self.dominio):
                    if (
                        enlace not in self.urls_procesadas
                        and not self.base_datos.url_existe(enlace)
                    ):
                        await self.cola.put((enlace, profundidad + 1))
        except Exception as error:
            logger.error("Error al extraer datos de %s: %s", url, error)

    def _guardar_archivos_en_disco(
        self,
        url: str,
        html_completo: str,
        texto_limpio: str,
        javascript_codigo: str,
    ) -> tuple[str, list[tuple[str, str]]]:
        """Guarda los archivos de una página en una carpeta individual.

        Crea la carpeta `<ruta_directorio_archivos>/<slug>` y escribe en ella:
        `pagina.html`, `texto.txt` y `javascript.js`. Devuelve la ruta de la
        carpeta y la lista de pares (tipo, ruta_archivo) para registrar en BD.
        """
        slug = generar_slug(url)
        carpeta = Path(self.ruta_directorio_archivos) / slug
        carpeta.mkdir(parents=True, exist_ok=True)

        archivos: list[tuple[str, str, str]] = [
            ("html", "pagina.html", html_completo),
            ("texto", "texto.txt", texto_limpio),
            ("javascript", "javascript.js", javascript_codigo),
        ]

        rutas_archivos: list[tuple[str, str]] = []
        for tipo, nombre, contenido in archivos:
            ruta_archivo = carpeta / nombre
            ruta_archivo.write_text(contenido, encoding="utf-8")
            rutas_archivos.append((tipo, str(ruta_archivo)))

        return str(carpeta), rutas_archivos


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

def crear_ruta_ejecucion() -> str:
    """Genera la ruta de la carpeta dedicada a la ejecución actual.

    Devuelve `<RUTA_DIRECTORIO_ARCHIVOS>/ejecucion_<marca de tiempo>`, de modo
    que cada ejecución del scraper guarde sus páginas en una carpeta nueva e
    independiente de las anteriores.
    """
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(Path(RUTA_DIRECTORIO_ARCHIVOS) / f"ejecucion_{marca_tiempo}")


async def main() -> None:
    """Función principal: configura el crawler y ejecuta el rastreo."""
    # Deriva el dominio de la URL inicial si no se especificó uno explícito.
    dominio: str = DOMINIO_PERMITIDO or obtener_dominio(URL_INICIAL)

    # Cada ejecución usa una carpeta nueva (marca de tiempo).
    ruta_directorio_archivos = crear_ruta_ejecucion()
    logger.info("Carpeta de archivos de esta ejecución: %s", ruta_directorio_archivos)

    base_datos = BaseDatos(RUTA_BASE_DATOS)
    crawler = Crawler(
        url_inicial=URL_INICIAL,
        dominio=dominio,
        max_depth=PROFUNDIDAD_MAXIMA,
        max_paginas=MAX_PAGINAS,
        delay=RETARDO_ENTRE_PETICIONES,
        timeout=TIEMPO_ESPERA_NAVEGACION,
        base_datos=base_datos,
        ruta_directorio_archivos=ruta_directorio_archivos,
    )

    try:
        await crawler.iniciar()
    finally:
        base_datos.cerrar()

    logger.info(
        "Proceso finalizado. Páginas procesadas: %d", crawler.paginas_procesadas
    )


if __name__ == "__main__":
    asyncio.run(main())
