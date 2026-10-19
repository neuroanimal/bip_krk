#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generowanie raportu HTML — styl, tracking klikania i budowa dokumentu.

Moduł wydzielony ze skryptu 5 (``5_generate_report.py``), który rozrósł się
ponad rozsądną długość. Tutaj trafiła cała warstwa prezentacji HTML:

* :data:`HTML_STYLE` — arkusz stylów raportu (kolory pilności i świeżości,
  karty ofert, wyróżnienie NOWE, wygaszenie klikniętych, pasek narzędzi),
* :data:`HTML_TRACKING_SCRIPT` — skrypt trackingu klikania oparty na
  ``localStorage`` (raport jest plikiem offline, bez serwera),
* :func:`build_failures_section` — zwijana sekcja diagnostyczna z tym,
  czego nie udało się pobrać,
* :func:`build_html` — złożenie całego dokumentu.

Logika merytoryczna (kategorie, pilność, świeżość, sortowanie) pozostaje
w skrypcie 5 — ten moduł tylko prezentuje przygotowane dane.
"""

from __future__ import annotations

import html as html_lib
from collections import Counter
from typing import Dict, List, NamedTuple, Optional, Tuple

import bip_common as bc
import contract_type as ct
import report_script
import report_stats

def summarize_body(body_text: Optional[str], max_chars: int = 600) -> str:
    """Buduje krótki opis oferty z treści szczegółów.

    Args:
        body_text: pełna treść ogłoszenia (może być None).
        max_chars: maksymalna długość skrótu.

    Returns:
        Skrócony opis (bez łamania w środku słowa, z wielokropkiem).
    """
    if not body_text:
        return "(brak pobranych szczegółów — uruchom skrypt 4)"
    cleaned = body_text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    cut = cleaned[:max_chars].rsplit(" ", 1)[0]
    return cut + " …"


def deadline_label(offer: Dict[str, object]) -> str:
    """Buduje czytelny opis terminu z liczbą dni (np. '2026-07-26 (za 3 dni)').

    Args:
        offer: wzbogacony rekord oferty.

    Returns:
        Tekst terminu wraz z informacją o pozostałych dniach.
    """
    deadline = offer.get("deadline")
    if not deadline:
        return "brak danych"
    days = offer.get("days_left")
    if not isinstance(days, int):
        return str(deadline)
    if days < 0:
        return f"{deadline} (termin minął)"
    if days == 0:
        return f"{deadline} (dziś!)"
    if days == 1:
        return f"{deadline} (jutro)"
    return f"{deadline} (za {days} dni)"


HTML_STYLE = """
:root {
    --bg: #f4f6f8;
    --card: #ffffff;
    --ink: #1f2933;
    --muted: #647380;
    --accent: #7b2d8e;
    --urgent: #d32f2f;
    --soon: #ef6c00;
    --ok: #2e7d32;
    --unknown: #607d8b;
}
* { box-sizing: border-box; }
body {
    font-family: "Segoe UI", Arial, sans-serif;
    background: var(--bg);
    color: var(--ink);
    margin: 0;
    line-height: 1.55;
}
header {
    background: linear-gradient(135deg, #7b2d8e 0%, #3a1c71 100%);
    color: #fff;
    padding: 1.6em 1.2em;
}
header h1 { margin: 0 0 .3em; font-size: 1.7em; }
header .meta { opacity: .9; font-size: .92em; }
.wrap { max-width: 960px; margin: 0 auto; padding: 1.2em; }

/* Układ trzykolumnowy: statystyki | treść | wykresy.
   Grid, nie flex — kolumny boczne mają stałą szerokość, a środek bierze
   resztę, co przy flexie wymagałoby dodatkowych reguł flex-basis. */
.layout { display: grid; grid-template-columns: 210px minmax(0,1fr) 210px;
          gap: 0; align-items: start; }
.main-col { min-width: 0; }  /* bez tego długie linki rozpychają grid */
.side { padding: 1.2em 0.8em; font-size: 0.82em; color: #24292f; }
.side h3 { font-size: 0.92em; margin: 1.1em 0 0.4em; color: #57606a;
           text-transform: uppercase; letter-spacing: 0.04em; }
.side h3:first-child { margin-top: 0; }
.side-left { border-right: 1px solid #d0d7de; }
.side-right { border-left: 1px solid #d0d7de; }

/* Pasek jest „przyklejony” przy przewijaniu, żeby liczby i wykresy były
   widoczne także po zjechaniu do dalszych kategorii. */
@media (min-width: 1100px) {
  .side { position: sticky; top: 0; max-height: 100vh; overflow-y: auto; }
}

table.stats { width: 100%; border-collapse: collapse; }
table.stats th { text-align: left; font-weight: 400; color: #57606a;
                 padding: 0.18em 0; font-size: 0.95em; }
table.stats td { text-align: right; font-variant-numeric: tabular-nums;
                 font-weight: 600; padding: 0.18em 0; }
table.stats td.ok { color: #1a7f37; }
table.stats td.new { color: #0969da; }
table.stats td.urgent { color: #cf222e; }

/* Pasek filtrów. Przyciski przełączane (klasa .on = widoczne),
   zgaszone = odfiltrowane. */
.filters { background: #fff; border: 1px solid #d0d7de; border-radius: 6px;
           padding: 0.6em 0.8em; margin: 0 0 1em; }
.frow { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35em;
        margin: 0.25em 0; }
.flabel { font-size: 0.82em; color: #57606a; min-width: 7.5em; }
.fbtn { font: inherit; font-size: 0.82em; cursor: pointer; padding: 0.2em 0.6em;
        border: 1px solid #d0d7de; border-radius: 999px; background: #f6f8fa;
        color: #8c959f; text-decoration: line-through; }
.fbtn.on { background: #ddf4ff; border-color: #54aeff; color: #0a3069;
           text-decoration: none; }
.fbtn.act { background: #f6f8fa; color: #24292f; text-decoration: none;
            border-radius: 6px; }
.fbtn:hover { border-color: #0969da; }
.fcount { margin-left: 0.4em; font-size: 0.86em; opacity: 0.75; }
.fsummary { font-size: 0.82em; color: #57606a; margin-left: 0.6em; }

/* Odznaki rodzaju umowy na karcie oferty. UoP wyróżniony zielenią, bo to
   forma dająca stabilność, o którą w tym projekcie chodzi. */
.contract { font-size: 0.68em; font-weight: 700; padding: 0.16em 0.5em;
            border-radius: 999px; margin-left: 0.4em; vertical-align: middle;
            background: #eaeef2; color: #57606a; white-space: nowrap; }
.contract.c-uop { background: #dafbe1; color: #116329; }
.contract.c-uz { background: #fff8c5; color: #7d4e00; }
.contract.c-b2b { background: #ddf4ff; color: #0a3069; }
.contract.c-dzielo { background: #fbefff; color: #6639ba; }

.chart { margin-bottom: 1.1em; }
.chart h4 { font-size: 0.82em; font-weight: 600; color: #57606a;
            margin: 0 0 0.3em; }
.chart svg { width: 100%; height: auto; }
.chart text.cl { font-size: 9px; fill: #57606a; }
.chart text.cv { font-size: 9px; fill: #6e7781;
                 font-variant-numeric: tabular-nums; }
.chart text.cd { font-size: 15px; font-weight: 700; fill: #24292f; }

/* Wąski ekran i druk: paski schodzą pod treść i tracą obramowania,
   żeby nie ciąć kolumny na kartce. */
@media (max-width: 1099px) {
  .layout { grid-template-columns: 1fr; }
  .side { border: 0; border-top: 1px solid #d0d7de; max-width: 960px;
          margin: 0 auto; }
  .side-right { display: grid; grid-template-columns: repeat(2, 1fr);
                gap: 0 1.5em; }
  .side-right h3 { grid-column: 1 / -1; }
}
@media print {
  .layout { grid-template-columns: 1fr; }
  .side { border: 0; page-break-inside: avoid; }
}
.legend { margin: 1em 0; font-size: .88em; color: var(--muted); }
.legend span { display: inline-block; margin-right: 1em; }
.dot {
    display: inline-block; width: .8em; height: .8em; border-radius: 50%;
    margin-right: .35em; vertical-align: middle;
}
.dot.urgent { background: var(--urgent); }
.dot.soon { background: var(--soon); }
.dot.ok { background: var(--ok); }
.dot.unknown { background: var(--unknown); }
h2.category {
    margin: 1.6em 0 .6em;
    padding: .45em .7em;
    border-radius: 8px;
    background: #ece2f3;
    color: var(--accent);
    border-left: 6px solid var(--accent);
    font-size: 1.25em;
}
.count { color: var(--muted); font-weight: normal; font-size: .8em; }
.offer {
    background: var(--card);
    border-radius: 10px;
    padding: 1em 1.1em;
    margin: .8em 0;
    box-shadow: 0 1px 3px rgba(0,0,0,.08);
    border-left: 6px solid var(--unknown);
}
.offer.urgent { border-left-color: var(--urgent); }
.offer.soon { border-left-color: var(--soon); }
.offer.ok { border-left-color: var(--ok); }
.offer h3 { margin: 0 0 .3em; font-size: 1.1em; }
.badge {
    display: inline-block; padding: .12em .6em; border-radius: 999px;
    font-size: .78em; font-weight: 600; color: #fff; margin-left: .4em;
}
.badge.urgent { background: var(--urgent); }
.badge.soon { background: var(--soon); }
.badge.ok { background: var(--ok); }
.badge.unknown { background: var(--unknown); }
/* Znacznik świeżości oferty (kiedy się pojawiła). */
.fresh {
    display: inline-block; padding: .12em .6em; border-radius: 999px;
    font-size: .78em; font-weight: 700; margin-left: .4em;
}
.fresh-new { background: #16a34a; color: #fff; }        /* NOWE — zielony */
.fresh-recent { background: #d1fae5; color: #065f46; }  /* ≤7 dni */
.fresh-old { background: #eceff1; color: #607d8b; }     /* starsze */
/* Wyróżnienie karty nowej oferty. */
.offer.is-new {
    border-left-width: 8px;
    box-shadow: 0 2px 8px rgba(22,163,74,.18);
    background: #f6fff9;
}
/* Oferta już KLIKNIĘTA (otwarta wcześniej) — wygaszona, by nie rozpraszała.
   Stan trzymany w localStorage przeglądarki (raport jest plikiem offline). */
.offer.clicked {
    opacity: .55;
    background: #f7f7f8;
}
.offer.clicked h3 { text-decoration: line-through; text-decoration-thickness: 1px; }
.seen-mark {
    display: inline-block; padding: .12em .6em; border-radius: 999px;
    font-size: .75em; font-weight: 600; margin-left: .4em;
    background: #455a64; color: #fff;
}
/* Pasek narzędzi trackingu (licznik + akcje). */
.toolbar {
    display: flex; flex-wrap: wrap; gap: .6em; align-items: center;
    background: #fff; border: 1px solid #dde3e8; border-radius: 8px;
    padding: .6em .8em; margin: .8em 0; font-size: .9em;
}
.toolbar button {
    font: inherit; cursor: pointer; border: 1px solid #b0bec5;
    background: #eceff1; border-radius: 6px; padding: .3em .7em;
}
.toolbar button:hover { background: #cfd8dc; }
.toolbar .counter { font-weight: 700; color: var(--accent); }
.meta { color: var(--muted); font-size: .9em; margin: .2em 0 .5em; }
.desc {
    white-space: pre-wrap;
    background: #fafbfc;
    border-left: 3px solid #d7dee5;
    padding: .6em .8em;
    border-radius: 4px;
    margin: .5em 0;
    font-size: .93em;
}
a { color: #0645ad; text-decoration: none; }
a:hover { text-decoration: underline; }
.links { font-size: .88em; margin-top: .4em; }
.links ul { margin: .3em 0 0; padding-left: 1.2em; }
/* Sekcja "dopasowane do profilu" — wyróżniona, na samej górze raportu. */
.profile-box {
    background: linear-gradient(135deg, #fff7ed 0%, #fffbeb 100%);
    border: 2px solid #f59e0b; border-radius: 10px;
    padding: .9em 1.1em; margin: 1em 0 1.4em;
}
.profile-box h2 {
    margin: 0 0 .2em; font-size: 1.2em; color: #b45309;
    background: none; border: none; padding: 0;
}
.profile-box .hint { color: #78716c; font-size: .88em; margin: 0 0 .6em; }
.profile-tags { font-size: .8em; color: #92400e; margin-top: .3em; }
.match {
    display: inline-block; padding: .12em .6em; border-radius: 999px;
    font-size: .75em; font-weight: 700; margin-left: .4em;
    background: #f59e0b; color: #fff;
}
.match.weak { background: #fcd34d; color: #78350f; }
/* Zwijana lista niedawno zamkniętych trafień z profilu. */
.closed-matches { margin-top: .8em; }
.closed-matches summary {
    cursor: pointer; font-weight: 600; color: #92400e; font-size: .92em;
}
.closed-matches .offer { opacity: .75; }
/* Sekcja diagnostyczna (co się nie pobrało) — zwinięta, nie rozprasza. */
.failures {
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    padding: .6em .9em; margin: 1.2em 0; font-size: .88em;
}
.failures summary { cursor: pointer; font-weight: 600; color: #b26a00; }
.failures ul { margin: .2em 0 .8em; padding-left: 1.3em; }
footer { text-align: center; color: var(--muted); font-size: .82em; padding: 2em 0; }
"""


# Skrypt trackingu klikania wstawiany do raportu HTML.
#
# Raport jest statycznym plikiem otwieranym z dysku (file://), bez serwera,
# więc kliknięcia nie mogą być wysłane do backendu. Zapisujemy je w
# localStorage przeglądarki pod kluczem BIP_KRK_CLICKED jako mapę
# { "<nab_id>": "<data ISO kliknięcia>" }. Dzięki temu:
#  * oferta raz otwarta jest wizualnie wygaszona (łatwo odróżnić "widziane"
#    od "jeszcze nieoglądanych") i to działa także w kolejnych raportach,
#  * licznik pokazuje, ile ofert zostało jeszcze nieprzejrzanych,
#  * przycisk "Eksportuj" pozwala pobrać stan do pliku clicks.json, który
#    można wczytać do datasetu (skrypt importujący), aby informacja
#    przetrwała zmianę przeglądarki/komputera.
# Skrypt przeglądarkowy (tracking + filtrowanie) żyje w osobnym module —
# patrz docstring ``report_script``.
HTML_TRACKING_SCRIPT = report_script.HTML_TRACKING_SCRIPT



def build_failures_section(failures: Dict[str, dict]) -> str:
    """Buduje sekcję HTML z niepowodzeniami pobierania (diagnostyka).

    Pokazuje, czego NIE udało się pobrać w ostatnich przebiegach — zgodnie
    z zasadą "nic nie ginie po cichu". Najważniejsze przypadki:

    * ``dead_link_fixed_from_archive`` — BIP zostawił martwy link na liście
      aktualnej, a działający adres znaleziono w archiwum (naprawione),
    * ``possible_stale_link`` — ta sama jednostka występuje jako aktywna
      i archiwalna (link na liście aktualnej może być martwy),
    * ``http_404`` / ``timeout`` — strona nie odpowiada,
    * ``no_praca_link`` — jednostka bez zakładki "PRACA - NOWE".

    Args:
        failures: rekordy z dziennika failures.json.

    Returns:
        Fragment HTML (pusty łańcuch, gdy nie ma czego pokazać).
    """
    # Pomijamy wpisy już rozwiązane oraz zwykły brak zakładki PRACA
    # (to normalne dla wielu jednostek i tylko zaśmiecałoby raport).
    interesting = [
        rec for rec in failures.values()
        if not rec.get("resolved") and rec.get("reason") != "no_praca_link"
    ]
    if not interesting:
        return ""

    def esc(value: object) -> str:
        """Escapuje tekst do HTML."""
        return html_lib.escape(str(value if value is not None else ""))

    # Grupujemy po powodzie, aby raport był czytelny.
    by_reason: Dict[str, List[dict]] = {}
    for record in interesting:
        by_reason.setdefault(str(record.get("reason")), []).append(record)

    parts: List[str] = []
    parts.append("<details class='failures'>")
    parts.append(
        f"<summary>Diagnostyka pobierania — {len(interesting)} "
        "zgłoszeń (kliknij, aby rozwinąć)</summary>"
    )
    for reason in sorted(by_reason):
        items = by_reason[reason]
        parts.append(f"<p class='meta'><strong>{esc(reason)}</strong> "
                     f"({len(items)})</p><ul>")
        for record in items[:25]:
            parts.append(
                f"<li>{esc(record.get('key'))} — "
                f"<a href='{esc(record.get('url'))}' target='_blank'>link</a>"
                f" <span class='meta'>{esc(record.get('detail'))}</span></li>"
            )
        if len(items) > 25:
            parts.append(f"<li class='meta'>… i {len(items) - 25} więcej</li>")
        parts.append("</ul>")
    parts.append("</details>")
    return "\n".join(parts)


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

    parts.append("<div class='frow'><span class='flabel'>Dopasowanie:"
                 "</span>")
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

    parts.append(
        "<div class='frow'>"
        "<button type='button' class='fbtn act' id='f-all'>"
        "Pokaż wszystkie</button>"
        "<span class='fsummary' id='f-summary'></span>"
        "</div>"
    )
    parts.append("</div>")
    return "".join(parts)


def build_offer_card(offer: Dict[str, object],
                     details: Dict[str, Dict[str, object]]) -> str:
    """Buduje kartę HTML jednej oferty.

    Wydzielone z :func:`build_html`, bo ta sama karta jest używana w dwóch
    miejscach: w sekcji "dopasowane do profilu" na górze raportu oraz
    w zwykłym grupowaniu po kategoriach.

    Args:
        offer: wzbogacony rekord oferty (kategoria, pilność, świeżość,
            dopasowanie do profilu).
        details: mapa klucz oferty -> szczegóły (dla opisu i odnośników).

    Returns:
        Fragment HTML z kartą oferty.
    """
    def esc(value: object) -> str:
        """Escapuje tekst do HTML."""
        return html_lib.escape(str(value if value is not None else ""))

    parts: List[str] = []
    urgency = str(offer.get("urgency", "unknown"))
    detail_url = offer.get("detail_url") or ""
    key = f"nab:{offer['nab_id']}" if offer.get("nab_id") else None
    det = details.get(key) if key else None
    body = det.get("body_text") if det else None

    # Etykieta znaczka pilności.
    days = offer.get("days_left")
    if isinstance(days, int) and days >= 0:
        badge_text = f"za {days} dni" if days > 1 else (
            "dziś" if days == 0 else "jutro")
    elif isinstance(days, int):
        badge_text = "po terminie"
    else:
        badge_text = "termin ?"

    # Znacznik świeżości (kiedy oferta się pojawiła).
    fresh_cls = str(offer.get("freshness_cls", "fresh-old"))
    fresh_text = str(offer.get("freshness", ""))
    is_new_cls = " is-new" if offer.get("is_new") else ""

    # Atrybut data-nab pozwala skryptowi trackingu rozpoznać ofertę
    # i zapamiętać jej kliknięcie w localStorage przeglądarki.
    nab_attr = esc(offer.get("nab_id") or "")
    # Znaczek dopasowania do profilu (kultura/sztuka/grafika).
    level = str(offer.get("profile_level") or "none")
    if level == "strong":
        match_badge = "<span class='match'>DLA CIEBIE</span>"
    elif level == "weak":
        match_badge = "<span class='match weak'>może pasować</span>"
    else:
        match_badge = ""
    # Atrybuty data-* zasilają filtrowanie po stronie przeglądarki
    # (pasek filtrów w nagłówku). Trzymamy je na karcie, a nie w osobnej
    # strukturze JS, żeby raport pozostał jednym plikiem bez danych
    # dublowanych w dwóch miejscach.
    contracts = offer.get("contract_types") or [ct.UNKNOWN]
    contract_attr = " ".join(str(c) for c in contracts)
    contract_badges = "".join(
        f"<span class='contract c-{esc(code)}' "
        f"title='{esc(ct.DESCRIPTIONS.get(str(code), ''))}'>"
        f"{esc(ct.LABELS.get(str(code), code))}</span>"
        for code in contracts
    )
    parts.append(
        f"<div class='offer {esc(urgency)}{is_new_cls}' "
        f"data-nab='{nab_attr}' "
        f"data-source='{esc(offer.get('source') or '?')}' "
        f"data-contract='{esc(contract_attr)}' "
        f"data-level='{esc(level)}'>"
    )
    parts.append(
        f"<h3>{esc(offer.get('title') or '(bez tytułu)')}"
        f"<span class='fresh {esc(fresh_cls)}'>{esc(fresh_text)}</span>"
        f"{contract_badges}"
        f"<span class='badge {esc(urgency)}'>{esc(badge_text)}</span>"
        f"{match_badge}"
        "</h3>"
    )
    parts.append("<div class='meta'>")
    parts.append(f"{esc(offer.get('unit_name') or '')} · ")
    parts.append(
        f"Termin: <strong>{esc(deadline_label(offer))}</strong> · "
    )
    parts.append(f"Nr ref.: {esc(offer.get('ref_number') or 'brak')}")
    # Źródło oferty — BIP, nuzle czy portal oświatowy.
    source_labels = {
        "bip_global": "BIP (lista globalna)",
        "bip_unit": "BIP (strona jednostki)",
        "nuzle": "nuzle.pl",
        "ofertypracy_edu": "ofertypracy.edu.pl",
    }
    source = str(offer.get("source") or "")
    if source:
        parts.append(
            f" · Źródło: {esc(source_labels.get(source, source))}"
        )
    parts.append("</div>")
    if detail_url:
        parts.append(
            f"<div class='meta'>Szczegóły: "
            f"<a href='{esc(detail_url)}' target='_blank'>"
            f"{esc(detail_url)}</a></div>"
        )
    parts.append(
        f"<div class='desc'>{esc(summarize_body(body))}</div>"
    )
    # Obszary dopasowania do profilu (dlaczego ta oferta pasuje).
    tags = offer.get("profile_tags") or []
    if tags and level != "none":
        parts.append(
            f"<div class='profile-tags'>Pasuje do: "
            f"{esc(', '.join(str(t) for t in tags))}</div>"
        )
    if det and det.get("links"):
        doc_links = [
            lnk for lnk in det["links"]
            if lnk.get("text") and len(lnk["text"]) > 3
        ][:10]
        if doc_links:
            parts.append("<div class='links'>Odnośniki w ogłoszeniu:"
                         "<ul>")
            for lnk in doc_links:
                parts.append(
                    f"<li><a href='{esc(lnk['url'])}' target='_blank'>"
                    f"{esc(lnk['text'])}</a></li>"
                )
            parts.append("</ul></div>")
    parts.append("</div>")
    return "\n".join(parts)


def build_profile_section(
    offers: List[Dict[str, object]],
    details: Dict[str, Dict[str, object]],
    recent_closed: Optional[List[Dict[str, object]]] = None,
    profile_description: str = "",
) -> str:
    """Buduje wyróżnioną sekcję „dopasowane do profilu” na górze raportu.

    Powstała w odpowiedzi na realny problem: wśród kilkuset ofert z BIP
    i portali tonęły te naprawdę trafne (kultura, sztuka, grafika, animacja),
    przez co raport wyglądał jakby zawierał „głównie administrację i
    sprzątanie”. Tutaj zbieramy oferty z wynikiem dopasowania i pokazujemy
    je NA SAMEJ GÓRZE, posortowane po trafności.

    Dodatkowo, w zwijanej liście, pokazujemy **niedawno zamknięte** trafienia
    z profilu. Nie da się już na nie aplikować, ale mają wartość
    orientacyjną: pokazują, jakie stanowiska w tym profilu realnie się
    pojawiają i w jakich instytucjach — co pomaga ocenić, gdzie warto
    pilnować ogłoszeń.

    Args:
        offers: wszystkie wzbogacone oferty raportu (aktualne).
        details: mapa klucz oferty -> szczegóły.
        recent_closed: opcjonalna lista dopasowanych ofert już zamkniętych
            (do zwijanej sekcji orientacyjnej).

    Returns:
        Fragment HTML sekcji (pusty, gdy nie ma dopasowań).
    """
    matched = [
        offer for offer in offers
        if str(offer.get("profile_level") or "none") in ("strong", "weak")
    ]
    if not matched and not recent_closed:
        return ""

    # Najpierw mocne dopasowania, potem wg trafności, a przy równej — wg
    # pilności terminu (bliższy termin wyżej).
    def sort_key(offer: Dict[str, object]) -> Tuple[int, int, int]:
        """Klucz sortowania dopasowanych ofert."""
        strong = 0 if offer.get("profile_level") == "strong" else 1
        score = -int(offer.get("profile_score") or 0)
        days = offer.get("days_left")
        urgency = days if isinstance(days, int) else 10_000
        return (strong, score, urgency)

    matched.sort(key=sort_key)

    strong_count = sum(1 for o in matched if o.get("profile_level") == "strong")

    parts: List[str] = ["<div class='profile-box'>"]
    parts.append(
        f"<h2>Dopasowane do profilu — {len(matched)} "
        f"{'oferta' if len(matched) == 1 else 'ofert'} "
        f"(mocnych trafień: {strong_count})</h2>"
    )
    # Opis pochodzi z definicji profilu (pakiet ``profiles``), bo aplikacja
    # obsługuje kilka profili i zaszyty tekst o kulturze byłby nieprawdą
    # w raporcie dla profilu danych/AI.
    parts.append(
        f"<p class='hint'>{html_lib.escape(profile_description)} "
        "Pominięte stanowiska jawnie spoza profilu.</p>"
    )
    for offer in matched:
        parts.append(build_offer_card(offer, details))

    # Niedawno zamknięte trafienia — wartość orientacyjna (jakie stanowiska
    # w tym profilu się pojawiają i gdzie). Zwinięte, by nie rozpraszały.
    if recent_closed:
        parts.append("<details class='closed-matches'>")
        parts.append(
            f"<summary>Niedawno zamknięte oferty z profilu — "
            f"{len(recent_closed)} (podpowiedź, gdzie warto pilnować "
            "ogłoszeń)</summary>"
        )
        for offer in recent_closed:
            parts.append(build_offer_card(offer, details))
        parts.append("</details>")

    parts.append("</div>")
    return "\n".join(parts)


class ReportMeta(NamedTuple):
    """Metadane raportu — wszystko poza samymi ofertami.

    Zgrupowane w jedną strukturę, bo podróżują razem i bez tego
    ``build_html`` miało siedem argumentów pozycyjnych, co łatwo pomylić
    przy wywołaniu.

    Attributes:
        failures: rekordy dziennika niepowodzeń (sekcja diagnostyczna).
        recent_closed: niedawno zamknięte trafienia z profilu.
        profile_label: nazwa profilu w nagłówku raportu.
        profile_description: zdanie opisujące profil pod nagłówkiem sekcji.
        stats: statystyki z ``report_stats.collect_stats`` do pasków
            bocznych; gdy None, paski się nie pojawiają.
    """

    failures: Optional[Dict[str, dict]] = None
    recent_closed: Optional[List[Dict[str, object]]] = None
    profile_label: str = ""
    profile_description: str = ""
    stats: Optional[Dict[str, object]] = None


def build_html(
    grouped: List[Tuple[str, List[Dict[str, object]]]],
    details: Dict[str, Dict[str, object]],
    total: int,
    meta: Optional[ReportMeta] = None,
) -> str:
    """Buduje kolorowy, estetyczny raport HTML pogrupowany po kategoriach.

    Args:
        grouped: oferty pogrupowane po kategorii (posortowane po pilności).
        details: mapa klucz oferty -> szczegóły.
        total: łączna liczba ofert w raporcie.
        failures: rekordy dziennika niepowodzeń (do sekcji diagnostycznej).

    Returns:
        Kompletny dokument HTML jako łańcuch.
    """
    def esc(value: object) -> str:
        """Escapuje tekst do bezpiecznego wstawienia w HTML."""
        return html_lib.escape(str(value if value is not None else ""))

    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang='pl'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, "
                 "initial-scale=1'>")
    meta = meta or ReportMeta()
    failures = meta.failures
    recent_closed = meta.recent_closed
    profile_label = meta.profile_label
    profile_description = meta.profile_description

    heading = "Raport ofert pracy — BIP Kraków"
    if profile_label:
        heading = f"{heading} · {profile_label}"
    parts.append(f"<title>{html_lib.escape(heading)}</title>")
    parts.append(f"<style>{HTML_STYLE}</style></head><body>")

    # Nagłówek raportu.
    parts.append("<header><div class='wrap'>")
    parts.append(f"<h1>{html_lib.escape(heading)}</h1>")
    parts.append(
        f"<div class='meta'>Wygenerowano: {esc(bc.now_iso())} · "
        f"ofert w raporcie: <strong>{total}</strong></div>"
    )
    parts.append("</div></header>")

    # Układ trzykolumnowy: liczby po lewej, treść w środku, wykresy po
    # prawej. Przy wąskim ekranie (i przy druku) paski schodzą pod treść —
    # patrz reguły @media w HTML_STYLE.
    stats = meta.stats
    parts.append("<div class='layout'>")
    if stats:
        parts.append(report_stats.build_stats_sidebar(stats))
    parts.append("<div class='main-col'><div class='wrap'>")

    # Legenda kolorów pilności oraz świeżości.
    parts.append(
        "<div class='legend'>"
        "<strong>Termin:</strong> "
        "<span><i class='dot urgent'></i>≤ 3 dni</span>"
        "<span><i class='dot soon'></i>≤ 7 dni</span>"
        "<span><i class='dot ok'></i>&gt; 7 dni</span>"
        "<span><i class='dot unknown'></i>termin nieznany</span>"
        " &nbsp;|&nbsp; <strong>Świeżość:</strong> "
        "<span class='fresh fresh-new'>NOWE (nieoglądane)</span> "
        "<span class='fresh fresh-recent'>≤ 7 dni</span> "
        "<span class='fresh fresh-old'>starsze</span>"
        "</div>"
    )

    # Pasek narzędzi trackingu klikania (działa lokalnie, bez serwera).
    parts.append(
        "<div class='toolbar'>"
        "<span class='counter' id='counter'>—</span>"
        "<button type='button' id='mark-all'>Oznacz wszystkie jako "
        "przejrzane</button>"
        "<button type='button' id='export-seen'>Eksportuj stan "
        "(clicks.json)</button>"
        "<button type='button' id='clear-seen'>Wyczyść historię</button>"
        "<span class='meta'>Kliknięte oferty są wygaszane i pamiętane "
        "w tej przeglądarce.</span>"
        "</div>"
    )

    if total == 0:
        parts.append("<p>Brak ofert spełniających kryteria.</p>")

    # Sekcja "dopasowane do profilu" — NA GÓRZE, przed kategoriami, bo to
    # ona jest właściwym celem raportu. Zbieramy oferty ze wszystkich grup.
    all_offers: List[Dict[str, object]] = []
    for _label, offers_in_group in grouped:
        all_offers.extend(offers_in_group)
    profile_section = build_profile_section(
        all_offers, details, recent_closed, profile_description)
    if stats:
        parts.append(build_filter_bar(stats))

    if profile_section:
        parts.append(profile_section)

    for label, offers in grouped:
        parts.append(
            f"<h2 class='category'>{esc(label)} "
            f"<span class='count'>({len(offers)})</span></h2>"
        )
        for offer in offers:
            parts.append(build_offer_card(offer, details))

    parts.append("</div>")  # .wrap

    # Sekcja diagnostyczna: czego nie udało się pobrać (zwinięta domyślnie).
    if failures:
        section = build_failures_section(failures)
        if section:
            parts.append("<div class='wrap'>")
            parts.append(section)
            parts.append("</div>")
    parts.append("</div>")  # koniec kolumny głównej
    if stats:
        parts.append(report_stats.build_charts_sidebar(stats))
    parts.append("</div>")  # koniec layoutu
    parts.append(
        "<footer>Źródło danych: Biuletyn Informacji Publicznej Miasta "
        "Krakowa · raport wygenerowany automatycznie</footer>"
    )
    # Skrypt trackingu klikania — na końcu, gdy karty są już w dokumencie.
    parts.append(HTML_TRACKING_SCRIPT)
    parts.append("</body></html>")
    return "\n".join(parts)
