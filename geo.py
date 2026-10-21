#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geografia ofert: odległość od domu i geokodowanie miejscowości.

PO CO
-----
Raport pokazywał oferty z Gorlic i Tarnowa — formalnie „małopolskie”,
ale 100+ km od Krakowa, więc bez sensu jako propozycja pracy. Potrzebny
był więc **punkt wyjazdu** (dom) i **promień** w kilometrach.

JAK TO DZIAŁA
-------------
1. **Dom** wybiera się w raporcie z listy 18 dzielnic Krakowa (domyślnie
   ``Bronowice``). Współrzędne dzielnic są **wbudowane**
   (:data:`KRAKOW_DISTRICTS`) — zgeokodowane raz przez Nominatim
   i zapisane w kodzie, żeby raport działał offline i nie zależał od
   dostępności usługi.
2. **Oferty** dostają współrzędne:
   * CBOP podaje je wprost (``miejscePracyLatitude/Longitude``),
   * pozostałe źródła geokodujemy po nazwie miejscowości przez
     Nominatim (OpenStreetMap), z zapisem w ``data*/geo_cache.json`` —
     każda miejscowość pytana jest raz w życiu.
3. **Odległość** liczy wzór haversine. Przelicza ją **przeglądarka**, nie
   Python — dzięki temu przesunięcie suwaka albo zmiana dzielnicy działa
   natychmiast, bez generowania raportu od nowa.

CZEGO TA ODLEGŁOŚĆ NIE ZNACZY
-----------------------------
To odległość **w linii prostej**, nie czas dojazdu. 10 km przez centrum
Krakowa w godzinach szczytu bywa dłuższe niż 25 km trasą wylotową.
Dlatego domyślny promień jest ustawiony hojnie (10 km od wybranej
dzielnicy obejmuje większość miasta), a oferty **bez rozpoznanej
lokalizacji nie są ukrywane** — brak danych nie może znaczyć „odrzuć”.

ZASADY KORZYSTANIA Z NOMINATIM
------------------------------
Usługa jest darmowa, ale wymaga własnego ``User-Agent`` i nie więcej niż
1 zapytania na sekundę — oba warunki są tu respektowane
(:data:`GEOCODE_DELAY`). Cache sprawia, że przy kolejnych przebiegach
zapytań praktycznie nie ma.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Dict, Optional, Tuple

import bip_common as bc

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GEOCODE_DELAY = 1.1  # sekundy między zapytaniami (wymóg usługi)

# Dzielnice Krakowa ze współrzędnymi — zgeokodowane raz, wbudowane celowo,
# żeby wybór domu działał bez internetu. Kolejność jak numeracja dzielnic.
KRAKOW_DISTRICTS: Dict[str, Tuple[float, float]] = {
    "Stare Miasto": (50.0614, 19.9357),
    "Grzegórzki": (50.0650, 19.9688),
    "Prądnik Czerwony": (50.0859, 19.9666),
    "Prądnik Biały": (50.1036, 19.9536),
    "Krowodrza": (50.0709, 19.9166),
    "Bronowice": (50.0833, 19.8698),
    "Zwierzyniec": (50.0602, 19.8642),
    "Dębniki": (50.0129, 19.8507),
    "Łagiewniki-Borek Fałęcki": (50.0200, 19.9294),
    "Swoszowice": (49.9886, 19.9541),
    "Podgórze Duchackie": (50.0162, 19.9594),
    "Bieżanów-Prokocim": (50.0171, 20.0230),
    "Podgórze": (50.0431, 19.9530),
    "Czyżyny": (50.0665, 20.0088),
    "Mistrzejowice": (50.0974, 20.0096),
    "Bieńczyce": (50.0861, 20.0292),
    "Wzgórza Krzesławickie": (50.0984, 20.0920),
    "Nowa Huta": (50.0806, 20.1293),
}

# Dzielnica domyślna — wskazana przez adresatkę.
DEFAULT_DISTRICT = "Bronowice"

# Domyślny promień poszukiwań w km.
DEFAULT_RADIUS_KM = 10

# Frazy, które NIE są miejscowością, choć stoją w polu miasta. Portal
# pracujwkulturze ma np. „Wszystkie miejscowości, w których lub w pobliżu
# których znajduje się teatr…” oraz „Cała Polska”.
NOT_A_PLACE = re.compile(
    r"cała polska|cala polska|wszystkie miejscowoś|zdaln|remote|online"
    r"|do ustalenia|różne lokalizacj",
    re.IGNORECASE,
)

# Promień Ziemi w km.
EARTH_RADIUS_KM = 6371.0


def distance_km(point_a: Tuple[float, float],
                point_b: Tuple[float, float]) -> float:
    """Liczy odległość w linii prostej między dwoma punktami (haversine).

    Args:
        point_a: (szerokość, długość) w stopniach.
        point_b: (szerokość, długość) w stopniach.

    Returns:
        Odległość w kilometrach.
    """
    lat1, lon1 = math.radians(point_a[0]), math.radians(point_a[1])
    lat2, lon2 = math.radians(point_b[0]), math.radians(point_b[1])
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    inner = (math.sin(d_lat / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(inner))


# Wzorzec miasta w nazwie jednostki, np. „Jacek Piróg (Lipinki,
# małopolskie)” albo „Luxoft DXC (Krakow, Warsaw)”. Źródła skladają tak
# ``unit_name``, więc to jedyny sposób odzyskania miasta, gdy osobnego
# pola nie ma. BEZ tego wzorca geokodowaliśmy całe nazwy firm — Nominatim
# zwracał wtedy albo nic, albo losową wioskę.
CITY_IN_NAME = re.compile(r"\(([^),]{3,40})(?:,|\))")


def city_from_unit_name(unit_name: str) -> str:
    """Wyłuskuje miasto z nazwy jednostki/pracodawcy.

    Args:
        unit_name: nazwa jednostki, np. ``Firma X (Lipinki, małopolskie)``.

    Returns:
        Nazwę miasta albo pusty łańcuch.
    """
    found = CITY_IN_NAME.search(str(unit_name or ""))
    return clean_place(found.group(1)) if found else ""


def clean_place(raw: str) -> str:
    """Normalizuje nazwę miejscowości z pola źródła.

    Źródła podają lokalizację bardzo różnie: ``Kraków``, ``Kraków,
    małopolskie``, ``Krakow, Warsaw, Wroclaw``, ``38-305 Lipinki 136``,
    ``Katowice i okolice``. Bierzemy pierwszy sensowny człon.

    Args:
        raw: surowa wartość pola lokalizacji.

    Returns:
        Nazwę miejscowości albo pusty łańcuch, gdy to nie miejsce.
    """
    text = str(raw or "").strip()
    if not text or NOT_A_PLACE.search(text):
        return ""
    # Odcinamy kod pocztowy i numery domów.
    text = re.sub(r"\b\d{2}-\d{3}\b", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    # Pierwszy człon przed przecinkiem/ukośnikiem.
    first = re.split(r"[,/;|]", text)[0]
    first = re.sub(r"\bi okolice\b", "", first, flags=re.IGNORECASE)
    first = re.sub(r"\s+", " ", first).strip(" -–·")
    return first if len(first) >= 3 else ""


def _load_cache() -> Dict[str, Optional[list]]:
    """Wczytuje cache geokodowania z dysku.

    Returns:
        Mapę ``nazwa -> [lat, lon]`` lub ``nazwa -> None`` dla nieudanych.
    """
    path = bc.DATA_DIR / "geo_cache.json"
    if not path.exists():
        return {}
    data = bc.load_dataset(path)
    return dict((data.get("records") or {}))


def _save_cache(cache: Dict[str, Optional[list]]) -> None:
    """Zapisuje cache geokodowania.

    Args:
        cache: mapa nazw na współrzędne.
    """
    bc.save_dataset(bc.DATA_DIR / "geo_cache.json", {"records": cache})


def geocode_places(places: set, session=None) -> Dict[str, Tuple[float,
                                                                float]]:
    """Geokoduje zbiór miejscowości, korzystając z cache.

    Nieudane próby też zapisujemy (jako ``None``), żeby nie pytać o to
    samo w każdym przebiegu — Nominatim prosi o oszczędność zapytań.

    Args:
        places: nazwy miejscowości.
        session: sesja HTTP; gdy None, używamy wyłącznie cache.

    Returns:
        Mapę ``nazwa -> (lat, lon)`` dla rozpoznanych miejsc.
    """
    cache = _load_cache()
    result: Dict[str, Tuple[float, float]] = {}
    pending = []

    for name in sorted(places):
        if not name:
            continue
        if name in KRAKOW_DISTRICTS:
            result[name] = KRAKOW_DISTRICTS[name]
            continue
        if name in cache:
            value = cache[name]
            if value:
                result[name] = (float(value[0]), float(value[1]))
            continue
        pending.append(name)

    if pending and session is not None:
        logging.info("Geokoduję %d nowych miejscowości (1 zapytanie/s)",
                     len(pending))
        for name in pending:
            coords = _geocode_one(session, name)
            cache[name] = list(coords) if coords else None
            if coords:
                result[name] = coords
            time.sleep(GEOCODE_DELAY)
        _save_cache(cache)

    return result


def _geocode_one(session, name: str) -> Optional[Tuple[float, float]]:
    """Pyta Nominatim o współrzędne jednej miejscowości.

    Args:
        session: sesja HTTP.
        name: nazwa miejscowości.

    Returns:
        Parę (lat, lon) albo None.
    """
    try:
        response = session.get(
            NOMINATIM_URL,
            # ``countrycodes=pl`` zamyka wyszukiwanie w Polsce. Bez tego
            # „Berlin” z oferty zagranicznej trafiał do polskiej wsi o tej
            # nazwie (49.87, 22.19) i udawał lokalizację w zasięgu.
            # Zagraniczne miasta po prostu się nie zgeokodują — i dobrze,
            # bo oferty zdalne nie powinny podlegać filtrowi odległości.
            params={"q": name, "format": "json", "limit": 1,
                    "countrycodes": "pl"},
            timeout=bc.HTTP_TIMEOUT,
            headers={"User-Agent": "bip-krk-job-tracker/1.0 "
                                   "(osobisty projekt)"},
        )
        if response.status_code != 200:
            return None
        payload = response.json()
    except (ValueError, Exception):  # pylint: disable=broad-exception-caught
        return None
    if not payload:
        return None
    try:
        return (round(float(payload[0]["lat"]), 4),
                round(float(payload[0]["lon"]), 4))
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def districts_json() -> str:
    """Zwraca dzielnice jako JSON do wbudowania w raport.

    Returns:
        Łańcuch JSON ``{"Nazwa": [lat, lon], ...}``.
    """
    return json.dumps({k: list(v) for k, v in KRAKOW_DISTRICTS.items()},
                      ensure_ascii=False)
