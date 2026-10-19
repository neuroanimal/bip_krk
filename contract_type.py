#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rozpoznawanie RODZAJU UMOWY — wspólne dla wszystkich źródeł.

PO CO ODDZIELNY MODUŁ
---------------------
Rodzaj umowy jest jednym z najważniejszych kryteriów wyboru oferty
(„budżetówka na UoP” to inna decyzja niż „kontrakt B2B”), a każde źródło
podaje go inaczej — albo wcale:

======================  ============================================
``cbop``                pole ``rodzajUmowy`` z polską nazwą, np.
                        „Umowa o pracę na okres próbny”
``nofluffjobs``         ``salary.type``: ``b2b`` albo ``permanent``
``bulldogjob``          trzy flagi: ``contractEmployment``,
                        ``contractB2b``, ``contractOther``
``arc_dev``             ``jobType``: ``contract`` / ``full-time``
``bip_global``, BIP     brak pola — trzeba czytać z treści ogłoszenia
``remote_intl``         brak pola (zagraniczne, zwykle kontrakt)
======================  ============================================

Dlatego jedna funkcja :func:`classify` rozstrzyga po tekście, a źródła,
które WIEDZĄ, zapisują wynik wprost w rekordzie (pole ``contract_types``)
i wtedy klasyfikator nie jest potrzebny.

KATEGORIE — osobno, nie łącznie
-------------------------------
Rozdzielamy **UoP**, **UZ** i **B2B**, bo to trzy różne sytuacje prawne
i finansowe (staż pracy, ZUS, urlop, zdolność kredytowa). Oferta może
dopuszczać kilka form naraz — dlatego wynikiem jest ZBIÓR, a nie jedna
wartość; bulldogjob regularnie podaje „UoP albo B2B”.

Umowa o dzieło jest osobno (``DZIELO``), bo w ogłoszeniach kulturalnych
pojawia się realnie — przy warsztatach i pojedynczych realizacjach.
"""

from __future__ import annotations

import re
from typing import Dict, List, Sequence, Set

UOP = "uop"
UZ = "uz"
B2B = "b2b"
DZIELO = "dzielo"
UNKNOWN = "nieznana"

# Etykiety do odznak w raporcie i do filtra.
LABELS: Dict[str, str] = {
    UOP: "UoP",
    UZ: "UZ",
    B2B: "B2B",
    DZIELO: "dzieło",
    UNKNOWN: "umowa nieznana",
}

# Pełne opisy — do tytułu (atrybut ``title``) odznaki.
DESCRIPTIONS: Dict[str, str] = {
    UOP: "Umowa o pracę",
    UZ: "Umowa zlecenie",
    B2B: "B2B (własna działalność lub przez pośrednika)",
    DZIELO: "Umowa o dzieło",
    UNKNOWN: "Rodzaj umowy nie podany w ogłoszeniu",
}

# Kolejność wyświetlania — od najstabilniejszej formy.
ORDER: Sequence[str] = (UOP, UZ, DZIELO, B2B, UNKNOWN)

# Wzorce rozpoznawania. Uwaga na kolejność sprawdzania: „umowa o dzieło”
# musi być sprawdzona PRZED „umowa o prac”, bo oba zaczynają się od
# „umowa o ”, a przy luźniejszym wzorcu dzieło wpadałoby jako UoP.
PATTERNS: Sequence[tuple] = (
    (DZIELO, re.compile(
        r"umow\w*\s+o\s+dzieł|umow\w*\s+o\s+dzielo|\bo\s+dzieło\b",
        re.IGNORECASE)),
    (UZ, re.compile(
        r"umow\w*\s+zlecen|umow\w*\s+o\s+zlecen|\bzlecenie\b|\bu[\s-]?z\b"
        r"|mandate contract|civil contract",
        re.IGNORECASE)),
    # Uwaga na polską alternację spółgłoskową: „etat” odmienia się na
    # „etacie”, więc rdzeń trzeba dopuścić w obu postaciach (eta[tc]).
    # Wzorzec „etat\w*” nie łapał „na etacie”.
    (UOP, re.compile(
        r"umow\w*\s+o\s+prac|\bu\s?o\s?p\b|\beta[tc]\w*|employment contract"
        r"|\bpermanent\b|full[\s-]?time employment",
        re.IGNORECASE)),
    (B2B, re.compile(
        r"\bb2b\b|kontrakt\w*\s+b2b|samozatrudnien|własn\w*\s+działalnoś"
        r"|\bjdg\b|faktur\w*\s+za\s+usług|freelance|\bcontract(?:or)?\b"
        r"|independent contractor",
        re.IGNORECASE)),
)


def classify(*texts: str) -> List[str]:
    """Rozpoznaje możliwe rodzaje umowy w podanych tekstach.

    Args:
        *texts: dowolne fragmenty (tytuł, opis, nazwa jednostki,
            ``rodzajUmowy`` ze źródła).

    Returns:
        Listę kodów rodzajów umowy w kolejności z :data:`ORDER`;
        ``[UNKNOWN]``, gdy nic nie rozpoznano.
    """
    haystack = " ".join(t for t in texts if t)
    if not haystack.strip():
        return [UNKNOWN]

    found: Set[str] = set()
    for code, pattern in PATTERNS:
        if pattern.search(haystack):
            found.add(code)

    if not found:
        return [UNKNOWN]
    return [code for code in ORDER if code in found]


def from_flags(uop: bool = False, uz: bool = False,
               b2b: bool = False) -> List[str]:
    """Składa listę rodzajów umowy ze znanych flag źródła.

    Używane tam, gdzie portal podaje gotowe pola logiczne (bulldogjob),
    więc nie trzeba niczego zgadywać z tekstu.

    Args:
        uop: umowa o pracę dopuszczalna.
        uz: umowa zlecenie dopuszczalna.
        b2b: kontrakt B2B dopuszczalny.

    Returns:
        Listę kodów; ``[UNKNOWN]``, gdy żadna flaga nie jest ustawiona.

    Note:
        Celowo NIE ma parametru dla flagi „inna forma” (bulldogjob
        ``contractOther``): nie da się jej przypisać do UoP/UZ/B2B, więc
        wynik byłby i tak ``UNKNOWN``. Wywołujący po prostu jej nie podaje.
    """
    found = set()
    if uop:
        found.add(UOP)
    if uz:
        found.add(UZ)
    if b2b:
        found.add(B2B)
    result = [code for code in ORDER if code in found]
    return result or [UNKNOWN]


def label(codes: Sequence[str]) -> str:
    """Zwraca czytelną etykietę zbioru rodzajów umowy.

    Args:
        codes: lista kodów.

    Returns:
        Etykietę typu ``„UoP / B2B”`` albo ``„umowa nieznana”``.
    """
    if not codes:
        return LABELS[UNKNOWN]
    return " / ".join(LABELS.get(code, code) for code in codes)
