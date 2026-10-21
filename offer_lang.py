#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rozpoznawanie JĘZYKA ogłoszenia — polski czy obcy.

PO CO
-----
Adresatka prosiła, żeby domyślnie brać pod uwagę **tylko ogłoszenia
polskie**, a angielskie móc włączyć osobnym przełącznikiem. Źródła
mieszają jedno z drugim: nofluffjobs i arc.dev publikują po angielsku,
BIP i CBOP po polsku, a pracujwkulturze bywa dwujęzyczny.

Żadne ze źródeł nie podaje języka w danych (jedynym wyjątkiem jest EURES,
którego nie używamy), więc rozpoznajemy go z treści.

JAK
---
Trzy sygnały, w tej kolejności:

1. **polskie znaki diakrytyczne** (ą, ć, ę, ł, ń, ó, ś, ź, ż) — jeśli są,
   to prawie na pewno polski. Pojedynczy znak nie wystarcza, bo nazwa
   własna („Kraków”) pojawia się też w ogłoszeniach angielskich;
2. **polskie słowa funkcyjne** („oraz”, „praca”, „umowa”, „wymagania”) —
   łapią teksty pisane bez ogonków;
3. **angielskie słowa funkcyjne** („and”, „the”, „experience”,
   „requirements”) — gdy przewyższają polskie, uznajemy ogłoszenie za
   angielskie.

Gdy nic nie przeważa (np. sam tytuł „Data Engineer”), rozstrzyga
pochodzenie ze źródła: portale polskojęzyczne dostają ``pl``, zagraniczne
``en``. To świadomy kompromis — tytuł bez treści nie daje pewności.
"""

from __future__ import annotations

import re
from typing import Tuple

PL = "pl"
EN = "en"

# Etykiety do interfejsu.
LABELS = {PL: "polskie", EN: "angielskie"}
LABELS_EN = {PL: "Polish", EN: "English"}

# Polskie znaki diakrytyczne.
DIACRITICS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")

# Słowa funkcyjne — krótkie, częste, rzadko występujące w drugim języku.
PL_WORDS = re.compile(
    r"\b(oraz|praca|pracy|umowa|umowy|wymagania|obowiązki|stanowisko"
    r"|zakres|oferujemy|poszukujemy|doświadczenie|wykształcenie|lub"
    r"|dla|przez|się|jest|będzie|zgłoszenia|termin|nabór)\b",
    re.IGNORECASE,
)
EN_WORDS = re.compile(
    r"\b(and|the|with|for|experience|requirements|responsibilities"
    r"|we are looking|you will|our team|skills|knowledge|remote|salary"
    r"|benefits|apply|position|role)\b",
    re.IGNORECASE,
)

# Źródła pisane po polsku i po angielsku — rozstrzygają przy remisie.
POLISH_SOURCES: Tuple[str, ...] = (
    "bip_global", "bip_unit", "cbop", "nuzle", "ofertypracy_edu",
    "kultura_instytucje", "pracujwkulturze", "bulldogjob",
)
ENGLISH_SOURCES: Tuple[str, ...] = ("remote_intl", "arc_dev")


def detect(text: str, source: str = "") -> str:
    """Rozpoznaje język ogłoszenia.

    Args:
        text: tytuł i treść ogłoszenia (im więcej, tym pewniej).
        source: kod źródła — rozstrzyga, gdy treść nie daje odpowiedzi.

    Returns:
        ``"pl"`` albo ``"en"``.
    """
    sample = str(text or "")

    # Dwa lub więcej znaków diakrytycznych to mocny sygnał. Jeden może być
    # nazwą własną („Kraków”) w tekście angielskim.
    if len(DIACRITICS.findall(sample)) >= 2:
        return PL

    pl_hits = len(PL_WORDS.findall(sample))
    en_hits = len(EN_WORDS.findall(sample))
    if pl_hits > en_hits:
        return PL
    if en_hits > pl_hits:
        return EN

    # Remis (zwykle sam tytuł) — rozstrzyga pochodzenie.
    if source in ENGLISH_SOURCES:
        return EN
    if source in POLISH_SOURCES:
        return PL
    return PL
