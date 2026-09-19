import os
import requests
from faster_whisper import WhisperModel

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "EAATfKPP7iGgBScOqmvJpR9v58PDeMkzSQAiF3M3IbdnKC8jcXTtDMCf1c6C54OezEfSxVjDXFby1mbkvgZCguHV7kcRoN9xMmCmOKik0GIXmXjgPBGgvoO8ObTWFdiDXZBUxGbHu2HxVwXp5lc8GOhO2oi7wfURoosBNnXoA7WIKXTeKSuoq773FTtY4tmMgZDZD")

# Cargamos el modelo una sola vez al iniciar el servidor (no en cada mensaje, sería muy lento)
# "small" es un buen balance para español en CPU. Si tu PC es potente, puedes probar "medium".
modelo = WhisperModel("small", device="cpu", compute_type="int8")


def transcribir_audio(media_id):
    """Descarga un audio de WhatsApp por su media_id y devuelve el texto transcrito."""

    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    # 1. Consultar la URL real del archivo
    resp = requests.get(
        f"https://graph.facebook.com/v21.0/{media_id}",
        headers=headers,
    )
    resp.raise_for_status()
    media_url = resp.json()["url"]

    # 2. Descargar el archivo de audio
    audio_resp = requests.get(media_url, headers=headers)
    audio_resp.raise_for_status()

    temp_path = f"temp_{media_id}.ogg"
    with open(temp_path, "wb") as f:
        f.write(audio_resp.content)

    # 3. Transcribir con Whisper local
    try:
        segments, info = modelo.transcribe(temp_path, language="es")
        texto = " ".join(segment.text for segment in segments).strip()
        return texto
    finally:
        os.remove(temp_path)