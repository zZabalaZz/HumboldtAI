import os
from pymongo import MongoClient

CONNECTION_STRING = os.environ.get("COSMOS_CONNECTION_STRING", "mongodb://localhost:27017/")

_client = None


def _get_collection():
    global _client
    if _client is None:
        _client = MongoClient(CONNECTION_STRING)
    db = _client["humboldtai"]
    return db["reportes_definitivos"]


def guardar_definitivo(reporte_id, fecha_hora, nombre, numero, mensaje_original,
                        latitud, longitud, datos_nasa=None, veredicto_clima=None,
                        datos_sentinel=None, veredicto_rio=None):
    coleccion = _get_collection()

    documento = {
        "reporte_id": reporte_id,
        "fecha_hora": fecha_hora,
        "nombre": nombre,
        "numero": numero,
        "mensaje_original": mensaje_original,
        "ubicacion": {
            "type": "Point",
            "coordinates": [longitud, latitud],
        },
        "imagen_url": None,
    }

    if datos_nasa is not None:
        documento["clima"] = {
            "temperatura_c": datos_nasa.get("temperatura_c"),
            "precipitacion_mm": datos_nasa.get("precipitacion_mm"),
            "humedad_pct": datos_nasa.get("humedad_relativa_pct"),
            "viento_ms": datos_nasa.get("velocidad_viento_ms"),
            "veredicto": veredicto_clima,
        }

    if datos_sentinel is not None:
        documento["rio"] = {
            "ndti": datos_sentinel.get("ndti"),
            "fecha_imagen_satelital": datos_sentinel.get("fecha_imagen_satelital"),
            "veredicto": veredicto_rio,
        }

    coleccion.insert_one(documento)


def crear_indice_geoespacial():
    coleccion = _get_collection()
    coleccion.create_index([("ubicacion", "2dsphere")])
