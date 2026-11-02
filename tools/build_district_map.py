#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Narzędzie jednorazowe: buduje plik granic dzielnic Krakowa dla mapy.

PO CO OSOBNE NARZĘDZIE
----------------------
Mapa w raporcie musi działać OFFLINE (raport to plik otwierany lokalnie,
często bez internetu), więc nie może dociągać kafelków ani granic z sieci.
Granice dzielnic pobieramy więc RAZ, upraszczamy i zapisujemy w repozytorium
jako ``krakow_districts.json`` (~kilkanaście kB). Raport tylko je wczytuje.

Uruchamiać ponownie wyłącznie, gdy zmieni się podział miasta.

SKĄD DANE
---------
1. **Overpass API** — lista relacji granic dzielnic: obszar „Kraków”
   (``admin_level=6``), relacje ``boundary=administrative`` z
   ``admin_level=9``. To daje dokładnie 18 dzielnic i ich identyfikatory.
2. **Nominatim ``/lookup``** — geometria tych relacji jako GeoJSON, jednym
   zapytaniem, z uproszczeniem po stronie serwera (``polygon_threshold``).

Szukanie dzielnicy po NAZWIE byłoby zawodne: „Stare Miasto” czy „Podgórze”
to także nazwy osiedli i obszarów historycznych o innych granicach. Po
identyfikatorze relacji nie ma tej dwuznaczności.

LICENCJA
--------
Dane © współtwórcy OpenStreetMap, licencja ODbL — atrybucja jest w raporcie
pod mapą i w polu ``attribution`` pliku wynikowego.

Uruchomienie::

    python tools/build_district_map.py
"""

import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "krakow_districts.json"

OVERPASS = "https://overpass-api.de/api/interpreter"
LOOKUP = "https://nominatim.openstreetmap.org/lookup"
UA = {"User-Agent": "bip-krk-job-tracker/1.0 (osobisty projekt)"}

QUERY = """[out:json][timeout:50];
area["name"="Kraków"]["admin_level"="6"]->.k;
rel(area.k)["boundary"="administrative"]["admin_level"="9"];
out ids tags;"""

# Uproszczenie geometrii w stopniach (~50 m). Wystarcza do mapy w pasku
# raportu, a plik pozostaje mały.
THRESHOLD = 0.0005


def main() -> int:
    """Pobiera, upraszcza i zapisuje granice dzielnic.

    Returns:
        0 przy sukcesie, 1 gdy liczba dzielnic jest inna niż 18.
    """
    rels = requests.post(OVERPASS, data={"data": QUERY}, headers=UA,
                         timeout=90).json()["elements"]
    ids = {r["id"]: r["tags"].get("name", "") for r in rels}
    print(f"Overpass: {len(ids)} relacji dzielnic")

    resp = requests.get(LOOKUP, headers=UA, timeout=90, params={
        "osm_ids": ",".join(f"R{i}" for i in ids),
        "format": "json", "polygon_geojson": 1,
        "polygon_threshold": THRESHOLD,
    }).json()

    districts = []
    for item in resp:
        geo = item.get("geojson") or {}
        if geo.get("type") == "Polygon":
            rings = [geo["coordinates"][0]]
        elif geo.get("type") == "MultiPolygon":
            rings = [poly[0] for poly in geo["coordinates"]]
        else:
            continue
        districts.append({
            "name": ids.get(int(item["osm_id"]), item.get("name", "")),
            # Zaokrąglenie do 5 miejsc (~1 m) — więcej to tylko bajty.
            "rings": [[[round(x, 5), round(y, 5)] for x, y in ring]
                      for ring in rings],
        })

    if len(districts) != 18:
        print(f"UWAGA: oczekiwano 18 dzielnic, jest {len(districts)}")
        return 1
    OUT.write_text(json.dumps({
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "districts": sorted(districts, key=lambda d: d["name"]),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    points = sum(len(r) for d in districts for r in d["rings"])
    print(f"Zapisano {OUT.name}: {len(districts)} dzielnic, {points} "
          f"punktów, {OUT.stat().st_size} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
