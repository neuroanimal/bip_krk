#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrypt 3b — pobiera oferty z GLOBALNEJ listy naborów BIP (szybka ścieżka).

Odkrycie: BIP udostępnia jedną, centralną stronę naborów wszystkich
miejskich jednostek organizacyjnych:

    https://www.bip.krakow.pl/?dok_id=104362

Zawiera ona **wszystkie** nabory (w jednym przebiegu: ~435 ofert ze ~176
jednostek) w trzech sekcjach: NABORY TRWAJĄCE, ZAKOŃCZONO PRZYJMOWANIE
ZGŁOSZEŃ, NABORY ZAKOŃCZONE. Każda oferta zawiera w linku ``bip_id``
jednostki, więc można ją powiązać z rekordem jednostki z ``units.json``.

Dzięki temu nie trzeba odwiedzać ~400 stron jednostek po kolei (co zajmowało
~45 minut) — jedno żądanie daje komplet. Skrypt 3 (per jednostka) pozostaje
jako ścieżka zapasowa/uzupełniająca, bo niektóre jednostki mogą publikować
nabory wyłącznie u siebie.

Struktura pozycji na stronie globalnej:

    <li><span class="bold"><a href="?bip_id=233&sub_dok_id=104362
        &nab_id=14311&MODE=nab&ACT=info">TYTUŁ</a><br/></span>
        NAZWA JEDNOSTKI (SKRÓT)<br/>
        (nr ref. DPSN-1/26, składanie ofert do dnia 2026-12-31)<br/></li>

Uruchomienie:

    python 3b_fetch_offers_global.py
    python 3b_fetch_offers_global.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import bip_common as bc

# Adres globalnej listy naborów (wszystkie jednostki naraz).
GLOBAL_NABORY_URL = "https://www.bip.krakow.pl/?dok_id=104362"

# Mapowanie nagłówków sekcji na kod statusu oferty (jak w skrypcie 3).
SECTION_STATUS = {
    "NABORY TRWAJĄCE": "trwajacy",
    "ZAKOŃCZONO PRZYJMOWANIE ZGŁOSZEŃ": "zakonczono_przyjmowanie",
    "NABORY ZAKOŃCZONE": "zakonczony",
}

# Wzorzec pojedynczej oferty w liście globalnej.
OFFER_RE = re.compile(
    r'<li><span class="bold"><a href="([^"]*nab_id=(\d+)[^"]*)">'
    r"(.*?)</a><br/></span>(.*?)<br/>\((.*?)\)<br/></li>",
    re.DOTALL,
)

# Nr referencyjny i termin z przypisu oferty.
REF_RE = re.compile(r"nr\s+ref\.\s*([^,)]+)", re.IGNORECASE)
DEADLINE_RE = re.compile(
    r"składani[ea]\s+ofert\s+do\s+dnia\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE,
)

# bip_id jednostki z linku oferty (do powiązania z units.json).
BIP_ID_RE = re.compile(r"bip_id=(\d+)")


def strip_tags(text: str) -> str:
    """Usuwa znaczniki HTML i normalizuje białe znaki.

    Args:
        text: fragment HTML.

    Returns:
        Czysty tekst.
    """
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def split_sections(html: str) -> List[Tuple[str, str]]:
    """Dzieli stronę globalną na sekcje (status, fragment HTML).

    Args:
        html: pełny HTML strony globalnej.

    Returns:
        Listę krotek (kod statusu, fragment HTML sekcji).
    """
    # Znajdujemy pozycje nagłówków sekcji i cniemy HTML między nimi.
    positions: List[Tuple[int, str]] = []
    for header, status in SECTION_STATUS.items():
        index = html.find(header)
        if index >= 0:
            positions.append((index, status))
    positions.sort()

    sections: List[Tuple[str, str]] = []
    for order, (start, status) in enumerate(positions):
        end = positions[order + 1][0] if order + 1 < len(positions) else len(html)
        sections.append((status, html[start:end]))
    return sections


def parse_global_offers(html: str) -> List[Dict[str, object]]:
    """Parsuje wszystkie oferty z globalnej listy naborów.

    Args:
        html: HTML strony globalnej.

    Returns:
        Listę ofert: {nab_id, status, title, unit_name_raw, unit_bip_id,
        detail_url, ref_number, deadline, raw_text}.
    """
    offers: List[Dict[str, object]] = []
    for status, segment in split_sections(html):
        for match in OFFER_RE.finditer(segment):
            href, nab_id, title_html, unit_html, note_html = match.groups()
            title = strip_tags(title_html)
            unit_name = strip_tags(unit_html)
            note = strip_tags(note_html)

            ref_match = REF_RE.search(note)
            deadline_match = DEADLINE_RE.search(note)
            bip_match = BIP_ID_RE.search(href)

            offers.append({
                "nab_id": nab_id,
                "status": status,
                "title": title,
                "unit_name_raw": unit_name,
                "unit_bip_id": bip_match.group(1) if bip_match else None,
                "detail_url": urljoin(bc.BASE_URL, href.replace("&amp;", "&")),
                "ref_number": ref_match.group(1).strip() if ref_match else None,
                "deadline": deadline_match.group(1) if deadline_match else None,
                "raw_text": f"{title} {unit_name} ({note})",
            })
    return offers


def resolve_unit_key(offer: Dict[str, object],
                     units: Dict[str, dict]) -> Optional[str]:
    """Dopasowuje ofertę do klucza jednostki z units.json.

    Oferta w liście globalnej ma ``bip_id`` jednostki w linku, a jej nazwa
    zawiera zwykle skrót w nawiasie, np. "Zarząd Dróg Miasta Krakowa (ZDMK)".
    Jednostki w naszym datasecie mają klucz ``bip_id:N`` **albo** ``slug:XXX``
    (gdy na liście jednostek były linkowane "ładnym" slugiem — wtedy numeru
    bip_id nie znamy, bo slug go nie ujawnia).

    Dopasowanie próbujemy w trzech krokach, od najpewniejszego:
    1. klucz ``bip_id:N`` wprost,
    2. rekord jednostki z zapisanym polem ``bip_id`` równym temu z oferty,
    3. **skrót z nawiasu w nazwie** porównany ze slugiem jednostki
       (slugi BIP to właśnie te skróty: ZDMK, DPSN, MHK...),
    4. zapasowo: porównanie znormalizowanych nazw jednostki.

    Args:
        offer: oferta z globalnej listy.
        units: rekordy jednostek z units.json.

    Returns:
        Klucz jednostki albo None, gdy nie udało się dopasować.
    """
    bip_id = offer.get("unit_bip_id")

    # 1) Bezpośredni klucz "bip_id:N".
    if bip_id:
        direct = f"bip_id:{bip_id}"
        if direct in units:
            return direct
        # 2) Jednostka zapisana pod slugiem, ale z polem bip_id (gdy znane).
        for key, record in units.items():
            if str(record.get("bip_id") or "") == str(bip_id):
                return key

    unit_name = str(offer.get("unit_name_raw") or "")

    # 3) Skrót w nawiasie == slug jednostki (np. "... (ZDMK)" -> slug:ZDMK).
    abbrev_match = re.search(r"\(([A-ZĄĆĘŁŃÓŚŹŻ0-9_\-]{2,12})\)\s*$",
                             unit_name)
    if abbrev_match:
        slug_key = f"slug:{abbrev_match.group(1)}"
        if slug_key in units:
            return slug_key

    # 4) Zapasowo: porównanie nazw (bez wielkości liter, bez skrótu i spacji).
    def normalize(text: str) -> str:
        """Normalizuje nazwę jednostki do porównania."""
        without_abbrev = re.sub(r"\s*\([^)]*\)\s*$", "", text)
        return re.sub(r"\s+", " ", without_abbrev).strip().lower()

    target = normalize(unit_name)
    if target:
        for key, record in units.items():
            if normalize(str(record.get("name") or "")) == target:
                return key

    return None


def main() -> int:
    """Punkt wejścia skryptu 3b.

    Returns:
        0 przy sukcesie, 1 przy błędzie pobrania.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera oferty z globalnej listy naborów BIP.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    logging.info("Pobieram globalną listę naborów: %s", GLOBAL_NABORY_URL)
    html = bc.fetch(session, GLOBAL_NABORY_URL)
    if html is None:
        logging.error("Nie udało się pobrać globalnej listy naborów.")
        bc.record_failure(
            stage="3b_global",
            key="GLOBAL_NABORY",
            url=GLOBAL_NABORY_URL,
            reason="fetch_failed",
        )
        return 1

    offers = parse_global_offers(html)
    logging.info("Sparsowano ofert: %d", len(offers))

    units_ds = bc.load_dataset(bc.UNITS_DATASET)
    units = units_ds.get("records", {})

    dataset = bc.load_dataset(bc.OFFERS_DATASET)
    records = dataset["records"]
    seen_now = bc.now_iso()

    seen_keys: List[str] = []
    unmatched = 0

    for offer in offers:
        unit_key = resolve_unit_key(offer, units)
        if unit_key is None:
            unmatched += 1
            # Notujemy brak dopasowania jednostki — to sygnał, że lista
            # jednostek jest nieaktualna (np. nowa jednostka w BIP).
            bc.record_failure(
                stage="3b_global",
                key=f"nab:{offer['nab_id']}",
                url=str(offer.get("detail_url")),
                reason="unit_not_matched",
                detail=f"bip_id={offer.get('unit_bip_id')} "
                       f"unit={offer.get('unit_name_raw')}",
            )

        unit_record = units.get(unit_key or "", {})
        key = f"nab:{offer['nab_id']}"
        fields = {
            "nab_id": offer["nab_id"],
            "unit_key": unit_key,
            # Nazwa jednostki: preferujemy naszą z units.json (spójna),
            # a gdy brak dopasowania — nazwę z listy globalnej.
            "unit_name": unit_record.get("name") or offer["unit_name_raw"],
            "praca_url": GLOBAL_NABORY_URL,
            "status": offer["status"],
            "title": offer["title"],
            "detail_url": offer["detail_url"],
            "ref_number": offer["ref_number"],
            "deadline": offer["deadline"],
            "raw_text": offer["raw_text"],
            "source": "bip_global",
        }
        bc.upsert_record(records, key=key, fields=fields, seen_now=seen_now)
        seen_keys.append(key)

    # Deaktywujemy tylko oferty pochodzące z tego samego źródła, których
    # w tym przebiegu nie widzieliśmy (nie ruszamy ofert z innych źródeł).
    global_keys = {
        key for key, rec in records.items()
        if rec.get("source") == "bip_global"
    }
    deactivated = bc.deactivate_missing(
        {k: records[k] for k in global_keys}, seen_keys, seen_now,
    )

    bc.save_snapshot("offers_global", {
        "fetched_at": seen_now,
        "url": GLOBAL_NABORY_URL,
        "count": len(offers),
        "offers": offers,
    })
    bc.save_dataset(bc.OFFERS_DATASET, dataset)

    active_trwajace = sum(
        1 for r in records.values()
        if r.get("active") and r.get("status") == "trwajacy"
    )
    logging.info(
        "Gotowe. Ofert: %d (bez dopasowanej jednostki: %d), aktywnych "
        "trwających: %d, świeżo wygaszonych: %d.",
        len(offers), unmatched, active_trwajace, deactivated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
