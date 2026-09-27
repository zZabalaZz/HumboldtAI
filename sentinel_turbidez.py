import ee
import os
import requests

SERVICE_ACCOUNT_KEY = os.environ.get(
    "SENTINEL_KEY_PATH", "/home/zabala/HumboldtAI/sentinel-key.json"
)


def _inicializar():
    credenciales = ee.ServiceAccountCredentials(None, SERVICE_ACCOUNT_KEY)
    ee.Initialize(credenciales)


def obtener_turbidez_sentinel(latitud, longitud, fecha, rango_dias=30, incluir_imagen=True):
    """
    Devuelve NDTI + fecha de la imagen, y opcionalmente los bytes de un thumbnail
    en color real (RGB) del área alrededor del punto, listo para guardar en Mongo.
    """
    _inicializar()

    punto = ee.Geometry.Point([longitud, latitud])
    fecha_fin = ee.Date(fecha)
    fecha_inicio = fecha_fin.advance(-rango_dias, "day")

    coleccion = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(punto)
        .filterDate(fecha_inicio, fecha_fin)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .sort("system:time_start", False)
    )

    cantidad = coleccion.size().getInfo()
    if cantidad == 0:
        return None

    imagen = coleccion.first()

    ndti = imagen.normalizedDifference(["B4", "B3"]).rename("NDTI")
    resultado = ndti.reduceRegion(
        reducer=ee.Reducer.first(), geometry=punto, scale=10
    ).getInfo()

    fecha_imagen = ee.Date(imagen.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    salida = {
        "ndti": resultado.get("NDTI"),
        "fecha_imagen_satelital": fecha_imagen,
        "imagen_bytes": None,
    }

    if incluir_imagen:
        # Recorte pequeno alrededor del punto (aprox 1km x 1km) en color real
        area = punto.buffer(500).bounds()
        visualizacion = imagen.visualize(bands=["B4", "B3", "B2"], min=0, max=3000)
        url = visualizacion.getThumbURL({
            "region": area,
            "dimensions": 512,
            "format": "png",
        })
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            salida["imagen_bytes"] = resp.content
        except Exception as e:
            print(f"No se pudo descargar el thumbnail: {e}")

    return salida


if __name__ == "__main__":
    resultado = obtener_turbidez_sentinel(7.0653, -73.8547, "2026-09-19", rango_dias=30)
    if resultado:
        print("NDTI:", resultado["ndti"], "| Fecha:", resultado["fecha_imagen_satelital"])
        if resultado["imagen_bytes"]:
            print("Imagen descargada:", len(resultado["imagen_bytes"]), "bytes")
            with open("prueba_sentinel.png", "wb") as f:
                f.write(resultado["imagen_bytes"])
            print("Guardada en prueba_sentinel.png para revisarla")
