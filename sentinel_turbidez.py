import ee
import os

# Ruta al archivo de credenciales de la cuenta de servicio
SERVICE_ACCOUNT_KEY = os.environ.get(
    "SENTINEL_KEY_PATH", "/home/zabala/HumboldtAI/sentinel-key.json"
)


def _inicializar():
    """Autentica con Earth Engine usando la cuenta de servicio (sin interacción humana)."""
    credenciales = ee.ServiceAccountCredentials(None, SERVICE_ACCOUNT_KEY)
    ee.Initialize(credenciales)


def obtener_turbidez_sentinel(latitud, longitud, fecha, rango_dias=10):
    """
    Busca la imagen Sentinel-2 más reciente y sin nubes para ese punto,
    dentro de un rango de días antes de 'fecha' (YYYY-MM-DD),
    y calcula el índice de turbidez (NDTI) en ese punto exacto.

    Devuelve un diccionario con el valor y la fecha real de la imagen usada,
    o None si no encontró ninguna imagen utilizable.
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
        .sort("system:time_start", False)  # más reciente primero
    )

    imagen = coleccion.first()

    # NDTI = (Rojo - Verde) / (Rojo + Verde) -- B4=Rojo, B3=Verde en Sentinel-2
    ndti = imagen.normalizedDifference(["B4", "B3"]).rename("NDTI")

    resultado = ndti.reduceRegion(
        reducer=ee.Reducer.first(), geometry=punto, scale=10
    ).getInfo()

    fecha_imagen = ee.Date(imagen.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    return {
        "ndti": resultado.get("NDTI"),
        "fecha_imagen_satelital": fecha_imagen,
    }


if __name__ == "__main__":
    # Prueba con coordenadas del río Magdalena y una fecha de hace 2 semanas
    resultado = obtener_turbidez_sentinel(7.5, -74.8, "2026-09-08")
    print(resultado)
