"""
Script de revalidacion diferida: busca reportes climaticos que quedaron
en 'sin_evidencia' por el rezago de NASA POWER, y los vuelve a evaluar
ahora que el dato satelital ya deberia estar disponible.

Pensado para correr una vez al dia via cron, no dentro del webhook.
"""
import os
from datetime import datetime, timedelta
from pymongo import MongoClient

from nasa_power import obtener_clima_nasa
from evaluar_reporte import evaluar_coincidencia

CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING", "mongodb://localhost:27017/")


def revalidar_reportes_climaticos(dias_atras=7):
    client = MongoClient(CONNECTION_STRING)
    coleccion = client["humboldtai"]["reportes_definitivos"]

    # Buscamos documentos con clima marcado como sin_evidencia
    pendientes = coleccion.find({"clima.veredicto": "sin_evidencia"})

    fecha_limite = datetime.now() - timedelta(days=dias_atras)
    revalidados = 0

    for doc in pendientes:
        fecha_reporte = datetime.strptime(doc["fecha_hora"], "%Y-%m-%d %H:%M:%S")

        # Solo reintentamos si ya pasaron suficientes dias para que NASA tenga el dato
        if fecha_reporte > fecha_limite:
            continue

        fecha_str = fecha_reporte.strftime("%Y-%m-%d")
        lat = doc["ubicacion"]["coordinates"][1]
        lon = doc["ubicacion"]["coordinates"][0]

        try:
            datos_nasa = obtener_clima_nasa(lat, lon, fecha_str)
        except Exception as e:
            print(f"Error consultando NASA POWER para reporte #{doc['reporte_id']}: {e}")
            continue

        if datos_nasa.get("precipitacion_mm") == -999:
            print(f"Reporte #{doc['reporte_id']}: NASA sigue sin dato para {fecha_str}, se reintenta despues")
            continue

        nuevo_veredicto = evaluar_coincidencia(doc["mensaje_original"], datos_nasa)

        coleccion.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "clima.temperatura_c": datos_nasa.get("temperatura_c"),
                "clima.precipitacion_mm": datos_nasa.get("precipitacion_mm"),
                "clima.humedad_pct": datos_nasa.get("humedad_relativa_pct"),
                "clima.viento_ms": datos_nasa.get("velocidad_viento_ms"),
                "clima.veredicto": nuevo_veredicto,
            }}
        )
        print(f"Reporte #{doc['reporte_id']} revalidado: {nuevo_veredicto}")
        revalidados += 1

    print(f"\nTotal revalidados: {revalidados}")


if __name__ == "__main__":
    revalidar_reportes_climaticos()
