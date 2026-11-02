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
        # Dodane na prośbę adresatki: świetlice i organizacja wydarzeń to
        # praca, którą realnie wykonuje (zajęcia dla grup, imprezy).
        "świetlic", "swietlic", "wychowawc w świetlic",
        # Uwaga na odmianę: „organizacj**i** imprez” nie pasuje do wzorca
        # „organizacj imprez”, więc rdzeń „imprez” stoi osobno.
        "imprez", "wydarzeń kulturaln", "wydarzen kulturaln",
        "koordynator wydarze", "event",
    )),
    ("media społecznościowe / promocja", 4, (
        # Dodane na prośbę adresatki — prowadzenie social mediów
        # instytucji kultury jest w jej zasięgu (grafika + treści).
        "media społecznościow", "mediów społecznościow", "social media",
        "specjalist ds. mediów", "specjalist ds. social",
        "content creator", "twórc treści", "prowadzeni fanpage",
        "komunikacj w mediach", "promocj w mediach",
        # Budżetowa nazwa tej samej roli. Instytucje publiczne prawie nie
        # piszą „social media” — piszą „specjalista ds. promocji /
        # komunikacji” (wniosek z analizy rynku 21.10). Rdzeń „promocj”
        # i „komunikacj” jest ogólny, więc kwalifikuje TYLKO z kontekstem
        # kultury albo instytucji publicznej (patrz CONTEXT_REQUIRED).
        "ds. promocj", "dzial promocj", "dzialu promocj", "promocji i komunikacj",
        "komunikacji i promocj", "ds. komunikacj",
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
    # „wychowawca” NIE jest już wykluczony: adresatka poprosiła o oferty
    # typu „wychowawca w świetlicy”, a to praca z grupą, którą wykonuje.
    # Zostaje „nauczyciel”, bo nauczanie przedmiotu wymaga uprawnień.
    "nauczyciel przedmiotu", "nauczyciel matematyki", "nauczyciel jęz",
    # Zawody medyczne — bywały łapane przez nazwę placówki (poradnie).
    "lekarz", "lekarka", "psychiatra", "psycholog kliniczn", "logopeda",
    "terapeut", "rehabilitant", "fizjoterapeut",
    # (4) UI/UX na wyraźną prośbę adresatki: „usuń z wyszukiwań ui/ux,
    # bo w tym nie siedzę i nie mam wiedzy”. To pokrewna, ale inna
    # specjalizacja (projektowanie produktów cyfrowych), wymagająca
    # narzędzi i portfolio, których nie ma.
    "ux design", "ui design", "ux/ui", "ui/ux", "ux researcher",
    "product designer", "game designer", "interaction designer",
    "solution designer", "design engineer",
    # Instruktorzy SPORTU i rekreacji — osobna klasa fałszów, odkryta po
    # dodaniu jooble: fraza „instruktor” ściągała instruktorów fitness,
    # pływania, OCR i tańca. Wymagają sprawności i uprawnień, których ten
    # profil nie obejmuje, więc odpadają po tytule.
    "fitness", "pływani", "plywani", "ocr", "crossfit", "siłowni",
    "silowni", "personalny", "instruktor sportu", "instruktor tańca",
    "zajęć tanecznych", "zajec tanecznych", "instruktor jazdy",
    "instruktor nauki jazdy", "ratownik", "trener personaln",
    # Krótsze rdzenie, bo pełne frazy przegrywały z odmianą:
    # „zatrudnię instruktorA nauki jazdy” nie pasowało do „instruktor nauki
    # jazdy”, a „Instruktor Sportów Walki” do żadnej frazy z listy.
    "nauki jazdy", "sport", "robotyk", "serwis", "inzynier", "maszyn",
    # Śpiew i występy — inna dziedzina sztuki niż plastyka i edukacja
    # („Przesłuchania: Głos tenorowy | Chór Polskiego Radia”).
    "przesluchani", "tenor", "sopran", "chorzyst", "spiewak",
    # Technika sceniczna — teatr jako pracodawca się zgadza, ale to praca
    # elektryka i akustyka, nie plastyka („Realizatorka oświetlenia”).
    "realizator", "oswietleni", "akustyk", "dzwiekowc", "elektryk",
    # UX w krótkiej postaci („Education Designer: UX, UI, and AI”,
    # „Principal Experience Designer”) — pełne frazy jej nie łapały.
    " ux", "ux,", "ux/", "experience designer",
    # Obsługa klienta i moderacja treści w centrach usług — w jooble
    # wchodziły przez „media społecznościowe” w opisie. Do tego wymóg
    # obcego języka w tytule („…with Czech”, „German speaking”) — to
    # zawsze rola dla native speakera, nie dla tego profilu.
    # Promocja w znaczeniu handlowym: promocja sprzedaży, promotor/ka
    # w sklepie, merchandising — to praca w terenie przy produkcie.
    "promocji sprzedaz", "promotor", "merchandis", "hostess",
    "customer success", "reviewer", "moderator", "client partner",
    "call center", "with czech", "with german", "german speaking",
    "with dutch", "with french", "with italian", "with spanish",
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
    # Sport UKRYTY W OPISIE przy właściwej instytucji. Przypadek z jooble:
    # „Nauczyciel-Instruktor” w Młodzieżowym Domu Kultury Fort 49 — dom
    # kultury to właściwy pracodawca, ale opis podaje „Zawód: instruktor
    # sportu”. Nie wykluczamy (instytucja się zgadza), tylko degradujemy
    # do „może pasować” i zostawiamy decyzję człowiekowi.
    "zawód: instruktor sportu", "zawod: instruktor sportu",
    "instruktor sportu", "zajęcia sportow", "zajecia sportow",
)

# Degradacje liczone WYŁĄCZNIE z tytułu.
#
# Formy, które nie dają stabilnego zatrudnienia albo wymagają innego
# doświadczenia, a o stabilność tu chodzi: staż, praktyki, wolontariat
# (bez pensji), konkurs na dyrektora (lata zarządzania instytucją),
# sprzedaż biletów i wydarzeń.
#
# Dlaczego tylko tytuł — błąd, który to wymusił: w opisie „staż” to
# najczęściej „STAŻ PRACY” (wymagane doświadczenie), a „praktyk” to
# „doświadczenie PRAKTYCZNE”. Liczone z opisu degradowały ofertę ASP
# i Klub Dukat — dwie najlepsze w raporcie — do „może pasować”.
DEMOTE_TITLE_KEYWORDS: Tuple[str, ...] = (
    "staż", "praktyki", "wolontari", "dyrektor", "sprzedaż",
    "kandydat na stanowisko",
)

# Rdzenie OGÓLNE — liczą się jako rdzeń profilu TYLKO w kontekście
# kulturalnym (w tytule albo w nazwie pracodawcy).
#
# Powód, zmierzony na danych z jooble: samo słowo „instruktor” dawało
# odznakę „DLA CIEBIE” instruktorowi sportów walki, nauki jazdy, robotyki
# i „Inżynierowi Serwisu / Instruktorowi Maszyn”. Lista wykluczeń łatała
# to przypadek po przypadku i zawsze była o krok z tyłu — bo pytała „czy
# to sport?”, zamiast „czy to kultura?”. Teraz odwracamy pytanie: ogólny
# rdzeń bez kontekstu kulturalnego jest tylko sygnałem wspierającym.
#
# ``words``      — kontekst, który kwalifikuje w pełni,
# ``weak_words`` — kontekst, który kwalifikuje, ale najwyżej do „może
#                  pasować” (zajęcia dla dzieci bywają plastyczne, bywają
#                  sportowe; terapia zajęciowa wymaga kursu).
CONTEXT_REQUIRED = {
    "stems": ("instruktor", "animator", "warsztat", "event", "trener",
              "promocj", "komunikacj"),
    "words": (
        "kultur", "plastyczn", "artystyczn", "sztuk", "rysun", "malars",
        "ceramik", "grafik", "teatr", "muze", "galeri", "bibliote",
        "świetlic", "klub", "dom kultury", "ośrodek kultury", "fotograf",
        "rękodzieł", "wystaw", "edukacj",
    ),
    # Urząd gminy czy starostwo to budżetówka, ale nie kultura — promocja
    # gminy bywa w zasięgu (grafika + social media), więc „może pasować”.
    "weak_words": ("urząd", "urzad", "gmin", "starostw", "powiat",
                   "dla dzieci", "dzieci i młodzież", "zajęć",
                   "terapii zajęciow", "terapia zajęciow"),
}

# Obszary RDZENIOWE — tylko one mogą samodzielnie zakwalifikować ofertę.
# Obszary pozostałe ("instytucja kultury", "promocja / media kultury") są
# WSPIERAJĄCE: podnoszą wynik, gdy jest już trafienie rdzeniowe, ale same
# nie wystarczą. Bez tego podziału do wyników wchodziły oferty typu
# "Dentysta" (trafienie kontekstowe w opisie) i "Wykładowca – Instruktor
# (Montażysta Rusztowań)" (słowo "instruktor" bez związku z kulturą).
CORE_AREAS: Tuple[str, ...] = (
    "grafika / design",
    "media społecznościowe / promocja",
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
