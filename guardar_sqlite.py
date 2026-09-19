import os
import sqlite3
from datetime import datetime

# Ruta absoluta: siempre guarda junto a este archivo, sin importar desde dónde se ejecute
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reportes_raw.db")


def _crear_tabla_si_no_existe(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT,
            nombre TEXT,
            numero TEXT,
            tipo TEXT,
            mensaje TEXT,
            latitud REAL,
            longitud REAL,
            procesado INTEGER DEFAULT 0
        )
    """)
    conn.commit()


def guardar_pedido(numero, nombre, texto, tipo, timestamp_whatsapp, latitud=None, longitud=None):
    """Agrega una fila a la base de datos SQLite con el reporte recibido."""

    fecha_hora = datetime.fromtimestamp(int(timestamp_whatsapp)).strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    try:
        _crear_tabla_si_no_existe(conn)
        conn.execute(
            "INSERT INTO reportes (fecha_hora, nombre, numero, tipo, mensaje, latitud, longitud) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fecha_hora, nombre, numero, tipo, texto, latitud, longitud),
        )
        conn.commit()
    finally:
        conn.close()