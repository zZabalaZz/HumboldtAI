import re

# Umbrales PROVISIONALES: calibrarlos con datos reales de la zona.
UMBRAL_LLUVIA_MM = 1.0       # lluvia diaria
UMBRAL_CALOR_MAX_C = 32      # temperatura MAXIMA diaria
UMBRAL_CALOR_MEDIA_C = 28    # solo si no hay temperatura maxima
UMBRAL_FRIO_C = 18           # temperatura media
UMBRAL_VIENTO_MS = 3
UMBRAL_SEQUIA_MM = 30        # lluvia acumulada en 30 dias
UMBRAL_SEQUIA_DIAS = 15      # dias secos seguidos (< 1 mm)
UMBRAL_NDTI = 0.05           # turbidez del rio

PALABRAS_LLUVIA = ["llover", "lloviendo", "lluvia", "aguacero", "diluvio"]
PALABRAS_CALOR = ["calor", "caluroso", "hace mucho sol"]
PALABRAS_FRIO = ["frío", "frio", "helado"]
PALABRAS_VIENTO = ["viento", "ventoso", "brisa fuerte"]
PALABRAS_SEQUIA = ["sequía", "sequia", "reseco", "muy seco", "tierra seca", "no llueve", "no ha llovido"]
PALABRAS_OTRAS = ["soleado", "nublado", "nube", "tormenta", "granizo"]
PALABRAS_RIO = ["turbio", "turbia", "sucio", "sucia", "barroso", "barrosa", "claro", "clara", "creciente",
                "subió", "subio", "bajó", "bajo el nivel", "crecida", "desbordó", "desbordo"]
# "río" como palabra completa: antes "rio" sin limites coincidia con "frío" y con "Rionegro"
RE_RIO = re.compile(r"\b(río|rio)s?\b")


def _contiene(texto, palabras):
    return any(p in texto for p in palabras)


def _ok(v):
    return v is not None and v != -999  # -999 = "sin dato" de NASA POWER


def es_reporte_climatico(texto):
    if texto is None:
        return False
    t = texto.lower()
    return _contiene(t, PALABRAS_LLUVIA + PALABRAS_CALOR + PALABRAS_FRIO + PALABRAS_VIENTO
                     + PALABRAS_SEQUIA + PALABRAS_OTRAS)


def es_reporte_sequia(texto):
    return texto is not None and _contiene(texto.lower(), PALABRAS_SEQUIA)


def es_reporte_rio(texto):
    if texto is None:
        return False
    t = texto.lower()
    return bool(RE_RIO.search(t)) or _contiene(t, PALABRAS_RIO)


# --- Condiciones reales del dia segun NASA POWER (las usa tambien el gemelo digital) ---
def hay_lluvia(nasa):
    return _ok(nasa.get("precipitacion_mm")) and nasa["precipitacion_mm"] > UMBRAL_LLUVIA_MM


def hay_calor(nasa):
    if _ok(nasa.get("temperatura_max_c")):
        return nasa["temperatura_max_c"] > UMBRAL_CALOR_MAX_C
    return _ok(nasa.get("temperatura_c")) and nasa["temperatura_c"] > UMBRAL_CALOR_MEDIA_C


def hay_frio(nasa):
    return _ok(nasa.get("temperatura_c")) and nasa["temperatura_c"] < UMBRAL_FRIO_C


def hay_viento(nasa):
    return _ok(nasa.get("velocidad_viento_ms")) and nasa["velocidad_viento_ms"] > UMBRAL_VIENTO_MS


def hay_sequia(nasa):
    """True/False, o None si no hay indicadores de 30 dias para juzgar."""
    acum, dias = nasa.get("lluvia_acum_mm"), nasa.get("dias_secos")
    if not _ok(acum) or not _ok(dias):
        return None
    return acum < UMBRAL_SEQUIA_MM or dias >= UMBRAL_SEQUIA_DIAS


def _veredicto(coincide):
    return "coincide" if coincide else "no_coincide"


def evaluar_coincidencia(texto_reporte, datos_nasa):
    """coincide / no_coincide / sin_evidencia. Ojo: aun no maneja negaciones ("no esta lloviendo")."""
    if texto_reporte is None or not datos_nasa:
        return "sin_evidencia"
    t = texto_reporte.lower()

    if _contiene(t, PALABRAS_SEQUIA):  # usa sus propios indicadores de 30 dias
        s = hay_sequia(datos_nasa)
        return "sin_evidencia" if s is None else _veredicto(s)

    if not _ok(datos_nasa.get("precipitacion_mm")):
        return "sin_evidencia"  # rezago de NASA POWER

    if _contiene(t, PALABRAS_LLUVIA):
        return _veredicto(hay_lluvia(datos_nasa))
    if _contiene(t, PALABRAS_CALOR):
        return _veredicto(hay_calor(datos_nasa))
    if _contiene(t, PALABRAS_FRIO):
        return _veredicto(hay_frio(datos_nasa))
    if _contiene(t, PALABRAS_VIENTO):
        return _veredicto(hay_viento(datos_nasa))
    return "sin_evidencia"


def evaluar_turbidez(texto_reporte, ndti):
    """NDTI mas alto = agua mas turbia. UMBRAL_NDTI es un valor inicial, por calibrar."""
    if texto_reporte is None or ndti is None:
        return "sin_evidencia"
    t = texto_reporte.lower()
    if _contiene(t, ["turbio", "turbia", "sucio", "sucia", "barroso", "barrosa", "crecida"]):
        return _veredicto(ndti > UMBRAL_NDTI)
    if _contiene(t, ["claro", "clara"]):
        return _veredicto(ndti <= UMBRAL_NDTI)
    return "sin_evidencia"
