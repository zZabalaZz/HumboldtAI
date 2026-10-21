"""
Puntos sobre rios y quebradas de Giron y Rionegro (Santander), sacados de OpenStreetMap.

Se corre UNA vez (necesita internet) y deja zonas_rio.json junto al script:
    python zonas_rio.py
El gemelo digital lee ese archivo con cargar_zonas().
"""
import json
import os
import random
import time

import requests

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zonas_rio.json")
OVERPASS = "https://overpass-api.de/api/interpreter"
MUNICIPIOS = ["Girón", "Rionegro"]
MAX_POR_TIPO = 200  # puntos guardados por municipio: hasta 200 de rio y 200 de quebrada

# Municipios (admin_level 6) dentro del departamento de Santander (admin_level 4):
# asi no se confunde con Rionegro de Antioquia ni con otros Giron.
CONSULTA = """
[out:json][timeout:90];
area["name"="Santander"]["boundary"="administrative"]["admin_level"="4"]->.dep;
rel(area.dep)["name"="{muni}"]["boundary"="administrative"]["admin_level"="6"];
map_to_area->.muni;
way(area.muni)["waterway"~"^(river|stream)$"];
out geom;
"""


def descargar_municipio(muni):
    resp = requests.post(
        OVERPASS,
        data={"data": CONSULTA.format(muni=muni)},
        headers={"User-Agent": "HumboldtAI-gemelo-digital/1.0"},
        timeout=120,
    )
    resp.raise_for_status()
    puntos = []
    for el in resp.json().get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        for g in el["geometry"][::4]:  # un punto cada 4 nodos
            puntos.append({
                "rio": tags.get("name", "sin nombre"),
                "tipo": tags.get("waterway"),
                "lat": g["lat"],
                "lon": g["lon"],
            })
    return puntos


def construir():
    zonas = {}
    for i, muni in enumerate(MUNICIPIOS):
        if i:
            time.sleep(5)  # cortesia con el servidor de Overpass
        pts = descargar_municipio(muni)
        rios = [p for p in pts if p["tipo"] == "river"]
        otros = [p for p in pts if p["tipo"] != "river"]
        if not pts:
            raise RuntimeError(f"Overpass no devolvió ríos para {muni}: revisa el nombre o la consulta")
        random.shuffle(rios)
        random.shuffle(otros)
        zonas[muni] = rios[:MAX_POR_TIPO] + otros[:MAX_POR_TIPO]
        nombres = sorted({p["rio"] for p in zonas[muni]})
        print(f"{muni}: {len(rios)} puntos de río, {len(otros)} de quebrada")
        print("   ", ", ".join(nombres[:20]))
    with open(RUTA, "w", encoding="utf-8") as f:
        json.dump(zonas, f, ensure_ascii=False)
    print("Guardado en", RUTA)
    return zonas


def cargar_zonas():
    if not os.path.exists(RUTA):
        raise FileNotFoundError("Falta zonas_rio.json: corre primero  python zonas_rio.py")
    with open(RUTA, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    construir()
