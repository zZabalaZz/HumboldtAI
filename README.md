# HumboldtAI

Prototipo de recolección de datos hidrometeorológicos mediante crowdsensing por WhatsApp, desarrollado como parte del Proyecto de Grado en Ingeniería de Sistemas (UNAB). Los reportes ciudadanos se validan cruzándolos con fuentes satelitales (NASA POWER y Sentinel-2), y quedan almacenados para su visualización en un dashboard tipo mapa de calor.

## Cómo funciona (arquitectura)

```
Campesino en WhatsApp
        │
        ▼
  Meta WhatsApp Cloud API
        │
        ▼
  Webhook (Flask, en Azure VM)  ──►  PostgreSQL (reportes_raw)
        │                              guarda TODO mensaje tal cual llega
        │
        │  cuando llega una ubicación, se empareja
        │  con el último texto/audio pendiente del mismo número
        ▼
  ¿Es un reporte de clima?  ──► NASA POWER (temperatura, lluvia, humedad, viento)
  ¿Es un reporte de río?    ──► Sentinel-2 / Google Earth Engine (turbidez + imagen satelital)
        │
        ▼
  MongoDB / Azure DocumentDB (reportes_definitivos)
  guarda SOLO reportes climáticos/de río reales, con su veredicto
        │
        ▼
  Cron diario (revalidar_nasa.py)
  corrige los veredictos "sin_evidencia" una vez NASA POWER
  ya tiene el dato (tiene varios días de rezago)
```

## Dos bases de datos, dos propósitos

- **PostgreSQL (`reportes_raw`)**: todo mensaje que llega, sin filtrar. Es el registro crudo, útil para auditoría y depuración.
- **MongoDB (`reportes_definitivos`)**: solo los reportes que sí hablan de clima o río, con su ubicación, el veredicto de si coincide con la fuente satelital, y una imagen. Esta es la base que alimentará el dashboard.

## Estructura de un documento en `reportes_definitivos`

```json
{
  "reporte_id": 123,
  "fecha_hora": "2026-09-26 21:16:01",
  "nombre": "Juan Pérez",
  "numero": "573xxxxxxxxx",
  "mensaje_original": "está lloviendo",
  "ubicacion": { "type": "Point", "coordinates": [longitud, latitud] },
  "clima": {
    "temperatura_c": 19.7,
    "precipitacion_mm": 5.7,
    "humedad_pct": 79.9,
    "viento_ms": 0.6,
    "veredicto": "coincide"
  },
  "rio": {
    "ndti": 0.03,
    "fecha_imagen_satelital": "2026-09-14",
    "veredicto": "no_coincide",
    "imagen": "<binario PNG, ver nota abajo>"
  }
}
```

Un documento puede tener solo `clima`, solo `rio`, o ambos, según de qué hable el mensaje. `veredicto` es uno de: `coincide`, `no_coincide`, `sin_evidencia` (este último se corrige automáticamente días después vía cron).

### Nota para quien construya el dashboard

El campo `rio.imagen` es un **binario PNG**, no una URL. Para mostrarlo en una página web, conviértelo a base64 y úsalo así:
```html
<img src="data:image/png;base64,{{ base64_de_la_imagen }}">
```

## Archivos del proyecto

| Archivo | Qué hace |
|---|---|
| `python webhook.py` | Servidor Flask que recibe los mensajes de WhatsApp |
| `guardar_postgres.py` | Guarda/lee reportes crudos en PostgreSQL |
| `guardar_cosmos.py` | Guarda reportes validados en MongoDB |
| `transcribir_audio.py` | Descarga y transcribe notas de voz (Whisper local) |
| `nasa_power.py` | Consulta la API de NASA POWER |
| `sentinel_turbidez.py` | Consulta Sentinel-2 vía Google Earth Engine (turbidez + imagen) |
| `evaluar_reporte.py` | Reglas para clasificar mensajes y comparar contra los datos satelitales |
| `revalidar_nasa.py` | Cron diario que corrige veredictos pendientes |
| `privacy.html` | Política de privacidad requerida por Meta |
| `requirements.txt` | Dependencias de Python |

## Instalación

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Cómo correrlo

El servicio corre permanentemente en una VM de Azure como servicio `systemd` (`humboldtai-webhook`), no requiere que nadie lo inicie manualmente. Para desarrollo local, cada script puede probarse de forma aislada (ej. `python nasa_power.py`) sin necesidad de levantar todo el sistema.

El cron diario ejecuta `revalidar_nasa.py` (todos los días a las 6:00).

### Variables de entorno necesarias

Ninguna tiene valor por defecto en el código; si falta alguna, el programa falla al iniciar. Los valores reales **nunca** se suben al repositorio.

- `WEBHOOK_VERIFY_TOKEN`: token de verificación del webhook de Meta
- `WHATSAPP_TOKEN`: token de acceso a la API de WhatsApp Cloud
- `DB_PASSWORD`: contraseña de PostgreSQL
- `COSMOS_CONNECTION_STRING`: cadena de conexión a MongoDB/Azure DocumentDB
- `SENTINEL_KEY_PATH`: ruta al archivo de credenciales de la cuenta de servicio de Google Earth Engine (el archivo se guarda fuera del repositorio)

## Pendientes conocidos

- Dashboard de mapa de calor: en desarrollo (los datos ya están disponibles en MongoDB).
- Las fotos que el usuario envíe directamente por WhatsApp (distintas a la imagen satelital) aún no se capturan; decisión de diseño por definir con la directora del proyecto.
- El umbral de NDTI para considerar el agua "turbia" (`0.05`) es un valor inicial, pendiente de calibrar con reportes reales.
