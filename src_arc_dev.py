#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło zewnętrzne: arc.dev — zdalne zlecenia i etaty dev dostępne z Polski.

PO CO
-----
Uzupełnia lukę, o którą prosił użytkownik: **zlecenia** (kontrakty), a nie
tylko etaty, dla IT/DS/AI. arc.dev pośredniczy w pracy zdalnej dla
programistów i jawnie podaje, z których krajów można aplikować — czego
zwykłe portale nie robią.

CO WCHODZI DO RAPORTU
---------------------
Oferta musi być **rolą z profilu** (``ROLE_PATTERN``) i **dostępna
z Polski**, a to drugie rozstrzygamy po polu ``requiredCountries``:

* lista zawiera ``PL``  → ``Polska wprost``,
* lista jest pusta/brak → ``bez ograniczeń krajowych``,
* lista bez ``PL``      → oferta odrzucona.

Rozkład z badania (2026-10-16, 30 ofert ``arcJobs``): 6 wymieniało PL
wprost, 17 nie miało żadnego ograniczenia, 13 miało listę krajów — czyli
23 z 30 były dostępne. Bez czytania tego pola trzeba by zgadywać.

SKĄD DANE
---------
``/remote-jobs`` to aplikacja Next.js; dane są w ``__NEXT_DATA__`` pod
**dwiema** listami:

* ``props.pageProps.arcJobs``      — oferty z arc.dev; mają też stawki
  (``minHourlyRate``/``maxHourlyRate``, ``minAnnualSalary``), strefę czasu
  i ``overlapHours`` (wymagane pokrycie godzin z klientem),
* ``props.pageProps.externalJobs`` — ogłoszenia zewnętrzne; w badaniu
  prawie wyłącznie marketingowe, więc filtr roli jest tu konieczny.

SPRAWDZONE I ODRZUCONE (ta sama runda badania)
----------------------------------------------
* ``theprotocol.it`` — **403**. To grupa pracuj.pl, czyli ta sama bariera
  Cloudflare, którą opisano w ``src_nofluffjobs``.
* ``4programmers.net/Praca``, ``crossweb.pl``, ``useme.com`` — **403**.
* ``freelancer.com`` — API odpowiada (200), ale **ignoruje parametr
  ``query``**: zapytanie „machine learning” zwróciło „Educational Articles
  for Students”, „3-Minute Kids Song Animations” i „Refer Website Clients”.
  Dodatkowo stawki to dół rynku (2–8 USD za zlecenie). Ta sama pułapka co
  ``category`` w remotive — opisana w ``src_remote_intl``.
* ``solid.jobs`` — HTML zawiera **tylko taksonomię filtrów**
  (``java-developer``, ``python-developer``…), zero firm i wynagrodzeń
  (``companyName``: 0 wystąpień, ``salaryFrom``: 0). Adres API
  przechwycony z ruchu aplikacji (``/api/offers?division=it``) odpowiada
  ``{"title":"Endpoint not found","detail":"API endpoint nie istnieje."}``
  — więc sama aplikacja również dostaje 404 i dane pobiera inaczej.
* ``rocketjobs.pl/api/offers`` — 404 (portal renderowany po stronie
  klienta, opisany w ``src_nofluffjobs``).
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import bip_common as bc
import contract_type as ct

JOBS_URL = "https://arc.dev/remote-jobs"

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# Role z profilu danych/AI/backendu. Pełniejszy zestaw niż w
# ``src_remote_intl``, bo arc.dev jest portalem wyłącznie dla developerów.
ROLE_PATTERN = re.compile(
    r"data\s*(scien|engineer|analy)|machine learning|\bml\b|\bai\b"
    r"|python|backend|back-end|full\s*stack|fullstack|java\b|android"
    r"|ios\b|mobile|analytics|mlops|llm|software engineer|architect"
    r"|platform engineer",
    re.IGNORECASE,
)

# Role odsiewane mimo trafienia wyżej (arc.dev miesza ogłoszenia
# zewnętrzne, w badaniu głównie marketingowe i sprzedażowe).
ROLE_EXCLUDE = re.compile(
    r"marketing|sales|recruiter|seo\b|influencer|account manager"
    r"|customer success|salesforce",
    re.IGNORECASE,
)

UNIT_KEY = "src:arc_dev"
UNIT_NAME = "arc.dev"


def extract_jobs(html: str) -> List[Dict[str, Any]]:
    """Wyłuskuje obie listy ofert z bloku ``__NEXT_DATA__``.

    Args:
        html: treść strony ``/remote-jobs``.

    Returns:
        Połączoną listę ofert (pusta, gdy nie udało się odczytać).
    """
    found = NEXT_DATA_RE.search(html)
    if not found:
        return []
    try:
        page = (json.loads(found.group(1)).get("props") or {})
        props = page.get("pageProps") or {}
    except (ValueError, AttributeError):
        return []

    jobs: List[Dict[str, Any]] = []
    for key in ("arcJobs", "externalJobs"):
        chunk = props.get(key)
        if isinstance(chunk, list):
            jobs.extend(x for x in chunk if isinstance(x, dict))
    return jobs


def availability(job: Dict[str, Any]) -> str:
    """Ustala, czy i dlaczego oferta jest dostępna z Polski.

    Args:
        job: surowy rekord oferty.

    Returns:
        Opis powodu albo pusty łańcuch, gdy oferta nie dotyczy Polski.
    """
    countries = job.get("requiredCountries")
    if isinstance(countries, list) and countries:
        if "PL" in countries:
            return f"Polska wprost ({len(countries)} krajów)"
        return ""
    return "bez ograniczeń krajowych"


def _rate_label(job: Dict[str, Any]) -> str:
    """Składa opis stawki, jeśli portal ją podaje.

    Stawka godzinowa jest tu istotna, bo źródło obejmuje ZLECENIA, a nie
    tylko etaty.

    Args:
        job: surowy rekord oferty.

    Returns:
        Opis stawki albo pusty łańcuch.
    """
    low, high = job.get("minHourlyRate"), job.get("maxHourlyRate")
    if low or high:
        return f"{low or '?'}-{high or '?'} USD/h"
    low, high = job.get("minAnnualSalary"), job.get("maxAnnualSalary")
    if low or high:
        return f"{low or '?'}-{high or '?'} USD/rok"
    return ""


def _published(job: Dict[str, Any]) -> str:
    """Zamienia znacznik publikacji na datę ISO.

    Args:
        job: surowy rekord oferty.

    Returns:
        Datę ``YYYY-MM-DD`` albo pusty łańcuch.
    """
    stamp = job.get("postedAt")
    if isinstance(stamp, str) and len(stamp) >= 10:
        return stamp[:10]
    if isinstance(stamp, (int, float)):
        try:
            seconds = stamp / 1000 if stamp > 1e11 else stamp
            return datetime.fromtimestamp(
                seconds, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return ""
    return ""


def _categories_label(job: Dict[str, Any]) -> str:
    """Składa listę kategorii oferty w jeden łańcuch.

    Pole ``categories`` jest listą SŁOWNIKÓW (a nie łańcuchów), co wywaliło
    pierwszy przebieg z ``TypeError: expected str instance, dict found``.
    Obsługujemy oba kształty, bo portal może je zmienić.

    Args:
        job: surowy rekord oferty.

    Returns:
        Kategorie rozdzielone przecinkiem albo pusty łańcuch.
    """
    raw = job.get("categories")
    if not isinstance(raw, list):
        return ""
    names = []
    for item in raw:
        if isinstance(item, dict):
            value = item.get("name") or item.get("title") or item.get("slug")
        else:
            value = item
        if value:
            names.append(str(value))
    return ", ".join(names)


def build_record(job: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Przekształca ofertę arc.dev na format datasetu.

    Args:
        job: surowy rekord oferty.
        reason: powód dostępności z Polski.

    Returns:
        Rekord w formacie ``data_it/offers.json``.
    """
    title = str(job.get("title") or job.get("jobRole") or "").strip()
    company = job.get("company")
    if isinstance(company, dict):
        company = company.get("name")
    company = str(company or "").strip() or "arc.dev (klient nieujawniony)"

    slug = str(job.get("urlString") or "")
    url = f"https://arc.dev/remote-jobs/{slug}" if slug else JOBS_URL
    rate = _rate_label(job)
    kind = str(job.get("jobType") or job.get("positionType") or "").strip()
    overlap = job.get("overlapHours")
    overlap_label = f"pokrycie {overlap} h" if overlap else ""

    extra = " · ".join(x for x in (kind, rate, overlap_label, reason) if x)

    return {
        "nab_id": f"arc-{slug or re.sub(r'[^a-z0-9]+', '-', title.lower())}",
        "unit_key": UNIT_KEY,
        "unit_name": f"{company} — {extra} [{UNIT_NAME}]",
        "praca_url": url,
        "status": "trwajacy",
        "title": title,
        "detail_url": url,
        "ref_number": "",
        "deadline": "",
        "raw_text": " ".join(str(x) for x in (
            title, company, kind, rate, _categories_label(job),
            job.get("experienceLevel") or "",
        ) if x),
        "contract_types": ct.classify(kind),
        "contract_raw": kind,
        "source": "arc_dev",
        "published": _published(job),
        "category_hint": "",
    }


def main() -> int:
    """Punkt wejścia etapu.

    Returns:
        0 przy powodzeniu, 1 gdy nie udało się odczytać ofert.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera zdalne oferty i zlecenia dev z arc.dev "
                    "dostępne z Polski.",
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
        bc.record_failure(stage="src_arc_dev", key="jobs", url=JOBS_URL,
                          reason=reason or "fetch_failed")
        return 1

    jobs = extract_jobs(html)
    if not jobs:
        bc.record_failure(stage="src_arc_dev", key="jobs", url=JOBS_URL,
                          reason="no_offers_parsed",
                          detail="HTTP 200, __NEXT_DATA__ bez arcJobs")
        logging.error("Nie znaleziono ofert w __NEXT_DATA__.")
        return 1

    logging.info("Ofert w feedzie: %d", len(jobs))

    records: List[Dict[str, Any]] = []
    skipped_country = 0
    skipped_role = 0
    for job in jobs:
        title = str(job.get("title") or job.get("jobRole") or "")
        if not ROLE_PATTERN.search(title) or ROLE_EXCLUDE.search(title):
            skipped_role += 1
            continue
        why = availability(job)
        if not why:
            skipped_country += 1
            continue
        records.append(build_record(job, why))

    logging.info("Zakwalifikowanych: %d (odrzucone: rola %d, kraj %d)",
                 len(records), skipped_role, skipped_country)
    if args.limit:
        records = records[: args.limit]
    for record in records:
        logging.info("   • %s | %s", record["title"][:44],
                     record["unit_name"][:52])

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
               if v.get("source") == "arc_dev"}
        expired = bc.deactivate_missing(own, seen_keys, seen_now)

    bc.save_dataset(bc.OFFERS_DATASET, dataset)
    bc.save_snapshot("src_arc_dev", {
        "fetched_at": seen_now,
        "total_in_feed": len(jobs),
        "kept": len(records),
        "offers": records,
    })
    bc.clear_failure(stage="src_arc_dev", key="jobs",
                     reason="no_offers_parsed")
    logging.info("Gotowe. Zapisano: %d (świeżo wygaszonych: %d).",
                 len(records), expired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
