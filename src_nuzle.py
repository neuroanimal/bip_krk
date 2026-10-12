#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło: nuzle.pl — multiwyszukiwarka ofert pracy (filtr: Kraków).

Portal agreguje ogłoszenia z wielu serwisów pracy. Nie udostępnia REST API
(sprawdzone: brak wp-json/graphql/Next.js), ale ma stabilny, serwerowy HTML
z "ładnymi" adresami:

    https://www.nuzle.pl/krakow.html            — oferty dla Krakowa
    https://www.nuzle.pl/<branza>,krakow        — zawężenie do branży

USTALENIE (sprawdzone): **nuzle nie ma paginacji przez URL**. Warianty
``?page=2``, ``?p=2``, ``?strona=2`` oraz ``/krakow,2`` zwracają dokładnie
tę samą listę co strona pierwsza (te same ``data-id``), więc doładowywanie
kolejnych ofert odbywa się po stronie klienta (AJAX/scroll). Z jednego
żądania dostajemy ~55 ofert i to jest limit tej ścieżki — dlatego domyślnie
pobieramy JEDNĄ stronę. Opcja --pages pozostaje na wypadek, gdyby portal
dodał paginację w przyszłości (deduplikacja po data-id chroni przed
zdublowaniem rekordów).

Struktura pojedynczej oferty (kontener ``.list-all-offer``):

    data-id="71380168"                      — identyfikator oferty
    <h2><a href="...,g4673763">TYTUŁ</a>    — tytuł + link do szczegółów
      <span class="new">Nowe</span>         — znacznik świeżości portalu
      <span class="label-important">PILNE</span>
    <p class="desc-list-offer">OPIS…</p>
    <span class="hide">2026-10-11</span>    — DATA PUBLIKACJI
    …class="…city…">Kraków</…>               — lokalizacja

Oferty prowadzą na zewnętrzne portale (nuzle jest agregatorem), dlatego
w rekordzie zapisujemy adres nuzle jako ``detail_url``.

Filtrowanie nauczycielskich: tytuł/opis sprawdzamy pod kątem słów
kluczowych ("nauczyciel", "wychowawca", "pedagog"...), bo nuzle nie ma
pola typu stanowiska.

Uruchomienie:

    python src_nuzle.py                  # Kraków, 2 strony (domyślnie)
    python src_nuzle.py --pages 5
    python src_nuzle.py --keep-teachers  # nie odfiltrowuj nauczycielskich
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import Any, Dict, List

from bs4 import BeautifulSoup

import bip_common as bc

# Adres listy ofert dla Krakowa.
NUZLE_KRAKOW_URL = "https://www.nuzle.pl/krakow.html"

# Słowa kluczowe wskazujące ofertę nauczycielską/pedagogiczną (do pominięcia).
# Dopasowanie po rdzeniu, aby złapać odmiany ("nauczyciela", "nauczycielka").
TEACHER_KEYWORDS = (
    "nauczyciel",
    "wychowawca",
    "wychowawczyni",
    "pedagog",
    "logopeda",
    "psycholog szkoln",
    "lektor",
    "korepetycj",
    "opiekun w żłobku",
)

# Data publikacji ukryta w <span class="hide">YYYY-MM-DD</span>.
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def is_teacher_offer(title: str, description: str) -> bool:
    """Ocenia, czy oferta dotyczy stanowiska nauczycielskiego/pedagogicznego.

    nuzle nie ma pola typu stanowiska, więc decydujemy po treści tytułu
    (głównie) i opisu.

    Args:
        title: tytuł oferty.
        description: opis oferty (może być pusty).

    Returns:
        True, gdy oferta wygląda na nauczycielską.
    """
    haystack = f"{title} {description}".lower()
    return any(keyword in haystack for keyword in TEACHER_KEYWORDS)


def parse_offers(html: str) -> List[Dict[str, Any]]:
    """Parsuje oferty z listy nuzle.

    Args:
        html: HTML strony z listą ofert.

    Returns:
        Listę ofert: {offer_id, title, detail_url, description, published,
        is_new_portal, is_urgent, location}.
    """
    soup = BeautifulSoup(html, "html.parser")
    offers: List[Dict[str, Any]] = []

    for box in soup.select(".list-all-offer"):
        anchor = box.find("a", href=True)
        if anchor is None:
            continue
        title = anchor.get_text(strip=True)
        if not title:
            continue

        # Opis oferty (skrócony na liście).
        desc_node = box.select_one(".desc-list-offer")
        description = desc_node.get_text(" ", strip=True) if desc_node else ""

        # Data publikacji w ukrytym spanie.
        published = None
        for hidden in box.select("span.hide"):
            match = DATE_RE.search(hidden.get_text(strip=True))
            if match:
                published = match.group(1)
                break

        # Lokalizacja (klasa zawierająca "city").
        location = None
        city_node = box.select_one("[class*=city]")
        if city_node is not None:
            location = city_node.get_text(strip=True)

        offers.append({
            "offer_id": box.get("data-id") or anchor["href"],
            "title": title,
            "detail_url": anchor["href"],
            "description": description,
            "published": published,
            # Znaczniki własne portalu — przydatne jako dodatkowy sygnał.
            "is_new_portal": box.select_one("span.new") is not None,
            "is_urgent": box.select_one(".label-important") is not None,
            "location": location,
        })

    return offers


def normalize_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    """Przekształca ofertę nuzle na nasz wspólny format rekordu.

    Args:
        offer: oferta sparsowana z listy.

    Returns:
        Rekord w formacie wspólnym (zgodnym z ofertami BIP).
    """
    return {
        "nab_id": f"nuzle-{offer['offer_id']}",
        "unit_key": None,
        # nuzle agreguje ogłoszenia firm — nazwy pracodawcy nie zawsze podaje
        # na liście, więc używamy lokalizacji jako opisu "jednostki".
        "unit_name": offer.get("location") or "nuzle.pl (agregator)",
        "praca_url": NUZLE_KRAKOW_URL,
        "status": "trwajacy",
        "title": offer["title"],
        "detail_url": offer["detail_url"],
        "ref_number": None,
        # nuzle nie podaje terminu składania — mamy datę publikacji.
        "deadline": None,
        "published": offer.get("published"),
        "raw_text": offer.get("description", "")[:1500],
        "source": "nuzle",
        "portal_new": offer.get("is_new_portal"),
        "portal_urgent": offer.get("is_urgent"),
        "category_hint": "Oferty komercyjne (nuzle)",
    }


def main() -> int:
    """Punkt wejścia źródła nuzle.pl.

    Returns:
        0 przy sukcesie, 1 przy błędzie pobrania pierwszej strony.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty z nuzle.pl dla Krakowa.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--pages", type=int, default=1,
        help="Liczba stron wyników (domyślnie 1 — nuzle nie ma paginacji "
             "przez URL, kolejne strony zwracają te same oferty).",
    )
    parser.add_argument(
        "--keep-teachers", action="store_true",
        help="Nie odfiltrowuj ofert nauczycielskich/pedagogicznych.",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    all_offers: List[Dict[str, Any]] = []
    for page in range(1, args.pages + 1):
        url = (NUZLE_KRAKOW_URL if page == 1
               else f"{NUZLE_KRAKOW_URL}?page={page}")
        logging.info("Pobieram stronę %d: %s", page, url)
        html, reason = bc.fetch_with_reason(session, url)
        if html is None:
            bc.record_failure(stage="src_nuzle", key=f"page_{page}",
                              url=url, reason=reason or "fetch_failed")
            if page == 1:
                logging.error("Nie udało się pobrać pierwszej strony nuzle.")
                return 1
            break
        page_offers = parse_offers(html)
        logging.info("  ofert na stronie: %d", len(page_offers))
        if not page_offers:
            break
        all_offers.extend(page_offers)

    # Deduplikacja po identyfikatorze oferty (strony mogą się nakładać).
    unique: Dict[str, Dict[str, Any]] = {}
    for offer in all_offers:
        unique[str(offer["offer_id"])] = offer
    logging.info("Unikalnych ofert: %d (z %d pobranych)",
                 len(unique), len(all_offers))

    # Filtrowanie nauczycielskich.
    kept: List[Dict[str, Any]] = []
    skipped_teacher = 0
    for offer in unique.values():
        if not args.keep_teachers and is_teacher_offer(
                offer["title"], offer.get("description", "")):
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

    # Deaktywacja tylko rekordów z tego źródła. UWAGA: pobieramy ograniczoną
    # liczbę stron, więc oferty z dalszych stron nie są "zniknięte" — dlatego
    # deaktywujemy wyłącznie, gdy pobrano wszystkie żądane strony bez przerwy.
    own_keys = {
        key for key, rec in records.items() if rec.get("source") == "nuzle"
    }
    deactivated = bc.deactivate_missing(
        {k: records[k] for k in own_keys}, seen_keys, seen_now,
    )

    bc.save_snapshot("src_nuzle", {
        "fetched_at": seen_now,
        "pages": args.pages,
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
