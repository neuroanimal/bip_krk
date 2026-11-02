#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło zewnętrzne: jooble.org przez oficjalne REST API (z kluczem).

DLACZEGO PRZEZ API, A NIE ZE STRONY
-----------------------------------
Jooble agreguje ogłoszenia z całego internetu — także z portali, które
same blokują odczyt (pracuj.pl, OLX). To czyni go cennym, ale strony
jooble są równie zamknięte: w badaniu 403 dawały kolejno strona
wyszukiwania, kanał RSS, a nawet strona dokumentacji ``/api/about``;
headless Chrome dostawał wyzwanie Cloudflare. Czytelna była wyłącznie
``sitemap.xml``, lecz zawiera tylko numeryczne identyfikatory
(``/jdp/9045649725498974320``) bez tytułu i miasta, a te strony też
odpowiadały 403.

Jedyną drogą jest **oficjalne API partnerskie** z kluczem przyznawanym
po zgłoszeniu:

    POST https://pl.jooble.org/api/<KLUCZ>
    Content-type: application/json
    {"keywords": "grafik", "location": "Kraków"}

Odpowiedź: ``{"totalCount": N, "jobs": [...]}`` — 30 ofert na zapytanie,
z polami ``title``, ``company``, ``location``, ``salary`` (tekstem),
``snippet``, ``type`` (wymiar/rodzaj), ``updated``, ``link``, ``id``.

KLUCZ JEST SEKRETEM — NIE MA GO W KODZIE
----------------------------------------
Repozytorium jest publiczne, więc klucz wczytujemy z zewnątrz, w tej
kolejności:

1. zmienna środowiskowa ``JOOBLE_API_KEY``,
2. plik ``jooble.key`` obok projektu (jedna linia; dopisany do
   ``.gitignore``).

Bez klucza etap **kończy się spokojnie** (kod 0) i tylko odnotowuje brak
w dzienniku — to źródło opcjonalne i jego brak nie może psuć raportu.

LIMIT 500 WYSZUKIWAŃ — DLATEGO MAŁO ZAPYTAŃ
-------------------------------------------
Darmowy klucz ma **500 wyszukiwań**, a każde wywołanie API to jedno
wyszukiwanie. Przy czterech zapytaniach na przebieg wystarcza na ~125
uruchomień, czyli kwartał codziennego użycia. Dlatego:

* domyślnie pytamy o :data:`DEFAULT_QUERIES` (cztery frazy rdzeniowe),
* nie stronicujemy (jedna strona = 30 ofert na frazę),
* liczymy zużycie lokalnie w ``data*/jooble_usage.json`` i ostrzegamy
  po przekroczeniu :data:`WARN_AFTER`.

Lokalny licznik to **przybliżenie** — nie wie o zapytaniach wykonanych
spoza tego narzędzia i nie zna stanu po stronie jooble. Służy do
orientacji, a nie do rozliczeń.
"""

from __future__ import annotations

import argparse
import html as html_lib
import logging
import os
import re
from typing import Any, Dict, List, Tuple

import bip_common as bc
import contract_type as ct

SERVES = {"kultura", "it"}

API_URL = "https://pl.jooble.org/api/{key}"

# Nazwa zmiennej środowiskowej i pliku z kluczem.
KEY_ENV = "JOOBLE_API_KEY"
KEY_FILE = "jooble.key"

# Zapytania domyślne PER PROFIL — krótka lista, bo każde to jedno
# wyszukiwanie z limitu 500.
DEFAULT_QUERIES: Dict[str, Tuple[str, ...]] = {
    # „specjalista ds. promocji” dodane po analizie rynku 21.10: tak
    # instytucje publiczne nazywają rolę, którą firmy nazywają „social
    # media” — bez tej frazy ich ogłoszenia nie trafiały do raportu.
    # Pięć fraz = pięć wyszukiwań na przebieg, czyli ~95 przebiegów z 500.
    "kultura": ("grafik", "instruktor kultury", "animator kultury",
                "media społecznościowe", "specjalista ds. promocji"),
    "it": ("data engineer", "data scientist", "python developer",
           "machine learning"),
}

# Lokalizacja zapytania — jooble sam rozumie promień wokół miasta.
LOCATION = "Kraków"

# Po tylu zapytaniach ostrzegamy, że limit się kończy.
WARN_AFTER = 400
HARD_LIMIT = 500

UNIT_KEY = "src:jooble"
UNIT_NAME = "jooble.org"


def read_key() -> str:
    """Wczytuje klucz API ze zmiennej środowiskowej albo pliku.

    Returns:
        Klucz albo pusty łańcuch, gdy nie znaleziono.
    """
    from_env = os.environ.get(KEY_ENV, "").strip()
    if from_env:
        return from_env
    path = bc.PROJECT_ROOT / KEY_FILE
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _usage_path():
    """Zwraca ścieżkę pliku z lokalnym licznikiem zapytań."""
    return bc.DATA_DIR / "jooble_usage.json"


def read_usage() -> int:
    """Odczytuje lokalny licznik wykonanych zapytań.

    Returns:
        Liczbę zapytań odnotowanych do tej pory.
    """
    path = _usage_path()
    if not path.exists():
        return 0
    data = bc.load_dataset(path)
    try:
        return int((data.get("records") or {}).get("queries", 0))
    except (TypeError, ValueError):
        return 0


def bump_usage(count: int) -> int:
    """Zwiększa lokalny licznik zapytań i zapisuje go.

    Args:
        count: ile zapytań wykonano w tym przebiegu.

    Returns:
        Nową wartość licznika.
    """
    total = read_usage() + count
    bc.save_dataset(_usage_path(), {"records": {"queries": total}})
    return total


def search(session, key: str, keywords: str) -> List[Dict[str, Any]]:
    """Wykonuje jedno zapytanie do API jooble.

    Args:
        session: sesja HTTP.
        key: klucz API.
        keywords: fraza wyszukiwania.

    Returns:
        Listę ofert (pusta przy błędzie — błąd ląduje w dzienniku).
    """
    try:
        response = session.post(
            API_URL.format(key=key),
            json={"keywords": keywords, "location": LOCATION},
            timeout=bc.HTTP_TIMEOUT,
            headers={"Content-type": "application/json"},
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        bc.record_failure(stage="src_jooble", key=keywords, url=API_URL,
                          reason="request_failed", detail=str(exc)[:200])
        return []

    if response.status_code != 200:
        # 401/403 najpewniej znaczy zły albo wyczerpany klucz — notujemy
        # to osobno, bo wymaga działania człowieka, nie poprawki w kodzie.
        reason = ("http_401_klucz" if response.status_code in (401, 403)
                  else f"http_{response.status_code}")
        bc.record_failure(stage="src_jooble", key=keywords, url=API_URL,
                          reason=reason, detail=response.text[:200])
        return []

    try:
        payload = response.json()
    except ValueError as exc:
        bc.record_failure(stage="src_jooble", key=keywords, url=API_URL,
                          reason="invalid_json", detail=str(exc)[:200])
        return []

    jobs = payload.get("jobs") or []
    logging.info("  '%s': %d ofert (w bazie: %s)", keywords, len(jobs),
                 payload.get("totalCount"))
    bc.clear_failure(stage="src_jooble", key=keywords,
                     reason="request_failed")
    return jobs


def build_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Przekształca ofertę jooble na format datasetu.

    Args:
        job: rekord z API.

    Returns:
        Rekord w formacie ``data*/offers.json``.
    """
    title = str(job.get("title") or "").strip()
    company = str(job.get("company") or "").strip()
    location = str(job.get("location") or "").strip()
    # Snippet przychodzi z HTML-em i encjami („<b>instruktor</b>”,
    # „&nbsp;”), które bez oczyszczenia lądowały w opisie oferty.
    snippet = re.sub(r"<[^>]+>", " ", str(job.get("snippet") or ""))
    snippet = re.sub(r"\s+", " ", html_lib.unescape(snippet)).strip()
    pay = str(job.get("salary") or "").strip()
    kind = str(job.get("type") or "").strip()

    # „type” jooble to wymiar/rodzaj zatrudnienia tekstem („Niepełny
    # etat”, „Umowa zlecenie”), więc rozstrzyga go klasyfikator.
    contracts = ct.classify(kind, pay, snippet)

    return {
        "nab_id": f"jbl-{job.get('id')}",
        "unit_key": UNIT_KEY,
        "unit_name": (f"{company} ({location}) [{UNIT_NAME}]" if company
                      else f"{UNIT_NAME} ({location})"),
        "praca_url": str(job.get("link") or ""),
        "status": "trwajacy",
        "title": title,
        "detail_url": str(job.get("link") or ""),
        "ref_number": "",
        "deadline": "",  # jooble nie podaje terminu składania
        "raw_text": f"{title} {company} {kind} {pay} {snippet}".strip(),
        "source": "jooble",
        "published": str(job.get("updated") or "")[:10],
        "category_hint": "",
        "contract_types": contracts,
        "contract_raw": kind,
        "offer_city": location,
        "salary_text_raw": pay,
    }


def main() -> int:
    """Punkt wejścia etapu.

    Returns:
        0 zawsze przy braku klucza (źródło opcjonalne), 1 przy awarii API.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty z jooble.org przez oficjalne REST API.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Ogranicz liczbę zapisanych ofert (tryb próbny).",
    )
    parser.add_argument(
        "--queries", default="",
        help="Własne frazy po przecinku (zamiast domyślnych). Uwaga: "
             "każda fraza to jedno wyszukiwanie z limitu 500.",
    )
    bc.add_profile_argument(parser)
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.use_profile(args.profile)

    key = read_key()
    if not key:
        # Brak klucza nie jest awarią — to źródło opcjonalne.
        logging.warning(
            "Brak klucza API jooble. Ustaw zmienną %s albo zapisz klucz "
            "w pliku %s. Pomijam to źródło.", KEY_ENV, KEY_FILE)
        bc.record_failure(stage="src_jooble", key="config", url=API_URL,
                          reason="missing_api_key",
                          detail=f"ustaw {KEY_ENV} lub plik {KEY_FILE}")
        return 0

    queries = (tuple(q.strip() for q in args.queries.split(",") if q.strip())
               if args.queries
               else DEFAULT_QUERIES.get(args.profile, ()))
    if not queries:
        logging.error("Brak zapytań dla profilu '%s'.", args.profile)
        return 1

    used = read_usage()
    if used >= HARD_LIMIT:
        logging.warning(
            "Lokalny licznik pokazuje %d wykonanych zapytań — darmowy "
            "limit (%d) prawdopodobnie wyczerpany. Pomijam, żeby nie "
            "generować błędów.", used, HARD_LIMIT)
        return 0
    if used >= WARN_AFTER:
        logging.warning("Zużyto już ~%d z %d zapytań API jooble.",
                        used, HARD_LIMIT)

    session = bc.build_session()
    raw: List[Dict[str, Any]] = []
    for keywords in queries:
        logging.info("Zapytanie '%s' (lokalizacja: %s)", keywords, LOCATION)
        raw.extend(search(session, key, keywords))
    total_used = bump_usage(len(queries))
    logging.info("Zapytań w tym przebiegu: %d (lokalnie łącznie ~%d z %d)",
                 len(queries), total_used, HARD_LIMIT)

    if not raw:
        logging.error("Żadne zapytanie nie zwróciło ofert.")
        return 1

    # Deduplikacja po identyfikatorze — frazy zachodzą na siebie.
    unique: Dict[str, Dict[str, Any]] = {}
    for job in raw:
        key_id = str(job.get("id") or "")
        if key_id and key_id not in unique:
            unique[key_id] = job

    records = [build_record(j) for j in unique.values()]
    if args.limit:
        records = records[: args.limit]
    logging.info("Unikalnych ofert: %d (z %d pobranych)", len(records),
                 len(raw))

    seen_now = bc.now_iso()
    dataset = bc.load_dataset(bc.OFFERS_DATASET)
    records_map = dataset.setdefault("records", {})
    seen_keys = set()
    for record in records:
        bc.upsert_record(records_map, record["nab_id"], record, seen_now)
        seen_keys.add(record["nab_id"])

    expired = 0
    if not args.limit:
        own = {k: v for k, v in records_map.items()
               if v.get("source") == "jooble"}
        expired = bc.deactivate_missing(own, seen_keys, seen_now)

    bc.save_dataset(bc.OFFERS_DATASET, dataset)
    bc.save_snapshot("src_jooble", {
        "fetched_at": seen_now,
        "queries": list(queries),
        "kept": len(records),
        "offers": records,
    })
    logging.info("Gotowe. Zapisano: %d (świeżo wygaszonych: %d).",
                 len(records), expired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
