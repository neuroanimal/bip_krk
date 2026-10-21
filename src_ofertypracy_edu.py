#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło: ofertypracy.edu.pl — oferty w jednostkach systemu oświaty.

Portal Ministerstwa ("Informacja o wolnych stanowiskach pracy w jednostkach
systemu oświaty") zbudowany na Laravel + Inertia.js. Udostępnia JSON przez
ten sam adres co strona, pod warunkiem podania nagłówków Inertia:

    X-Inertia: true
    X-Inertia-Version: <hash wersji ze strony>

Filtry przekazywane są w query stringu jako ``filter[<pole>]=<wartość>``,
a wynik jest stronicowany (``offers.meta.total``, ``offers.data``).

WAŻNE — typy pracownika (``employeeTypes``), bo o nie chodzi w filtrowaniu:

    1 = Nauczyciel przedmiotu lub zajęć   <- pomijamy (nauczycielskie)
    2 = Nauczyciel                        <- pomijamy (nauczycielskie)
    3 = Wychowawca                        <- pomijamy (nauczycielskie)
    4 = Pracownik niepedagogiczny         <- TO NAS INTERESUJE

Czyli portal **nie jest** wyłącznie nauczycielski: kategoria 4 to stanowiska
niepedagogiczne (administracja, kadry, księgowość, obsługa). Domyślnie
pobieramy tylko ją; opcja --all-types pozwala wziąć wszystkie.

Lokalizacja: powiat ``m. Kraków`` ma id ``1261`` (województwo MAŁOPOLSKIE
= ``12``), ustalone przez ``api/counties?voivodeship_id=12``.

Uruchomienie:

    python src_ofertypracy_edu.py                 # Kraków, niepedagogiczne
    python src_ofertypracy_edu.py --all-types     # Kraków, wszystkie typy
    python src_ofertypracy_edu.py --verbose
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import bip_common as bc

# Profile, dla których to źródło ma sens. Uruchomienie go z innym
# profilem jest POMYŁKĄ, nie konfiguracją — zdarzyło się w pracy nad
# projektem i wsypało 50 ofert IT do datasetu profilu kultury,
# bo skrypt odpalono ręcznie bez --profile. Dlatego źródło samo
# odmawia zapisu, a nie polega na orchestratorze.
SERVES = {"kultura"}

# Adres portalu (strona główna = wyszukiwarka ofert).
EDU_BASE_URL = "https://ofertypracy.edu.pl/"

# Identyfikatory lokalizacji (ustalone z api/counties).
VOIVODESHIP_MALOPOLSKIE = "12"
COUNTY_KRAKOW_CITY = "1261"  # "m. Kraków"

# Typ pracownika: 4 = Pracownik niepedagogiczny (nie-nauczycielski).
EMPLOYEE_TYPE_NON_PEDAGOGICAL = "4"

# Nazwy typów pracownika uznawanych za nauczycielskie (do odfiltrowania,
# gdy pobieramy wszystkie typy).
TEACHER_TYPE_IDS = {"1", "2", "3"}

# Ile ofert na stronę (portal pozwala na większe strony niż domyślne 15).
PER_PAGE = 50


def fetch_inertia_version(session) -> Optional[str]:
    """Pobiera hash wersji Inertia ze strony głównej portalu.

    Nagłówek ``X-Inertia-Version`` musi zgadzać się z wersją zasobów,
    inaczej serwer zwraca pełny HTML zamiast JSON.

    Args:
        session: sesja HTTP.

    Returns:
        Hash wersji albo None, gdy nie udało się odczytać.
    """
    html = bc.fetch(session, EDU_BASE_URL)
    if html is None:
        return None
    match = re.search(r'data-page="([^"]+)"', html)
    if not match:
        return None
    try:
        payload = json.loads(html_lib.unescape(match.group(1)))
    except json.JSONDecodeError:
        return None
    return payload.get("version")


def fetch_offers_page(session, version: str, filters: Dict[str, str],
                      page: int) -> Optional[Dict[str, Any]]:
    """Pobiera jedną stronę wyników z Inertia API portalu.

    Args:
        session: sesja HTTP.
        version: hash wersji Inertia.
        filters: filtry w postaci {pole: wartość} (bez prefiksu 'filter').
        page: numer strony (1-based).

    Returns:
        Słownik ``props.offers`` (z kluczami data/meta) albo None przy błędzie.
    """
    params: List[tuple] = [(f"filter[{key}]", value)
                           for key, value in filters.items()]
    params.append(("page", str(page)))
    params.append(("perPage", str(PER_PAGE)))
    url = f"{EDU_BASE_URL}?{urlencode(params)}"

    response = session.get(
        url,
        headers={"X-Inertia": "true", "X-Inertia-Version": version},
        timeout=bc.HTTP_TIMEOUT,
    )
    if response.status_code >= 400:
        bc.record_failure(
            stage="src_edu",
            key=f"page_{page}",
            url=url,
            reason=f"http_{response.status_code}",
        )
        return None

    try:
        payload = response.json()
    except json.JSONDecodeError:
        # Serwer zwrócił HTML — zwykle niezgodna wersja Inertia.
        bc.record_failure(
            stage="src_edu",
            key=f"page_{page}",
            url=url,
            reason="inertia_version_mismatch",
            detail="odpowiedź nie jest JSON-em",
        )
        return None

    return payload.get("props", {}).get("offers")


def is_teacher_offer(offer: Dict[str, Any]) -> bool:
    """Ocenia, czy oferta dotyczy stanowiska nauczycielskiego.

    Portal rozróżnia typy pracownika (1-3 nauczycielskie, 4 niepedagogiczny).
    Sprawdzamy identyfikator, a gdy go brak — nazwę typu.

    Args:
        offer: rekord oferty z API.

    Returns:
        True, gdy oferta jest nauczycielska (do odfiltrowania).
    """
    type_id = offer.get("employee_type_id")
    if type_id is not None and str(type_id) in TEACHER_TYPE_IDS:
        return True
    # Zapasowo: po nazwie typu (gdy API zwraca obiekt zagnieżdżony).
    type_obj = offer.get("employee_type") or {}
    name = str(type_obj.get("name") or offer.get("employee_type_name") or "")
    lowered = name.lower()
    if "nauczyciel" in lowered or "wychowawca" in lowered:
        return True
    return False


def normalize_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    """Przekształca ofertę z API portalu na nasz wspólny format rekordu.

    Mapujemy pola na te same nazwy, których używają oferty z BIP, aby raport
    mógł je prezentować jednolicie.

    Args:
        offer: rekord oferty z API.

    Returns:
        Rekord w formacie wspólnym (title, unit_name, deadline, detail_url...).
    """
    offer_id = offer.get("id")
    # Adres szczegółów: route 'oferty/{offer}'.
    detail_url = f"{EDU_BASE_URL}oferty/{offer_id}" if offer_id else None

    # Nazwa placówki może być w polu zagnieżdżonym.
    school = offer.get("school") or offer.get("institution") or {}
    unit_name = (school.get("name") if isinstance(school, dict) else None) \
        or offer.get("school_name") or offer.get("institution_name") \
        or "(placówka oświatowa)"

    position = (offer.get("position")
                or offer.get("position_name")
                or offer.get("title")
                or "(bez tytułu)")

    employee_type = offer.get("employee_type") or {}
    type_name = (employee_type.get("name")
                 if isinstance(employee_type, dict) else None)

    return {
        "nab_id": f"edu-{offer_id}",
        "unit_key": None,
        "unit_name": unit_name,
        "praca_url": EDU_BASE_URL,
        "status": "trwajacy",
        "title": str(position),
        "detail_url": detail_url,
        "ref_number": offer.get("reference_number"),
        "deadline": (offer.get("application_deadline")
                     or offer.get("expires_at")
                     or offer.get("deadline")),
        "raw_text": json.dumps(offer, ensure_ascii=False)[:1500],
        "source": "ofertypracy_edu",
        "employee_type_name": type_name,
        "category_hint": "Oświata (niepedagogiczne)",
    }


def main() -> int:
    """Punkt wejścia źródła ofertypracy.edu.pl.

    Returns:
        0 przy sukcesie, 1 przy błędzie.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty z ofertypracy.edu.pl (Kraków).",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--all-types", action="store_true",
        help="Pobierz wszystkie typy pracownika (domyślnie tylko "
             "niepedagogiczne, czyli nie-nauczycielskie).",
    )
    parser.add_argument(
        "--max-pages", type=int, default=20,
        help="Maksymalna liczba stron wyników (zabezpieczenie).",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    version = fetch_inertia_version(session)
    if not version:
        logging.error("Nie udało się odczytać wersji Inertia z %s",
                      EDU_BASE_URL)
        bc.record_failure(stage="src_edu", key="init", url=EDU_BASE_URL,
                          reason="no_inertia_version")
        return 1
    logging.info("Wersja Inertia: %s", version)

    # Filtry: Kraków (miasto) + ewentualnie tylko niepedagogiczne.
    filters: Dict[str, str] = {
        "voivodeship_id": VOIVODESHIP_MALOPOLSKIE,
        "county_id": COUNTY_KRAKOW_CITY,
    }
    if not args.all_types:
        filters["employee_type_id"] = EMPLOYEE_TYPE_NON_PEDAGOGICAL

    logging.info("Filtry: %s", filters)

    all_offers: List[Dict[str, Any]] = []
    page = 1
    while page <= args.max_pages:
        offers = fetch_offers_page(session, version, filters, page)
        if offers is None:
            break
        data = offers.get("data") or []
        meta = offers.get("meta") or {}
        total = meta.get("total", 0)
        if page == 1:
            logging.info("Ofert wg filtrów: %s", total)
        all_offers.extend(data)
        last_page = meta.get("last_page") or 1
        if page >= last_page or not data:
            break
        page += 1

    logging.info("Pobrano rekordów: %d", len(all_offers))

    # Filtrowanie nauczycielskich (gdy pobierano wszystkie typy).
    kept: List[Dict[str, Any]] = []
    skipped_teacher = 0
    for offer in all_offers:
        if args.all_types and is_teacher_offer(offer):
            skipped_teacher += 1
            continue
        kept.append(offer)

    # Zapis do wspólnego datasetu ofert.
    dataset = bc.load_dataset(bc.OFFERS_DATASET)
    records = dataset["records"]
    seen_now = bc.now_iso()
    seen_keys: List[str] = []

    for offer in kept:
        normalized = normalize_offer(offer)
        key = str(normalized["nab_id"])
        bc.upsert_record(records, key=key, fields=normalized,
                         seen_now=seen_now)
        seen_keys.append(key)

    # Deaktywujemy tylko rekordy z tego źródła, których już nie ma.
    own_keys = {
        key for key, rec in records.items()
        if rec.get("source") == "ofertypracy_edu"
    }
    deactivated = bc.deactivate_missing(
        {k: records[k] for k in own_keys}, seen_keys, seen_now,
    )

    bc.save_snapshot("src_ofertypracy_edu", {
        "fetched_at": seen_now,
        "filters": filters,
        "total_fetched": len(all_offers),
        "kept": len(kept),
        "offers": kept,
    })
    bc.save_dataset(bc.OFFERS_DATASET, dataset)

    logging.info(
        "Gotowe. Zapisano: %d (pominięto nauczycielskich: %d, świeżo "
        "wygaszonych: %d).", len(kept), skipped_teacher, deactivated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
