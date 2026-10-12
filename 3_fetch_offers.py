#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrypt 3 — pobiera oferty pracy ze stron "PRACA - NOWE" jednostek.

Wejście: ``data/praca_links.json`` (wynik skryptu 2).
Wyjście: ``data/offers.json`` — pojedyncze oferty pracy z rozbiciem na
sekcje strony:

* NABORY TRWAJĄCE            -> status "trwajacy" (nabór aktualny),
* ZAKOŃCZONO PRZYJMOWANIE... -> status "zakonczono_przyjmowanie",
* NABORY ZAKOŃCZONE          -> status "zakonczony".

Strona nie udostępnia XML/JSON/CSV, więc parsujemy HTML. Każda oferta
w sekcji ma zwykle: tytuł (link do szczegółów ``&nab_id=...&ACT=info``),
nazwę jednostki oraz przypis "(nr ref. ..., składanie ofert do dnia
YYYY-MM-DD)". Gdy sekcja zawiera komunikat typu "brak aktualnych ogłoszeń"
lub "brak wyników wyszukiwania" — zapisujemy to jako pustą sekcję (fakt
braku ofert również jest daną).

Zasada "collect once": każda oferta to rekord z datą pierwszego i
ostatniego zaobserwowania. Oferta, która zniknie ze strony, zostaje
oznaczona jako nieaktywna (``inactive_since``), lecz nie jest usuwana.

Uruchomienie:

    python 3_fetch_offers.py
    python 3_fetch_offers.py --limit 10 --verbose
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

import bip_common as bc

# Mapowanie nagłówków sekcji (wielkimi literami) na kod statusu oferty.
SECTION_STATUS = {
    "NABORY TRWAJĄCE": "trwajacy",
    "ZAKOŃCZONO PRZYJMOWANIE ZGŁOSZEŃ": "zakonczono_przyjmowanie",
    "NABORY ZAKOŃCZONE": "zakonczony",
}

# Komunikaty oznaczające brak ofert w sekcji.
EMPTY_MARKERS = ("brak aktualnych ogłoszeń", "brak wyników wyszukiwania")

# Wyłuskanie numeru naboru z linku szczegółów (klucz oferty).
NAB_ID_RE = re.compile(r"nab_id=(\d+)")

# Wyłuskanie nr referencyjnego i daty składania z przypisu:
# "(nr ref. GUP-KK.1101.10.2026.SS, składanie ofert do dnia 2026-07-26)".
REF_RE = re.compile(r"nr\s+ref\.\s*([^,)]+)", re.IGNORECASE)
DEADLINE_RE = re.compile(
    r"składani[ea]\s+ofert\s+do\s+dnia\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE,
)


def extract_nab_id(href: str) -> Optional[str]:
    """Zwraca numer naboru (nab_id) z linku szczegółów oferty.

    Args:
        href: adres linku szczegółów oferty.

    Returns:
        nab_id jako łańcuch cyfr albo ``None``.
    """
    match = NAB_ID_RE.search(href)
    return match.group(1) if match else None


def parse_offer_note(text: str) -> Dict[str, Optional[str]]:
    """Wyciąga nr referencyjny i termin składania z przypisu oferty.

    Args:
        text: tekst przypisu (np. '(nr ref. ..., składanie ofert do dnia
            2026-07-26)').

    Returns:
        Słownik {ref_number, deadline} (wartości mogą być None).
    """
    ref_match = REF_RE.search(text)
    deadline_match = DEADLINE_RE.search(text)
    return {
        "ref_number": ref_match.group(1).strip() if ref_match else None,
        "deadline": deadline_match.group(1) if deadline_match else None,
    }


def parse_offers(html: str, page_url: str) -> Dict[str, object]:
    """Parsuje stronę "PRACA - NOWE" na listę ofert i status sekcji.

    Podejście: dla każdego nagłówka ``<h2>`` będącego znaną sekcją bierzemy
    najbliższą następującą listę ``<ol>``/``<ul>`` i traktujemy jej
    elementy ``<li>`` jako oferty. Gdy zamiast listy jest komunikat o braku
    ofert — zapisujemy sekcję jako pustą.

    Args:
        html: treść HTML strony.
        page_url: adres strony (do rozwijania linków względnych).

    Returns:
        Słownik {offers: [...], sections: {status: liczba/empty}}.
    """
    soup = BeautifulSoup(html, "html.parser")
    offers: List[Dict[str, object]] = []
    sections: Dict[str, object] = {}

    for header in soup.find_all("h2"):
        header_text = re.sub(r"\s+", " ", header.get_text()).strip().upper()
        status = SECTION_STATUS.get(header_text)
        if status is None:
            continue  # nagłówek spoza interesujących sekcji

        # Zbieramy tekst i listy występujące po nagłówku, aż do kolejnego h2.
        list_node: Optional[Tag] = None
        text_between = ""
        for sibling in header.next_elements:
            if isinstance(sibling, Tag) and sibling.name == "h2":
                break  # dotarliśmy do następnej sekcji
            if isinstance(sibling, Tag) and sibling.name in ("ol", "ul"):
                list_node = sibling
                break
            if isinstance(sibling, str):
                text_between += sibling

        if list_node is None:
            # Brak listy -> sprawdzamy komunikat o braku ofert.
            lowered = text_between.lower()
            is_empty = any(marker in lowered for marker in EMPTY_MARKERS)
            sections[status] = "empty" if is_empty else "unknown"
            continue

        # Parsujemy elementy listy jako oferty.
        items = list_node.find_all("li", recursive=False)
        sections[status] = len(items)
        for item in items:
            anchor = item.find("a", href=True)
            title = anchor.get_text(strip=True) if anchor else item.get_text(strip=True)
            detail_url = urljoin(page_url, anchor["href"]) if anchor else None
            nab_id = extract_nab_id(anchor["href"]) if anchor else None

            # Cały tekst elementu -> jednostka + przypis (nr ref, deadline).
            full_text = re.sub(r"\s+", " ", item.get_text(" ", strip=True))
            note = parse_offer_note(full_text)

            offers.append({
                "nab_id": nab_id,
                "status": status,
                "title": title,
                "detail_url": detail_url,
                "raw_text": full_text,
                "ref_number": note["ref_number"],
                "deadline": note["deadline"],
            })

    return {"offers": offers, "sections": sections}


def main() -> int:
    """Punkt wejścia skryptu 3.

    Returns:
        Kod wyjścia (0 = sukces, 1 = brak datasetu linków).
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty pracy ze stron 'PRACA - NOWE'.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--only-active", action="store_true",
        help="Tylko jednostki z aktywnym linkiem 'PRACA - NOWE'.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Ogranicz liczbę przetwarzanych jednostek (do testów).",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    links_ds = bc.load_dataset(bc.PRACA_LINKS_DATASET)
    if not links_ds["records"]:
        logging.error(
            "Brak linków w %s — uruchom najpierw 2_fetch_praca_links.py.",
            bc.PRACA_LINKS_DATASET,
        )
        return 1

    # Wybieramy tylko rekordy faktycznie mające link do naborów.
    targets = []
    for key, rec in links_ds["records"].items():
        if not rec.get("has_praca_link"):
            continue
        if args.only_active and not rec.get("active", True):
            continue
        targets.append((key, rec))
    if args.limit is not None:
        targets = targets[: args.limit]

    logging.info("Do przetworzenia: %d stron 'PRACA - NOWE'.", len(targets))

    dataset = bc.load_dataset(bc.OFFERS_DATASET)
    records = dataset["records"]
    seen_now = bc.now_iso()

    snapshot_rows: List[dict] = []
    seen_keys: List[str] = []
    total_offers = 0

    for index, (unit_key, rec) in enumerate(targets, start=1):
        praca_url = rec["praca_url"]
        unit_name = rec.get("unit_name", "")
        logging.info("[%d/%d] %s", index, len(targets), unit_name[:45])

        html = bc.fetch(session, praca_url)
        if html is None:
            logging.warning("Pominięto (błąd pobierania): %s", unit_key)
            continue

        parsed = parse_offers(html, praca_url)
        offers = parsed["offers"]
        total_offers += len(offers)

        # Zapis surowego snapshotu tej strony (per jednostka).
        snapshot_rows.append({
            "unit_key": unit_key,
            "unit_name": unit_name,
            "praca_url": praca_url,
            "sections": parsed["sections"],
            "offers": offers,
        })

        for offer in offers:
            # Klucz oferty: nab_id jest globalnie unikalny w serwisie; gdy
            # go brak (rzadko) — budujemy klucz z jednostki i tytułu.
            if offer["nab_id"]:
                key = f"nab:{offer['nab_id']}"
            else:
                key = f"{unit_key}|{offer['title'][:60]}"

            fields = {
                "nab_id": offer["nab_id"],
                "unit_key": unit_key,
                "unit_name": unit_name,
                "praca_url": praca_url,
                "status": offer["status"],
                "title": offer["title"],
                "detail_url": offer["detail_url"],
                "ref_number": offer["ref_number"],
                "deadline": offer["deadline"],
                "raw_text": offer["raw_text"],
                # Źródło pozwala rozdzielić oferty ze stron jednostek od
                # ofert z globalnej listy BIP (skrypt 3b) i innych portali.
                "source": "bip_unit",
            }
            bc.upsert_record(records, key=key, fields=fields, seen_now=seen_now)
            seen_keys.append(key)

    # Oferty, których już nie widać na stronach -> nieaktywne (z datą).
    #
    # UWAGA: tylko przy pełnym przebiegu. Z --limit nie odwiedziliśmy
    # wszystkich stron, więc brak oferty nie znaczy, że zniknęła.
    # Dodatkowo nie ruszamy ofert z innych źródeł (np. globalnej listy BIP),
    # bo ten skrypt widzi tylko oferty ze stron per-jednostka.
    if args.limit is None:
        own_keys = {
            key for key, rec in records.items()
            if rec.get("source") in (None, "bip_unit")
        }
        deactivated = bc.deactivate_missing(
            {k: records[k] for k in own_keys}, seen_keys, seen_now,
        )
    else:
        deactivated = 0
        logging.info("Tryb z --limit: pomijam deaktywację ofert "
                     "(ochrona danych).")

    bc.save_snapshot("offers", {"fetched_at": seen_now, "pages": snapshot_rows})
    bc.save_dataset(bc.OFFERS_DATASET, dataset)

    active_trwajace = sum(
        1 for r in records.values()
        if r.get("active") and r.get("status") == "trwajacy"
    )
    logging.info(
        "Gotowe. Zebrano %d ofert (w tym aktywnych trwających naborów: %d), "
        "świeżo wygaszonych: %d. Dataset: %s",
        total_offers, active_trwajace, deactivated, bc.OFFERS_DATASET,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
