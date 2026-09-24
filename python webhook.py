import logging
import os
from datetime import datetime

from flask import Flask, jsonify, request

from guardar_postgres import guardar_pedido, buscar_ultimo_reporte_sin_ubicacion, marcar_como_procesado
from guardar_cosmos import guardar_definitivo
from transcribir_audio import transcribir_audio
from nasa_power import obtener_clima_nasa
from sentinel_turbidez import obtener_turbidez_sentinel
from evaluar_reporte import es_reporte_climatico, es_reporte_rio, evaluar_coincidencia, evaluar_turbidez

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN", "zzabalazz")


@app.route("/webhook", methods=["GET"])
def verificar():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Token invalido", 403


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


def procesar_ubicacion(numero, nombre, latitud, longitud, fecha_hora):
    reporte_previo = buscar_ultimo_reporte_sin_ubicacion(numero)
    if reporte_previo is None:
        logger.info("No hay reporte pendiente de %s para emparejar.", numero)
        return

    texto = reporte_previo["mensaje"]
    es_clima = es_reporte_climatico(texto)
    es_rio = es_reporte_rio(texto)

    if not es_clima and not es_rio:
        logger.info("Reporte #%s no es climatico ni de rio ('%s') - descartado.",
                    reporte_previo["id"], texto)
        marcar_como_procesado(reporte_previo["id"])
        return

    fecha = fecha_hora.split(" ")[0]
    datos_nasa = None
    veredicto_clima = None
    datos_sentinel = None
    veredicto_rio = None

    if es_clima:
        try:
            datos_nasa = obtener_clima_nasa(latitud, longitud, fecha)
            veredicto_clima = evaluar_coincidencia(texto, datos_nasa)
        except Exception as e:
            logger.error("Error consultando NASA POWER: %s", e)

    if es_rio:
        try:
            datos_sentinel = obtener_turbidez_sentinel(latitud, longitud, fecha)
            if datos_sentinel is not None:
                veredicto_rio = evaluar_turbidez(texto, datos_sentinel.get("ndti"))
        except Exception as e:
            logger.error("Error consultando Sentinel-2: %s", e)

    guardar_definitivo(
        reporte_id=reporte_previo["id"], fecha_hora=reporte_previo["fecha_hora"],
        nombre=nombre, numero=numero, mensaje_original=texto,
        latitud=latitud, longitud=longitud,
        datos_nasa=datos_nasa, veredicto_clima=veredicto_clima,
        datos_sentinel=datos_sentinel, veredicto_rio=veredicto_rio,
    )
    marcar_como_procesado(reporte_previo["id"])
    logger.info("Reporte #%s guardado en definitiva (clima=%s, rio=%s)",
                reporte_previo["id"], veredicto_clima, veredicto_rio)


@app.route("/webhook", methods=["POST"])
def recibir():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body required"}), 400

    messages = []
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = value.get("contacts", [])
            nombre = contacts[0].get("profile", {}).get("name") if contacts else None

            for message in value.get("messages", []):
                numero = message.get("from")
                tipo = message.get("type")
                timestamp = message.get("timestamp")
                latitud = None
                longitud = None

                if tipo == "audio":
                    media_id = message.get("audio", {}).get("id")
                    try:
                        texto = transcribir_audio(media_id)
                    except Exception as e:
                        logger.error("Error transcribiendo audio: %s", e)
                        texto = "[No se pudo transcribir el audio]"
                elif tipo == "location":
                    ubicacion = message.get("location", {})
                    latitud = ubicacion.get("latitude")
                    longitud = ubicacion.get("longitude")
                    texto = f"Ubicacion compartida: {latitud}, {longitud}"
                else:
                    texto = message.get("text", {}).get("body")

                reporte_id = guardar_pedido(numero, nombre, texto, tipo, timestamp, latitud, longitud)

                if tipo == "location":
                    fecha_hora_str = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
                    procesar_ubicacion(numero, nombre, latitud, longitud, fecha_hora_str)

                messages.append({
                    "id": message.get("id"), "from": numero, "nombre": nombre,
                    "type": tipo, "text": texto, "timestamp": timestamp,
                })

    logger.info("Received %d message(s): %s", len(messages), messages)
    return jsonify({"received": True}), 200


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
