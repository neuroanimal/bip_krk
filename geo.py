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

# Rozpoznanie samego „Krakowa” w każdej pisowni (patrz geocode_places).
KRAKOW_NAME = re.compile(r"^\s*(krak[oó]w|krakow|cracow|cracovia)\s*$",
                         re.IGNORECASE)

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
        # Kraków bez dzielnicy = Rynek, a NIE wynik Nominatim. Usługa
        # zwraca dla „Kraków” centroid obszaru administracyjnego
        # (50.047, 19.997) — 10,0 km od Bronowic, podczas gdy Rynek jest
        # 5,3 km. Kilka ofert stało przez to dokładnie na granicy promienia.
        if KRAKOW_NAME.search(name):
            result[name] = KRAKOW_DISTRICTS["Stare Miasto"]
            continue
        # Klucz z wersją metody — patrz :data:`CACHE_PREFIX`.
        if f"{CACHE_PREFIX}city|{name}" in cache:
            value = cache[f"{CACHE_PREFIX}city|{name}"]
            if value:
                result[name] = (float(value[0]), float(value[1]))
            continue
        pending.append(name)

    if pending and session is not None:
        logging.info("Geokoduję %d nowych miejscowości (1 zapytanie/s)",
                     len(pending))
        for name in pending:
            coords = _geocode_one(session, name)
            cache[f"{CACHE_PREFIX}city|{name}"] = (list(coords) if coords
                                                   else None)
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
            # BEZ ograniczenia do Polski — i to jest poprawka wcześniejszej
            # decyzji. ``countrycodes=pl`` miało zapobiec pomyłkom, a
            # wywołało odwrotną: „Berlin” z oferty niemieckiej trafiał do
            # polskiej WSI Berlin (49.87, 22.19), czyli udawał miejsce pod
            # Rzeszowem. Bez ograniczenia Berlin to Berlin (52.52, 13.40),
            # a polskie miasta i tak wychodzą w Polsce.
            params={"q": name, "format": "json", "limit": 1},
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


# ---------------------------------------------------------------------------
# PRECYZYJNA LOKALIZACJA OFERTY (adres → instytucja → dzielnica → miasto)
# ---------------------------------------------------------------------------
#
# Wcześniej oferta z samym „Kraków” dostawała współrzędne CENTRUM miasta.
# Skutek: ogłoszenie z Klubu Dukat (os. Zgody, Nowa Huta) wychodziło jako
# 5,5 km od Bronowic zamiast 11,6 km, a promień 10 km go przepuszczał.
# Ręczny słownik „klub → dzielnica” trzeba by utrzymywać w nieskończoność,
# więc pytamy o konkretny punkt, w tej kolejności:
#
# 1. ``api``       — współrzędne podane przez źródło (CBOP),
# 2. ``address``   — adres ulicy z treści ogłoszenia („os. Zgody 1”),
# 3. ``employer``  — nazwa instytucji + miasto („Teatr Groteska, Kraków”),
# 4. ``district``  — nazwa dzielnicy Krakowa w tekście („Bronowice, Kraków”
#                    — tak podaje lokalizację jooble),
# 5. ``city``      — samo miasto (dotychczasowe zachowanie, najmniej
#                    dokładne — oznaczane w raporcie jako przybliżone).
#
# Każdy wynik z punktów 2–3 jest WALIDOWANY: musi leżeć najwyżej
# :data:`VALIDATE_KM` od miasta oferty. Bez tego „Teatr Ludowy” czy
# „Dom Kultury” mógłby trafić do imiennika w innym województwie.

# Adres w treści ogłoszenia: osiedle, ulica, aleja, plac z numerem.
ADDRESS_RE = re.compile(
    r"\b(?:os\.|osiedle|ul\.|ulica|al\.|aleja|pl\.|plac)\s*"
    r"[A-ZŁŚŻŹĆĄĘÓŃ][\w\.\-ąćęłńóśźżĄĆĘŁŃÓŚŹŻ ]{1,40}?\s\d+[a-zA-Z]?\b")

# Maksymalna odległość wyniku od miasta oferty, żeby uznać go za wiarygodny.
VALIDATE_KM = 30.0

# Pracodawcy, których nazwa NIE nadaje się do geokodowania (portale,
# pośrednicy, zastępcze opisy) — pytanie o nie dałoby losowy punkt.
NOT_GEOCODABLE_EMPLOYERS = re.compile(
    r"kontakt przez pup|jooble|nuzle|nofluffjobs|bulldogjob|arc\.dev"
    r"|agencja pracy|recruitment|rekrutac|klient nieujawniony|cbop",
    re.IGNORECASE)

# Wersja kluczy w pamięci podręcznej. Zmieniona, gdy zmieniła się metoda:
# stare wpisy (pytane z ``countrycodes=pl`` bez regionu) zamieniały
# „Berlin” w polską wieś, a „Lipinki” w imiennika w Wielkopolsce.
CACHE_PREFIX = "v2|"


def _cached_lookup(session, cache: Dict[str, Optional[list]], query: str,
                   restrict_pl: bool) -> Optional[Tuple[float, float]]:
    """Geokoduje zapytanie z pamięcią podręczną (nieudane też zapamiętujemy).

    Args:
        session: sesja HTTP albo None (wtedy tylko pamięć).
        cache: słownik pamięci podręcznej (modyfikowany w miejscu).
        query: pełne zapytanie dla Nominatim.
        restrict_pl: czy zawęzić wyniki do Polski.

    Returns:
        Para (lat, lon) albo None.
    """
    key = f"{CACHE_PREFIX}{'pl' if restrict_pl else 'any'}|{query}"
    if key in cache:
        value = cache[key]
        return (float(value[0]), float(value[1])) if value else None
    if session is None:
        return None
    params = {"q": query, "format": "json", "limit": 1}
    if restrict_pl:
        params["countrycodes"] = "pl"
    coords = None
    try:
        response = session.get(
            NOMINATIM_URL, params=params, timeout=bc.HTTP_TIMEOUT,
            headers={"User-Agent": "bip-krk-job-tracker/1.0 "
                                   "(osobisty projekt)"})
        payload = response.json() if response.status_code == 200 else []
        if payload:
            coords = (round(float(payload[0]["lat"]), 4),
                      round(float(payload[0]["lon"]), 4))
    except Exception:  # pylint: disable=broad-exception-caught
        # Sieć, zły JSON, nietypowa odpowiedź — wszystko kończy się tak samo:
        # brak punktu. Geokodowanie jest dodatkiem i nie może przerwać raportu.
        coords = None
    time.sleep(GEOCODE_DELAY)
    cache[key] = list(coords) if coords else None
    return coords


def _district_in(text: str) -> Optional[Tuple[str, Tuple[float, float]]]:
    """Szuka nazwy dzielnicy Krakowa w tekście.

    Args:
        text: tytuł, nazwa pracodawcy albo pole lokalizacji.

    Returns:
        Para (nazwa dzielnicy, współrzędne) albo None.
    """
    lowered = str(text or "").lower()
    # Dłuższe nazwy najpierw — „Podgórze Duchackie” przed „Podgórze”.
    for name in sorted(KRAKOW_DISTRICTS, key=len, reverse=True):
        if name.lower() in lowered:
            return name, KRAKOW_DISTRICTS[name]
    return None


def locate_offer(offer: Dict[str, object], city: str,
                 city_point: Optional[Tuple[float, float]],
                 session=None,
                 cache: Optional[Dict[str, Optional[list]]] = None
                 ) -> Tuple[Optional[Tuple[float, float]], str]:
    """Ustala jak najdokładniejszy punkt oferty.

    Args:
        offer: rekord oferty (tytuł, opis, pracodawca, ewentualnie lat/lon).
        city: rozpoznane miasto oferty.
        city_point: współrzędne miasta (do walidacji i jako ostatnia deska).
        session: sesja HTTP (None = tylko pamięć podręczna).
        cache: pamięć podręczna geokodowania.

    Returns:
        Para (współrzędne albo None, poziom dokładności: ``api``,
        ``address``, ``employer``, ``district``, ``city`` albo ``""``).
    """
    cache = {} if cache is None else cache
    lat, lon = offer.get("lat"), offer.get("lon")
    if lat not in (None, "") and lon not in (None, ""):
        try:
            return (float(lat), float(lon)), "api"
        except (TypeError, ValueError):
            pass

    def plausible(point: Optional[Tuple[float, float]]) -> bool:
        """Czy wynik leży w rozsądnej odległości od miasta oferty."""
        if point is None:
            return False
        return city_point is None or distance_km(point, city_point) <= VALIDATE_KM

    text = f"{offer.get('raw_text') or ''}"
    employer = re.split(r"\s*[\(\[]|\s+[—–]\s+",
                        str(offer.get("unit_name") or ""), maxsplit=1)[0]

    if city:
        found = ADDRESS_RE.search(text)
        if found:
            point = _cached_lookup(session, cache,
                                   f"{found.group(0).strip()}, {city}", True)
            if plausible(point):
                return point, "address"
        if employer and not NOT_GEOCODABLE_EMPLOYERS.search(employer) \
                and len(employer) >= 6:
            point = _cached_lookup(session, cache, f"{employer}, {city}", True)
            if plausible(point):
                return point, "employer"

    for source_text in (offer.get("offer_city"), offer.get("title"),
                        offer.get("unit_name")):
        hit = _district_in(str(source_text or ""))
        if hit:
            return hit[1], "district"

    if city_point is not None:
        return city_point, "city"
    return None, ""


def load_cache() -> Dict[str, Optional[list]]:
    """Publiczny dostęp do pamięci podręcznej geokodowania.

    Returns:
        Słownik pamięci (modyfikowalny; zapisz przez :func:`save_cache`).
    """
    return _load_cache()


def save_cache(cache: Dict[str, Optional[list]]) -> None:
    """Zapisuje pamięć podręczną geokodowania.

    Args:
        cache: słownik pamięci.
    """
    _save_cache(cache)
