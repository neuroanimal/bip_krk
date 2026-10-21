#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Statystyki i wykresy do pasków bocznych raportu.

DLACZEGO WŁASNY GENERATOR SVG, A NIE BIBLIOTEKA WYKRESÓW
--------------------------------------------------------
Raport jest **pojedynczym plikiem HTML otwieranym lokalnie**, często bez
internetu (tak go używa adresatka). Biblioteka z CDN (Chart.js, Plotly)
oznaczałaby puste prostokąty przy braku sieci i zależność od zewnętrznego
serwera w pliku, który ma żyć latami w katalogu ``reports/``. Dołączenie
jej lokalnie to kilkaset kilobajtów na każdy raport.

Dlatego wykresy są **statycznym, wbudowanym SVG** liczonym tutaj:
działają offline, nie wymagają JavaScriptu, skalują się przy druku i ważą
tyle, ile mają danych. Minus: brak interaktywności — świadomy wybór,
bo wykres ma odpowiadać na pytanie „czego jest dużo i skąd to jest”,
a nie zachęcać do klikania.

CO POKAZUJEMY
-------------
Lewy pasek — **liczby**: ile ofert, ile dopasowanych, ile nowych, ile
pilnych (termin ≤ 7 dni), rozkład po źródłach i po statusie.
Prawy pasek — **wykresy**: dopasowanie do profilu, oferty po źródle,
terminy w czasie, napływ ofert w ostatnich dniach.
"""

from __future__ import annotations

import html as html_lib
from collections import Counter
from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

# Paleta spójna ze stylem raportu (zielony = dobre, czerwony = pilne).
COLOR_STRONG = "#1a7f37"
COLOR_WEAK = "#9a6700"
COLOR_NONE = "#656d76"
COLOR_URGENT = "#cf222e"
COLOR_BAR = "#0969da"
COLOR_GRID = "#d0d7de"

# Ile pozycji maksymalnie na wykresie słupkowym (dalej robi się nieczytelny).
MAX_BARS = 8

# Ile dni wstecz pokazuje wykres napływu ofert.
INFLOW_DAYS = 14

# Próg „pilne” w dniach do terminu.
URGENT_DAYS = 7


def _parse_iso(value: object) -> Optional[date]:
    """Zamienia łańcuch ISO (data lub data z czasem) na obiekt daty.

    Args:
        value: wartość z datasetu (``YYYY-MM-DD`` lub ``...THH:MM:SS``).

    Returns:
        Obiekt daty albo None, gdy nie da się odczytać.
    """
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def collect_stats(offers: Sequence[Dict[str, object]]) -> Dict[str, object]:
    """Liczy statystyki raportu z listy wzbogaconych ofert.

    Args:
        offers: oferty po wzbogaceniu (mają ``profile_level``, ``is_new``,
            ``deadline``, ``source``, ``status``).

    Returns:
        Słownik statystyk gotowy do wyrenderowania w pasku bocznym.
    """
    today = date.today()
    levels = Counter(str(o.get("profile_level") or "none") for o in offers)
    sources = Counter(str(o.get("source") or "?") for o in offers)
    statuses = Counter(str(o.get("status") or "?") for o in offers)

    # Rodzaje umowy liczymy per OFERTA, ale oferta może dopuszczać kilka
    # form (bulldogjob często „UoP albo B2B”), więc suma liczników bywa
    # większa niż liczba ofert. To zamierzone: filtr ma pokazać, ile ofert
    # da się dostać na daną formę.
    contracts: Counter = Counter()
    for offer in offers:
        for code in (offer.get("contract_types") or ["nieznana"]):
            contracts[str(code)] += 1

    urgent = 0
    with_deadline = 0
    for offer in offers:
        deadline = _parse_iso(offer.get("deadline"))
        if deadline is None:
            continue
        with_deadline += 1
        days_left = (deadline - today).days
        if 0 <= days_left <= URGENT_DAYS:
            urgent += 1

    inflow: Counter = Counter()
    for offer in offers:
        first_seen = _parse_iso(offer.get("first_seen"))
        if first_seen is None:
            continue
        age = (today - first_seen).days
        if 0 <= age < INFLOW_DAYS:
            inflow[first_seen.isoformat()] += 1

    return {
        "total": len(offers),
        "new": sum(1 for o in offers if o.get("is_new")),
        "clicked": sum(1 for o in offers if o.get("clicked_at")),
        "strong": levels.get("strong", 0),
        "weak": levels.get("weak", 0),
        "nomatch": levels.get("none", 0),
        "urgent": urgent,
        "with_deadline": with_deadline,
        "no_deadline": len(offers) - with_deadline,
        "sources": sources,
        "contracts": contracts,
        # Ile ofert ma w ogóle podaną kwotę — decyduje, czy pokazywać
        # przycisk sortowania po wynagrodzeniu.
        "with_pay": sum(1 for o in offers if o.get("salary_pln")),
        # Języki ogłoszeń i obszary dopasowania — zasilają etykiety filtra.
        "langs": Counter(str(o.get("lang") or "pl") for o in offers),
        "areas": _count_areas(offers),
        "in_city": sum(1 for o in offers if o.get("in_city")),
        "located": sum(1 for o in offers if o.get("lat")),
        "statuses": statuses,
        "inflow": inflow,
    }


def _count_areas(offers) -> Counter:
    """Liczy, ile ofert trafia w każdy obszar profilu.

    Obszary pochodzą z ``profile_tags`` wyliczonych przez
    ``profile_match`` — nie dublujemy słownika, tylko pokazujemy to, co
    naprawdę zdecydowało o dopasowaniu. Dzięki temu etykiety filtra w
    raporcie odpowiadają realnej zawartości, a nie liście życzeń.

    Args:
        offers: wzbogacone oferty.

    Returns:
        Licznik ``obszar -> liczba ofert``.
    """
    counter: Counter = Counter()
    for offer in offers:
        for tag in (offer.get("profile_tags") or []):
            counter[str(tag)] += 1
    return counter


def _bar_chart(title: str, pairs: Sequence[Tuple[str, int]],
               color: str = COLOR_BAR) -> str:
    """Rysuje poziomy wykres słupkowy jako SVG.

    Poziomy, nie pionowy — nazwy źródeł i kategorii są długie, a w pionie
    trzeba by je obracać, co jest nieczytelne w wąskim pasku.

    Args:
        title: nagłówek wykresu.
        pairs: pary (etykieta, wartość), już posortowane.
        color: kolor słupków.

    Returns:
        Fragment HTML z wbudowanym SVG (pusty, gdy brak danych).
    """
    data = [(label, value) for label, value in pairs if value > 0][:MAX_BARS]
    if not data:
        return ""

    row_height = 22
    label_width = 104
    bar_width = 120
    height = len(data) * row_height + 6
    top = max(value for _label, value in data)

    parts = [f"<div class='chart'><h4>{html_lib.escape(title)}</h4>"]
    parts.append(
        f"<svg viewBox='0 0 {label_width + bar_width + 34} {height}' "
        f"role='img' aria-label='{html_lib.escape(title)}'>"
    )
    for index, (label, value) in enumerate(data):
        y_pos = index * row_height + 4
        width = max(2, round(value / top * bar_width))
        short = label if len(label) <= 17 else label[:16] + "…"
        parts.append(
            f"<text x='0' y='{y_pos + 11}' class='cl'>"
            f"{html_lib.escape(short)}</text>"
        )
        parts.append(
            f"<rect x='{label_width}' y='{y_pos + 2}' width='{width}' "
            f"height='12' rx='2' fill='{color}'></rect>"
        )
        parts.append(
            f"<text x='{label_width + width + 4}' y='{y_pos + 12}' "
            f"class='cv'>{value}</text>"
        )
    parts.append("</svg></div>")
    return "".join(parts)


def _donut_chart(title: str, pairs: Sequence[Tuple[str, int, str]]) -> str:
    """Rysuje pierścień (donut) jako SVG — udział kategorii w całości.

    Pierścień, nie koło: w środku mieści się suma, co od razu odpowiada na
    pytanie „ile tego w ogóle jest”.

    Args:
        title: nagłówek wykresu.
        pairs: trójki (etykieta, wartość, kolor).

    Returns:
        Fragment HTML z wbudowanym SVG (pusty, gdy brak danych).
    """
    data = [(label, value, color) for label, value, color in pairs
            if value > 0]
    total = sum(value for _l, value, _c in data)
    if not total:
        return ""

    radius = 38
    stroke = 16
    circumference = 2 * 3.14159265 * radius
    offset = 0.0

    parts = [f"<div class='chart'><h4>{html_lib.escape(title)}</h4>"]
    parts.append("<svg viewBox='0 0 190 96' role='img' "
                 f"aria-label='{html_lib.escape(title)}'>")
    parts.append("<g transform='translate(48,48)'>")
    for _label, value, color in data:
        length = value / total * circumference
        # Sztuczka bez trygonometrii: łuk rysujemy kreskowaniem obwodu,
        # a kolejne wycinki przesuwamy ujemnym dash-offset.
        parts.append(
            f"<circle r='{radius}' fill='none' stroke='{color}' "
            f"stroke-width='{stroke}' "
            f"stroke-dasharray='{length:.2f} {circumference - length:.2f}' "
            f"stroke-dashoffset='{-offset:.2f}' "
            "transform='rotate(-90)'></circle>"
        )
        offset += length
    parts.append(
        f"<text x='0' y='5' text-anchor='middle' class='cd'>{total}</text>"
    )
    parts.append("</g>")

    for index, (label, value, color) in enumerate(data):
        y_pos = 18 + index * 18
        parts.append(
            f"<rect x='98' y='{y_pos - 8}' width='9' height='9' rx='2' "
            f"fill='{color}'></rect>"
        )
        parts.append(
            f"<text x='112' y='{y_pos}' class='cl'>"
            f"{html_lib.escape(label)}: {value}</text>"
        )
    parts.append("</svg></div>")
    return "".join(parts)


def _sparkline(title: str, inflow: Counter) -> str:
    """Rysuje słupki napływu ofert w ostatnich dniach.

    Args:
        title: nagłówek wykresu.
        inflow: licznik ``data ISO -> liczba nowych ofert``.

    Returns:
        Fragment HTML z wbudowanym SVG (pusty, gdy brak danych).
    """
    if not inflow:
        return ""
    today = date.today()
    days = [(today.toordinal() - offset) for offset in range(INFLOW_DAYS)][::-1]
    values = [inflow.get(date.fromordinal(d).isoformat(), 0) for d in days]
    if not any(values):
        return ""

    width, height = 170, 54
    top = max(values)
    slot = width / len(values)

    parts = [f"<div class='chart'><h4>{html_lib.escape(title)}</h4>"]
    parts.append(f"<svg viewBox='0 0 {width} {height + 14}' role='img' "
                 f"aria-label='{html_lib.escape(title)}'>")
    parts.append(f"<line x1='0' y1='{height}' x2='{width}' y2='{height}' "
                 f"stroke='{COLOR_GRID}'></line>")
    for index, value in enumerate(values):
        bar_h = 0 if top == 0 else round(value / top * (height - 4))
        x_pos = index * slot + 1
        parts.append(
            f"<rect x='{x_pos:.1f}' y='{height - bar_h}' "
            f"width='{slot - 2:.1f}' height='{bar_h}' rx='1' "
            f"fill='{COLOR_BAR}'></rect>"
        )
    first = date.fromordinal(days[0]).strftime("%d.%m")
    last = date.fromordinal(days[-1]).strftime("%d.%m")
    parts.append(f"<text x='0' y='{height + 12}' class='cv'>{first}</text>")
    parts.append(
        f"<text x='{width}' y='{height + 12}' text-anchor='end' "
        f"class='cv'>{last}</text>"
    )
    parts.append("</svg></div>")
    return "".join(parts)


def build_stats_sidebar(stats: Dict[str, object]) -> str:
    """Buduje lewy pasek boczny z liczbami.

    Args:
        stats: wynik :func:`collect_stats`.

    Returns:
        Fragment HTML paska.
    """
    rows: List[Tuple[str, object, str]] = [
        ("Ofert w raporcie", stats["total"], ""),
        ("Dopasowanych", int(stats["strong"]) + int(stats["weak"]), "ok"),
        ("— mocnych trafień", stats["strong"], "ok"),
        ("— może pasować", stats["weak"], ""),
        ("NOWE od ostatniego raportu", stats["new"], "new"),
        (f"Pilne (termin ≤ {URGENT_DAYS} dni)", stats["urgent"], "urgent"),
        ("Już oglądane", stats["clicked"], ""),
        ("Bez podanego terminu", stats["no_deadline"], ""),
    ]

    parts = ["<aside class='side side-left'>", "<h3>Statystyki</h3>",
             "<table class='stats'>"]
    for label, value, css in rows:
        cls = f" class='{css}'" if css else ""
        parts.append(
            f"<tr><th>{html_lib.escape(label)}</th>"
            f"<td{cls}>{value}</td></tr>"
        )
    parts.append("</table>")

    sources: Counter = stats["sources"]  # type: ignore[assignment]
    if sources:
        parts.append("<h3>Źródła</h3><table class='stats'>")
        for name, count in sources.most_common():
            parts.append(
                f"<tr><th>{html_lib.escape(name)}</th><td>{count}</td></tr>"
            )
        parts.append("</table>")

    parts.append("</aside>")
    return "".join(parts)


def build_charts_sidebar(stats: Dict[str, object]) -> str:
    """Buduje prawy pasek boczny z wykresami SVG.

    Args:
        stats: wynik :func:`collect_stats`.

    Returns:
        Fragment HTML paska.
    """
    sources: Counter = stats["sources"]  # type: ignore[assignment]
    inflow: Counter = stats["inflow"]  # type: ignore[assignment]

    parts = ["<aside class='side side-right'>", "<h3>Wykresy</h3>"]
    parts.append(_donut_chart("Dopasowanie do profilu", [
        ("mocne", int(stats["strong"]), COLOR_STRONG),
        ("może pasować", int(stats["weak"]), COLOR_WEAK),
        ("poza profilem", int(stats["nomatch"]), COLOR_NONE),
    ]))
    parts.append(_bar_chart("Oferty po źródle", sources.most_common()))
    parts.append(_donut_chart("Terminy", [
        (f"pilne (≤{URGENT_DAYS} dni)", int(stats["urgent"]), COLOR_URGENT),
        ("z terminem", int(stats["with_deadline"]) - int(stats["urgent"]),
         COLOR_BAR),
        ("bez terminu", int(stats["no_deadline"]), COLOR_NONE),
    ]))
    parts.append(_sparkline(f"Napływ ofert ({INFLOW_DAYS} dni)", inflow))
    parts.append("</aside>")
    return "".join(parts)
