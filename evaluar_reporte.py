def es_reporte_climatico(texto):
    if texto is None:
        return False
    texto = texto.lower()
    palabras = [
        "llover", "lloviendo", "lluvia", "aguacero", "diluvio",
        "calor", "caluroso", "hace mucho sol", "soleado",
        "frío", "frio", "helado",
        "viento", "ventoso", "brisa fuerte",
        "nublado", "nube", "tormenta", "granizo",
    ]
    return any(p in texto for p in palabras)


def es_reporte_rio(texto):
    """Detecta si el mensaje habla del estado del río (turbidez, nivel)."""
    if texto is None:
        return False
    texto = texto.lower()
    palabras = [
        "río", "rio", "turbio", "turbia", "sucio", "sucia", "barroso", "barrosa",
        "claro", "clara", "creciente", "subió", "subio", "bajó", "bajo el nivel",
        "crecida", "desbordó", "desbordo",
    ]
    return any(p in texto for p in palabras)


def evaluar_coincidencia(texto_reporte, datos_nasa):
    if texto_reporte is None:
        return "sin_evidencia"
    texto = texto_reporte.lower()
    precipitacion = datos_nasa.get("precipitacion_mm")
    temperatura = datos_nasa.get("temperatura_c")
    viento = datos_nasa.get("velocidad_viento_ms")

    if precipitacion == -999 or precipitacion is None:
        return "sin_evidencia"

    if any(p in texto for p in ["llover", "lloviendo", "lluvia", "aguacero", "diluvio"]):
        return "coincide" if precipitacion > 1.0 else "no_coincide"
    if any(p in texto for p in ["calor", "caluroso", "hace mucho sol"]):
        return "coincide" if (temperatura is not None and temperatura > 28) else "no_coincide"
    if any(p in texto for p in ["frío", "frio", "helado"]):
        return "coincide" if (temperatura is not None and temperatura < 18) else "no_coincide"
    if any(p in texto for p in ["viento", "ventoso", "brisa fuerte"]):
        return "coincide" if (viento is not None and viento > 3) else "no_coincide"
    return "sin_evidencia"


def evaluar_turbidez(texto_reporte, ndti):
    """
    Compara la percepción de la persona sobre el río contra el NDTI de Sentinel-2.
    NDTI más alto = agua más turbia/barrosa. Umbral inicial 0.05 (ajustar con datos reales).
    """
    if texto_reporte is None or ndti is None:
        return "sin_evidencia"
    texto = texto_reporte.lower()

    if any(p in texto for p in ["turbio", "turbia", "sucio", "sucia", "barroso", "barrosa", "crecida"]):
        return "coincide" if ndti > 0.05 else "no_coincide"
    if any(p in texto for p in ["claro", "clara"]):
        return "coincide" if ndti <= 0.05 else "no_coincide"
    return "sin_evidencia"
