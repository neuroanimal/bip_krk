#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrypt 2 — dla każdej jednostki znajduje link "PRACA - NOWE".

Wejście: dataset jednostek ``data/units.json`` (wynik skryptu 1).
Wyjście: dataset ``data/praca_links.json`` — dla każdej jednostki jej link
do zakładki "PRACA - NOWE" (o adresie postaci ``?bip_id=N&dok_id=M``) lub
adnotacja o braku takiego linku.

Skrypt podąża za adresem jednostki niezależnie od tego, czy jest to
bezpośredni ``?bip_id=N``, czy "ładny" slug typu ``/GUP`` (slug i tak
przekierowuje na właściwy ``bip_id``).

Zasada "collect once": każda jednostka trafia do datasetu z datą
dostępności linku (``active`` / ``first_seen``). Gdy link zniknie —
zostaje oznaczony jako nieaktywny (``inactive_since``), a gdy wróci —
jest reaktywowany. Brak linku "PRACA - NOWE" jest zapisany jawnie polem
``has_praca_link: false`` (a nie przez pominięcie rekordu).

Uruchomienie:

    python 2_fetch_praca_links.py
    python 2_fetch_praca_links.py --limit 20 --only-active
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import bip_common as bc

# Etykiety linku do naborów. Serwis używa "PRACA - NOWE", ale zabezpieczamy
# się na drobne warianty (spacje, myślnik, wielkość liter) porównując po
# usunięciu białych znaków i zmianie na wielkie litery.
PRACA_LABELS = ("PRACA - NOWE", "PRACA-NOWE", "PRACA NOWE")


def normalize_label(text: str) -> str:
    """Normalizuje etykietę linku do porównania (bez spacji, wielkie litery).

    Args:
        text: surowy tekst linku.

    Returns:
        Tekst bez białych znaków, wielkimi literami (np. 'PRACA-NOWE').
    """
    # Zbijamy wszelkie białe znaki do pojedynczej spacji, potem porównujemy.
    collapsed = re.sub(r"\s+", " ", text).strip().upper()
    return collapsed


def find_praca_link(html: str) -> Optional[str]:
    """Znajduje link "PRACA - NOWE" w HTML strony jednostki.

    Args:
        html: treść HTML strony jednostki.

    Returns:
        Adres URL (pełny) linku "PRACA - NOWE" albo ``None``, gdy go brak.
    """
    soup = BeautifulSoup(html, "html.parser")
    wanted = {normalize_label(x) for x in PRACA_LABELS}

    for anchor in soup.find_all("a", href=True):
        label = normalize_label(anchor.get_text())
        if label in wanted:
            # Rozwijamy adres względny (np. "?bip_id=28&dok_id=104362").
            return urljoin(bc.BASE_URL, anchor["href"])

    # Wariant zapasowy: dopuszczamy etykietę zawierającą "PRACA" i "NOWE"
    # (gdyby serwis dodał sufiks/prefiks), aby nie przegapić linku.
    for anchor in soup.find_all("a", href=True):
        label = normalize_label(anchor.get_text())
        if "PRACA" in label and "NOWE" in label:
            return urljoin(bc.BASE_URL, anchor["href"])

    return None


def select_units(
    records: Dict[str, dict],
    only_active: bool,
    limit: Optional[int],
) -> List[str]:
    """Wybiera klucze jednostek do przetworzenia wg opcji wywołania.

    Args:
        records: rekordy jednostek z ``units.json``.
        only_active: gdy True, bierzemy tylko aktywne jednostki.
        limit: opcjonalne ograniczenie liczby jednostek (do testów).

    Returns:
        Listę kluczy jednostek do odwiedzenia.
    """
    keys = []
    for key, rec in records.items():
        if only_active and not rec.get("active", True):
            continue
        keys.append(key)
    if limit is not None:
        keys = keys[:limit]
    return keys


def main() -> int:
    """Punkt wejścia skryptu 2.

    Returns:
        Kod wyjścia (0 = sukces, 1 = brak datasetu jednostek).
    """
    parser = argparse.ArgumentParser(
        description="Znajduje link 'PRACA - NOWE' dla każdej jednostki.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--only-active", action="store_true",
        help="Przetwarzaj wyłącznie aktywne jednostki.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Ogranicz liczbę przetwarzanych jednostek (do testów).",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    # Wczytujemy jednostki z wyniku skryptu 1.
    units_ds = bc.load_dataset(bc.UNITS_DATASET)
    if not units_ds["records"]:
        logging.error(
            "Brak jednostek w %s — uruchom najpierw 1_fetch_units.py.",
            bc.UNITS_DATASET,
        )
        return 1

    keys = select_units(units_ds["records"], args.only_active, args.limit)
    logging.info("Do przetworzenia: %d jednostek.", len(keys))

    dataset = bc.load_dataset(bc.PRACA_LINKS_DATASET)
    records = dataset["records"]
    seen_now = bc.now_iso()

    snapshot_rows: List[dict] = []
    seen_keys: List[str] = []
    found = 0
    missing = 0

    for index, key in enumerate(keys, start=1):
        unit = units_ds["records"][key]
        url = unit["url"]
        name = unit.get("name", "")
        logging.info("[%d/%d] %s (%s)", index, len(keys), name[:40], url)

        html = bc.fetch(session, url)
        if html is None:
            # Nie udało się pobrać — nie mieszamy w statusie, pomijamy.
            logging.warning("Pominięto (błąd pobierania): %s", key)
            continue

        praca_url = find_praca_link(html)
        has_link = praca_url is not None
        if has_link:
            found += 1
        else:
            missing += 1

        fields = {
            "unit_key": key,
            "unit_name": name,
            "unit_url": url,
            "has_praca_link": has_link,
            # Gdy brak linku — jawnie zapisujemy None (adnotacja o braku).
            "praca_url": praca_url,
        }
        bc.upsert_record(records, key=key, fields=fields, seen_now=seen_now)
        seen_keys.append(key)
        snapshot_rows.append(fields)

    # Deaktywacja jednostek, których w tym przebiegu nie odwiedzono
    # (np. wypadły z listy). Rekord zostaje z datą wygaśnięcia.
    deactivated = bc.deactivate_missing(records, seen_keys, seen_now)

    bc.save_snapshot("praca_links", {
        "fetched_at": seen_now,
        "rows": snapshot_rows,
    })
    bc.save_dataset(bc.PRACA_LINKS_DATASET, dataset)

    logging.info(
        "Gotowe. Z linkiem 'PRACA - NOWE': %d, bez linku: %d, "
        "świeżo wygaszonych: %d. Dataset: %s",
        found, missing, deactivated, bc.PRACA_LINKS_DATASET,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
