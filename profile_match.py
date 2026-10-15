#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dopasowanie ofert do profilu zawodowego — kultura, sztuka, grafika.

Problem, który ten moduł rozwiązuje: w datasecie jest ~435 ofert z BIP plus
oferty z portali zewnętrznych. Wśród nich tonie kilka trafień naprawdę
pasujących do profilu, dlatego z raportu wychodziło wrażenie, że „są głównie
oferty administracyjne i sprzątanie”.

Profil, pod który dopasowujemy (kompetencje):

* malarstwo i techniki malarskie (akwarela), rysunek,
* grafika warsztatowa (druk wypukły/wklęsły, własna prasa graficzna),
* grafika komputerowa, graphic design, DTP,
* animacja kultury, prowadzenie warsztatów dla wszystkich grup wiekowych,
* pedagogika, edukacja (muzealna, kulturalna, plastyczna).

Preferencja: sektor publiczny (instytucje kultury, muzea, domy i ośrodki
kultury, galerie, teatry) — ze względu na stabilność zatrudnienia.

Jak to działa: każda oferta dostaje **wynik dopasowania** (profile_score)
na podstawie trafień słów kluczowych w tytule (waga wyższa) i treści, oraz
listę dopasowanych obszarów (``profile_tags``). Oferty jawnie niepasujące
(sprzątanie, ochrona, kierowca, kucharz itp.) dostają wynik ujemny, aby nie
zaśmiecały sekcji „dla Ciebie”.

Moduł jest czysto obliczeniowy — nie pobiera niczego z sieci.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Grupy słów kluczowych: (etykieta obszaru, waga, wzorce).
# Wzorce dopasowujemy po rdzeniu wyrazu, bez końcówek, aby łapać odmiany
# ("grafik", "grafiki", "graficzny"). Porównanie jest bez wielkości liter.
PROFILE_KEYWORDS: List[Tuple[str, int, Tuple[str, ...]]] = [
    ("grafika / design", 5, (
        "grafik", "graficz", "graphic design", "dtp", "projektant",
        "projektowanie graficzne", "skład komputerowy", "ilustrator",
        "ilustracj", "typograf", "identyfikacj wizualn",
    )),
    ("sztuka / plastyka", 5, (
        "plastyk", "malarstw", "malarsk", "rysunk", "rysunek", "akwarel",
        "artystyczn", "artyst", "sztuk", "rzeźb", "druk artystyczn",
        "grafika warsztatow", "serigraf", "linoryt", "akwafort",
    )),
    ("animacja kultury / warsztaty", 5, (
        "animator kultury", "animacj kultury", "animator", "warsztat",
        "instruktor", "organizator kultur", "organizator/organizatorka",
        "upowszechniani kultury", "działalnoś kulturaln",
    )),
    ("edukacja kulturalna / muzealna", 4, (
        "edukator", "edukacj muzealn", "edukacj kulturaln",
        "edukacj artystyczn", "edukacj plastyczn", "pedagog",
        "asystent muzealn", "asystentka muzealn", "przewodnik muzealn",
        "lekcje muzealn",
    )),
    ("instytucja kultury / muzeum / galeria", 3, (
        "muzeum", "muzealn", "galeri", "kurator", "wystaw",
        "dom kultury", "ośrodek kultury", "centrum kultury",
        "teatr", "biblioteka", "kolekcj", "zbior",
    )),
    ("konserwacja / zbiory", 3, (
        "konserwator dzieł", "konserwacj dzieł", "konserwacj zbior",
        "inwentaryzacj zbior", "digitalizacj zbior", "archiwist",
    )),
    ("promocja / media kultury", 2, (
        "promocj", "social media", "media społecznościow", "content",
        "redaktor", "copywrit", "komunikacj marketingow",
    )),
]

# Stanowiska jawnie NIE pasujące do profilu — obniżają wynik, aby nie
# trafiały do sekcji dopasowanych (żona wprost wskazała, że to nie jej profil).
EXCLUDE_KEYWORDS: Tuple[str, ...] = (
    "sprzątacz", "sprzątaj", "osoba sprzątająca", "pokojow",
    "ochron", "portier", "woźn", "dozorc", "stróż",
    "kierowc", "kucharz", "kuchenn", "pomoc kuchenn", "zmywak",
    "opiekun w żłobku", "pielęgniar", "ratownik", "opiekun medyczn",
    "księgow", "kadr i płac", "płac", "zamówień publiczn",
    "informatyk", "programist", "administrator sieci", "serwisant",
    "hydraulik", "elektryk", "konserwator techniczn", "ślusarz",
    "robotnik", "pracownik fizyczn", "magazynier", "kasjer",
    "nauczyciel", "wychowawca",
    # Zawody medyczne — bywały łapane przez nazwę placówki (poradnie).
    "lekarz", "lekarka", "psychiatra", "psycholog kliniczn", "logopeda",
    "terapeut", "rehabilitant", "fizjoterapeut",
    # Zawody budowlane/produkcyjne — wchodziły przez słowo „warsztat”
    # („Zbrojarz WARSZTATOWY”, „Zbrojarz-warsztat”), które w profilu
    # oznacza warsztaty twórcze, a nie warsztat produkcyjny.
    "zbrojarz", "spawacz", "slusarz", "tokarz", "stolarz", "mechanik",
    "monter", "operator maszyn",
)

# Oferty WIARYGODNE, ale wymagające odrębnych kwalifikacji — degradujemy je
# do „może pasować”, zamiast wykluczać albo promować.
#
# Powód: „Instruktor terapii zajęciowej” w Warsztacie Terapii Zajęciowej to
# realnie praca dla kogoś, kto prowadzi zajęcia plastyczne — a więc
# sensowna propozycja. Ale wymaga kursu terapii zajęciowej, więc nie może
# stać w jednym rzędzie z „GRAFIK/GRAFICZKA” czy ofertą ASP i nosić
# odznaki „DLA CIEBIE”. Decyzję o aplikowaniu zostawiamy człowiekowi,
# tylko porządkujemy kolejność.
DEMOTE_KEYWORDS: Tuple[str, ...] = (
    "terapii zajeciowej", "terapia zajeciowa", "terapii zajęciowej",
    "terapia zajęciowa", "oligofrenopedagog",
)

# Obszary RDZENIOWE — tylko one mogą samodzielnie zakwalifikować ofertę.
# Obszary pozostałe ("instytucja kultury", "promocja / media kultury") są
# WSPIERAJĄCE: podnoszą wynik, gdy jest już trafienie rdzeniowe, ale same
# nie wystarczą. Bez tego podziału do wyników wchodziły oferty typu
# "Dentysta" (trafienie kontekstowe w opisie) i "Wykładowca – Instruktor
# (Montażysta Rusztowań)" (słowo "instruktor" bez związku z kulturą).
CORE_AREAS: Tuple[str, ...] = (
    "grafika / design",
    "sztuka / plastyka",
    "animacja kultury / warsztaty",
    "edukacja kulturalna / muzealna",
    "konserwacja / zbiory",
)

# Progi interpretacji wyniku.
SCORE_STRONG = 8   # mocne dopasowanie (co najmniej dwa trafne obszary)
SCORE_WEAK = 3     # słabe, ale warte pokazania

# Pracodawcy JEDNOZNACZNIE artystyczni/kulturalni. Ich obecność pozwala
# uznać ofertę za mocne trafienie nawet wtedy, gdy sam tytuł jest ogólny.
#
# Przypadek, który to wymusił: „Asystent/asystentka w grupie pracowników
# badawczo-dydaktycznych” w **Akademii Sztuk Pięknych im. Jana Matejki**
# (Katedra grafiki, od 5600 zł). Tytuł nie zawiera żadnego słowa z profilu,
# więc reguła „mocne wymaga trafienia rdzeniowego w tytule” degradowała
# najlepszą ofertę w całym raporcie do „może pasować”.
#
# UWAGA na różnicę wobec wcześniejszego błędu: tu wymieniamy konkretne,
# niedwuznaczne instytucje sztuki. Nie wystarcza TYP placówki — to właśnie
# ogólne „Poradnia Psychologiczno-Pedagogiczna” generowało trafienia dla
# „LEKARZ PSYCHIATRA” (patrz INSTITUTION_NOISE).
ARTS_EMPLOYERS: Tuple[str, ...] = (
    "akademia sztuk pieknych", "akademia sztuk pięknych",
    "muzeum narodowe", "zamek krolewski", "zamek królewski",
    "teatr", "filharmonia", "opera", "galeria sztuki",
    "dom kultury", "osrodek kultury", "ośrodek kultury",
    "centrum kultury", "cricoteka", "muzeum historyczne",
)

# PUŁAPKA JĘZYKOWA: po polsku "grafik" to zarówno zawód (grafik komputerowy),
# jak i harmonogram pracy ("elastyczny grafik", "decydować o swoim grafiku").
# Listowanie wszystkich fraz zawiodło (złapało "Tancerkę w klubie", bo w opisie
# była fraza "decydować o swoim grafiku"), dlatego rozpoznajemy znaczenie
# KONTEKSTOWO: jeśli w otoczeniu słowa "grafik" stoi którekolwiek z poniższych
# słów, chodzi o harmonogram i takie wystąpienie usuwamy z tekstu.
SCHEDULE_CONTEXT_WORDS: Tuple[str, ...] = (
    "elastyczn", "dogodn", "swoim", "swój", "własnym", "ustalać", "ustalasz",
    "decydować", "decydujesz", "zmianow", "dyżur", "godzin", "pracy",
    "miesięczn", "tygodniow", "harmonogram", "dostosuj", "układa",
)

# Ile znaków wokół słowa „grafik” sprawdzamy w poszukiwaniu kontekstu.
SCHEDULE_CONTEXT_WINDOW = 45

# Nazwy instytucji, w których słowo „pedagogiczn” jest częścią TYPU placówki,
# a nie opisem stanowiska. Bez tego do wyników wchodziły oferty typu
# „LEKARZ/LEKARKA PSYCHIATRA” czy „Referent” z Poradni
# Psychologiczno-Pedagogicznej — trafiały przez nazwę pracodawcy.
INSTITUTION_NOISE: Tuple[str, ...] = (
    "psychologiczno-pedagogiczn",
    "psychologiczno pedagogiczn",
    "poradni pedagogiczn",
)


def _strip_institution_noise(text: str) -> str:
    """Usuwa nazwy typu placówki, które myliłyby dopasowanie do profilu.

    Args:
        text: znormalizowany tekst (zwykle nazwa jednostki + opis).

    Returns:
        Tekst bez fraz oznaczających typ placówki.
    """
    for phrase in INSTITUTION_NOISE:
        text = text.replace(phrase, " ")
    return text


def _strip_schedule_meanings(text: str) -> str:
    """Usuwa wystąpienia „grafik”, w których chodzi o harmonogram pracy.

    Dla każdego wystąpienia rdzenia „grafik” sprawdzamy okno kontekstu
    (:data:`SCHEDULE_CONTEXT_WINDOW` znaków po obu stronach). Jeśli pojawia
    się tam słowo wskazujące na harmonogram (np. „elastyczny”, „swoim”,
    „zmianowy”, „godzin”), usuwamy to wystąpienie — nie jest to zawód.

    Args:
        text: znormalizowany tekst (małe litery).

    Returns:
        Tekst z usuniętymi „harmonogramowymi” wystąpieniami słowa „grafik”.
    """
    result = text
    # Iterujemy od końca, aby podmiany nie psuły pozycji kolejnych trafień.
    for match in reversed(list(re.finditer(r"grafik\w*", result))):
        start = max(0, match.start() - SCHEDULE_CONTEXT_WINDOW)
        end = min(len(result), match.end() + SCHEDULE_CONTEXT_WINDOW)
        context = result[start:match.start()] + result[match.end():end]
        if any(word in context for word in SCHEDULE_CONTEXT_WORDS):
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
    """Ocenia dopasowanie oferty do profilu (kultura, sztuka, grafika).

    Trafienie w TYTULE waży podwójnie względem trafienia w opisie lub nazwie
    jednostki — tytuł najlepiej opisuje stanowisko.

    Args:
        title: tytuł oferty.
        description: treść/opis oferty (opcjonalnie).
        unit_name: nazwa jednostki/pracodawcy (opcjonalnie).

    Returns:
        Słownik: profile_score (int), profile_tags (lista obszarów),
        profile_level ('strong' / 'weak' / 'none'), profile_excluded (bool).
    """
    title_norm = _strip_schedule_meanings(_normalize(title))
    body_norm = _strip_institution_noise(
        _strip_schedule_meanings(_normalize(f"{description} {unit_name}"))
    )

    score = 0
    tags: List[str] = []
    core_in_title = False
    core_anywhere = False

    for label, weight, patterns in PROFILE_KEYWORDS:
        hit_title = any(pattern in title_norm for pattern in patterns)
        hit_body = any(pattern in body_norm for pattern in patterns)
        if hit_title:
            score += weight * 2
        elif hit_body:
            score += weight
        if hit_title or hit_body:
            tags.append(label)
            if label in CORE_AREAS:
                core_anywhere = True
                if hit_title:
                    core_in_title = True

    # Wykluczenia liczymy tylko z tytułu — w opisie mogą pojawiać się
    # przypadkowo (np. "współpraca z księgowością" w ofercie dla animatora).
    excluded = any(pattern in title_norm for pattern in EXCLUDE_KEYWORDS)
    if excluded:
        score -= 10

    # Degradacja: oferta jest wiarygodna, ale wymaga odrębnych kwalifikacji
    # (patrz DEMOTE_KEYWORDS). Nie usuwamy jej — tylko nie pozwalamy jej
    # nosić odznaki „DLA CIEBIE” na równi z ofertą wprost z profilu.
    demoted = any(pattern in title_norm or pattern in body_norm
                  for pattern in DEMOTE_KEYWORDS)

    # Kwalifikacja: musi być trafienie w obszarze RDZENIOWYM. Trafienie
    # wyłącznie w obszarze wspierającym (np. sama nazwa "muzeum" w opisie)
    # nie czyni oferty dopasowaną do profilu.
    arts_employer = any(name in _normalize(unit_name)
                        for name in ARTS_EMPLOYERS)
    if excluded or not core_anywhere or score < SCORE_WEAK:
        level = "none"
    elif (score >= SCORE_STRONG and not demoted
          and (core_in_title or arts_employer)):
        # Mocne dopasowanie wymaga trafienia rdzeniowego w TYTULE — to
        # odróżnia "GRAFIK/GRAFICZKA" od oferty, która tylko wspomina
        # projektowanie w opisie obowiązków. Wyjątkiem jest jednoznacznie
        # artystyczny pracodawca (ARTS_EMPLOYERS), np. ASP.
        level = "strong"
    else:
        level = "weak"

    return {
        "profile_score": score,
        "profile_tags": tags,
        "profile_level": level,
        "profile_excluded": excluded,
    }
