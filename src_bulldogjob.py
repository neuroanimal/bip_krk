#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło zewnętrzne: bulldogjob.pl — oferty IT w Krakowie.

PO CO, OBOK NOFLUFFJOBS
-----------------------
nofluffjobs pokrywa dane i AI bardzo dobrze (147 unikalnych ofert
w Krakowie w badaniu), ale jest jednym portalem — awaria albo zmiana API
zostawiłaby profil bez źródła. bulldogjob daje drugie, niezależne wejście
i mocniej reprezentuje klasyczny backend/JEE oraz mobile, czyli
pozostałe kompetencje z profilu.

SKĄD DANE
---------
Strona ``/companies/jobs/s/city,Krakow`` to aplikacja Next.js, a pełna
lista ofert jest w ``<script id="__NEXT_DATA__">`` jako JSON — nie trzeba
parsować zmiennego HTML. Lista leży pod ``props.pageProps.jobs``. **Uwaga na nazwy pól** — kosztowały
jeden nieudany przebieg: stanowisko jest w ``position``, a NIE w ``title``;
``company`` to obiekt z ``name``; identyfikator do adresu oferty jest
w ``id`` (np. ``258526-senior-java-developer-krakow-luxoft-dxc``).
Przydatne dodatki: ``technologyTags`` (lista technologii — zasila ocenę
profilu), ``experienceLevel``, ``employmentType``, ``remote``,
``contractB2b`` / ``contractEmployment`` (rodzaj umowy),
``denominatedSalaryLong``.

SPRAWDZONE I ODRZUCONE (badanie 2026-10-16)
-------------------------------------------
* ``justjoin.it`` — API zwraca **503** (``api.justjoin.it/v2/...``),
  strona również; blokada po stronie serwisu.
* ``theprotocol.it`` — **403** (grupa pracuj.pl, ta sama bariera co
  pracuj.pl opisana w ``src_nofluffjobs``).
* ``bulldogjob.pl/api/graphql`` — 404; publiczne GraphQL nie jest
  wystawione, dlatego czytamy ``__NEXT_DATA__``.
* **CBOP dla IT jest słaby** i trzeba o tym wiedzieć: fraza
  „programista” daje w Małopolsce głównie automatykę przemysłową
  („Programista-Operator CNC”, „Automatyk/Programista Robotów
  Przemysłowych”), a „analityk danych” — zero ofert w całym kraju.
  CBOP zostaje w potoku profilu IT tylko dlatego, że urzędy pracy
  publikują etaty uczelni i instytutów, nieobecne na portalach IT.

PUŁAPKA
-------
Pole ``city`` bywa listą kilku miast w jednym łańcuchu („Krakow, Warsaw,
Wroclaw”), więc filtr po Krakowie musi być zawarciem podłańcucha, a nie
porównaniem równości — inaczej traci się oferty wielolokalizacyjne.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Dict, List

import bip_common as bc
import contract_type as ct

JOBS_URL = "https://bulldogjob.pl/companies/jobs/s/city,Krakow"

# Blok z danymi aplikacji Next.js.
NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# Marker lokalizacji (pole ``city`` bywa listą — patrz pułapka w docstringu).
KRAKOW_MARKERS = ("krakow", "kraków", "cracow")

UNIT_KEY = "src:bulldogjob"
UNIT_NAME = "bulldogjob.pl"


def extract_jobs(html: str) -> List[Dict[str, Any]]:
    """Wyłuskuje listę ofert z bloku ``__NEXT_DATA__``.

    Szukamy rekurencyjnie listy słowników, w których jest klucz ``title``
    i ``company`` — zamiast zakładać konkretną ścieżkę w drzewie, która
    zmienia się z wersją aplikacji.

    Args:
        html: treść strony z listą ofert.

    Returns:
        Listę surowych rekordów ofert (pusta, gdy nie udało się odczytać).
    """
    found = NEXT_DATA_RE.search(html)
    if not found:
        return []
    try:
        data = json.loads(found.group(1))
    except ValueError:
        return []

    def walk(node: Any, depth: int = 0) -> List[Dict[str, Any]]:
        """Przechodzi drzewo JSON w poszukiwaniu listy ofert."""
        if depth > 10:
            return []
        if isinstance(node, dict):
            for value in node.values():
                result = walk(value, depth + 1)
                if result:
                    return result
        elif isinstance(node, list):
            # Rozpoznajemy listę po polach ``position`` i ``company``
            # (patrz uwaga o nazwach pól w docstringu modułu).
            if (node and isinstance(node[0], dict)
                    and "position" in node[0] and "company" in node[0]):
                return [x for x in node if isinstance(x, dict)]
            for value in node[:12]:
                result = walk(value, depth + 1)
                if result:
                    return result
        return []

    return walk(data)


def _is_krakow(job: Dict[str, Any]) -> bool:
    """Sprawdza, czy oferta dotyczy Krakowa.

    Args:
        job: surowy rekord oferty.

    Returns:
        True, gdy pole miasta wymienia Kraków.
    """
    city = str(job.get("city") or "").lower()
    return any(marker in city for marker in KRAKOW_MARKERS)


def _contract_label(job: Dict[str, Any]) -> str:
    """Składa czytelny opis rodzaju umowy.

    Rodzaj umowy ma znaczenie przy wyborze oferty (B2B kontra umowa
    o pracę), a portal podaje go jako trzy osobne flagi.

    Args:
        job: surowy rekord oferty.

    Returns:
        Opis typu „UoP, B2B” albo pusty łańcuch.
    """
    kinds = []
    if job.get("contractEmployment"):
        kinds.append("UoP")
    if job.get("contractB2b"):
        kinds.append("B2B")
    if job.get("contractOther"):
        kinds.append("inna")
    return ", ".join(kinds)


def build_record(job: Dict[str, Any]) -> Dict[str, Any]:
    """Przekształca ofertę bulldogjob na format datasetu.

    Args:
        job: surowy rekord oferty.

    Returns:
        Rekord w formacie ``data_it/offers.json``.
    """
    title = str(job.get("position") or "").strip()
    company = job.get("company")
    if isinstance(company, dict):
        company = company.get("name")
    company = str(company or "").strip()
    city = str(job.get("city") or "").strip()
    slug = str(job.get("id") or "")
    contract = _contract_label(job)
    level = str(job.get("experienceLevel") or "").strip()
    # Technologie są najlepszym sygnałem dopasowania do profilu — oferta
    # „Software Engineer” z tagiem „PySpark” znaczy coś innego niż ta
    # z tagiem „Salesforce”.
    tags = job.get("technologyTags")
    tech = ", ".join(str(t) for t in tags) if isinstance(tags, list) else ""
    remote = "zdalnie" if job.get("remote") else ""

    extra = " · ".join(x for x in (level, contract, remote) if x)
    url = (f"https://bulldogjob.pl/companies/jobs/{slug}" if slug
           else JOBS_URL)

    return {
        "nab_id": f"bdj-{slug or re.sub(r'[^a-z0-9]+', '-', title.lower())}",
        "unit_key": UNIT_KEY,
        "unit_name": (f"{company} ({city}) — {extra} [{UNIT_NAME}]"
                      if company else UNIT_NAME),
        "praca_url": url,
        "status": "trwajacy",
        "title": title,
        "detail_url": url,
        "ref_number": "",
        "deadline": "",  # portal nie podaje terminu składania
        "raw_text": " ".join(x for x in (
            title, company, city, level, contract, tech,
        ) if x),
        # Portal podaje gotowe flagi, więc korzystamy z nich wprost.
        # Flagi ``contractOther`` nie mapujemy — patrz uwaga w
        # ``contract_type.from_flags``.
        "contract_types": ct.from_flags(
            uop=bool(job.get("contractEmployment")),
            b2b=bool(job.get("contractB2b")),
        ),
        "source": "bulldogjob",
        "published": "",
        "category_hint": "",
    }


def main() -> int:
    """Punkt wejścia etapu.

    Returns:
        0 przy powodzeniu, 1 gdy nie udało się odczytać listy ofert.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty IT z bulldogjob.pl (Kraków).",
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
    session = bc.build_session()

    logging.info("Pobieram %s", JOBS_URL)
    html, reason = bc.fetch_with_reason(session, JOBS_URL)
    if html is None:
        bc.record_failure(stage="src_bulldogjob", key="jobs", url=JOBS_URL,
                          reason=reason or "fetch_failed")
        logging.error("Nie udało się pobrać listy ofert.")
        return 1

    jobs = extract_jobs(html)
    if not jobs:
        # HTTP 200 bez ofert znaczy zwykle zmianę struktury __NEXT_DATA__ —
        # notujemy, bo inaczej wyglądałoby to jak „brak ofert”.
        bc.record_failure(stage="src_bulldogjob", key="jobs", url=JOBS_URL,
                          reason="no_offers_parsed",
                          detail="HTTP 200, __NEXT_DATA__ bez listy ofert")
        logging.error("Nie znaleziono ofert w __NEXT_DATA__.")
        return 1

    logging.info("Ofert na stronie: %d", len(jobs))
    local = [j for j in jobs if _is_krakow(j)]
    logging.info("Z Krakowa: %d", len(local))

    records = [build_record(j) for j in local]
    if args.limit:
        records = records[: args.limit]
    for record in records:
        logging.info("   • %s | %s", record["title"][:46],
                     record["unit_name"][:46])

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
               if v.get("source") == "bulldogjob"}
        expired = bc.deactivate_missing(own, seen_keys, seen_now)

    bc.save_dataset(bc.OFFERS_DATASET, dataset)
    bc.save_snapshot("src_bulldogjob", {
        "fetched_at": seen_now,
        "total_on_page": len(jobs),
        "kept": len(records),
        "offers": records,
    })
    bc.clear_failure(stage="src_bulldogjob", key="jobs",
                     reason="no_offers_parsed")
    logging.info("Gotowe. Zapisano: %d (świeżo wygaszonych: %d).",
                 len(records), expired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
