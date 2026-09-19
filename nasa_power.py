import requests

BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# Parámetros que pedimos a NASA POWER:
# T2M = temperatura a 2m, PRECTOTCORR = precipitación, RH2M = humedad relativa, WS2M = velocidad del viento
PARAMETROS = "T2M,PRECTOTCORR,RH2M,WS2M"


def obtener_clima_nasa(latitud, longitud, fecha):
    """
    Consulta NASA POWER para una ubicación y fecha específicas.
    fecha debe ser un string en formato 'YYYY-MM-DD'.
    Devuelve un diccionario con las variables climáticas de ese día.
    """
    fecha_formato_nasa = fecha.replace("-", "")  # NASA POWER espera YYYYMMDD

    params = {
        "parameters": PARAMETROS,
        "community": "AG",  # comunidad "Agroclimatology", la más relevante para este caso
        "longitude": longitud,
        "latitude": latitud,
        "start": fecha_formato_nasa,
        "end": fecha_formato_nasa,
        "format": "JSON",
    }

    resp = requests.get(BASE_URL, params=params)
    resp.raise_for_status()
    data = resp.json()

    propiedades = data["properties"]["parameter"]

    return {
        "temperatura_c": propiedades["T2M"].get(fecha_formato_nasa),
        "precipitacion_mm": propiedades["PRECTOTCORR"].get(fecha_formato_nasa),
        "humedad_relativa_pct": propiedades["RH2M"].get(fecha_formato_nasa),
        "velocidad_viento_ms": propiedades["WS2M"].get(fecha_formato_nasa),
    }


if __name__ == "__main__":
    # Prueba rápida con coordenadas de Bucaramanga y la fecha de hoy
    resultado = obtener_clima_nasa(7.1193, -73.1227, "2026-08-27")
    print(resultado)
