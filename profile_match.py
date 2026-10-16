#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ocena dopasowania oferty do PROFILU zawodowego.

Moduł zawiera wyłącznie LOGIKĘ oceniania. Definicje „co pasuje do kogo”
(słowa kluczowe, obszary rdzeniowe, wykluczenia, progi) są w pakiecie
``profiles`` — po jednym module na profil. Profil wybiera się raz, na
starcie etapu, przez :func:`set_profile`; domyślny to ``profiles.DEFAULT``
(kultura), więc wywołania bez wyboru działają jak wcześniej.

DLACZEGO TAK
------------
Dwa profile (kultura/sztuka oraz dane/AI) różnią się wyłącznie danymi,
nie mechaniką: oba potrzebują wag, podziału na obszary rdzeniowe
i wspierające, wykluczeń, degradacji i rozstrzygania homonimów. Trzymanie
logiki w jednym miejscu znaczy, że poprawka (jak kontekstowe rozpoznanie
homonimu) działa od razu dla każdego profilu.

MECHANIZMY, KTÓRE TU ŻYJĄ — każdy powstał z konkretnego błędu
-------------------------------------------------------------
* **trafienie w tytule waży podwójnie** — tytuł opisuje stanowisko
  lepiej niż opis obowiązków;
* **wymóg trafienia RDZENIOWEGO** — bez niego dopasowań było 96 zamiast
  27, bo samo słowo „muzeum” w opisie kwalifikowało ofertę;
* **homonim kontekstowy** — „grafik” to zawód albo harmonogram; lista
  fraz zawiodła (łapała „Tancerkę w klubie”, bo w opisie było
  „decydować o swoim grafiku”), więc rozstrzyga okno ±45 znaków;
* **szum nazwy placówki** — „Poradnia Psychologiczno-**Pedagogiczna**”
  dawała trafienia dla „LEKARZ PSYCHIATRA” i „Referent”;
* **degradacja** — „Instruktor terapii zajęciowej” to realna praca dla
  osoby prowadzącej zajęcia plastyczne, ale wymaga kursu terapii, więc
  nie może nosić odznaki „DLA CIEBIE” obok oferty z ASP;
* **preferowani pracodawcy** — oferta ASP miała tytuł „Asystent w grupie
  pracowników badawczo-dydaktycznych”, bez ani jednego słowa z profilu,
  a była najlepszym trafieniem w całym raporcie.
"""

from __future__ import annotations

import re
from types import ModuleType
from typing import Dict, List

import profiles

# Ile znaków wokół homonimu sprawdzamy w poszukiwaniu kontekstu.
# „Grafik” w „elastyczny grafik pracy” i „GRAFIK/GRAFICZKA” różni się
# wyłącznie otoczeniem, nie samym słowem.
SCHEDULE_CONTEXT_WINDOW = 45

# Rdzenie, dla których w ogóle sprawdzamy kontekst homonimu — zależne od
# profilu, dlatego trzymane obok jego definicji byłoby nadmiarem; tu
# wystarczy jedna lista rdzeni wieloznacznych spotykanych w obu profilach.
HOMONYM_STEMS = ("grafik", "analityk")

# Aktualnie wybrany profil (moduł z pakietu ``profiles``).
_ACTIVE: ModuleType = profiles.get(profiles.DEFAULT)


def set_profile(slug: str) -> ModuleType:
    """Ustawia profil używany przez :func:`score_offer`.

    Args:
        slug: identyfikator profilu (np. ``kultura``, ``it``).

    Returns:
        Moduł wybranego profilu — przydaje się do odczytania ``LABEL``
        i ``DESCRIPTION`` w raporcie.

    Raises:
        KeyError: gdy profil nie istnieje (komunikat zawiera listę
            dostępnych).
    """
    global _ACTIVE  # pylint: disable=global-statement
    _ACTIVE = profiles.get(slug)
    return _ACTIVE


def active_profile() -> ModuleType:
    """Zwraca aktualnie wybrany moduł profilu.

    Returns:
        Moduł profilu.
    """
    return _ACTIVE


def _strip_institution_noise(text: str) -> str:
    """Usuwa nazwy typu placówki, które myliłyby dopasowanie do profilu.

    Args:
        text: znormalizowany tekst (zwykle nazwa jednostki + opis).

    Returns:
        Tekst bez fraz oznaczających typ placówki.
    """
    for phrase in _ACTIVE.INSTITUTION_NOISE:
        text = text.replace(phrase, " ")
    return text


def _strip_homonyms(text: str) -> str:
    """Usuwa wystąpienia wieloznacznych rdzeni użytych w innym znaczeniu.

    Dla każdego wystąpienia rdzenia z :data:`HOMONYM_STEMS` sprawdzamy
    okno :data:`SCHEDULE_CONTEXT_WINDOW` znaków po obu stronach. Jeśli
    pojawia się tam słowo z ``SCHEDULE_CONTEXT_WORDS`` profilu, usuwamy
    to wystąpienie — w tym znaczeniu nie jest to zawód z profilu.

    Przykłady, na których to zbudowano: „elastyczny **grafik** pracy”
    (harmonogram, nie zawód) oraz „**analityk** kredytowy” (inna
    specjalizacja niż analityk danych).

    Args:
        text: znormalizowany tekst (małe litery).

    Returns:
        Tekst z usuniętymi wystąpieniami w niewłaściwym znaczeniu.
    """
    result = text
    joined = "|".join(HOMONYM_STEMS)
    pattern = re.compile(rf"(?:{joined})\w*")
    # Iterujemy od końca, aby podmiany nie psuły pozycji kolejnych trafień.
    for match in reversed(list(pattern.finditer(result))):
        start = max(0, match.start() - SCHEDULE_CONTEXT_WINDOW)
        end = min(len(result), match.end() + SCHEDULE_CONTEXT_WINDOW)
        context = result[start:match.start()] + result[match.end():end]
        if any(word in context for word in _ACTIVE.SCHEDULE_CONTEXT_WORDS):
            result = result[:match.start()] + " " + result[match.end():]
    return result


def _normalize(text: str) -> str:
    """Normalizuje tekst do dopasowywania słów kluczowych.

    Args:
        text: dowolny tekst (tytuł, opis).

    Returns:
        Tekst małymi literami, ze zbitymi białymi znakami.
    """
    return re.sub(r"\s+", " ", (text or "")).lower()


def score_offer(title: str, description: str = "",
                unit_name: str = "") -> Dict[str, object]:
    """Ocenia dopasowanie oferty do aktualnie wybranego profilu.

    Trafienie w TYTULE waży podwójnie względem trafienia w opisie lub
    nazwie jednostki — tytuł najlepiej opisuje stanowisko.

    Args:
        title: tytuł oferty.
        description: treść/opis oferty (opcjonalnie).
        unit_name: nazwa jednostki/pracodawcy (opcjonalnie).

    Returns:
        Słownik: profile_score (int), profile_tags (lista obszarów),
        profile_level ('strong' / 'weak' / 'none'), profile_excluded (bool).
    """
    title_norm = _strip_homonyms(_normalize(title))
    # Tytuł PRZED usunięciem homonimów — potrzebny do wykluczeń.
    #
    # Kolejność ma znaczenie i kosztowała jeden fałszywy wynik: dla
    # „Analityk kredytowy” filtr homonimu usuwał słowo „analityk” (bo
    # w kontekście jest „kredytow”), więc wykluczenie „analityk kredytow”
    # nie miało już czego dopasować i oferta wychodziła jako „może
    # pasować”. Wykluczenia opisują to, co tytuł MÓWI, więc muszą działać
    # na tekście nietkniętym.
    title_for_exclude = _normalize(title)
    body_norm = _strip_institution_noise(
        _strip_homonyms(_normalize(f"{description} {unit_name}"))
    )

    score = 0
    tags: List[str] = []
    core_in_title = False
    core_anywhere = False

    for label, weight, patterns in _ACTIVE.PROFILE_KEYWORDS:
        hit_title = any(pattern in title_norm for pattern in patterns)
        hit_body = any(pattern in body_norm for pattern in patterns)
        if hit_title:
            score += weight * 2
        elif hit_body:
            score += weight
        if hit_title or hit_body:
            tags.append(label)
            if label in _ACTIVE.CORE_AREAS:
                core_anywhere = True
                if hit_title:
                    core_in_title = True

    # Wykluczenia liczymy tylko z tytułu — w opisie mogą pojawiać się
    # przypadkowo (np. „współpraca z księgowością” w ofercie dla animatora).
    excluded = any(pattern in title_for_exclude
                   for pattern in _ACTIVE.EXCLUDE_KEYWORDS)
    if excluded:
        score -= 10

    # Degradacja: oferta jest wiarygodna, ale wymaga odrębnych kwalifikacji.
    # Nie usuwamy jej — tylko nie pozwalamy jej nosić odznaki „DLA CIEBIE”
    # na równi z ofertą wprost z profilu.
    demoted = any(pattern in title_norm or pattern in body_norm
                  for pattern in _ACTIVE.DEMOTE_KEYWORDS)

    # Kwalifikacja: musi być trafienie w obszarze RDZENIOWYM. Trafienie
    # wyłącznie w obszarze wspierającym (np. samo „SQL” w wymaganiach albo
    # sama nazwa „muzeum” w opisie) nie czyni oferty dopasowaną.
    preferred = any(name in _normalize(unit_name)
                    for name in _ACTIVE.PREFERRED_EMPLOYERS)
    if excluded or not core_anywhere or score < _ACTIVE.SCORE_WEAK:
        level = "none"
    elif (score >= _ACTIVE.SCORE_STRONG and not demoted
          and (core_in_title or preferred)):
        # Mocne dopasowanie wymaga trafienia rdzeniowego w TYTULE — to
        # odróżnia „GRAFIK/GRAFICZKA” od oferty, która tylko wspomina
        # projektowanie w opisie obowiązków. Wyjątkiem jest pracodawca
        # z PREFERRED_EMPLOYERS (np. ASP w profilu kultury).
        level = "strong"
    else:
        level = "weak"

    return {
        "profile_score": score,
        "profile_tags": tags,
        "profile_level": level,
        "profile_excluded": excluded,
    }
