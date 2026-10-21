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
import unicodedata
from types import ModuleType
from typing import Dict, List, Tuple

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

# Pamięć podręczna wzorców po złożeniu znaków (patrz :func:`_fold`),
# kluczowana identyfikatorem modułu profilu — składamy raz, nie przy
# każdej ofercie.
_FOLDED: Dict[int, Dict[str, object]] = {}

# Ile liter może kontynuować frazę pracodawcy, żeby nadal uznać ją za to
# samo słowo w innym przypadku („teatr” → „teatru”, „teatrze”), a nie za
# inne słowo („teatr” → „teatralny”). Patrz :func:`_employer_matches`.
EMPLOYER_SUFFIX_MAX = 3


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
    for phrase in _folded_profile()["noise"]:
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
        if any(word in context for word in _folded_profile()["schedule"]):
            result = result[:match.start()] + " " + result[match.end():]
    return result


def _fold(text: str) -> str:
    """Sprowadza tekst do postaci porównywalnej: małe litery, bez ogonków.

    DLACZEGO SKŁADANIE ZNAKÓW
    -------------------------
    Wcześniej każdy wzorzec był pisany podwójnie („świetlic” i „swietlic”,
    „pływani” i „plywani”), bo ogłoszenia bywają pisane bez polskich
    znaków. To dawało dwa problemy: listy puchły, a i tak zdarzały się
    luki, gdy ktoś zapomniał drugiej wersji. Składamy więc OBIE strony —
    tekst ogłoszenia i wzorce — do tej samej postaci (``ą→a``, ``ł→l``…),
    i jeden wzorzec obsługuje obie pisownie.

    Args:
        text: dowolny tekst.

    Returns:
        Tekst złożony: małe litery, bez znaków diakrytycznych, ze zbitymi
        białymi znakami.
    """
    lowered = (text or "").lower().replace("ł", "l")
    decomposed = unicodedata.normalize("NFKD", lowered)
    stripped = "".join(ch for ch in decomposed
                       if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped)


def _normalize(text: str) -> str:
    """Normalizuje tekst do dopasowywania słów kluczowych.

    Zachowane jako osobna nazwa, bo używają jej inne moduły; od wprowadzenia
    składania znaków to po prostu :func:`_fold`.

    Args:
        text: dowolny tekst (tytuł, opis).

    Returns:
        Tekst złożony (patrz :func:`_fold`).
    """
    return _fold(text)


def _folded_profile() -> Dict[str, object]:
    """Zwraca wzorce aktywnego profilu po złożeniu znaków (z pamięci).

    Returns:
        Słownik z kluczami odpowiadającymi stałym profilu.
    """
    key = id(_ACTIVE)
    cached = _FOLDED.get(key)
    if cached is not None:
        return cached

    def fold_all(items) -> Tuple[str, ...]:
        """Składa krotkę wzorców i usuwa powtórzenia (zachowując kolejność)."""
        return tuple(dict.fromkeys(_fold(item) for item in items))

    context = getattr(_ACTIVE, "CONTEXT_REQUIRED", {}) or {}
    folded = {
        "keywords": [(label, weight, fold_all(patterns))
                     for label, weight, patterns in _ACTIVE.PROFILE_KEYWORDS],
        "exclude": fold_all(_ACTIVE.EXCLUDE_KEYWORDS),
        "demote": fold_all(_ACTIVE.DEMOTE_KEYWORDS),
        "demote_title": fold_all(getattr(_ACTIVE, "DEMOTE_TITLE_KEYWORDS",
                                         ())),
        "preferred": fold_all(_ACTIVE.PREFERRED_EMPLOYERS),
        "schedule": fold_all(_ACTIVE.SCHEDULE_CONTEXT_WORDS),
        "noise": fold_all(_ACTIVE.INSTITUTION_NOISE),
        "context_stems": fold_all(context.get("stems", ())),
        "context_words": fold_all(context.get("words", ())),
        "weak_words": fold_all(context.get("weak_words", ())),
    }
    _FOLDED[key] = folded
    return folded


def _employer_name(unit_name: str) -> str:
    """Odcina od nazwy jednostki dopiski doklejane przez źródła.

    Źródła składają ``unit_name`` jako „Pracodawca (miasto, region)”,
    „Pracodawca — praca zdalna, otwarte: EMEA [portal]” itd. Do oceny
    pracodawcy potrzebna jest tylko pierwsza część.

    Args:
        unit_name: pełna nazwa jednostki z rekordu.

    Returns:
        Sama nazwa pracodawcy.
    """
    return re.split(r"\s*[\(\[]|\s+[—–]\s+", str(unit_name or ""), maxsplit=1)[0]


def _employer_matches(phrase: str, employer: str) -> bool:
    """Czy fraza preferowanego pracodawcy występuje w nazwie jako SŁOWO.

    Zwykłe zawieranie podłańcucha było błędem: „teatr” pasowało do
    „Dziennik **Teatr**alny”, więc gazeta zatrudniająca recenzentów
    uchodziła za teatr i podbijała ofertę do „DLA CIEBIE”. Fraza musi więc
    zaczynać się na granicy wyrazu i nie może być ciągnięta dalej niż o
    :data:`EMPLOYER_SUFFIX_MAX` litery — to zostawia odmianę („teatru”,
    „teatrze”), a odcina słowa pochodne („teatralny”).

    Args:
        phrase: złożona fraza z listy preferowanych pracodawców.
        employer: złożona nazwa pracodawcy.

    Returns:
        True, gdy fraza występuje jako (odmienione) słowo.
    """
    pattern = (rf"(?<![a-z0-9]){re.escape(phrase)}"
               rf"(?![a-z]{{{EMPLOYER_SUFFIX_MAX + 1},}})")
    return re.search(pattern, employer) is not None


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

    folded = _folded_profile()
    # Do rozpoznania pracodawcy bierzemy SAMĄ nazwę — bez dopisków,
    # które źródła doklejają w nawiasie albo po myślniku (miasto, zasięg,
    # rodzaj umowy, portal). Błąd, który to wymusił: jednostka „Dziennik
    # Teatralny (Wszystkie miejscowości, w których znajduje się teatr…)”
    # pasowała do „teatr” właśnie przez dopisek lokalizacji.
    employer_norm = _normalize(_employer_name(unit_name))
    context_text = f"{title_norm} {employer_norm}"
    generic = folded["context_stems"]
    has_context = any(w in context_text for w in folded["context_words"])
    weak_context = any(w in context_text for w in folded["weak_words"])

    score = 0
    tags: List[str] = []
    core_in_title = False
    core_anywhere = False
    capped_weak = False

    for label, weight, patterns in folded["keywords"]:
        hits_title = [p for p in patterns if p in title_norm]
        hits_body = [p for p in patterns if p in body_norm]
        if hits_title:
            score += weight * 2
        elif hits_body:
            score += weight
        if not (hits_title or hits_body):
            continue
        tags.append(label)
        if label not in _ACTIVE.CORE_AREAS:
            continue

        # Trafienie WYŁĄCZNIE ogólnym rdzeniem („instruktor”, „warsztat”)
        # kwalifikuje tylko w kontekście kulturalnym — patrz
        # ``CONTEXT_REQUIRED`` w definicji profilu. Bez kontekstu zostaje
        # sygnałem wspierającym: podbija wynik, ale nie kwalifikuje.
        only_generic = all(any(g in p for g in generic)
                           for p in hits_title + hits_body) if generic else False
        if only_generic and not has_context:
            if weak_context:
                capped_weak = True
            else:
                continue
        core_anywhere = True
        if hits_title:
            core_in_title = True

    # Wykluczenia liczymy tylko z tytułu — w opisie mogą pojawiać się
    # przypadkowo (np. „współpraca z księgowością” w ofercie dla animatora).
    excluded = any(pattern in title_for_exclude
                   for pattern in folded["exclude"])
    if excluded:
        score -= 10

    # Degradacja: oferta jest wiarygodna, ale wymaga odrębnych kwalifikacji.
    # Nie usuwamy jej — tylko nie pozwalamy jej nosić odznaki „DLA CIEBIE”
    # na równi z ofertą wprost z profilu.
    demoted = (capped_weak
               or any(pattern in title_norm or pattern in body_norm
                      for pattern in folded["demote"])
               or any(pattern in title_for_exclude
                      for pattern in folded["demote_title"]))

    # Kwalifikacja: musi być trafienie w obszarze RDZENIOWYM. Trafienie
    # wyłącznie w obszarze wspierającym (np. samo „SQL” w wymaganiach albo
    # sama nazwa „muzeum” w opisie) nie czyni oferty dopasowaną.
    preferred = any(_employer_matches(name, employer_norm)
                    for name in folded["preferred"])
    if excluded or not core_anywhere or score < _ACTIVE.SCORE_WEAK:
        level = "none"
    elif (score >= _ACTIVE.SCORE_STRONG and not demoted
          and (core_in_title or preferred)):
        # Mocne dopasowanie wymaga trafienia rdzeniowego w TYTULE — to
        # odróżnia „GRAFIK/GRAFICZKA” od oferty, która tylko wspomina
        # projektowanie w opisie obowiązków. Wyjątkiem jest pracodawca
        # z PREFERRED_EMPLOYERS (np. ASP w profilu kultury), dopasowany
        # jako SŁOWO — patrz :func:`_employer_matches`.
        level = "strong"
    else:
        level = "weak"

    return {
        "profile_score": score,
        "profile_tags": tags,
        "profile_level": level,
        "profile_excluded": excluded,
    }
