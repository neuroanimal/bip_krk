#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Źródło: instytucje kultury publikujące nabory na własnych stronach.

DLACZEGO to źródło istnieje — luka w pokryciu BIP Krakowa:

BIP Miasta Krakowa obejmuje wyłącznie **miejskie** jednostki organizacyjne.
Tymczasem w Krakowie działa wiele instytucji kultury szczebla **narodowego
i wojewódzkiego**, których w tym BIP nie ma — a są najbliżej profilu
poszukiwań (muzea, teatry, galerie). Potwierdzone: Muzeum Narodowe
w Krakowie nie występuje w ``units.json``, bo nie jest jednostką miejską.

CO SPRAWDZONO (żeby nie dodawać martwych źródeł):

* ``mnk.pl`` (Muzeum Narodowe) — DZIAŁA: statyczny HTML, bez blokad,
  4 realne nabory, linki w formacie
  „Oferty pracy <data po polsku> <tytuł stanowiska>”.
* ``teatrwkrakowie.pl`` (Teatr im. Słowackiego) — ma sekcję
  „Zamówienia publiczne / Ogłoszenia / Praca”.
* ``bip.malopolska.pl`` (regionalny BIP) — ODRZUCONE: instytucje typu
  Zamek Królewski na Wawelu nie mają tam sekcji pracy (tylko przetargi),
  brak jednolitej struktury naborów.
* własne strony **miejskich** ośrodków kultury — ODRZUCONE jako gorsze od
  BIP: ``ckpodgorza.pl/praca`` pokazuje jako „Aktualne ogłoszenia” ofertę
  z terminem 17.08.2026 (minionym), a BIP ma ją poprawnie jako zakończoną.
* ``pracuj.pl``, ``olx.pl`` — ODRZUCONE: captcha Cloudflare blokuje nawet
  prawdziwą przeglądarkę headless.

Parser jest heurystyczny (każda instytucja ma inny szablon), dlatego:
* bierzemy linki z obszaru treści, o sensownej długości tekstu,
* wymagamy, by tekst linku wyglądał na ofertę pracy (słowa kluczowe
  stanowisk albo data publikacji),
* nieudane pobranie lub zero trafień notujemy w dzienniku niepowodzeń,
  żeby zmiana szablonu strony nie przeszła niezauważona.

Uruchomienie:

    python src_kultura_instytucje.py
    python src_kultura_instytucje.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import bip_common as bc

# Lista instytucji: (klucz, nazwa, adres strony z ofertami).
# Dodanie nowej instytucji = jedna linia tutaj. Zalecenie: najpierw ręcznie
# sprawdzić, czy strona ma realne oferty (patrz docstring modułu).
INSTITUTIONS: List[Tuple[str, str, str]] = [
    ("mnk", "Muzeum Narodowe w Krakowie",
     "https://mnk.pl/o-muzeum/praca/oferty-pracy/"),
    ("slowacki", "Teatr im. Juliusza Słowackiego w Krakowie",
     "https://teatrwkrakowie.pl/praca"),
    ("cricoteka", "Ośrodek Dokumentacji Sztuki Tadeusza Kantora Cricoteka",
     "https://cricoteka.pl/praca"),
]

# Słowa wskazujące, że tekst linku to oferta pracy (a nie np. wystawa).
JOB_HINTS: Tuple[str, ...] = (
    "nabór", "nabor", "oferta pracy", "oferty pracy", "stanowisko",
    "poszukujemy", "zatrudnimy", "rekrutacj", "konkurs na stanowisko",
    "specjalista", "asystent", "instruktor", "kustosz", "kurator",
    "pracownik", "koordynator", "referent", "inspektor", "grafik",
    "edukator", "animator", "konserwator", "kasjer", "opiekun",
)

# Data po polsku, np. "29 września 2026" — częsta na stronach instytucji.
PL_MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5,
    "czerwca": 6, "lipca": 7, "sierpnia": 8, "września": 9,
    "października": 10, "listopada": 11, "grudnia": 12,
}
PL_DATE_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(PL_MONTHS) + r")\s+(\d{4})", re.IGNORECASE,
)

# Data w formacie liczbowym (zapasowo).
NUM_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})\.(\d{1,2})\.(\d{4})")


def parse_pl_date(text: str) -> Optional[str]:
    """Wyłuskuje datę z tekstu (format polski lub liczbowy) jako ISO.

    Args:
        text: tekst mogący zawierać datę publikacji.

    Returns:
        Data w formacie 'YYYY-MM-DD' albo None.
    """
    match = PL_DATE_RE.search(text)
    if match:
        day = int(match.group(1))
        month = PL_MONTHS[match.group(2).lower()]
        year = int(match.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    match = NUM_DATE_RE.search(text)
    if match:
        if match.group(1):
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return (f"{match.group(6)}-{int(match.group(5)):02d}"
                f"-{int(match.group(4)):02d}")
    return None


def clean_title(text: str) -> str:
    """Oczyszcza tekst linku do postaci tytułu stanowiska.

    Usuwa etykietę rubryki („Oferty pracy”), datę publikacji oraz
    powtarzający się przedrostek „Nabór na stanowisko:”.

    Args:
        text: surowy tekst linku.

    Returns:
        Oczyszczony tytuł oferty.
    """
    result = re.sub(r"\s+", " ", text).strip()
    # Usuń etykietę rubryki na początku.
    result = re.sub(r"^(oferty pracy|oferta pracy|praca|aktualności)\s*",
                    "", result, flags=re.IGNORECASE)
    # Usuń datę (polską i liczbową).
    result = PL_DATE_RE.sub(" ", result)
    result = NUM_DATE_RE.sub(" ", result)
    # Ujednolicenie przedrostka naboru.
    result = re.sub(r"^\s*nabór na\s+stanowisko:?\s*", "", result,
                    flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip(" -–:·|")


def looks_like_job(text: str) -> bool:
    """Ocenia, czy tekst linku wygląda na ofertę pracy.

    Args:
        text: tekst linku.

    Returns:
        True, gdy tekst zawiera słowo wskazujące na ofertę pracy.
    """
    lowered = text.lower()
    return any(hint in lowered for hint in JOB_HINTS)


def parse_institution_page(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Parsuje stronę instytucji, wyciągając oferty pracy.

    Parser jest heurystyczny — instytucje mają różne szablony. Bierzemy
    linki z tej samej domeny, o tekście długości 10-200 znaków, które
    wyglądają na ofertę pracy (słowo kluczowe) i nie są nawigacją.

    Args:
        html: treść HTML strony z ofertami.
        page_url: adres strony (do rozwijania linków i filtru domeny).

    Returns:
        Listę ofert: {title, detail_url, published}.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Usuwamy nawigację, stopkę i menu — tam są linki nie będące ofertami.
    for tag in soup(["nav", "footer", "header", "script", "style"]):
        tag.decompose()

    host = urlparse(page_url).netloc
    offers: List[Dict[str, Any]] = []
    seen_urls = set()

    for anchor in soup.find_all("a", href=True):
        # Tytuł: jeśli link opakowuje nagłówek (tak robi np. mnk.pl, gdzie
        # cały kafelek z opisem jest klikalny i tekst linku ma 600-800
        # znaków), bierzemy TEKST NAGŁÓWKA — zawiera samą nazwę stanowiska.
        heading = anchor.find(["h1", "h2", "h3", "h4"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        raw_text = anchor.get_text(" ", strip=True)
        if not raw_text:
            continue

        # Do oceny „czy to oferta” używamy nagłówka, gdy jest, bo jest
        # precyzyjniejszy; w przeciwnym razie całego tekstu linku.
        candidate = heading_text or raw_text
        # Odrzucamy skrajnie krótkie i podejrzanie długie teksty bez nagłówka
        # (te drugie to zwykle całe akapity nawigacyjne).
        if len(candidate) < 10 or (not heading_text and len(raw_text) > 200):
            continue
        if not looks_like_job(candidate):
            continue

        url = urljoin(page_url, anchor["href"])
        # Tylko linki w obrębie tej samej instytucji.
        if urlparse(url).netloc != host:
            continue
        # Pomijamy link do samej listy ofert.
        if url.rstrip("/") == page_url.rstrip("/") or url in seen_urls:
            continue
        seen_urls.add(url)

        title = clean_title(candidate)
        if len(title) < 5:
            continue

        offers.append({
            "title": title,
            "detail_url": url,
            # Datę szukamy w pełnym tekście linku (bywa obok nagłówka).
            "published": parse_pl_date(raw_text),
        })

    return offers


def normalize_offer(offer: Dict[str, Any], inst_key: str,
                    inst_name: str, page_url: str) -> Dict[str, Any]:
    """Przekształca ofertę instytucji na wspólny format rekordu.

    Args:
        offer: oferta sparsowana ze strony.
        inst_key: klucz instytucji (np. 'mnk').
        inst_name: pełna nazwa instytucji.
        page_url: adres strony z ofertami.

    Returns:
        Rekord w formacie wspólnym (zgodnym z ofertami BIP).
    """
    # Identyfikator z adresu szczegółów (ostatni segment ścieżki).
    slug = urlparse(offer["detail_url"]).path.rstrip("/").split("/")[-1]
    return {
        "nab_id": f"kult-{inst_key}-{slug[:60]}",
        "unit_key": None,
        "unit_name": inst_name,
        "praca_url": page_url,
        "status": "trwajacy",
        "title": offer["title"],
        "detail_url": offer["detail_url"],
        "ref_number": None,
        # Instytucje rzadko podają termin w liście — zostaje data publikacji.
        "deadline": None,
        "published": offer.get("published"),
        "raw_text": offer["title"],
        "source": "kultura_instytucje",
        # Podpowiedź kategorii — to z definicji instytucje kultury.
        "category_hint": "Instytucje kultury (poza BIP miasta)",
    }


def main() -> int:
    """Punkt wejścia źródła instytucji kultury.

    Returns:
        0 przy sukcesie (także gdy część instytucji zawiodła), 1 gdy żadnej
        nie udało się pobrać.
    """
    parser = argparse.ArgumentParser(
        description="Pobiera nabory ze stron instytucji kultury.",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()
    session = bc.build_session()

    dataset = bc.load_dataset(bc.OFFERS_DATASET)
    records = dataset["records"]
    seen_now = bc.now_iso()
    seen_keys: List[str] = []

    snapshot: List[Dict[str, Any]] = []
    ok_count = 0

    for inst_key, inst_name, page_url in INSTITUTIONS:
        logging.info("=== %s ===", inst_name)
        html, reason = bc.fetch_with_reason(session, page_url)
        if html is None:
            bc.record_failure(stage="src_kultura", key=inst_key,
                              url=page_url, reason=reason or "fetch_failed",
                              detail=inst_name)
            continue
        ok_count += 1

        offers = parse_institution_page(html, page_url)
        logging.info("  znalezionych ofert: %d", len(offers))
        if not offers:
            # Brak ofert może być stanem faktycznym, ale równie dobrze
            # oznacza zmianę szablonu strony — notujemy, by to wychwycić.
            bc.record_failure(stage="src_kultura", key=inst_key,
                              url=page_url, reason="no_offers_parsed",
                              detail=f"{inst_name} — zero trafień parsera")
        else:
            bc.clear_failure("src_kultura", inst_key, "no_offers_parsed")

        for offer in offers:
            normalized = normalize_offer(offer, inst_key, inst_name, page_url)
            key = str(normalized["nab_id"])
            bc.upsert_record(records, key=key, fields=normalized,
                             seen_now=seen_now)
            seen_keys.append(key)
            logging.info("   • %s", offer["title"][:70])

        snapshot.append({
            "institution": inst_name,
            "url": page_url,
            "offers": offers,
        })

    if ok_count == 0:
        logging.error("Nie udało się pobrać żadnej instytucji.")
        return 1

    # Deaktywujemy tylko rekordy z tego źródła, których już nie widać.
    own_keys = {
        key for key, rec in records.items()
        if rec.get("source") == "kultura_instytucje"
    }
    deactivated = bc.deactivate_missing(
        {k: records[k] for k in own_keys}, seen_keys, seen_now,
    )

    bc.save_snapshot("src_kultura_instytucje", {
        "fetched_at": seen_now,
        "institutions": snapshot,
    })
    bc.save_dataset(bc.OFFERS_DATASET, dataset)

    logging.info(
        "Gotowe. Instytucji pobranych: %d/%d, ofert zapisanych: %d, "
        "świeżo wygaszonych: %d.",
        ok_count, len(INSTITUTIONS), len(seen_keys), deactivated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
