#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Profil zawodowy: kultura, sztuka, grafika, animacja, edukacja kulturalna.

To ORYGINALNY profil, dla którego powstał projekt (praca dla osoby po
kierunkach artystycznych, szukającej stabilności w sektorze publicznym).
Stałe przeniesiono tutaj z ``profile_match.py`` bez zmian merytorycznych,
gdy doszedł drugi profil (IT/dane) — logika oceniania została w
``profile_match``, a tu jest wyłącznie DEFINICJA profilu.

Każdy profil musi udostępniać ten sam zestaw nazw — kontrakt opisuje
docstring ``profiles/__init__.py``.
"""

from typing import List, Tuple

# Nazwa wyświetlana w raporcie i w nazwach plików.
LABEL = "Kultura i sztuka"
SLUG = "kultura"

# Opis pokazywany pod nagłówkiem sekcji „Dopasowane do profilu”.
DESCRIPTION = (
    "Kultura i sztuka, grafika i design, animacja kultury, warsztaty, "
    "edukacja muzealna i kulturalna."
)

PROFILE_KEYWORDS: List[Tuple[str, int, Tuple[str, ...]]] = [
    ("grafika / design", 5, (
        "grafik", "graficz", "graphic design", "dtp", "projektant",
        "projektowanie graficzne", "skład komputerowy", "ilustrator",
        "ilustracj", "typograf", "identyfikacj wizualn",
        # Odpowiedniki angielskie — potrzebne dla ofert zagranicznych
        # (źródło src_remote_intl). Celowo NIE dodajemy "ux", "ui",
        # "product design" ani "game design": to pokrewne, ale inne
        # specjalizacje (produkt cyfrowy), nie grafika warsztatowa/DTP.
        "graphic designer", "visual design", "art direct",
        "illustration", "illustrator", "typography", "brand design",
        "desktop publishing", "prepress",
    )),
    ("sztuka / plastyka", 5, (
        "plastyk", "malarstw", "malarsk", "rysunk", "rysunek", "akwarel",
        "artystyczn", "artyst", "sztuk", "rzeźb", "druk artystyczn",
        "grafika warsztatow", "serigraf", "linoryt", "akwafort",
        # Angielskie odpowiedniki.
        "fine art", "painting", "watercolor", "watercolour",
        "printmaking", "screen print", "etching",
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
        # Angielskie odpowiedniki — „education designer”, „course
        # writer” i podobne łączą dydaktykę z projektowaniem, co pokrywa
        # się z jej doświadczeniem w prowadzeniu warsztatów.
        "museum educat", "art educat", "education designer",
        "workshop facilitat", "teaching artist",
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
PREFERRED_EMPLOYERS: Tuple[str, ...] = (
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
