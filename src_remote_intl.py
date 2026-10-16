#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło zewnętrzne: zagraniczne oferty zdalne dostępne z Polski.

PO CO
-----
Wszystkie dotychczasowe źródła są polskojęzyczne i lokalne. Tymczasem
zagraniczne firmy rekrutują na stanowiska kreatywne zdalnie i **Polska
mieści się w ich zasięgu** — zwykle nie dlatego, że wymieniają ją wprost,
ale bo ogłoszenie jest otwarte na „Europe”, „EMEA” albo „Anywhere in the
World”. Takie oferty nie trafiały do raportu w ogóle.

CO WCHODZI DO RAPORTU
---------------------
Oferta musi spełnić **oba** warunki:

1. **rola kreatywna** — grafika, design, ilustracja, brand, motion, DTP,
   UX/UI, kierunek artystyczny (``ROLE_PATTERN``);
2. **dostępność z Polski**, w jednym z dwóch wariantów:
   * ``Polska wprost`` — ogłoszenie wymienia Kraków/Polskę w jednej
     z pisowni (``Kraków, Krakow, Cracow, Cracovia, Poland, Polska,
     Polen, Polonia``),
   * ``otwarte`` — lokalizacja to Europe / EMEA / Worldwide / Anywhere,
     czyli Polska się kwalifikuje.

Powód takiego rozdziału: w badaniu (2026-10-15) na 15 ofert designerskich
w remotive **żadna nie wymieniała Polski**, ale 13 było otwartych na
„Worldwide” lub „Europe”. Filtrowanie wyłącznie po słowie „Poland”
odrzuciłoby wszystkie. Wariant dopasowania zapisujemy w nazwie jednostki,
żeby było widać, skąd wniosek.

ŹRÓDŁA I DLACZEGO TE
--------------------
* ``weworkremotely.com/categories/remote-design-jobs.rss`` — RSS,
  **najczystsze źródło**: w badaniu 30 ofert i wszystkie 30 rzeczywiście
  designerskie. Pole ``region`` wprost podaje zasięg („Anywhere in the
  World”, „Europe”, „EMEA”).
* ``remoteok.com/api`` — JSON, ostatnie ~100 ofert ze wszystkich
  kategorii. Parametr ``?tags=design`` jest **ignorowany** (zwraca ten sam
  pełny zestaw), dlatego role filtrujemy po stronie klienta.

SPRAWDZONE I ODRZUCONE
----------------------
* ``remotive.com/api/remote-jobs?category=design`` — **odrzucone**:
  darmowe API ignoruje parametr ``category`` i zwraca stałą próbkę 15
  ofert, w której nie ma ANI JEDNEJ z kategorii Design (są: „All others”,
  „Artificial Intelligence”, „Data and Analytics”, „Information
  Technology”, „Marketing”, „Sales”, „Software Development”, „Writing”;
  pierwsza pozycja to „Remote Office Assistant”). Slug ``design`` jest
  prawidłowy — potwierdzony w ``/api/remote-jobs/categories`` — więc to
  ograniczenie darmowego planu, nie błąd zapytania.
* **EURES** (oficjalny portal UE, ``europa.eu/eures``) — API działa
  (``POST /eures/api/jv-searchengine/public/jv-search/search`` z ciałem
  ``{"keywords":[{"keyword":"...","specificSearchCode":"EVERYWHERE"}],
  "locationCodes":["pl"]}``; w ``locationMap`` kod NUTS ``PL21`` oznacza
  Małopolskie). Ale dla tego profilu jest bezużyteczny: na 79 ofert dla
  „graphic designer” w Polsce **tylko 2 były obcojęzyczne**, a jedyna
  obcojęzyczna wzmiankująca Kraków to niemiecka oferta sprzedażowa
  („Business Development Representative”). Przyczyna: EURES agreguje
  krajowe urzędy pracy, więc w części polskiej duplikuje CBOP.
* ``behance.net/joblist`` — 403.
* ``dribbble.com/jobs`` — odpowiada 200, ale bez API; wymagałby parsowania
  HTML pod zmieniający się układ. Do rozważenia, gdy pozostałe zawiodą.

OGRANICZENIA — TRZEBA O NICH WIEDZIEĆ
-------------------------------------
To **nie budżetówka**: zagraniczne firmy komercyjne, często współpraca
B2B, a nie umowa o pracę, więc bez stabilności, o którą tu chodzi.
Wymagany jest **biegły angielski** (także pisany). Przewaga ofert dotyczy
designu produktowego i UX, nie grafiki warsztatowej ani DTP. Feedy
pokazują tylko najnowsze ogłoszenia (remoteok ~99), więc źródło widzi
wycinek rynku, nie całość.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import bip_common as bc

# Role kreatywne — oferta bez trafienia tutaj jest pomijana.
ROLE_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "kultura": re.compile(
        r"graphic|design|illustrat|creative|brand|visual|art\s*direct"
        r"|motion|dtp|typograph|ux\b|ui\b|artist",
        re.IGNORECASE,
    ),
    "it": re.compile(
        r"data\s*(scien|engineer|analy)|machine learning|\bml\b|\bai\b"
        r"|python|backend|back-end|full\s*stack|java\b|android|ios\b"
        r"|analytics|mlops|llm",
        re.IGNORECASE,
    ),
}

# Role, które słowo „design” wciąga mimo braku związku z grafiką:
# „Electrical Design Engineer”, „Design Engineer”, „Site Engineer”.
# Odsiewamy je JUŻ NA WEJŚCIU, żeby nie zaśmiecały datasetu — inaczej
# trafiały do raportu jako oferty kreatywne.
# Wykluczenia PER PROFIL: w profilu kultury słowo „engineer” to szum
# („Electrical Design Engineer”), a w profilu danych jest pożądane.
ROLE_EXCLUDES: Dict[str, "re.Pattern[str]"] = {
    "kultura": re.compile(
        r"engineer|developer|programmer|architect\b|devops|security"
        r"|compliance|analyst|sales|account manager",
        re.IGNORECASE,
    ),
    "it": re.compile(
        r"recruiter|sales|account manager|customer success|teacher",
        re.IGNORECASE,
    ),
}

# Lokalizacja otwarta, w której Polska się kwalifikuje.
OPEN_PATTERN = re.compile(
    r"worldwide|anywhere|europe|emea|global", re.IGNORECASE)

# Polska/Kraków we wszystkich pisowniach, o jakie prosił użytkownik.
POLAND_PATTERN = re.compile(
    r"krak[oó]w|krakow|crac[oó]v|cracow|cracovia|poland|polska|polen"
    r"|polonia",
    re.IGNORECASE,
)

# Źródła: (klucz, etykieta, adres, format).
FEEDS: Dict[str, Tuple[Tuple[str, str, str, str], ...]] = {
    "kultura": (
        ("wwr", "weworkremotely.com",
         "https://weworkremotely.com/categories/remote-design-jobs.rss",
         "rss"),
        ("remoteok", "remoteok.com", "https://remoteok.com/api", "remoteok"),
    ),
    "it": (
        ("wwr-prog", "weworkremotely.com",
         "https://weworkremotely.com/categories/remote-programming-jobs.rss",
         "rss"),
        ("wwr-devops", "weworkremotely.com",
         "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs"
         ".rss", "rss"),
        ("remoteok", "remoteok.com", "https://remoteok.com/api", "remoteok"),
    ),
}

UNIT_KEY = "src:remote_intl"


def _match_reason(text: str, location: str) -> Optional[str]:
    """Ustala, czy i dlaczego oferta jest dostępna z Polski.

    Args:
        text: tytuł (i ewentualnie fragment opisu) oferty.
        location: pole lokalizacji/zasięgu z feedu.

    Returns:
        Opis powodu („Polska wprost” / „otwarte: ...”) albo None.
    """
    if POLAND_PATTERN.search(f"{text} {location}"):
        return "Polska wprost"
    if OPEN_PATTERN.search(location):
        return f"otwarte: {location.strip()[:40]}"
    if not location.strip():
        # Brak lokalizacji na portalu pracy ZDALNEJ znaczy zwykle „bez
        # ograniczeń”. Oznaczamy osobno, bo to domysł, nie deklaracja.
        return "brak ograniczeń (nie podano lokalizacji)"
    return None


def _tag(text: str) -> str:
    """Rozpoznaje tryb pracy podany w ogłoszeniu.

    Args:
        text: tytuł i lokalizacja oferty.

    Returns:
        Etykietę trybu pracy.
    """
    lowered = text.lower()
    if "hybrid" in lowered or "hybryd" in lowered:
        return "hybrydowa"
    if "on-site" in lowered or "onsite" in lowered:
        return "stacjonarna"
    return "zdalna"


def parse_remoteok(payload: str) -> List[Dict[str, str]]:
    """Wyłuskuje oferty z API remoteok.

    Pierwszy element odpowiedzi to metadane (nota prawna), nie oferta —
    dlatego wymagamy obecności pola ``position``.

    Args:
        payload: treść odpowiedzi JSON.

    Returns:
        Listę słowników o jednolitych kluczach.
    """
    try:
        data = json.loads(payload)
    except ValueError:
        return []
    result = []
    for job in data:
        if not isinstance(job, dict) or not job.get("position"):
            continue
        result.append({
            "title": str(job.get("position") or "").strip(),
            "company": str(job.get("company") or "").strip(),
            "location": str(job.get("location") or ""),
            "url": str(job.get("url") or job.get("apply_url") or ""),
            "published": str(job.get("date") or "")[:10],
        })
    return result


def parse_rss(payload: str) -> List[Dict[str, str]]:
    """Wyłuskuje oferty z kanału RSS weworkremotely.

    Args:
        payload: treść kanału RSS.

    Returns:
        Listę słowników o jednolitych kluczach.
    """
    result = []
    for block in re.findall(r"<item>(.*?)</item>", payload, re.S):
        def field(name: str, src: str = block) -> str:
            """Odczytuje pojedyncze pole elementu RSS."""
            found = re.search(
                rf"<{name}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{name}>",
                src, re.S)
            return re.sub(r"\s+", " ", found.group(1)).strip() if found else ""

        title = field("title")
        # WWR wpisuje „Firma: Stanowisko” — rozdzielamy na pracodawcę i rolę.
        company, _, position = title.partition(":")
        result.append({
            "title": (position or title).strip(),
            "company": company.strip() if position else "",
            "location": field("region"),
            "url": field("link"),
            "published": "",
        })
    return result


PARSERS = {"remoteok": parse_remoteok, "rss": parse_rss}


def build_record(job: Dict[str, str], feed_label: str,
                 reason: str) -> Dict[str, Any]:
    """Przekształca ofertę na format datasetu.

    Args:
        job: oferta w formacie jednolitym.
        feed_label: nazwa portalu źródłowego.
        reason: powód uznania oferty za dostępną z Polski.

    Returns:
        Rekord w formacie ``data/offers.json``.
    """
    mode = _tag(f"{job['title']} {job['location']}")
    employer = job["company"] or feed_label
    # Powód dopasowania wchodzi do nazwy jednostki, bo to on uzasadnia
    # obecność oferty w raporcie („otwarte: Europe” vs „Polska wprost”).
    unit_name = f"{employer} — praca {mode}, {reason} [{feed_label}]"
    key = re.sub(r"[^a-z0-9]+", "-",
                 f"{employer}-{job['title']}".lower())[:90]

    return {
        "nab_id": f"intl-{key}",
        "unit_key": UNIT_KEY,
        "unit_name": unit_name,
        "praca_url": job["url"],
        "status": "trwajacy",
        "title": job["title"],
        "detail_url": job["url"],
        "ref_number": "",
        "deadline": "",  # portale pracy zdalnej nie podają terminu
        "raw_text": f"{job['title']} {employer} {job['location']}".strip(),
        "source": "remote_intl",
        "published": job["published"],
        "category_hint": "",
    }


def main() -> int:
    """Punkt wejścia etapu.

    Returns:
        0 przy powodzeniu, 1 gdy żaden feed nie odpowiedział.
    """
    parser = argparse.ArgumentParser(
        description="Zagraniczne oferty zdalne dostępne z Polski "
                    "(role kreatywne).",
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
    feeds = FEEDS.get(args.profile)
    role_pattern = ROLE_PATTERNS.get(args.profile)
    role_exclude = ROLE_EXCLUDES.get(args.profile)
    if not feeds or role_pattern is None or role_exclude is None:
        logging.error("Brak konfiguracji dla profilu '%s'.", args.profile)
        return 1
    session = bc.build_session()

    records: List[Dict[str, Any]] = []
    seen_titles = set()
    ok_feeds = 0

    for key, label, url, kind in feeds:
        logging.info("=== %s ===", label)
        payload, reason = bc.fetch_with_reason(session, url)
        if payload is None:
            bc.record_failure(stage="src_remote_intl", key=key, url=url,
                              reason=reason or "fetch_failed")
            continue
        ok_feeds += 1
        jobs = PARSERS[kind](payload)
        logging.info("  ofert w feedzie: %d", len(jobs))

        kept = 0
        for job in jobs:
            if not job["title"] or not role_pattern.search(job["title"]):
                continue
            if role_exclude.search(job["title"]):
                continue  # „Design Engineer” itp. — patrz ROLE_EXCLUDE
            match = _match_reason(job["title"], job["location"])
            if match is None:
                continue
            dedup_key = job["title"].lower()
            if dedup_key in seen_titles:
                continue
            seen_titles.add(dedup_key)
            records.append(build_record(job, label, match))
            kept += 1
            logging.info("   • %s | %s", job["title"][:46], match[:38])
        logging.info("  zakwalifikowanych: %d", kept)
        if not jobs:
            bc.record_failure(stage="src_remote_intl", key=key, url=url,
                              reason="no_offers_parsed",
                              detail="feed odpowiedział, parser zwrócił 0")

    if ok_feeds == 0:
        logging.error("Żaden feed nie odpowiedział — przerywam.")
        return 1

    if args.limit:
        records = records[: args.limit]

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
               if v.get("source") == "remote_intl"}
        expired = bc.deactivate_missing(own, seen_keys, seen_now)

    bc.save_dataset(bc.OFFERS_DATASET, dataset)
    bc.save_snapshot("src_remote_intl", {
        "fetched_at": seen_now,
        "feeds": [label for _k, label, _u, _t in feeds],
        "kept": len(records),
        "offers": records,
    })
    logging.info("Gotowe. Zapisano: %d (świeżo wygaszonych: %d).",
                 len(records), expired)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
