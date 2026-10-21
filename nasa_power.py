from datetime import datetime, timedelta

import requests

BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# T2M = temperatura media, T2M_MAX = maxima diaria, PRECTOTCORR = lluvia (mm/dia),
# RH2M = humedad relativa, WS2M = viento a 2 m
PARAMETROS = "T2M,T2M_MAX,PRECTOTCORR,RH2M,WS2M"


def _consultar(parametros, latitud, longitud, inicio, fin):
    """inicio y fin en formato YYYY-MM-DD. Devuelve {parametro: {YYYYMMDD: valor}}."""
    params = {
        "parameters": parametros,
        "community": "AG",
        "longitude": longitud,
        "latitude": latitud,
        "start": inicio.replace("-", ""),
        "end": fin.replace("-", ""),
        "format": "JSON",
    }
    resp = requests.get(BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()["properties"]["parameter"]


def obtener_clima_nasa(latitud, longitud, fecha):
    """Clima de UN dia (fecha 'YYYY-MM-DD'). -999 = NASA aun no tiene el dato."""
    p = _consultar(PARAMETROS, latitud, longitud, fecha, fecha)
    f = fecha.replace("-", "")
    return {
        "temperatura_c": p["T2M"].get(f),
        "temperatura_max_c": p.get("T2M_MAX", {}).get(f),
        "precipitacion_mm": p["PRECTOTCORR"].get(f),
        "humedad_relativa_pct": p["RH2M"].get(f),
        "velocidad_viento_ms": p["WS2M"].get(f),
    }


def obtener_sequia_nasa(latitud, longitud, fecha, dias=30):
    """
    Indicadores de sequia en los `dias` previos a `fecha` (incluida): lluvia acumulada y racha de
    dias secos (< 1 mm) que termina en el ultimo dia con dato. Ignora los dias -999 (rezago de NASA).
    Devuelve None si faltan mas del 20 % de los dias.
    """
    fin = datetime.strptime(fecha, "%Y-%m-%d").date()
    inicio = fin - timedelta(days=dias - 1)
    serie = _consultar("PRECTOTCORR", latitud, longitud, inicio.isoformat(), fin.isoformat())["PRECTOTCORR"]
    validos = [(d, v) for d, v in sorted(serie.items()) if v is not None and v != -999]
    if len(validos) < int(dias * 0.8):
        return None
    racha = 0
    for _, v in reversed(validos):
        if v < 1.0:
            racha += 1
        else:
            break
    return {
        "lluvia_acum_mm": round(sum(v for _, v in validos), 1),
        "dias_secos": racha,
        "dias_con_dato": len(validos),
    }


def obtener_clima_para_reporte(latitud, longitud, fecha, incluir_sequia=False):
    """Clima del dia y, si el reporte habla de sequia, tambien los indicadores de 30 dias."""
    datos = obtener_clima_nasa(latitud, longitud, fecha)
    if incluir_sequia:
        datos.update(obtener_sequia_nasa(latitud, longitud, fecha) or {})
    return datos


if __name__ == "__main__":
    print(obtener_clima_para_reporte(7.07, -73.11, "2026-09-15", incluir_sequia=True))
