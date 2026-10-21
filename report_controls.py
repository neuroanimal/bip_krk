#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Paski sterowania raportu: język, geografia, filtry i sortowanie.

Wydzielone z ``report_html.py``, gdy ten ponownie przekroczył 1000 linii.
Podział jest rzeczowy: tutaj powstaje **sterowanie** (co użytkownik
klika), a w ``report_html`` **dokument** (jak wygląda oferta i cała
strona). Zachowanie tych kontrolek w przeglądarce żyje osobno, w
``report_script``.

Każdy pasek powstał z konkretnej uwagi adresatki — powody są opisane
w docstringach poszczególnych funkcji, żeby nikt ich później nie usunął
jako „zbędnych”.
"""

from __future__ import annotations

import html as html_lib
from collections import Counter
from typing import Dict

import contract_type as ct
import geo

def build_locale_bar() -> str:
    """Buduje mały pasek w prawym górnym rogu: język ofert i interfejsu.

    Celowo **małe i w narożniku** — adresatka prosiła, żeby nie zajmowało
    ekranu. Język ofert stoi po lewej od flagi interfejsu, bo to dwie
    różne rzeczy i łatwo je pomylić:

    * **język ogłoszeń** — które oferty w ogóle pokazywać (domyślnie tylko
      polskie, angielskie odznaczone),
    * **język interfejsu** — w jakim języku są napisy raportu (domyślnie
      polski; przełącza flaga).

    Returns:
        Fragment HTML paska.
    """
    return (
        "<div class='locale'>"
        "<span class='loc-lang' title='Języki ogłoszeń brane pod uwagę "
        "(nie interfejsu)'>"
        "<span class='loc-ico'>✎</span>"
        "<button type='button' class='lbtn on' data-offer-lang='pl'>PL"
        "</button>"
        "<button type='button' class='lbtn' data-offer-lang='en'>EN"
        "</button>"
        "</span>"
        "<span class='loc-ui' title='Język interfejsu / interface language'>"
        "<span class='loc-ico'>🌐</span>"
        "<button type='button' class='flag on' data-ui-lang='pl' "
        "title='Język interfejsu: polski'>🇵🇱</button>"
        "<button type='button' class='flag' data-ui-lang='en' "
        "title='Interface language: English'>🇬🇧</button>"
        "</span>"
        "</div>"
    )


def build_geo_bar(stats: Dict[str, object]) -> str:
    """Buduje pasek wyboru miejsca wyjazdu i promienia poszukiwań.

    Powstał z konkretnej skargi: w raporcie były oferty z Gorlic
    i Tarnowa (100+ km), formalnie „małopolskie”. Adresatka poprosiła
    o zawężenie do „Krakowa i 10 km za jego granicę”, stąd dwa osobne
    elementy:

    * **dom** — dzielnica Krakowa (domyślnie Bronowice); od niej liczymy
      odległość pokazywaną przy ofertach spoza miasta,
    * **promień** — suwak w km (domyślnie 10), dotyczy ofert **poza
      Krakowem**; oferty w samym Krakowie są zawsze w zasięgu, bo dojazd
      w obrębie miasta jest normalny (gdyby liczyć je promieniem,
      10 km od Bronowic ucięłoby Nową Hutę — 18,5 km — a tam właśnie
      była oferta, której adresatce brakowało).

    Odległość liczy przeglądarka, więc zmiana dzielnicy albo suwaka
    działa natychmiast, bez generowania raportu od nowa.

    Args:
        stats: statystyki raportu (liczba ofert z lokalizacją).

    Returns:
        Fragment HTML paska.
    """
    options = "".join(
        f"<option value='{html_lib.escape(name)}'"
        f"{' selected' if name == geo.DEFAULT_DISTRICT else ''}>"
        f"{html_lib.escape(name)}</option>"
        for name in geo.KRAKOW_DISTRICTS
    )
    located = int(stats.get("located", 0) or 0)
    in_city = int(stats.get("in_city", 0) or 0)

    return (
        "<div class='frow geo'>"
        "<span class='flabel' data-t='home'>Miejsce wyjazdu:</span>"
        f"<select id='geo-home' class='gsel'>{options}</select>"
        "<span class='flabel geo-rad' data-t='radius'>Promień poza "
        "Krakowem:</span>"
        f"<input type='range' id='geo-radius' min='0' max='120' step='5' "
        f"value='{geo.DEFAULT_RADIUS_KM}' class='gslider'>"
        f"<span class='gval' id='geo-radius-val'>"
        f"{geo.DEFAULT_RADIUS_KM} km</span>"
        "<label class='gchk'><input type='checkbox' id='geo-city' checked>"
        "<span data-t='always_city'>Kraków zawsze</span></label>"
        f"<span class='fsummary' id='geo-summary'>"
        f"w Krakowie: {in_city} · z lokalizacją: {located}</span>"
        "</div>"
    )


def build_filter_bar(stats: Dict[str, object]) -> str:
    """Buduje pasek filtrów raportu (rodzaj umowy, dopasowanie, źródło).

    DLACZEGO FILTROWANIE PO STRONIE PRZEGLĄDARKI
    --------------------------------------------
    Raport jest plikiem statycznym — nie ma serwera, który mógłby
    przefiltrować dane po kliknięciu. Wszystkie oferty są więc w HTML,
    a filtr jedynie ukrywa karty (``display:none``). Dzięki temu działa
    offline i natychmiast, bez przeładowania.

    Rodzaje umowy są **rozdzielone**: UoP, UZ i B2B to trzy różne sytuacje
    prawne i finansowe (staż pracy, ZUS, urlop, zdolność kredytowa), więc
    łączenie ich w „inne niż UoP” zacierałoby najważniejszą różnicę.
    Osobna pozycja „umowa nieznana” jest konieczna, bo BIP podaje rodzaj
    umowy tylko w części ogłoszeń — ukrycie ich byłoby ukryciem ofert,
    o których po prostu nie wiemy.

    Args:
        stats: statystyki raportu (do liczników przy filtrach).

    Returns:
        Fragment HTML paska filtrów.
    """
    contracts: Counter = stats.get("contracts") or Counter()
    sources: Counter = stats.get("sources") or Counter()

    parts = ["<div class='filters' id='filters'>"]

    parts.append("<div class='frow'><span class='flabel'>Rodzaj umowy:"
                 "</span>")
    for code in ct.ORDER:
        count = contracts.get(code, 0)
        if not count:
            continue
        parts.append(
            f"<button type='button' class='fbtn on' data-filter='contract' "
            f"data-value='{html_lib.escape(code)}' "
            f"title='{html_lib.escape(ct.DESCRIPTIONS.get(code, ''))}'>"
            f"{html_lib.escape(ct.LABELS.get(code, code))}"
            f"<span class='fcount'>{count}</span></button>"
        )
    parts.append("</div>")

    # Obszary dopasowania jako klikalne etykiety — adresatka chciała
    # widzieć, CO jest brane pod uwagę, i móc to zmienić. Wartości
    # pochodzą z ``profile_tags``, czyli z tego, co realnie zdecydowało
    # o dopasowaniu, a nie z osobnej listy życzeń.
    areas: Counter = stats.get("areas") or Counter()
    if areas:
        parts.append("<div class='frow'><span class='flabel' "
                     "data-t='areas'>Obszary:</span>")
        for name, count in areas.most_common():
            parts.append(
                f"<button type='button' class='fbtn on' data-filter='area' "
                f"data-value='{html_lib.escape(name)}'>"
                f"{html_lib.escape(name)}"
                f"<span class='fcount'>{count}</span></button>"
            )
        parts.append("</div>")

    parts.append(build_geo_bar(stats))

    parts.append("<div class='frow'><span class='flabel' "
                 "data-t='match'>Dopasowanie:</span>")
    for value, text in (("strong", "DLA CIEBIE"), ("weak", "może pasować"),
                        ("none", "poza profilem")):
        count = int(stats.get({"strong": "strong", "weak": "weak",
                               "none": "nomatch"}[value], 0) or 0)
        if not count:
            continue
        parts.append(
            f"<button type='button' class='fbtn on' data-filter='level' "
            f"data-value='{value}'>{text}"
            f"<span class='fcount'>{count}</span></button>"
        )
    parts.append("</div>")

    if len(sources) > 1:
        parts.append("<div class='frow'><span class='flabel'>Źródło:"
                     "</span>")
        for name, count in sources.most_common():
            parts.append(
                f"<button type='button' class='fbtn on' data-filter='source' "
                f"data-value='{html_lib.escape(name)}'>"
                f"{html_lib.escape(name)}"
                f"<span class='fcount'>{count}</span></button>"
            )
        parts.append("</div>")

    # Sortowanie. Domyślne „po pilności” zostaje takie jak było — raport
    # ma przede wszystkim nie przegapić terminu. Sortowanie po płacy jest
    # ORIENTACYJNE: przelicza B2B netto/h i UoP brutto/mies. na jedną
    # miarę, co opisuje docstring modułu ``salary``.
    with_pay = int(stats.get("with_pay", 0) or 0)
    parts.append("<div class='frow'><span class='flabel'>Sortuj:</span>")
    for value, text, title in (
        ("urgency", "po pilności", "Najpierw oferty z najbliższym terminem"),
        ("pay", "po wynagrodzeniu",
         "Malejąco, po przeliczeniu na PLN/miesiąc — orientacyjnie, "
         "bo B2B podaje się netto, a UoP brutto"),
        ("score", "po dopasowaniu", "Najpierw najlepiej dopasowane"),
    ):
        if value == "pay" and not with_pay:
            continue
        extra = " on" if value == "urgency" else ""
        count = (f"<span class='fcount'>{with_pay}</span>"
                 if value == "pay" else "")
        parts.append(
            f"<button type='button' class='fbtn sbtn{extra}' "
            f"data-sort='{value}' title='{html_lib.escape(title)}'>"
            f"{text}{count}</button>"
        )
    parts.append("</div>")

    parts.append(
        "<div class='frow'>"
        "<button type='button' class='fbtn act' id='f-all'>"
        "Pokaż wszystkie</button>"
        "<span class='fsummary' id='f-summary'></span>"
        "</div>"
    )
    parts.append("</div>")
    return "".join(parts)
