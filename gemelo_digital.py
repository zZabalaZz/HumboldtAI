"""
Gemelo digital v2 de la red de sensores humanos (reportes SINTETICOS).

- Los puntos salen de rios y quebradas de Giron y Rionegro (OpenStreetMap, ver zonas_rio.py).
- El clima de cada dia sale de NASA POWER (verdad diaria). De ahi se simula un horario de lluvia
  coherente por (municipio, fecha): la misma fecha produce siempre el mismo horario.
- Un "episodio" son varios reportes en minutos consecutivos cuyo texto sigue el estado simulado:
  "va a llover" -> "esta lloviendo" -> "recien paro".
- Con el cielo seco los voluntarios reportan calor (temperatura maxima), frio, viento o sequia
  (lluvia acumulada en 30 dias), con los mismos umbrales que usa el validador (evaluar_reporte.py).
- Los reportes del rio usan el NDTI de Sentinel-2 como verdad.
- Con probabilidad 1 - P_ACIERTO un reporte es erroneo a proposito (queda marcado veraz=False).

Todo queda marcado como sintetico:
  - Mongo: origen = "gemelo_digital" y un bloque "simulacion" con la verdad del simulador
  - Postgres: numero 57999xxxxxxx y nombre "Gemelo digital NN"

OJO: el texto sale de los mismos datos con los que luego se valida, asi que la tasa de
"coincide" es circular (~P_ACIERTO). Es un parametro del simulador, no un resultado.

Uso:
  python zonas_rio.py                      # una sola vez
  python gemelo_digital.py [N]             # N episodios (por defecto TWIN_N o 4)
  TWIN_DRY=1 python gemelo_digital.py 2    # solo muestra, no guarda nada
"""
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone

from evaluar_reporte import (UMBRAL_LLUVIA_MM, UMBRAL_NDTI, es_reporte_climatico, es_reporte_rio,
                             evaluar_coincidencia, evaluar_turbidez, hay_calor, hay_frio, hay_sequia,
                             hay_viento)
from guardar_cosmos import guardar_definitivo
from guardar_postgres import guardar_pedido, marcar_como_procesado
from nasa_power import obtener_clima_para_reporte
from sentinel_turbidez import obtener_turbidez_sentinel
from zonas_rio import cargar_zonas

N_EPISODIOS = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("TWIN_N", "4"))
P_ACIERTO = float(os.environ.get("TWIN_ACIERTO", "0.9"))  # prob. de que un reporte sea veraz
P_RIO = float(os.environ.get("TWIN_P_RIO", "0.25"))       # fraccion de episodios sobre el rio
SOLO_MOSTRAR = bool(os.environ.get("TWIN_DRY"))
N_SENSORES = 20
CLAVES_REQUERIDAS = ["temperatura_c", "precipitacion_mm", "humedad_relativa_pct", "velocidad_viento_ms"]
LOCAL = timezone(timedelta(hours=-5))  # Colombia, sin horario de verano
# Reportes entre 6:00 y 18:30 hora local: asi la fecha local y la UTC coinciden
HORA_MIN, HORA_MAX = 6 * 60, 18 * 60 + 30

FRASES_ESTADO = {
    "lloviendo": ["Está lloviendo", "Está lloviendo duro por acá", "Cayó un aguacero y sigue lloviendo",
                  "Hay mucha lluvia ahorita"],
    "va_a_llover": ["Se está nublando, parece que va a llover", "Está oscuro y parece que va a llover",
                    "Ya viene la lluvia"],
    "recien_paro": ["Acaba de parar de llover", "Recién paró la lluvia", "Paró la lluvia hace un momento"],
    "llovio_antes": ["Hace un rato cayó un aguacero", "Hoy hubo lluvia fuerte"],
}
FRASES_CALOR = ["Hace mucho calor", "Está haciendo calor hoy", "Hace un calor insoportable"]
FRASES_FRIO = ["Hace mucho frío", "Amaneció muy frío", "Está haciendo frío por acá"]
FRASES_VIENTO = ["Hay mucho viento", "Está ventoso hoy", "Sopla un viento fuerte"]
FRASES_SEQUIA = ["Hay una sequía fuerte por acá", "Hace semanas que no llueve", "Está todo muy seco", "Todo está reseco"]
FRASES_RIO = {
    "turbio": ["El río está turbio", "El agua del río está sucia", "El río está barroso"],
    "claro": ["El río está claro", "El agua del río se ve clara"],
}
# Solo frases afirmativas: evaluar_coincidencia no maneja negaciones ("no está lloviendo").


def dato_valido(nasa):
    return nasa is not None and all(nasa.get(k) is not None and nasa[k] != -999 for k in CLAVES_REQUERIDAS)


def nasa_del_dia(muni, fecha, pts, cache):
    clave = (muni, fecha)
    if clave not in cache:
        lat = sum(p["lat"] for p in pts) / len(pts)
        lon = sum(p["lon"] for p in pts) / len(pts)
        try:
            nasa = obtener_clima_para_reporte(lat, lon, fecha, incluir_sequia=True)
        except Exception as e:
            print("  NASA POWER falló:", e)
            nasa = None
        cache[clave] = nasa if dato_valido(nasa) else None
    return cache[clave]


def dia_simulado(muni, fecha, nasa):
    """Horario de lluvia del dia (minutos locales). Determinista por (municipio, fecha)."""
    rng = random.Random(f"{muni}|{fecha}")
    eventos = []
    if nasa["precipitacion_mm"] > UMBRAL_LLUVIA_MM:  # mismo umbral que el validador
        n = 1 if nasa["precipitacion_mm"] < 5 else rng.randint(1, 3)
        for _ in range(n):
            # la lluvia andina cae sobre todo en la tarde
            ini = rng.randint(12 * 60, 17 * 60) if rng.random() < 0.7 else rng.randint(6 * 60, 17 * 60)
            eventos.append([ini, min(ini + rng.randint(20, 150), 18 * 60)])
        eventos.sort()
        fusion = []
        for e in eventos:
            if fusion and e[0] <= fusion[-1][1] + 20:
                fusion[-1][1] = max(fusion[-1][1], e[1])
            else:
                fusion.append(e)
        eventos = fusion
    return eventos


def estado(eventos, m):
    for ini, fin in eventos:
        if ini <= m <= fin:
            return "lloviendo"
    for ini, fin in eventos:
        if 0 < ini - m <= 30:
            return "va_a_llover"
        if 0 < m - fin <= 30:
            return "recien_paro"
    if any(m > fin for _, fin in eventos):
        return "llovio_antes"
    return "seco"


def frase_seco(nasa):
    """Con el cielo seco solo se reporta lo que el validador sabe juzgar: calor, frio, viento o sequia.
    Devuelve (texto, tema) o None. Las frases neutras ('esta nublado') se omiten: quedarian en
    sin_evidencia y el cron de revalidacion las reintentaria cada dia para siempre."""
    opciones = []
    if hay_sequia(nasa):
        opciones.append((FRASES_SEQUIA, "sequia"))
    if hay_calor(nasa):
        opciones.append((FRASES_CALOR, "calor"))
    if hay_frio(nasa):
        opciones.append((FRASES_FRIO, "frio"))
    if hay_viento(nasa):
        opciones.append((FRASES_VIENTO, "viento"))
    if not opciones:
        return None
    frases, tema = random.choice(opciones)
    return random.choice(frases), tema


def frase(est, nasa, veraz):
    """Devuelve (texto, tema) o None."""
    if veraz:
        if est in FRASES_ESTADO:
            return random.choice(FRASES_ESTADO[est]), "lluvia"
        return frase_seco(nasa)
    # reporte erroneo a proposito
    if est in ("seco", "llovio_antes"):
        opciones = [(random.choice(FRASES_ESTADO["lloviendo"]), "lluvia")]
        if hay_sequia(nasa) is False:  # False, no None: solo si hay datos y no hay sequia
            opciones.append((random.choice(FRASES_SEQUIA), "sequia"))
        return random.choice(opciones)
    falsas = []
    if not hay_calor(nasa):
        falsas.append((random.choice(FRASES_CALOR), "calor"))
    if not hay_frio(nasa):
        falsas.append((random.choice(FRASES_FRIO), "frio"))
    if not hay_viento(nasa):
        falsas.append((random.choice(FRASES_VIENTO), "viento"))
    return random.choice(falsas) if falsas else None


def punto_cerca(pts, radio_m):
    p = random.choice(pts)
    r = radio_m / 111_000
    lat = p["lat"] + random.uniform(-r, r)
    lon = p["lon"] + random.uniform(-r, r) / math.cos(math.radians(p["lat"]))
    return round(lat, 5), round(lon, 5)


def fecha_aleatoria():
    # 8-30 dias atras: NASA POWER tiene ~1 semana de rezago, asi el dato ya existe
    return (datetime.now(LOCAL) - timedelta(days=random.randint(8, 30))).date()


def sensor(n):
    return f"5799900{n:05d}", f"Gemelo digital {n:02d}"


def episodio_clima(zonas, cache):
    muni = random.choice(list(zonas))
    dia = fecha_aleatoria()
    fecha = dia.strftime("%Y-%m-%d")
    pts = zonas[muni]
    nasa = nasa_del_dia(muni, fecha, pts, cache)
    if nasa is None:
        return muni, fecha, []

    eventos = dia_simulado(muni, fecha, nasa)
    if eventos:
        ini, fin = random.choice(eventos)
        minutos = [random.choice([ini - random.randint(5, 25), ini + random.randint(3, 15),
                                  fin - random.randint(0, 10)])]
        for _ in range(random.randint(1, 3)):
            minutos.append(minutos[-1] + random.randint(5, 20))  # reportes seguidos, minutos despues
    else:
        minutos = sorted(random.sample(range(7 * 60, 17 * 60), random.randint(1, 2)))

    sensores = random.sample(range(1, N_SENSORES + 1), random.randint(1, 3))
    base = {n: punto_cerca(pts, 800) for n in sensores}  # cada sensor se queda cerca de su punto
    reportes = []
    for m in minutos:
        if not (HORA_MIN <= m <= HORA_MAX):
            continue
        est = estado(eventos, m)
        veraz = random.random() < P_ACIERTO
        res = frase(est, nasa, veraz)
        if res is None:
            continue
        texto, tema = res
        n = random.choice(sensores)
        lat0, lon0 = base[n]
        reportes.append({
            "sensor": sensor(n),
            "lat": round(lat0 + random.uniform(-0.0004, 0.0004), 5),
            "lon": round(lon0 + random.uniform(-0.0004, 0.0004), 5),
            "momento": datetime(dia.year, dia.month, dia.day, m // 60, m % 60, tzinfo=LOCAL),
            "texto": texto,
            "nasa": nasa,
            "sim": {"episodio": f"{muni}-{fecha}", "municipio": muni, "tema": tema, "estado_real": est, "veraz": veraz},
        })
    return muni, fecha, reportes


def episodio_rio(zonas):
    muni = random.choice(list(zonas))
    rios = [p for p in zonas[muni] if p["tipo"] == "river"]
    if not rios:
        return muni, None, []
    p = random.choice(rios)
    dia = fecha_aleatoria()
    fecha = dia.strftime("%Y-%m-%d")
    try:
        sat = obtener_turbidez_sentinel(p["lat"], p["lon"], fecha)
    except Exception as e:
        print("  Sentinel-2 falló:", e)
        return muni, fecha, []
    if not sat or sat.get("ndti") is None:
        return muni, fecha, []  # sin imagen utilizable: falta un dato requerido, no se guarda
    turbio = sat["ndti"] > UMBRAL_NDTI
    veraz = random.random() < P_ACIERTO
    texto = random.choice(FRASES_RIO["turbio" if turbio == veraz else "claro"])
    momento = datetime(dia.year, dia.month, dia.day, random.randint(7, 17), random.randint(0, 59), tzinfo=LOCAL)
    return muni, fecha, [{
        "sensor": sensor(random.randint(1, N_SENSORES)),
        "lat": p["lat"], "lon": p["lon"], "momento": momento, "texto": texto, "sat": sat,
        "sim": {"episodio": f"{muni}-{fecha}-rio", "municipio": muni, "tema": "rio", "rio": p["rio"],
                "estado_real": "turbio" if turbio else "claro", "veraz": veraz},
    }]


def guardar(rep):
    texto = rep["texto"]
    if not (es_reporte_climatico(texto) or es_reporte_rio(texto)):
        print("  omitido, no pasa el filtro de calidad:", texto)
        return False
    numero, nombre = rep["sensor"]
    ts = int(rep["momento"].timestamp())
    lat, lon = rep["lat"], rep["lon"]
    nasa, sat = rep.get("nasa"), rep.get("sat")
    v_clima = evaluar_coincidencia(texto, nasa) if nasa else None
    v_rio = evaluar_turbidez(texto, sat["ndti"]) if sat else None

    print(f"  {rep['momento']:%H:%M} {nombre} ({lat}, {lon}) \"{texto}\" "
          f"[{rep['sim']['tema']}, real={rep['sim']['estado_real']}, veraz={rep['sim']['veraz']}] -> clima={v_clima} rio={v_rio}")
    if SOLO_MOSTRAR:
        return True

    id_texto = guardar_pedido(numero, nombre, texto, "text", ts)
    guardar_pedido(numero, nombre, f"Ubicacion compartida: {lat}, {lon}", "location", ts + 20, lat, lon)
    guardar_definitivo(
        reporte_id=id_texto,
        fecha_hora=datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),  # igual que guardar_pedido
        nombre=nombre, numero=numero, mensaje_original=texto,
        latitud=lat, longitud=lon,
        datos_nasa=nasa, veredicto_clima=v_clima,
        datos_sentinel=sat, veredicto_rio=v_rio,
        extra={"origen": "gemelo_digital", "simulacion": rep["sim"]},
    )
    marcar_como_procesado(id_texto)
    return True


def main():
    zonas = cargar_zonas()
    cache = {}
    guardados = 0
    for i in range(N_EPISODIOS):
        es_rio = random.random() < P_RIO
        muni, fecha, reportes = episodio_rio(zonas) if es_rio else episodio_clima(zonas, cache)
        print(f"[{i + 1}/{N_EPISODIOS}] {'río' if es_rio else 'clima'} · {muni} · {fecha}")
        if not reportes:
            print("  omitido (faltó algún dato requerido o ningún reporte aplicaba)")
            continue
        for rep in sorted(reportes, key=lambda r: r["momento"]):
            guardados += guardar(rep)
    print(f"Listo: {guardados} reportes sintéticos" + (" (modo prueba, no se guardó)" if SOLO_MOSTRAR else ""))


if __name__ == "__main__":
    main()
