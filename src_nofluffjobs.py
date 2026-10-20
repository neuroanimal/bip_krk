#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło zewnętrzne: nofluffjobs.com — oferty projektowe/graficzne w Krakowie.

PO CO TO ŹRÓDŁO
---------------
W całym dotychczasowym potoku brakowało ofert dla **grafika**. BIP Krakowa
i instytucje kultury szukają grafików rzadko (trafiło się
„GRAFIK/GRAFICZKA” w Teatrze Groteska), a nuzle.pl nie ma ich wcale —
jego kategoria „grafik” jest zapchana ogłoszeniami o *elastycznym grafiku
pracy* (homonim). To źródło zasypuje tę lukę.

CO ZOSTAŁO SPRAWDZONE I ODRZUCONE (żeby nikt nie szukał drugi raz)
------------------------------------------------------------------
Badanie z 2026-10-14, zapytania o „grafik” / Kraków:

* ``pracuj.pl``, ``olx.pl`` — Cloudflare blokuje **wszystko**, w tym
  ``robots.txt`` i ``sitemap.xml`` (403 „Just a moment...”). Nie ma wejścia.
* ``jooble.org``, ``indeed.pl``, ``useme.com`` — 403.
* ``praca.pl`` — PUŁAPKA: strona zwraca „Nie znaleźliśmy ofert pracy
  spełniających wybrane kryteria”, a mimo to wyświetla karty „Grafik /
  Graficzka”, „Grafik Komputerowy”… **wszystkie z Łodzi** (nagłówek
  listingu: „Praca w grafik małopolskie łódzkie”). Czyli dla Krakowa zero,
  a podpowiedzi z innych regionów wyglądają jak wyniki.
* ``aplikuj.pl`` — odpowiada 200 i „125 ofert”, ale filtr frazy nie działa:
  pod adresem ``/praca/krakow/grafik`` są ogłoszenia dla magazynierów.
* ``nabory.kprm.gov.pl`` (służba cywilna) — działa i daje się czytać
  (``Ad[id_province]=1397``, ``Ad[id_city]=92`` dla Krakowa), ale dla frazy
  „grafik” ma **0 ofert w Krakowie**, a krakowskie nabory to administracja
  (Izba Administracji Skarbowej, Komenda Wojewódzka Policji, inspektoraty).
  Odrzucone jako szum, nie z powodu techniki.
* ``justjoin.it`` — 503, ``rocketjobs.pl`` — renderowanie po stronie
  klienta, brak ``__NEXT_DATA__`` do odczytania.

OGRANICZENIE, O KTÓRYM TRZEBA WIEDZIEĆ
--------------------------------------
nofluffjobs to portal **branży IT i marketingu, sektor prywatny** — a nie
budżetówka. „Design” znaczy tu głównie UX/UI produktów cyfrowych (Figma,
design system), czyli pokrewną, lecz inną specjalizację niż grafika
warsztatowa czy DTP. Wolumen jest mały: w badaniu 8 ofert UX i 1 unikalna
„Social Media Graphic Designer” w Krakowie. Źródło jest tanie (jedno
zapytanie na kategorię) i bez ryzyka blokady, więc traktujemy je jako
uzupełnienie, nie główny kanał.

API
---
``POST /api/search/posting`` z ciałem ``{"rawSearch": "..."}``.
Parametry zapytania są **wymagane**, inaczej 400:
``salaryCurrency=PLN``, ``salaryPeriod=month``, ``region=pl``.
Składnia ``rawSearch`` to pary ``klucz=wartość`` po spacji, np.
``"category=ux city=krakow"``.

UWAGA na duplikaty: API zwraca **ten sam nabór wielokrotnie**, raz na
lokalizację (zapytanie „graphic designer” dało 34 wyniki = 1 unikalna
oferta w wielu miastach). Deduplikujemy po polu ``url``.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import bip_common as bc
import contract_type as ct

# Endpoint wyszukiwania ofert.
API_URL = "https://nofluffjobs.com/api/search/posting"

# Parametry wymagane przez API (bez nich odpowiedź to 400 z komunikatem
# „Required parameter 'salaryCurrency' is not present”).
API_PARAMS: Dict[str, str] = {
    "page": "1",
    "limit": "60",
    "salaryCurrency": "PLN",
    "salaryPeriod": "month",
    "region": "pl",
}

# Baza adresu pojedynczej oferty (pole ``url`` rekordu to sam slug).
OFFER_URL_BASE = "https://nofluffjobs.com/job/"

# Zapytania istotne dla profilu. Kategoria „ux” to katalogowa kategoria
# portalu; „graphic designer” to zapytanie frazowe, bo grafiki klasycznej
# portal nie ma jako kategorii.
#
# ODRZUCONE zapytania (sprawdzone, nie dodawać):
#   „designer city=krakow” — zwraca 61 ofert, z czego 29 BACKENDOWYCH
#     („Solution Designer”, „Game Economy Designer” i zwykłe oferty dev),
#     bo portal dopasowuje słowo luźno. Czysty szum.
#   „grafik komputerowy”, „DTP” — 0 wyników; portal jest anglojęzyczny
#     i nie ma polskich nazw stanowisk.
# Zapytania PER PROFIL. Portal obsługuje oba: dla profilu kultury ma
# „Social Media Graphic Designer”, a dla profilu danych — 56 unikalnych
# ofert w kategorii „data” w samym Krakowie (Data Engineer, Data Scientist,
# AI Engineer, MLOps, Power BI; Tesco, GFT, deepsense.ai, XTB).
SEARCH_QUERIES: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "kultura": (
        ("ux/design", "category=ux city=krakow"),
        ("graphic designer", "graphic designer"),
    ),
    "it": (
        ("data", "category=data city=krakow"),
        ("ai/ml", "category=ai city=krakow"),
        ("backend", "category=backend city=krakow"),
        ("mobile", "category=mobile city=krakow"),
        ("data scientist", "data scientist"),
        ("machine learning", "machine learning"),
    ),
}

# Nazwa jednostki w raporcie (źródło nie ma podziału na jednostki miejskie).
UNIT_KEY = "src:nofluffjobs"
UNIT_NAME = "nofluffjobs.com (Kraków)"

# Miasta uznawane za Kraków (API podaje też „Remote”/None).
KRAKOW_MARKERS = ("krak",)


def _is_krakow(posting: Dict[str, Any]) -> bool:
    """Sprawdza, czy oferta dotyczy Krakowa.

    Zapytania frazowe (bez ``city=``) zwracają oferty z całej Polski,
    dlatego filtrujemy po stronie klienta.

    Args:
        posting: rekord oferty z API.

    Returns:
        True, gdy którakolwiek lokalizacja wskazuje Kraków.
    """
    places = (posting.get("location") or {}).get("places") or []
    for place in places:
        city = str((place or {}).get("city") or "").lower()
        if any(marker in city for marker in KRAKOW_MARKERS):
            return True
    return False


def _published_iso(posting: Dict[str, Any]) -> str:
    """Zamienia znacznik czasu publikacji na datę ISO.

    Args:
        posting: rekord oferty z API (pola ``posted``/``renewed`` w ms).

    Returns:
        Datę ``YYYY-MM-DD`` albo pusty łańcuch, gdy brak danych.
    """
    stamp = posting.get("posted") or posting.get("renewed")
    if not isinstance(stamp, (int, float)):
        return ""
    try:
        moment = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return ""
    return moment.date().isoformat()


def fetch_query(session, label: str, raw_search: str) -> List[Dict[str, Any]]:
    """Pobiera oferty dla jednego zapytania.

    Args:
        session: sesja HTTP.
        label: etykieta zapytania (do logów i diagnostyki).
        raw_search: treść pola ``rawSearch`` API.

    Returns:
        Listę rekordów ofert (surowych, jeszcze bez deduplikacji).
    """
    try:
        response = session.post(
            API_URL, params=API_PARAMS, json={"rawSearch": raw_search},
            timeout=bc.HTTP_TIMEOUT,
            headers={"Content-Type": "application/json",
                     "Accept": "application/json"},
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.warning("  zapytanie '%s' nie powiodło się: %s", label, exc)
        bc.record_failure(stage="src_nofluffjobs", key=label, url=API_URL,
                          reason="request_failed", detail=str(exc)[:200])
        return []

    if response.status_code != 200:
        logging.warning("  zapytanie '%s': HTTP %s", label,
                        response.status_code)
        bc.record_failure(stage="src_nofluffjobs", key=label, url=API_URL,
                          reason=f"http_{response.status_code}",
                          detail=response.text[:200])
        return []

    try:
        payload = response.json()
    except ValueError as exc:
        bc.record_failure(stage="src_nofluffjobs", key=label, url=API_URL,
                          reason="invalid_json", detail=str(exc)[:200])
        return []

    postings = payload.get("postings") or []
    logging.info("  '%s': zwrócono %d (total %s)", label, len(postings),
                 payload.get("totalCount"))
    bc.clear_failure(stage="src_nofluffjobs", key=label,
                     reason="request_failed")
    return postings


def build_record(posting: Dict[str, Any]) -> Dict[str, Any]:
    """Przekształca rekord API na format datasetu ofert.

    Args:
        posting: rekord oferty z API.

    Returns:
        Rekord w jednolitym formacie ``data/offers.json``.
    """
    slug = str(posting.get("url") or posting.get("id") or "")
    title = str(posting.get("title") or "").strip()
    employer = str(posting.get("name") or "").strip()
    category = str(posting.get("category") or "").strip()

    # ``salary.type`` to słownik portalu: w badaniu wyłącznie ``b2b``
    # (113 ofert) i ``permanent`` (37). Klasyfikator rozumie oba.
    salary_type = str((posting.get("salary") or {}).get("type") or "")
    pay = posting.get("salary") or {}

    return {
        # Widełki podane wprost przez portal — w badaniu zawsze PLN/Month.
        "salary_min": pay.get("from"),
        "salary_max": pay.get("to"),
        "salary_currency": str(pay.get("currency") or "PLN"),
        "salary_period": str(pay.get("period") or "Month"),
        "contract_types": ct.classify(salary_type),
        "contract_raw": salary_type,
        "nab_id": f"nfj-{slug}",
        "unit_key": UNIT_KEY,
        "unit_name": f"{employer} ({UNIT_NAME})" if employer else UNIT_NAME,
        "praca_url": f"{OFFER_URL_BASE}{slug}",
        "status": "trwajacy",  # portal pokazuje tylko aktywne ogłoszenia
        "title": title,
        "detail_url": f"{OFFER_URL_BASE}{slug}",
        "ref_number": "",
        "deadline": "",  # nofluffjobs nie podaje terminu składania
        "raw_text": " ".join(x for x in (title, employer, category) if x),
        "source": "nofluffjobs",
        "published": _published_iso(posting),
        "category_hint": "",
    }


def main() -> int:
    """Punkt wejścia etapu.

    Returns:
        0 przy powodzeniu, 1 gdy żadne zapytanie nie zadziałało.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty projektowe/graficzne z nofluffjobs.com.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Ogranicz liczbę zapisanych ofert (tryb próbny).",
    )
    bc.add_profile_argument(parser)
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.use_profile(args.profile)
    queries = SEARCH_QUERIES.get(args.profile)
    if not queries:
        logging.error("Brak zapytań dla profilu '%s'.", args.profile)
        return 1
    session = bc.build_session()

    raw: List[Dict[str, Any]] = []
    ok_queries = 0
    for label, raw_search in queries:
        logging.info("Zapytanie '%s': %s", label, raw_search)
        postings = fetch_query(session, label, raw_search)
        if postings:
            ok_queries += 1
        raw.extend(postings)

    if ok_queries == 0:
        logging.error("Żadne zapytanie nie zwróciło danych — przerywam.")
        return 1

    # Deduplikacja i odfiltrowanie ofert spoza Krakowa.
    #
    # UWAGA: nie da się deduplikować po ``url``/``id``, bo API zwraca ten
    # sam nabór jako OSOBNE wpisy per miasto, każdy z własnym slugiem:
    #   social-media-graphic-designer-bluebinary-krakow
    #   social-media-graphic-designer-bluebinary-wroclaw
    #   social-media-graphic-designer-bluebinary-remote
    # Jedno ogłoszenie dawało więc 17 kart w raporcie. Kluczem jest para
    # (tytuł, pracodawca), a z wariantów wybieramy ten ze slugiem
    # krakowskim, żeby link prowadził do właściwej lokalizacji.
    unique: Dict[Tuple[str, str], Dict[str, Any]] = {}
    skipped_other_city = 0
    for posting in raw:
        if not _is_krakow(posting):
            skipped_other_city += 1
            continue
        key = (str(posting.get("title") or "").strip().lower(),
               str(posting.get("name") or "").strip().lower())
        slug = str(posting.get("url") or "")
        current = unique.get(key)
        if current is None:
            unique[key] = posting
        elif "krakow" in slug and "krakow" not in str(current.get("url") or ""):
            unique[key] = posting  # wariant krakowski jest lepszy

    records = [build_record(p) for p in unique.values()]
    if args.limit:
        records = records[: args.limit]

    logging.info("Unikalnych ofert z Krakowa: %d (pominięto spoza: %d)",
                 len(records), skipped_other_city)

    seen_now = bc.now_iso()
    dataset = bc.load_dataset(bc.OFFERS_DATASET)
    records_map = dataset.setdefault("records", {})
    seen_keys = set()
    for record in records:
        bc.upsert_record(records_map, record["nab_id"], record, seen_now)
        seen_keys.add(record["nab_id"])

    # Deaktywujemy TYLKO własne rekordy (filtr po ``source``) i tylko przy
    # pełnym przebiegu — inaczej tryb próbny wygasiłby poprawne dane.
    expired = 0
    if not args.limit:
        own_keys = {
            key for key, rec in records_map.items()
            if rec.get("source") == "nofluffjobs"
        }
        expired = bc.deactivate_missing(
            {k: records_map[k] for k in own_keys}, seen_keys, seen_now,
        )

    bc.save_dataset(bc.OFFERS_DATASET, dataset)
    bc.save_snapshot("src_nofluffjobs", {
        "fetched_at": seen_now,
        "queries": [label for label, _ in queries],
        "total_fetched": len(raw),
        "kept": len(records),
        "offers": records,
    })
    logging.info("Gotowe. Zapisano: %d (świeżo wygaszonych: %d).",
                 len(records), expired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
