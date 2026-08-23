import logging
import os

from flask import Flask, jsonify, request

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
            for message in value.get("messages", []):
                messages.append(
                    {
                        "id": message.get("id"),
                        "from": message.get("from"),
                        "type": message.get("type"),
                        "text": message.get("text", {}).get("body"),
                        "timestamp": message.get("timestamp"),
                    }
                )

    logger.info("Received %d message(s): %s", len(messages), messages)
    return jsonify({"received": True}), 200


if __name__ == "__main__":
    app.run(port=5000)