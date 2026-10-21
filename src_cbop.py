#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło zewnętrzne: CBOP — Centralna Baza Ofert Pracy (oferty.praca.gov.pl).

DLACZEGO TO NAJWARTOŚCIOWSZE ŹRÓDŁO POZA BIP
--------------------------------------------
To **oficjalna rządowa baza** wszystkich powiatowych urzędów pracy —
17,5 tys. ofert w kraju. Obejmuje pracodawców, których nie ma ani w BIP
Krakowa (bo nie są jednostkami miejskimi), ani na własnych stronach.

Dowód wartości z pierwszego przebiegu: oferta **„Asystent/asystentka
w grupie pracowników badawczo-dydaktycznych” w Akademii Sztuk Pięknych
im. Jana Matejki w Krakowie** (od 5600 zł, termin 26.10.2026). Strona
``asp.krakow.pl/praca`` była przy badaniu **pusta** — ASP ogłasza się
przez CBOP. Bez tego źródła ta oferta nie trafiłaby do raportu w ogóle.

JAK ZOSTAŁO ODKRYTE API (dokumentacja, bo nie jest publicznie opisane)
---------------------------------------------------------------------
Portal to aplikacja Angular; zgadywanie ścieżek dawało tylko powłokę HTML
(wszystko pod ``/portal/`` zwraca 200 z ``index.cbop``). Endpoint udało
się znaleźć, uruchamiając portal w headless Chrome z ``--log-net-log``
i czytając przechwycone adresy: baza API to ``/portal-api/v3/``.
Nazwy pól filtra pochodzą z leniwie ładowanego modułu ``chunk-GKCIW4KD.js``.

* ``POST /portal-api/v3/oferta/wyszukiwanie`` — lista ofert,
  ciało: ``{"kodJezyka": "PL", "stanowiska": ["grafik"], "rozmiarStrony": 100}``
* ``GET  /portal-api/v3/oferta/szczegoly/<id>?kodJezyka=PL`` — szczegóły,
  w ``danePodstawowe.numer`` jest numer oferty (np. ``StPr/26/4192``).
* ``GET  /portal-api/v3/oferta/licznik?jezyk=PL`` — liczniki (kontrolnie).

PUŁAPKI
-------
* ``miejscowosci: ["Kraków"]`` **psuje odpowiedź** (``payload: null``) —
  to pole oczekuje identyfikatorów, nie nazw. Dlatego lokalizację
  filtrujemy po stronie klienta, po tekstowym polu ``miejscePracy``
  („Kraków, małopolskie”). Wolumen jest mały (15 ofert dla „grafik”
  w całym kraju), więc to tanie i odporne na zmiany słowników.
* **Link do oferty** ma postać
  ``/portal/lista-ofert/szczegoly-oferty/<id>`` — gdzie ``<id>`` to ten
  sam hash, który zwraca API. Nie udało się tego zgadnąć: próby
  ``#/oferta/<id>``, ``#/szczegolyOferty/<id>``, ``#/cbop-oferta/<id>``
  i ``#/szukajOferty?numeryOfert=...`` nie renderowały oferty. Format
  ustalono empirycznie — wyrenderowano listę ofert w headless Chrome
  i odczytano ``href`` z kart, które aplikacja generuje sama. Aplikacja
  **nie używa tras z hashem**, mimo że punkt wejścia nazywa się
  ``index.cbop``.
* Daty są w formacie ``DD.MM.YYYY``, a raport wymaga ISO — konwertujemy.
* Fraza „grafik” łapie też „pracownik produkcji - **elastyczny grafik**”
  (homonim harmonogramu); odsiewa to ``profile_match``.
* Stronicowanie działa **wyłącznie przez query string** — szczegóły
  w docstringu :func:`search_phrase`.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Dict, List, Optional, Tuple

import bip_common as bc
import contract_type as ct
import salary as sal

# Baza API (odkryta przez przechwycenie ruchu aplikacji — patrz docstring).
API_BASE = "https://oferty.praca.gov.pl/portal-api/v3"
SEARCH_URL = f"{API_BASE}/oferta/wyszukiwanie"
DETAIL_URL = f"{API_BASE}/oferta/szczegoly"

# Adres szczegółów oferty. Format ustalony empirycznie (patrz docstring):
# aplikacja NIE używa tras z hashem, a identyfikator to hash z API.
OFFER_URL_BASE = ("https://oferty.praca.gov.pl/portal/lista-ofert"
                  "/szczegoly-oferty/")
# Adres listy ofert — zapasowo, gdy brakuje identyfikatora.
PORTAL_SEARCH = "https://oferty.praca.gov.pl/portal/lista-ofert"

# Frazy stanowisk istotne dla profilu (kultura, sztuka, grafika, edukacja).
# Liczby z badania 2026-10-15 (kraj / Małopolska): grafik 15/5,
# instruktor 61/0, animator 15/0, kultur 18/1, warsztat 13/2,
# plastyk 5/1, edukator 5/1, muzeum 1/0.
SEARCH_PHRASES: Dict[str, Tuple[str, ...]] = {
    "kultura": (
        "grafik", "grafika", "plastyk", "animator", "instruktor",
        "edukator", "muzeum", "kultur", "warsztat", "wystaw",
    ),
    # Dla profilu danych CBOP jest źródłem SŁABYM i trzeba o tym wiedzieć:
    # „programista” daje w Małopolsce głównie automatykę przemysłową
    # (Programista-Operator CNC, Programista Robotów), a „analityk danych”
    # zero w całym kraju. Zostawiamy, bo urzędy pracy publikują też etaty
    # w uczelniach i instytutach, których nie ma na portalach IT.
    "it": (
        "programista", "informatyk", "analityk danych", "python",
        "java", "baz danych", "sztuczn inteligencj", "automatyzacj",
    ),
}

# Rozmiar strony i limit stron. API zwraca najwyżej 20 pozycji na stronę
# niezależnie od żądanego rozmiaru, więc chodzimy po stronach. MAX_PAGES to
# bezpiecznik przed pętlą, gdyby portal zaczął zwracać totalPages w kółko.
PAGE_SIZE = 20
MAX_PAGES = 12

# Markery lokalizacji uznawanej za okolicę Krakowa. Zostawiamy całe
# województwo, bo dojazd z Krakowa do Wieliczki czy Niepołomic jest realny,
# a instytucje kultury są rozproszone.
LOCATION_MARKERS = ("krak", "małopol", "malopol")

UNIT_KEY = "src:cbop"
UNIT_NAME = "CBOP / urzędy pracy"


def _to_iso(value: Optional[str]) -> str:
    """Zamienia datę ``DD.MM.YYYY`` na ``YYYY-MM-DD``.

    Raport parsuje wyłącznie ISO, a CBOP podaje daty po polsku.

    Args:
        value: data w formacie ``DD.MM.YYYY`` albo None.

    Returns:
        Datę ISO albo pusty łańcuch, gdy nie da się przekształcić.
    """
    if not value:
        return ""
    parts = str(value).strip().split(".")
    if len(parts) != 3:
        return ""
    day, month, year = parts
    if not (day.isdigit() and month.isdigit() and year.isdigit()):
        return ""
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _is_local(offer: Dict[str, Any]) -> bool:
    """Sprawdza, czy oferta dotyczy Krakowa lub Małopolski.

    Filtrujemy po stronie klienta, bo pole ``miejscowosci`` w API psuje
    odpowiedź (patrz docstring modułu).

    Args:
        offer: rekord oferty z API.

    Returns:
        True, gdy miejsce pracy wskazuje Kraków/Małopolskę.
    """
    place = str(offer.get("miejscePracy") or "").lower()
    return any(marker in place for marker in LOCATION_MARKERS)


def search_phrase(session, phrase: str) -> List[Dict[str, Any]]:
    """Pobiera WSZYSTKIE strony ofert dla jednej frazy stanowiska.

    Stronicowanie jest konieczne: fraza „instruktor” ma 61 ofert, a jedna
    strona zwraca najwyżej 20. Bez tego krakowskie oferty leżące na
    dalszych stronach po prostu nie trafiałyby do raportu.

    UWAGA: parametry stronicowania działają **wyłącznie w query stringu**
    (``?page=N&size=M``, styl Spring Pageable). Te same nazwy przekazane
    w ciele JSON (``strona``, ``numerStrony``, ``page``) są cicho
    ignorowane — odpowiedź zawsze wraca z ``number=0``.

    Args:
        session: sesja HTTP.
        phrase: fraza nazwy stanowiska.

    Returns:
        Listę rekordów ofert z całego kraju, ze wszystkich stron.
    """
    body = {"kodJezyka": "PL", "stanowiska": [phrase]}
    collected: List[Dict[str, Any]] = []
    page = 0

    while page < MAX_PAGES:
        params = {"page": str(page), "size": str(PAGE_SIZE)}
        try:
            response = session.post(SEARCH_URL, params=params, json=body,
                                    timeout=bc.HTTP_TIMEOUT,
                                    headers={"Accept": "application/json"})
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning("  fraza '%s' str.%d — błąd: %s", phrase, page,
                            exc)
            bc.record_failure(stage="src_cbop", key=f"{phrase}#{page}",
                              url=SEARCH_URL, reason="request_failed",
                              detail=str(exc)[:200])
            break

        if response.status_code != 200:
            bc.record_failure(stage="src_cbop", key=f"{phrase}#{page}",
                              url=SEARCH_URL,
                              reason=f"http_{response.status_code}",
                              detail=response.text[:200])
            break

        try:
            payload = (response.json() or {}).get("payload")
        except ValueError as exc:
            bc.record_failure(stage="src_cbop", key=f"{phrase}#{page}",
                              url=SEARCH_URL, reason="invalid_json",
                              detail=str(exc)[:200])
            break

        if not payload:
            # HTTP 200 z pustym payloadem to cichy błąd filtra — notujemy,
            # bo inaczej wyglądałoby to jak „brak ofert”.
            bc.record_failure(stage="src_cbop", key=f"{phrase}#{page}",
                              url=SEARCH_URL, reason="empty_payload",
                              detail="HTTP 200, payload=null")
            break

        result = payload.get("ofertyPracyPage") or {}
        chunk = result.get("content") or []
        collected.extend(chunk)
        total_pages = int(result.get("totalPages") or 1)
        if page == 0:
            logging.info("  '%s': %s ofert w kraju, stron: %d", phrase,
                         result.get("totalElements"), total_pages)
        page += 1
        if page >= total_pages or not chunk:
            break

    bc.clear_failure(stage="src_cbop", key=f"{phrase}#0",
                     reason="request_failed")
    return collected


def fetch_offer_number(session, offer_id: str) -> str:
    """Pobiera numer oferty (np. ``StPr/26/4192``) ze szczegółów.

    Numer jest potrzebny, bo nie ma działającego linku bezpośredniego —
    po numerze można odnaleźć ofertę w wyszukiwarce portalu.

    Args:
        session: sesja HTTP.
        offer_id: identyfikator oferty z listy.

    Returns:
        Numer oferty albo pusty łańcuch.
    """
    url = f"{DETAIL_URL}/{offer_id}?kodJezyka=PL"
    try:
        response = session.get(url, timeout=bc.HTTP_TIMEOUT,
                               headers={"Accept": "application/json"})
        if response.status_code != 200:
            return ""
        payload = (response.json() or {}).get("payload") or {}
    except (ValueError, Exception):  # pylint: disable=broad-exception-caught
        return ""
    basics = payload.get("danePodstawowe") or {}
    return str(basics.get("numer") or "")


def build_record(offer: Dict[str, Any], number: str) -> Dict[str, Any]:
    """Przekształca rekord CBOP na format datasetu ofert.

    Args:
        offer: rekord oferty z API.
        number: numer oferty (może być pusty).

    Returns:
        Rekord w jednolitym formacie ``data/offers.json``.
    """
    offer_id = str(offer.get("id") or "")
    link = f"{OFFER_URL_BASE}{offer_id}" if offer_id else PORTAL_SEARCH
    # CBOP podaje rodzaj umowy wprost („Umowa o pracę na czas określony”),
    # więc nie zgadujemy go z treści.
    contract_raw = str(offer.get("rodzajUmowy") or "")
    employer = str(offer.get("pracodawca") or "").strip()
    place = str(offer.get("miejscePracy") or "").strip()
    title = str(offer.get("stanowisko") or "").strip()
    # Opis sklejamy z wymagań i zakresu obowiązków — to po nim ocenia
    # dopasowanie do profilu, a karta w raporcie ma być samowystarczalna.
    description = " ".join(str(offer.get(key) or "") for key in
                           ("zakresObowiazkow", "wymagania", "wynagrodzenie",
                            "rodzajUmowy"))

    return {
        "nab_id": f"cbop-{offer_id}",
        "unit_key": UNIT_KEY,
        "unit_name": f"{employer} ({place})" if employer else UNIT_NAME,
        "praca_url": link,
        "status": "trwajacy",
        "title": title,
        "detail_url": link,
        "ref_number": number,
        "deadline": _to_iso(offer.get("dataWaznDo")),
        "raw_text": f"{title} {employer} {description}".strip(),
        # CBOP podaje wynagrodzenie tekstem („od 10 000 PLN Zgodnie
        # z przepisami…”), więc wyłuskujemy kwotę wzorcem.
        **dict(zip(("salary_min", "salary_max", "salary_currency"),
                   sal.parse_from_text(str(offer.get("wynagrodzenie")
                                           or "")))),
        "salary_period": "month",
        "contract_types": ct.classify(contract_raw),
        "contract_raw": contract_raw,
        # Współrzędne podaje samo API — nie trzeba geokodować.
        "lat": offer.get("miejscePracyLatitude"),
        "lon": offer.get("miejscePracyLongitude"),
        "offer_city": str(offer.get("miejscowoscNazwa") or "").strip(),
        "source": "cbop",
        "published": _to_iso(offer.get("dataDodaniaCbop")),
        "category_hint": "",
    }


def main() -> int:
    """Punkt wejścia etapu.

    Returns:
        0 przy powodzeniu, 1 gdy żadna fraza nie zwróciła danych.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty z CBOP (oferty.praca.gov.pl) dla "
                    "Krakowa i Małopolski.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Ogranicz liczbę zapisanych ofert (tryb próbny).",
    )
    bc.add_profile_argument(parser)
    parser.add_argument(
        "--skip-numbers", action="store_true",
        help="Nie pobieraj numerów ofert (szybciej, ale bez sygnatur).",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.use_profile(args.profile)
    phrases = SEARCH_PHRASES.get(args.profile)
    if not phrases:
        logging.error("Brak fraz dla profilu '%s'.", args.profile)
        return 1
    session = bc.build_session()

    # Zbieramy po frazach i od razu odsiewamy oferty spoza Małopolski.
    local: Dict[str, Dict[str, Any]] = {}
    ok_phrases = 0
    for phrase in phrases:
        logging.info("Fraza '%s'", phrase)
        offers = search_phrase(session, phrase)
        if offers:
            ok_phrases += 1
        for offer in offers:
            if not _is_local(offer):
                continue
            key = str(offer.get("id") or "")
            if key and key not in local:
                local[key] = offer

    if ok_phrases == 0:
        logging.error("Żadna fraza nie zwróciła danych — przerywam.")
        return 1

    logging.info("Ofert z Krakowa/Małopolski: %d (unikalnych)", len(local))

    offers_list = list(local.values())
    if args.limit:
        offers_list = offers_list[: args.limit]

    records: List[Dict[str, Any]] = []
    for offer in offers_list:
        number = ("" if args.skip_numbers
                  else fetch_offer_number(session, str(offer.get("id"))))
        record = build_record(offer, number)
        records.append(record)
        logging.info("  • %s | %s | do %s", record["title"][:46],
                     record["ref_number"] or "bez numeru",
                     record["deadline"] or "bez terminu")

    seen_now = bc.now_iso()
    dataset = bc.load_dataset(bc.OFFERS_DATASET)
    records_map = dataset.setdefault("records", {})
    seen_keys = set()
    for record in records:
        bc.upsert_record(records_map, record["nab_id"], record, seen_now)
        seen_keys.add(record["nab_id"])

    # Deaktywujemy tylko własne rekordy i tylko przy pełnym przebiegu.
    expired = 0
    if not args.limit:
        own = {k: v for k, v in records_map.items()
               if v.get("source") == "cbop"}
        expired = bc.deactivate_missing(own, seen_keys, seen_now)

    bc.save_dataset(bc.OFFERS_DATASET, dataset)
    bc.save_snapshot("src_cbop", {
        "fetched_at": seen_now,
        "phrases": list(phrases),
        "kept": len(records),
        "offers": records,
    })
    logging.info("Gotowe. Zapisano: %d (świeżo wygaszonych: %d).",
                 len(records), expired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
