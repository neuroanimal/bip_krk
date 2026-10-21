#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło zewnętrzne: pracujwkulturze.nck.pl — portal pracy w kulturze.

DLACZEGO TO NAJWAŻNIEJSZE ŹRÓDŁO DLA PROFILU KULTURY
----------------------------------------------------
Prowadzi je Narodowe Centrum Kultury i zbiera ogłoszenia instytucji
kultury z całej Polski — także tych, które nie publikują ani w BIP
miasta, ani na własnych stronach.

Dowód wartości: ogłoszenie **„Instruktor/Instruktorka – organizujący/a
działalność w Klubie Dukat (¼ etatu)”** Ośrodka Kultury Kraków-Nowa Huta
(termin 23.10.2026, 1450–1650 zł) — pojawiło się tu, a nie trafiło do
raportu z żadnego innego źródła.

API — ODKRYTE, NIE UDOKUMENTOWANE
---------------------------------
Portal to WordPress, ale **standardowe** ``/wp-json/wp/v2/jobs`` zwraca
``rest_no_route``, mimo że typ treści ``job`` (rest_base ``jobs``) jest
widoczny w ``/wp-json/wp/v2/types``. Prawdziwy endpoint leży we własnej
przestrzeni nazw i został znaleziony przez przechwycenie ruchu strony
w headless Chrome:

    GET /wp-json/job-board/v1/jobs?page=1&per_page=100

Odpowiedź to lista rekordów z bogatym zestawem pól, m.in.:

``title.rendered``   nazwa stanowiska
``city``             miasto (tekstem, np. ``Kraków``)
``wojewodztwo``      lista, np. ``['Małopolskie']``
``obszar``           lista obszarów — **taksonomia portalu**: Sztuka,
                     Edukacja, Muzeum, Zarządzanie projektem, Muzyka,
                     Marketing, Nowe media, Grafika, Teatr, Film,
                     Fotografia, Biblioteka, Literatura, Dostępność…
``organisation``     ``{"title": ..., "id": ...}`` — instytucja
``typ_wspolpracy``   lista: ``etat``, ``dzieło / na zlecenie``,
                     ``kontrakt B2B``, ``wolontariat``, ``staż / praktyki``
``salary_from/to``   widełki (liczby) oraz ``salary_type`` (netto/brutto)
``post_end``         termin składania w formacie ``DD.MM.YYYY``
``job_description``, ``requirements``, ``benefits``, ``how_to_apply``

FILTROWANIE
-----------
Portal jest ogólnopolski (w badaniu: 39 ofert z Warszawy, 9 z Krakowa na
100), więc zawężamy po województwie i mieście. Dodatkowo odsiewamy
obszary spoza profilu (``Księgowość``, ``Prawo``, ``IT``, ``Kadry``),
zostawiając te, o które prosiła adresatka: edukacja, grafika, marketing,
nowe media, zarządzanie projektem, muzyka, muzeum, sztuka.

Wolontariat i staż **zostają** — dla osoby wracającej na rynek po
zwolnieniu bywają realną ścieżką wejścia do instytucji; są oznaczone
rodzajem współpracy, więc filtr w raporcie pozwala je odrzucić.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import logging
import re
from typing import Any, Dict, List, Tuple

import bip_common as bc

# Profile, dla których to źródło ma sens. Uruchomienie go z innym
# profilem jest POMYŁKĄ, nie konfiguracją — zdarzyło się w pracy nad
# projektem i wsypało 50 ofert IT do datasetu profilu kultury,
# bo skrypt odpalono ręcznie bez --profile. Dlatego źródło samo
# odmawia zapisu, a nie polega na orchestratorze.
SERVES = {"kultura"}
import contract_type as ct

API_URL = "https://pracujwkulturze.nck.pl/wp-json/job-board/v1/jobs"

# Portal zwraca maksymalnie 100 rekordów na stronę.
PAGE_SIZE = 100
MAX_PAGES = 8

# Obszary (taksonomia ``obszar``) ISTOTNE dla profilu kultury — wprost
# z listy podanej przez adresatkę, rozszerzone o pokrewne.
RELEVANT_AREAS: Tuple[str, ...] = (
    "sztuka", "edukacja", "grafika", "marketing", "nowe media",
    "zarządzanie projektem", "muzyka", "muzeum", "teatr", "film",
    "fotografia", "biblioteka", "literatura", "dostępność", "szkolenia",
    "pr", "badania", "obsługa klienta",
)

# Obszary jawnie spoza profilu — gdy oferta ma TYLKO takie, pomijamy ją.
EXCLUDED_AREAS: Tuple[str, ...] = (
    "księgowość", "prawo", "it", "kadry", "obsługa techniczna",
    "administracja",
)

# Województwa w zasięgu (dojazd z Krakowa).
REGIONS: Tuple[str, ...] = ("małopolskie", "śląskie", "świętokrzyskie",
                            "podkarpackie")

# Mapowanie ``typ_wspolpracy`` portalu na kody rodzaju umowy.
COOPERATION_MAP: Dict[str, str] = {
    "etat": ct.UOP,
    "dzieło / na zlecenie": ct.UZ,
    "kontrakt b2b": ct.B2B,
}

UNIT_KEY = "src:pracujwkulturze"
UNIT_NAME = "pracujwkulturze.nck.pl"


def _text(value: Any) -> str:
    """Wyciąga czysty tekst z pola WordPressa (``{'rendered': ...}``).

    Args:
        value: wartość pola — łańcuch albo słownik z ``rendered``.

    Returns:
        Tekst bez znaczników HTML.
    """
    if isinstance(value, dict):
        value = value.get("rendered", "")
    # Portal zwraca treść z encjami HTML („Dom Kultury &#8222;Białogon&#8221;”),
    # więc po usunięciu znaczników trzeba je rozkodować — inaczej lądują
    # w tytule oferty w raporcie.
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _in_scope(job: Dict[str, Any]) -> bool:
    """Sprawdza, czy oferta mieści się w zasięgu geograficznym i tematycznym.

    Args:
        job: surowy rekord z API.

    Returns:
        True, gdy oferta dotyczy regionu w zasięgu i obszaru z profilu.
    """
    regions = [str(x).lower() for x in (job.get("wojewodztwo") or [])]
    if regions and not any(r in REGIONS for r in regions):
        return False

    areas = [str(x).lower() for x in (job.get("obszar") or [])]
    if not areas:
        return True  # brak taksonomii — nie odrzucamy, oceni profile_match
    if any(a in RELEVANT_AREAS for a in areas):
        return True
    # Zostały tylko obszary spoza profilu.
    return not all(a in EXCLUDED_AREAS for a in areas)


def _contracts(job: Dict[str, Any]) -> List[str]:
    """Mapuje ``typ_wspolpracy`` portalu na kody rodzaju umowy.

    Args:
        job: surowy rekord z API.

    Returns:
        Listę kodów rodzaju umowy.
    """
    found = []
    for raw in (job.get("typ_wspolpracy") or []):
        code = COOPERATION_MAP.get(str(raw).strip().lower())
        if code and code not in found:
            found.append(code)
    if found:
        return [c for c in ct.ORDER if c in found]
    # „wolontariat”, „staż / praktyki” nie są rodzajem umowy w naszym
    # słowniku — zostawiamy jako nieznany, a informacja trafia do opisu.
    return [ct.UNKNOWN]


def _deadline_iso(job: Dict[str, Any]) -> str:
    """Zamienia ``post_end`` (``DD.MM.YYYY``) na datę ISO.

    Args:
        job: surowy rekord z API.

    Returns:
        Datę ``YYYY-MM-DD`` albo pusty łańcuch.
    """
    parts = str(job.get("post_end") or "").strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return ""
    day, month, year = parts
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def build_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Przekształca rekord portalu na format datasetu ofert.

    Args:
        job: surowy rekord z API.

    Returns:
        Rekord w formacie ``data/offers.json``.
    """
    title = _text(job.get("title"))
    org = job.get("organisation") or {}
    employer = _text(org.get("title")) if isinstance(org, dict) else ""
    city = str(job.get("city") or "").strip()
    areas = ", ".join(str(x) for x in (job.get("obszar") or []))
    cooperation = ", ".join(str(x) for x in (job.get("typ_wspolpracy") or []))

    description = " ".join(_text(job.get(k)) for k in
                           ("job_description", "requirements", "tasks",
                            "benefits"))

    return {
        "nab_id": f"pwk-{job.get('id')}",
        "unit_key": UNIT_KEY,
        "unit_name": (f"{employer} ({city})" if employer
                      else f"{UNIT_NAME} ({city})"),
        "praca_url": str(job.get("link") or ""),
        "status": "trwajacy",
        "title": title,
        "detail_url": str(job.get("link") or ""),
        "ref_number": "",
        "deadline": _deadline_iso(job),
        "raw_text": f"{title} {employer} {areas} {cooperation} "
                    f"{description}".strip(),
        "source": "pracujwkulturze",
        "published": str(job.get("date") or "")[:10],
        "category_hint": "Kultura i Sztuka",
        "contract_types": _contracts(job),
        "contract_raw": cooperation,
        "salary_min": job.get("salary_from") or None,
        "salary_max": job.get("salary_to") or None,
        "salary_currency": "PLN",
        "salary_period": "month",
        "offer_city": city,
        "offer_areas": [str(x) for x in (job.get("obszar") or [])],
    }


def fetch_all(session) -> List[Dict[str, Any]]:
    """Pobiera wszystkie strony ofert z portalu.

    Args:
        session: sesja HTTP.

    Returns:
        Listę surowych rekordów ofert.
    """
    collected: List[Dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{API_URL}?page={page}&per_page={PAGE_SIZE}"
        payload, reason = bc.fetch_with_reason(session, url)
        if payload is None:
            bc.record_failure(stage="src_pracujwkulturze",
                              key=f"page_{page}", url=url,
                              reason=reason or "fetch_failed")
            break
        try:
            chunk = json.loads(payload)
        except ValueError as exc:
            bc.record_failure(stage="src_pracujwkulturze",
                              key=f"page_{page}", url=url,
                              reason="invalid_json", detail=str(exc)[:200])
            break
        if not isinstance(chunk, list) or not chunk:
            break
        collected.extend(chunk)
        logging.info("  strona %d: %d ofert", page, len(chunk))
        if len(chunk) < PAGE_SIZE:
            break
    return collected


def main() -> int:
    """Punkt wejścia etapu.

    Returns:
        0 przy powodzeniu, 1 gdy nie udało się pobrać ofert.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty z pracujwkulturze.nck.pl (NCK) "
                    "dla Krakowa i okolic.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Ogranicz liczbę zapisanych ofert (tryb próbny).",
    )
    parser.add_argument(
        "--all-regions", action="store_true",
        help="Nie filtruj po województwie (cała Polska) — do podglądu.",
    )
    bc.add_profile_argument(parser)
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.use_profile(args.profile)
    if args.profile not in SERVES:
        logging.error(
            "Źródło obsługuje profile %s, a podano '%s' — przerywam, "
            "żeby nie zapisać danych do niewłaściwego datasetu.",
            ", ".join(sorted(SERVES)), args.profile)
        return 1
    session = bc.build_session()

    logging.info("Pobieram oferty z %s", UNIT_NAME)
    jobs = fetch_all(session)
    if not jobs:
        logging.error("Nie pobrano żadnych ofert.")
        return 1
    logging.info("Ofert w portalu: %d", len(jobs))

    records: List[Dict[str, Any]] = []
    for job in jobs:
        if not args.all_regions and not _in_scope(job):
            continue
        records.append(build_record(job))

    logging.info("W zasięgu (region + obszar): %d", len(records))
    if args.limit:
        records = records[: args.limit]
    for record in records:
        logging.info("   • %s | %s | do %s", record["title"][:44],
                     record["unit_name"][:34],
                     record["deadline"] or "bez terminu")

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
               if v.get("source") == "pracujwkulturze"}
        expired = bc.deactivate_missing(own, seen_keys, seen_now)

    bc.save_dataset(bc.OFFERS_DATASET, dataset)
    bc.save_snapshot("src_pracujwkulturze", {
        "fetched_at": seen_now,
        "total_in_portal": len(jobs),
        "kept": len(records),
        "offers": records,
    })
    logging.info("Gotowe. Zapisano: %d (świeżo wygaszonych: %d).",
                 len(records), expired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
