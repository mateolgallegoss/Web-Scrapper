#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrar_archivos.py
==================
Genera las carpetas individuales de archivos para las páginas ya guardadas en
la base de datos SQLite, sin volver a navegar por la web.

Para cada fila de `paginas_scrapeadas` crea una carpeta
`<RUTA_DIRECTORIO_ARCHIVOS>/<slug>` con `pagina.html`, `texto.txt` y
`javascript.js`, actualiza `ruta_carpeta` y registra los archivos en la tabla
`archivos_guardados`.

Uso:
    python programas/migrar_archivos.py
    # o desde dentro de programas/: python migrar_archivos.py
"""

import logging
from pathlib import Path

from scraper import (
    RUTA_BASE_DATOS,
    RUTA_DIRECTORIO_ARCHIVOS,
    BaseDatos,
    generar_slug,
    resolver_ruta,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrador")


def migrar() -> None:
    """Lee la base de datos y genera las carpetas de archivos por página."""
    # Instancia BaseDatos para garantizar que existan las tablas y el esquema
    # actualizado (incluye migración de versiones anteriores).
    base_datos = BaseDatos(str(resolver_ruta(RUTA_BASE_DATOS)))
    conexion = base_datos.conexion

    filas = conexion.execute(
        "SELECT id, url, html_completo, texto_limpio, javascript_codigo "
        "FROM paginas_scrapeadas;"
    ).fetchall()

    if not filas:
        logger.info("No hay páginas para migrar.")
        base_datos.cerrar()
        return

    procesadas = 0
    for pagina_id, url, html_completo, texto_limpio, javascript_codigo in filas:
        slug = generar_slug(url)
        carpeta = resolver_ruta(RUTA_DIRECTORIO_ARCHIVOS) / slug
        carpeta.mkdir(parents=True, exist_ok=True)

        archivos = {
            "html": ("pagina.html", html_completo or ""),
            "texto": ("texto.txt", texto_limpio or ""),
            "javascript": ("javascript.js", javascript_codigo or ""),
        }

        with conexion:
            for tipo, (nombre, contenido) in archivos.items():
                ruta_archivo = carpeta / nombre
                ruta_archivo.write_text(contenido, encoding="utf-8")
                conexion.execute(
                    """
                    INSERT OR REPLACE INTO archivos_guardados
                        (pagina_id, tipo, ruta_archivo)
                    VALUES (?, ?, ?);
                    """,
                    (pagina_id, tipo, str(ruta_archivo)),
                )
            conexion.execute(
                "UPDATE paginas_scrapeadas SET ruta_carpeta = ? WHERE id = ?;",
                (str(carpeta), pagina_id),
            )
        procesadas += 1

    base_datos.cerrar()
    logger.info("Migración finalizada. Carpetas creadas: %d", procesadas)


if __name__ == "__main__":
    migrar()