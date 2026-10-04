import os
import psycopg2
from datetime import datetime

# Estas variables las vamos a definir como variables de entorno en la VM,
# no escritas aquí directamente (por seguridad)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "reportes_raw")
DB_USER = os.environ.get("DB_USER", "humboldt_bot")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")


def _conectar():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def _crear_tablas_si_no_existen(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reportes (
                id SERIAL PRIMARY KEY,
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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reportes_definitivos (
                id SERIAL PRIMARY KEY,
                reporte_id INTEGER,
                fecha_hora TEXT,
                nombre TEXT,
                numero TEXT,
                mensaje_original TEXT,
                latitud REAL,
                longitud REAL,
                temperatura_nasa REAL,
                precipitacion_nasa REAL,
                humedad_nasa REAL,
                viento_nasa REAL,
                veredicto TEXT
            )
        """)
    conn.commit()


def guardar_pedido(numero, nombre, texto, tipo, timestamp_whatsapp, latitud=None, longitud=None):
    fecha_hora = datetime.fromtimestamp(int(timestamp_whatsapp)).strftime("%Y-%m-%d %H:%M:%S")

    conn = _conectar()
    try:
        _crear_tablas_si_no_existen(conn)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reportes (fecha_hora, nombre, numero, tipo, mensaje, latitud, longitud)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (fecha_hora, nombre, numero, tipo, texto, latitud, longitud),
            )
            reporte_id = cur.fetchone()[0]
        conn.commit()
        return reporte_id
    finally:
        conn.close()


def buscar_ultimo_reporte_sin_ubicacion(numero):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, fecha_hora, nombre, numero, tipo, mensaje FROM reportes
                   WHERE numero = %s AND tipo IN ('text', 'audio') AND latitud IS NULL AND procesado = 0
                   ORDER BY id DESC LIMIT 1""",
                (numero,),
            )
            fila = cur.fetchone()
            if fila is None:
                return None
            return {
                "id": fila[0], "fecha_hora": fila[1], "nombre": fila[2],
                "numero": fila[3], "tipo": fila[4], "mensaje": fila[5],
            }
    finally:
        conn.close()


def marcar_como_procesado(reporte_id):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE reportes SET procesado = 1 WHERE id = %s", (reporte_id,))
        conn.commit()
    finally:
        conn.close()


def guardar_definitivo(reporte_id, fecha_hora, nombre, numero, mensaje_original,
                        latitud, longitud, datos_nasa, veredicto):
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO reportes_definitivos
                   (reporte_id, fecha_hora, nombre, numero, mensaje_original, latitud, longitud,
                    temperatura_nasa, precipitacion_nasa, humedad_nasa, viento_nasa, veredicto)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    reporte_id, fecha_hora, nombre, numero, mensaje_original, latitud, longitud,
                    datos_nasa.get("temperatura_c"), datos_nasa.get("precipitacion_mm"),
                    datos_nasa.get("humedad_relativa_pct"), datos_nasa.get("velocidad_viento_ms"),
                    veredicto,
                ),
            )
        conn.commit()
    finally:
        conn.close()
