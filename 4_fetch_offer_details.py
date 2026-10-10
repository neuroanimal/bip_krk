#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrypt 4 — pobiera szczegóły ofert, w których nabór jest wciąż aktualny.

Wejście: ``data/offers.json`` (wynik skryptu 3).
Wyjście: ``data/offer_details.json`` — pełne szczegóły pojedynczych ofert.

Przetwarzamy wyłącznie oferty spełniające warunek "nabór wciąż aktualny":

* status ``trwajacy`` (sekcja "NABORY TRWAJĄCE"), oraz
* rekord jest ``active`` w datasecie ofert, oraz
* termin składania (``deadline``), jeśli znany, nie minął.

Strona szczegółów to zwykły HTML (brak XML/JSON/CSV). Wyciągamy z niej
tytuł/stanowisko, komórkę organizacyjną, termin, warunki pracy i płacy oraz
pełną treść ogłoszenia (jako tekst), zachowując też link źródłowy do
szczegółów. Dzięki temu skrypt 5 może zbudować raport z opisem i odnośnikiem.

Zasada "collect once": szczegóły są zapisywane z datą i godziną pobrania;
ponowne uruchomienie aktualizuje ``last_seen`` bez utraty ``first_seen``.

Uruchomienie:

    python 4_fetch_offer_details.py
    python 4_fetch_offer_details.py --include-all --verbose
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import bip_common as bc

# Etykiety pól, których szukamy w treści ogłoszenia (po polsku). Dla każdej
# etykiety próbujemy wyciągnąć fragment tekstu następujący po niej.
FIELD_LABELS = {
    "wymiar_czasu_pracy": r"wymiar czasu pracy",
    "wynagrodzenie": r"wynagrodzenie",
    "termin_skladania": r"termin\w* składania",
}

# Rozpoznanie daty w formacie 'DD.MM.YYYY' (spotykany w treści szczegółów).
DATE_DOTTED_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def parse_deadline_to_date(deadline: Optional[str]) -> Optional[date]:
    """Zamienia łańcuch terminu na obiekt daty, jeśli to możliwe.

    Obsługuje format 'YYYY-MM-DD' (z listy ofert). Zwraca ``None``, gdy
    termin jest nieznany lub w nieobsługiwanym formacie.

    Args:
        deadline: łańcuch daty lub None.

    Returns:
        Obiekt :class:`datetime.date` albo ``None``.
    """
    if not deadline:
        return None
    try:
        year, month, day = (int(part) for part in deadline.split("-"))
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


def is_still_open(offer: Dict[str, object]) -> bool:
    """Ocenia, czy nabór jest wciąż aktualny (do pobrania szczegółów).

    Warunki: status "trwajacy", rekord aktywny oraz — jeśli znany —
    termin składania nie minął.

    Args:
        offer: rekord oferty z ``offers.json``.

    Returns:
        True, gdy nabór należy potraktować jako wciąż aktualny.
    """
    if offer.get("status") != "trwajacy":
        return False
    if not offer.get("active", True):
        return False
    deadline = parse_deadline_to_date(offer.get("deadline"))
    if deadline is not None and deadline < date.today():
        return False  # termin już minął
    return True


def extract_details(html: str) -> Dict[str, object]:
    """Wyciąga szczegóły oferty z HTML strony naboru.

    Args:
        html: treść HTML strony szczegółów.

    Returns:
        Słownik z polami: heading, body_text (pełny tekst), fields
        (wykryte pola typu wymiar/wynagrodzenie), links (odnośniki
        w treści, np. do dokumentów aplikacyjnych).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Nagłówek/tytuł stanowiska — pierwszy <h1> na stronie szczegółów.
    heading_node = soup.find("h1")
    heading = heading_node.get_text(strip=True) if heading_node else None

    # Usuwamy skrypty i style, by nie zaśmiecały treści.
    for tag in soup(["script", "style"]):
        tag.decompose()

    # Właściwa treść ogłoszenia znajduje się w kontenerze będącym rodzicem
    # nagłówka <h1> "Praca w jednostce" (na BIP jest to div.col-lg-9).
    # Ograniczamy się do niego, aby pominąć nawigację, menu i baner cookies.
    content_node = heading_node.parent if heading_node else None
    source_node = content_node if content_node is not None else soup

    # Pełny tekst treści — spłaszczony do czytelnego akapitowanego tekstu.
    body_text = source_node.get_text("\n", strip=True)
    # Zbijamy nadmiar pustych linii.
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)

    # Próbujemy wyłuskać wybrane pola po etykietach.
    fields: Dict[str, Optional[str]] = {}
    lowered = body_text.lower()
    for field_key, label_pattern in FIELD_LABELS.items():
        match = re.search(
            label_pattern + r"[^\n:]*[:\-]?\s*([^\n]+)", lowered,
        )
        if match:
            # Wyciągamy odpowiadający fragment z oryginalnej (nie lowercase)
            # treści, aby zachować wielkość liter i polskie znaki.
            start = match.start(1)
            end = match.end(1)
            fields[field_key] = body_text[start:end].strip()
        else:
            fields[field_key] = None

    # Zbieramy linki z treści (dokumenty, formularze) — pełne adresy.
    # Ograniczamy się do kontenera treści, aby pominąć linki nawigacyjne.
    links: List[Dict[str, str]] = []
    for anchor in source_node.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        if not text:
            continue
        links.append({
            "text": text,
            "url": urljoin(bc.BASE_URL, anchor["href"]),
        })

    return {
        "heading": heading,
        "body_text": body_text,
        "fields": fields,
        "links": links,
    }


def main() -> int:
    """Punkt wejścia skryptu 4.

    Returns:
        Kod wyjścia (0 = sukces, 1 = brak datasetu ofert).
    """
    parser = argparse.ArgumentParser(
        description="Pobiera szczegóły aktualnych (trwających) naborów.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--include-all", action="store_true",
        help="Pobierz szczegóły WSZYSTKICH ofert (nie tylko trwających).",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Ogranicz liczbę pobieranych szczegółów (do testów).",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    offers_ds = bc.load_dataset(bc.OFFERS_DATASET)
    if not offers_ds["records"]:
        logging.error(
            "Brak ofert w %s — uruchom najpierw 3_fetch_offers.py.",
            bc.OFFERS_DATASET,
        )
        return 1

    # Wybór ofert do pobrania szczegółów.
    targets = []
    for key, offer in offers_ds["records"].items():
        if not offer.get("detail_url"):
            continue  # bez linku szczegółów nie ma czego pobierać
        if args.include_all or is_still_open(offer):
            targets.append((key, offer))
    if args.limit is not None:
        targets = targets[: args.limit]

    logging.info("Do pobrania szczegółów: %d ofert.", len(targets))

    dataset = bc.load_dataset(bc.OFFER_DETAILS_DATASET)
    records = dataset["records"]
    seen_now = bc.now_iso()

    seen_keys: List[str] = []
    fetched = 0

    for index, (key, offer) in enumerate(targets, start=1):
        detail_url = offer["detail_url"]
        title = offer.get("title", "")
        logging.info("[%d/%d] %s", index, len(targets), title[:50])

        html = bc.fetch(session, detail_url)
        if html is None:
            logging.warning("Pominięto (błąd pobierania): %s", key)
            continue

        details = extract_details(html)
        fetched += 1

        fields = {
            "nab_id": offer.get("nab_id"),
            "unit_key": offer.get("unit_key"),
            "unit_name": offer.get("unit_name"),
            "title": title,
            "status": offer.get("status"),
            "deadline": offer.get("deadline"),
            "ref_number": offer.get("ref_number"),
            "detail_url": detail_url,
            "heading": details["heading"],
            "body_text": details["body_text"],
            "extracted_fields": details["fields"],
            "links": details["links"],
        }
        bc.upsert_record(records, key=key, fields=fields, seen_now=seen_now)
        seen_keys.append(key)

    # NIE deaktywujemy tu masowo — pobieramy tylko wąski podzbiór (trwające),
    # więc brak innych ofert w tym przebiegu nie oznacza ich wygaśnięcia.
    # Status wygaśnięcia śledzi skrypt 3 na poziomie listy ofert.

    bc.save_snapshot("offer_details", {
        "fetched_at": seen_now,
        "keys": seen_keys,
    })
    bc.save_dataset(bc.OFFER_DETAILS_DATASET, dataset)

    logging.info(
        "Gotowe. Pobrano szczegóły %d ofert. Dataset: %s",
        fetched, bc.OFFER_DETAILS_DATASET,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
