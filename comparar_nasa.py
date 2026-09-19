import sqlite3
import os
from nasa_power import obtener_clima_nasa

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reportes_raw.db")


def comparar_reportes_con_nasa():
    """Busca reportes con ubicación y los compara con los datos de NASA POWER de ese día."""

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # para poder acceder a las columnas por nombre
    cursor = conn.cursor()

    # Solo reportes que tengan latitud/longitud (los de tipo "location")
    cursor.execute("""
        SELECT id, fecha_hora, nombre, numero, mensaje, latitud, longitud
        FROM reportes
        WHERE latitud IS NOT NULL AND longitud IS NOT NULL
    """)
    reportes = cursor.fetchall()

    if not reportes:
        print("No hay reportes con ubicación todavía.")
        return

    for reporte in reportes:
        # fecha_hora viene como "2026-09-09 14:40:53" -> NASA POWER solo necesita la fecha (sin hora)
        fecha = reporte["fecha_hora"].split(" ")[0]

        print(f"\n--- Reporte #{reporte['id']} de {reporte['nombre']} ---")
        print(f"Fecha: {fecha} | Ubicación: {reporte['latitud']}, {reporte['longitud']}")

        try:
            clima_nasa = obtener_clima_nasa(reporte["latitud"], reporte["longitud"], fecha)
            print(f"NASA POWER dice -> {clima_nasa}")
        except Exception as e:
            print(f"Error consultando NASA POWER: {e}")

    conn.close()


if __name__ == "__main__":
    comparar_reportes_con_nasa()
