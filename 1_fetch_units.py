#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrypt 1 — pobiera listę miejskich jednostek organizacyjnych (MJO).

Źródła:

* strona główna listy jednostek (:data:`bip_common.UNITS_LIST_URL`) —
  jednostki AKTUALNE,
* sekcja "Archiwum BIP MJO" na dole tej strony (osobny dokument) —
  jednostki ARCHIWALNE (stare, potencjalnie nieaktualne linki).

Na stronie BIP nie ma udostępnionego XML/JSON/CSV — parametry ``format=xml``
itp. są ignorowane i serwis zawsze zwraca HTML. Dlatego parsujemy HTML.

Każda jednostka trafia do datasetu ``data/units.json`` z informacją o
dacie dostępności (``first_seen`` / ``active``) lub wygaśnięcia
(``inactive_since``). Jednostki obecne dziś na liście aktualnej są
oznaczane jako aktywne; jednostki znikające z listy — jako nieaktywne
(z datą), ale nie są usuwane (mogą wrócić do łask).

Uruchomienie (Windows i Linux identycznie):

    python 1_fetch_units.py
    python 1_fetch_units.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import bip_common as bc

# Adres dokumentu "Archiwum BIP MJO" (znaleziony na dole strony głównej
# listy jednostek). Wykrywamy go dynamicznie w HTML, a ten adres służy
# tylko jako zapasowy (fallback), gdyby link zniknął z widoku.
ARCHIVE_FALLBACK_URL = "https://www.bip.krakow.pl/?dok_id=134424"

# Wyrażenie do wyłuskania numeru bip_id z adresu jednostki.
BIP_ID_RE = re.compile(r"bip_id=(\d+)")


def extract_bip_id(href: str) -> Optional[str]:
    """Zwraca numer bip_id z adresu URL, jeśli występuje.

    Obsługuje dwa warianty linków spotykane na BIP:
    * bezpośredni ``?bip_id=28`` (numer widoczny w URL),
    * slug typu ``/GUP`` (numer nieznany z samego linku — zwraca None).

    Args:
        href: wartość atrybutu href linku jednostki.

    Returns:
        bip_id jako łańcuch cyfr albo ``None``, gdy w URL go nie ma.
    """
    match = BIP_ID_RE.search(href)
    if match:
        return match.group(1)
    return None


def extract_slug(href: str) -> Optional[str]:
    """Zwraca slug jednostki (np. 'GUP') z adresu typu '/GUP'.

    Slugi to skrótowe, "ładne" adresy przekierowujące na ``?bip_id=N``.
    Traktujemy je jako alternatywny klucz, gdy bip_id nie jest znany.

    Args:
        href: wartość atrybutu href linku jednostki.

    Returns:
        Slug (bez ukośnika) albo ``None``, gdy to nie jest link slug.
    """
    parsed = urlparse(urljoin(bc.BASE_URL, href))
    # Slug: ścieżka typu "/GUP", bez query stringa z bip_id.
    if parsed.query:
        return None
    path = parsed.path.strip("/")
    # Slug to pojedynczy segment złożony z liter/cyfr (np. GUP, PK1, ZDMK).
    if path and "/" not in path and re.fullmatch(r"[A-Za-z0-9_-]+", path):
        return path
    return None


def parse_units_from_html(html: str, source: str) -> List[Dict[str, str]]:
    """Wyciąga jednostki (linki + nazwy + kategorię) z HTML listy jednostek.

    Za jednostkę uznajemy każdy link, który albo zawiera ``bip_id=N``,
    albo jest slugiem prowadzącym do jednostki. Pomijamy linki nawigacyjne
    i kotwice (``#...``).

    Kategorię ustalamy przez liniowe skanowanie dokumentu: nagłówki
    ``<h2>``/``<h3>`` wyznaczają kategorię główną (np. "Kultura", "Zdrowie",
    "Edukacja"), a ``<h4>`` — podkategorię (np. "Żłobki"). Każda jednostka
    dziedziczy ostatnią napotkaną kategorię/podkategorię przed jej linkiem.

    Args:
        html: treść HTML strony.
        source: etykieta źródła ("current" lub "archive") — zapisywana
            w rekordzie, by rozróżnić listę aktualną od archiwum.

    Returns:
        Listę słowników: {key, bip_id, slug, name, url, source, category,
        subcategory}.
    """
    soup = BeautifulSoup(html, "html.parser")
    units: List[Dict[str, str]] = []
    seen_keys = set()

    # Bieżący kontekst kategorii, aktualizowany podczas skanowania w kolejności
    # dokumentu. h2/h3 -> kategoria główna; h4 -> podkategoria.
    current_category = None
    current_subcategory = None

    # Skanujemy nagłówki ORAZ linki w kolejności występowania w dokumencie.
    for element in soup.find_all(["h2", "h3", "h4", "a"]):
        tag = element.name

        if tag in ("h2", "h3"):
            # Nowa kategoria główna — kasuje ewentualną podkategorię.
            text = element.get_text(strip=True)
            if text:
                current_category = text
                current_subcategory = None
            continue

        if tag == "h4":
            # Podkategoria w obrębie bieżącej kategorii głównej.
            text = element.get_text(strip=True)
            if text:
                current_subcategory = text
            continue

        # tag == "a" — kandydat na link jednostki.
        href = element.get("href", "").strip()
        name = element.get_text(strip=True)

        # Pomijamy puste nazwy oraz kotwice wewnątrzstronowe (#link1).
        if not name or not href or href.startswith("#"):
            continue

        bip_id = extract_bip_id(href)
        slug = extract_slug(href) if bip_id is None else None

        # Interesują nas tylko linki jednostek (bip_id lub slug).
        if bip_id is None and slug is None:
            continue

        # Klucz rekordu: preferujemy bip_id (stabilny), a gdy go brak — slug.
        key = f"bip_id:{bip_id}" if bip_id else f"slug:{slug}"

        # Deduplikacja w obrębie jednej strony (linki bywają powtórzone).
        if key in seen_keys:
            continue
        seen_keys.add(key)

        units.append({
            "key": key,
            "bip_id": bip_id,
            "slug": slug,
            "name": name,
            "url": urljoin(bc.BASE_URL, href),
            "source": source,
            "category": current_category,
            "subcategory": current_subcategory,
        })

    return units


def find_archive_url(html: str) -> str:
    """Znajduje adres dokumentu "Archiwum BIP MJO" na stronie głównej.

    Link jest wykrywany po tekście zawierającym słowo "Archiwum". Gdy nie
    uda się go znaleźć, używamy adresu zapasowego :data:`ARCHIVE_FALLBACK_URL`.

    Args:
        html: treść HTML strony głównej listy jednostek.

    Returns:
        Pełny adres URL dokumentu archiwum.
    """
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True).lower()
        if "archiw" in text:  # "Archiwum BIP MJO"
            url = urljoin(bc.BASE_URL, anchor["href"])
            logging.info("Znaleziono link do archiwum: %s", url)
            return url
    logging.warning(
        "Nie znaleziono linku 'Archiwum' — używam adresu zapasowego %s",
        ARCHIVE_FALLBACK_URL,
    )
    return ARCHIVE_FALLBACK_URL


def main() -> int:
    """Punkt wejścia skryptu 1.

    Returns:
        Kod wyjścia procesu (0 = sukces, 1 = błąd pobierania).
    """
    parser = argparse.ArgumentParser(
        description="Pobiera listę jednostek MJO (aktualne + archiwum).",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Szczegółowe logi (DEBUG).",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    # --- 1. Strona główna: jednostki AKTUALNE ---------------------------
    logging.info("Pobieram listę aktualnych jednostek: %s", bc.UNITS_LIST_URL)
    main_html = bc.fetch(session, bc.UNITS_LIST_URL)
    if main_html is None:
        logging.error("Nie udało się pobrać listy jednostek — przerywam.")
        return 1

    current_units = parse_units_from_html(main_html, source="current")
    logging.info("Znaleziono %d aktualnych jednostek.", len(current_units))

    # --- 2. Archiwum BIP MJO: jednostki ARCHIWALNE ----------------------
    archive_url = find_archive_url(main_html)
    logging.info("Pobieram archiwum jednostek: %s", archive_url)
    archive_html = bc.fetch(session, archive_url)
    archive_units: List[Dict[str, str]] = []
    if archive_html is not None:
        archive_units = parse_units_from_html(archive_html, source="archive")
        logging.info("Znaleziono %d jednostek w archiwum.", len(archive_units))
    else:
        logging.warning("Nie udało się pobrać archiwum — pomijam ten krok.")

    # --- 3. Surowy snapshot ("collect once") ----------------------------
    bc.save_snapshot("units", {
        "fetched_at": bc.now_iso(),
        "current_url": bc.UNITS_LIST_URL,
        "archive_url": archive_url,
        "current": current_units,
        "archive": archive_units,
    })

    # --- 4. Aktualizacja datasetu (upsert + deaktywacja) ----------------
    dataset = bc.load_dataset(bc.UNITS_DATASET)
    records = dataset["records"]
    seen_now = bc.now_iso()

    # Jednostki z listy aktualnej są aktywne. Klucze zbieramy, aby potem
    # oznaczyć jako nieaktywne te, których dziś na liście zabrakło.
    current_keys = []
    for unit in current_units:
        bc.upsert_record(
            records,
            key=unit["key"],
            fields={
                "bip_id": unit["bip_id"],
                "slug": unit["slug"],
                "name": unit["name"],
                "url": unit["url"],
                "source": "current",
                "category": unit.get("category"),
                "subcategory": unit.get("subcategory"),
            },
            seen_now=seen_now,
        )
        current_keys.append(unit["key"])

    # Jednostki znikające z listy aktualnej -> nieaktywne (z datą wygaśnięcia).
    # UWAGA: bierzemy pod uwagę tylko rekordy, które wcześniej były "current",
    # aby archiwalne nie mieszały się w tej deaktywacji.
    current_prev_keys = [
        key for key, rec in records.items()
        if rec.get("source") == "current"
    ]
    deactivated = bc.deactivate_missing(
        {k: records[k] for k in current_prev_keys},
        seen_keys=current_keys,
        seen_now=seen_now,
    )

    # Jednostki z archiwum zapisujemy jako nieaktywne (o ile nie są też
    # obecne na liście aktualnej — wtedy zostają aktywne).
    archived_new = 0
    for unit in archive_units:
        if unit["key"] in current_keys:
            continue  # jest też na aktualnej liście -> pozostaje aktywna
        existing = records.get(unit["key"])
        if existing is None:
            # Nowa jednostka widziana tylko w archiwum -> od razu nieaktywna.
            rec = bc.upsert_record(
                records,
                key=unit["key"],
                fields={
                    "bip_id": unit["bip_id"],
                    "slug": unit["slug"],
                    "name": unit["name"],
                    "url": unit["url"],
                    "source": "archive",
                    "category": unit.get("category"),
                    "subcategory": unit.get("subcategory"),
                },
                seen_now=seen_now,
            )
            rec["active"] = False
            rec["inactive_since"] = seen_now
            archived_new += 1

    bc.save_dataset(bc.UNITS_DATASET, dataset)

    total_active = sum(1 for r in records.values() if r.get("active"))
    logging.info(
        "Gotowe. Rekordów łącznie: %d (aktywnych: %d, świeżo wygaszonych: "
        "%d, nowych archiwalnych: %d). Dataset: %s",
        len(records), total_active, deactivated, archived_new,
        bc.UNITS_DATASET,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
