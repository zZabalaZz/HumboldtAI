"""
API de solo lectura para el dashboard (index.html).

Se registra en el mismo Flask del webhook:
    from api import api
    app.register_blueprint(api)

Convierte los documentos de reportes_definitivos al formato que espera el
frontend (lat/lng, municipio, estado...) y ANONIMIZA: nunca devuelve nombre,
numero ni el texto original del mensaje.
"""
import hashlib
import hmac
import math
import os

from bson import ObjectId
from flask import Blueprint, Response, abort, jsonify, request
from flask_cors import CORS

from guardar_cosmos import _get_collection

api = Blueprint("api", __name__, url_prefix="/api")

# Origenes permitidos para el navegador, separados por coma. Solo scheme+host,
# sin ruta. Ej: "https://santiago.github.io". Si el index.html se sirve desde
# el mismo dominio por nginx, no hace falta definirla.
_origenes = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _origenes:
    CORS(api, origins=_origenes)

# Secreto para seudonimizar los numeros (HMAC). Sin el, la API se niega a responder.
ANON_SECRET = os.environ.get("ANON_SECRET", "").encode()

# Decimales de las coordenadas publicadas: 2 ~ 1 km, 3 ~ 110 m
PRECISION_COORD = 2

# Aproximacion PROVISIONAL: municipio mas cercano a estos centros (los mismos del
# frontend). Reemplazar por poligonos municipales reales (DANE) cuando se pueda.
CENTROS = {"Girón": (7.07, -73.18), "Rionegro": (7.30, -73.19)}
RADIO_MAX_KM = 25

PALABRAS_TIPO = [
    ("Lluvia", ["llover", "lloviendo", "lluvia", "aguacero", "diluvio", "tormenta", "granizo"]),
    ("Calor", ["calor", "caluroso", "hace mucho sol", "soleado"]),
    ("Frío", ["frío", "frio", "helado"]),
    ("Viento", ["viento", "ventoso", "brisa fuerte"]),
]


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def _municipio(lat, lng):
    nombre, centro = min(CENTROS.items(), key=lambda kv: _km(lat, lng, *kv[1]))
    return nombre if _km(lat, lng, *centro) <= RADIO_MAX_KM else "Otro"


def _sensor(numero):
    h = hmac.new(ANON_SECRET, str(numero).encode(), hashlib.sha256).hexdigest()
    return f"Sensor #{int(h[:6], 16) % 1000:03d}"


def _valido(v):
    return v is not None and v != -999  # -999 = "sin dato" de NASA POWER


def _tipo(doc):
    if "rio" in doc:
        return "Estado del río"
    texto = (doc.get("mensaje_original") or "").lower()
    for etiqueta, palabras in PALABRAS_TIPO:
        if any(p in texto for p in palabras):
            return etiqueta
    return "Clima"


def _estado(doc):
    # Mismos umbrales que usa el frontend en la consulta de precipitacion.
    # La severidad de reportes de rio NO esta definida todavia.
    mm = (doc.get("clima") or {}).get("precipitacion_mm")
    if _valido(mm):
        return "critico" if mm >= 50 else "alerta" if mm >= 30 else "normal"
    return "normal"


def _a_reporte(doc):
    """Lista blanca: solo estos campos salen de la API."""
    lng, lat = doc["ubicacion"]["coordinates"]
    r = {
        "id": str(doc["_id"]),
        "sensor": _sensor(doc.get("numero")),
        "municipio": _municipio(lat, lng),
        "lat": round(lat, PRECISION_COORD),
        "lng": round(lng, PRECISION_COORD),
        "tipo": _tipo(doc),
        "fecha": doc["fecha_hora"].replace(" ", "T") + "Z",  # la VM guarda en UTC
        "estado": _estado(doc),
        "veredicto_clima": (doc.get("clima") or {}).get("veredicto"),
    }
    rio = doc.get("rio")
    if rio:
        r["rio"] = {
            "ndti": rio.get("ndti"),
            "fecha_imagen": rio.get("fecha_imagen_satelital"),
            "veredicto": rio.get("veredicto"),
        }
    return r


def _docs():
    if not ANON_SECRET:
        abort(500, "Falta ANON_SECRET en el entorno del servicio")
    # {"rio.imagen": 0}: no traer los binarios en los listados
    return (
        _get_collection()
        .find({"ubicacion": {"$exists": True}}, {"rio.imagen": 0})
        .sort("_id", -1)
        .limit(500)
    )


@api.get("/reportes")
def reportes():
    muni = request.args.get("municipio")
    salida = [r for r in map(_a_reporte, _docs()) if not muni or r["municipio"] == muni]
    return jsonify(salida)


@api.get("/precipitacion")
def precipitacion():
    muni = request.args.get("municipio")
    salida = []
    for doc in _docs():
        mm = (doc.get("clima") or {}).get("precipitacion_mm")
        if not _valido(mm):
            continue
        r = _a_reporte(doc)
        if muni and r["municipio"] != muni:
            continue
        salida.append({
            "id": r["id"],
            "nombre": f"Reporte {r['sensor']}",
            "municipio": r["municipio"],
            "lat": r["lat"],
            "lng": r["lng"],
            "mm_24h": mm,  # NASA POWER entrega mm por DIA, no una ventana movil de 24 h
        })
    return jsonify(salida)


@api.get("/reportes/<reporte_id>/imagen")
def imagen(reporte_id):
    if not ANON_SECRET:
        abort(500, "Falta ANON_SECRET en el entorno del servicio")
    try:
        oid = ObjectId(reporte_id)
    except Exception:
        abort(404)
    doc = _get_collection().find_one({"_id": oid}, {"rio.imagen": 1})
    datos = ((doc or {}).get("rio") or {}).get("imagen")
    if not datos:
        abort(404)
    return Response(
        bytes(datos),
        mimetype="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
