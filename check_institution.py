#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Narzędzie pomocnicze: sprawdza, czy instytucja ma scrapowalną stronę pracy.

Służy do BADANIA kandydatów przed dodaniem ich do
``src_kultura_instytucje.INSTITUTIONS``. Zasada: nie dodajemy źródła, dopóki
nie wiemy, że ma realne oferty i da się je odczytać bez obchodzenia blokad.

Dla każdej instytucji próbuje typowych adresów podstron z pracą
(``/praca``, ``/kariera``, ``/oferty-pracy``, ``/praca-w-...`` itd.),
a następnie ocenia, czy strona wygląda na listę ofert: liczy trafienia
parsera z ``src_kultura_instytucje`` oraz wykrywa komunikaty typu
„brak ofert”.

Uruchomienie:

    python check_institution.py            # sprawdza listę kandydatów
    python check_institution.py URL...     # sprawdza podane adresy
"""

from __future__ import annotations

import argparse
from typing import List, Tuple
from urllib.parse import urljoin

import bip_common as bc
from src_kultura_instytucje import parse_institution_page

# Typowe ścieżki podstron z ofertami pracy na stronach instytucji.
CANDIDATE_PATHS: Tuple[str, ...] = (
    "/praca", "/kariera", "/oferty-pracy", "/praca/oferty-pracy",
    "/o-nas/praca", "/o-muzeum/praca", "/dla-mediow/praca",
    "/bip/praca", "/bip/oferty-pracy", "/nabory", "/ogloszenia/praca",
    "/pl/praca", "/praca-w-muzeum", "/rekrutacja",
)

# Kandydaci do sprawdzenia: (nazwa, adres główny).
# Instytucje kultury i sztuki w Krakowie i okolicy, których nie obejmuje
# BIP Miasta Krakowa (szczebel narodowy, wojewódzki, uczelnie, fundacje).
CANDIDATES: List[Tuple[str, str]] = [
    ("Zamek Królewski na Wawelu", "https://wawel.krakow.pl"),
    ("Muzeum Sztuki i Techniki Japońskiej Manggha", "https://manggha.pl"),
    ("Muzeum Etnograficzne w Krakowie", "https://etnomuzeum.eu"),
    ("Muzeum Archeologiczne w Krakowie", "https://www.ma.krakow.pl"),
    ("Międzynarodowe Centrum Kultury", "https://mck.krakow.pl"),
    ("Muzeum Lotnictwa Polskiego", "https://muzeumlotnictwa.pl"),
    ("Muzeum Żup Krakowskich Wieliczka", "https://muzeum.wieliczka.pl"),
    ("Opera Krakowska", "https://opera.krakow.pl"),
    ("Filharmonia im. K. Szymanowskiego w Krakowie",
     "https://filharmonia.krakow.pl"),
    ("Narodowy Stary Teatr im. H. Modrzejewskiej", "https://stary.pl"),
    ("Akademia Sztuk Pięknych im. J. Matejki", "https://www.asp.krakow.pl"),
    ("Europejskie Centrum Muzyki K. Pendereckiego",
     "https://penderecki-center.pl"),
    ("Muzeum Auschwitz-Birkenau", "https://www.auschwitz.org"),
    ("Instytut Książki", "https://instytutksiazki.pl"),
    ("Muzeum Fotografii w Krakowie", "https://mufo.krakow.pl"),
]

# Komunikaty świadczące o braku aktualnych ofert.
EMPTY_MARKERS = (
    "brak aktualnych", "brak ofert", "nie prowadzimy",
    "obecnie nie poszukujemy", "nie poszukujemy obecnie",
    "brak otwartych", "aktualnie nie prowadzimy",
)


def check_url(session, url: str) -> Tuple[bool, int, str]:
    """Sprawdza jeden adres pod kątem obecności listy ofert pracy.

    Args:
        session: sesja HTTP.
        url: adres do sprawdzenia.

    Returns:
        Krotkę (czy pobrano, liczba trafień parsera, uwaga tekstowa).
    """
    html, reason = bc.fetch_with_reason(session, url)
    if html is None:
        return False, 0, str(reason)

    offers = parse_institution_page(html, url)
    lowered = html.lower()
    empty = any(marker in lowered for marker in EMPTY_MARKERS)
    note = "komunikat o braku ofert" if empty else ""
    return True, len(offers), note


def main() -> int:
    """Punkt wejścia narzędzia badawczego.

    Returns:
        0 zawsze (to narzędzie diagnostyczne, nie etap potoku).
    """
    parser = argparse.ArgumentParser(
        description="Sprawdza, czy instytucja ma scrapowalną stronę pracy.",
    )
    parser.add_argument("urls", nargs="*",
                        help="Adresy do sprawdzenia (zamiast listy).")
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    session = bc.build_session()

    if args.urls:
        targets = [(url, url) for url in args.urls]
        paths: Tuple[str, ...] = ("",)
    else:
        targets = CANDIDATES
        paths = CANDIDATE_PATHS

    print(f"{'instytucja':46s} {'ofert':>5s}  adres / uwaga")
    print("-" * 100)

    for name, base in targets:
        best: Tuple[int, str, str] = (0, "", "nie znaleziono strony pracy")
        for path in paths:
            url = urljoin(base, path) if path else base
            ok, count, note = check_url(session, url)
            if not ok:
                continue
            if count > best[0] or (count == best[0] and not best[1]):
                best = (count, url, note or "")
            if count > 0:
                break  # mamy trafienia — wystarczy

        count, url, note = best
        mark = "OK " if count > 0 else ("-- " if url else "!! ")
        print(f"{mark}{name[:43]:43s} {count:5d}  {url or '-'}")
        if note:
            print(f"{'':49s}  ({note})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
