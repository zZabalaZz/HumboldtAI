import logging
import os

from flask import Flask, jsonify, request

from guardar_sqlite import guardar_pedido
from transcribir_audio import transcribir_audio

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN", "zzabalazz")
print(f"Token esperado por Flask: '{VERIFY_TOKEN}'")

# --- Paso 1: verificación del webhook (Meta la llama UNA sola vez al guardar la config) ---
@app.route("/webhook", methods=["GET"])
def verificar():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Token inválido", 403


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["POST"])
def recibir():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON body required"}), 400

    messages = []
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Sacamos el nombre del contacto (si viene) - una vez por cada "value"
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
                    texto = f"Ubicación compartida: {latitud}, {longitud}"
                else:
                    texto = message.get("text", {}).get("body")

                # Guardamos el pedido en la base de datos
                guardar_pedido(numero, nombre, texto, tipo, timestamp, latitud, longitud)

                messages.append(
                    {
                        "id": message.get("id"),
                        "from": numero,
                        "nombre": nombre,
                        "type": tipo,
                        "text": texto,
                        "timestamp": timestamp,
                        "latitud": latitud,
                        "longitud": longitud,
                    }
                )

    logger.info("Received %d message(s): %s", len(messages), messages)
    return jsonify({"received": True}), 200


if __name__ == "__main__":
    app.run(port=5000)