#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrypt 5 — generuje raport z ofert pracy wraz z linkami do szczegółów.

Łączy dane ze wszystkich wcześniejszych etapów:

* ``data/offers.json``        — lista ofert (status, termin, nr ref.),
* ``data/offer_details.json`` — szczegóły pobrane dla trwających naborów,
* ``data/units.json``         — nazwy, kategorie i stan jednostek.

Raport grupuje oferty **po kategorii jednostki** (np. "Kultura i Sztuka",
"Szkolnictwo", "Opieka zdrowotna"), a wewnątrz każdej kategorii sortuje je
**po pilności** — od najbliższego terminu składania (najpilniejsze na górze).
Kolejność kategorii jest ustalona priorytetem: Kultura i Sztuka jest
najważniejsza i pojawia się jako pierwsza.

Raport powstaje w dwóch formatach w katalogu ``reports/``:

* Markdown (``raport_praca_YYYY-MM-DD_HHMMSS.md``) — czytelny na GitHubie,
* HTML (``raport_praca_YYYY-MM-DD_HHMMSS.html``) — kolorowy, estetyczny,
  do otwarcia w przeglądarce, z odnośnikami do pełnych szczegółów i wizualnym
  oznaczeniem pilności (kolor zależny od liczby dni do terminu).

Domyślnie raport obejmuje aktualne (trwające i aktywne) nabory. Opcją
``--all`` można ująć wszystkie zebrane oferty.

Uruchomienie:

    python 5_generate_report.py
    python 5_generate_report.py --all
"""

from __future__ import annotations

import argparse
import html as html_lib
import logging
from datetime import date
from typing import Dict, List, Optional, Tuple

import bip_common as bc

# Priorytet kategorii — im niższa liczba, tym wyżej w raporcie. Dopasowanie
# jest po fragmencie nazwy (małe litery), aby złapać warianty nazewnictwa
# używane na stronie BIP (np. "Kultura", "Instytucje kultury"). Kategorie
# niewymienione trafiają na koniec (priorytet domyślny).
CATEGORY_PRIORITY: List[Tuple[str, str, int]] = [
    # (fragment do dopasowania, ładna etykieta wyświetlana, priorytet)
    ("kultur", "Kultura i Sztuka", 0),
    ("sztuk", "Kultura i Sztuka", 0),
    ("edukac", "Szkolnictwo i Edukacja", 1),
    ("szkol", "Szkolnictwo i Edukacja", 1),
    ("pomoc", "Pomoc społeczna", 2),
    ("zdrow", "Opieka zdrowotna", 3),
    ("sport", "Sport i Rekreacja", 4),
    ("komunal", "Gospodarka komunalna", 5),
    ("porządek", "Porządek publiczny i bezpieczeństwo", 6),
    ("bezpiecz", "Porządek publiczny i bezpieczeństwo", 6),
    ("spółk", "Spółki miejskie", 7),
    ("inne", "Inne podmioty", 8),
]

# Priorytet i etykieta dla kategorii nierozpoznanej.
DEFAULT_PRIORITY = 99
DEFAULT_LABEL = "Pozostałe"


def parse_deadline_to_date(deadline: Optional[str]) -> Optional[date]:
    """Zamienia 'YYYY-MM-DD' na obiekt daty (lub None).

    Args:
        deadline: łańcuch daty albo None.

    Returns:
        Obiekt daty albo None, gdy format nieobsługiwany.
    """
    if not deadline:
        return None
    try:
        year, month, day = (int(part) for part in deadline.split("-"))
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    """Wyłuskuje datę (bez czasu) z łańcucha ISO 8601.

    Pola ``first_seen``/``last_seen`` mają postać '2026-09-22T15:58:21+02:00'.
    Do liczenia "ile dni temu" wystarczy część z datą (pierwsze 10 znaków).

    Args:
        value: łańcuch ISO 8601 albo None.

    Returns:
        Obiekt :class:`datetime.date` albo None.
    """
    if not value or len(value) < 10:
        return None
    return parse_deadline_to_date(value[:10])


def days_since(seen: Optional[date]) -> Optional[int]:
    """Liczy, ile dni temu (względem dziś) wystąpiła data.

    Args:
        seen: data pierwszego zaobserwowania albo None.

    Returns:
        Liczbę dni (0 = dzisiaj) albo None, gdy brak daty.
    """
    if seen is None:
        return None
    return (date.today() - seen).days


def freshness_label(days_ago: Optional[int], is_new: bool) -> str:
    """Buduje czytelny opis świeżości oferty.

    Dla ofert "nowych/nieoglądanych" (pojawiły się od ostatniego raportu)
    dodaje prefiks "NOWE:". Dla pozostałych podaje samo "N dni temu".

    Args:
        days_ago: ile dni temu pojawiła się oferta (0 = dzisiaj).
        is_new: czy oferta jest nowa/nieoglądana od ostatniego raportu.

    Returns:
        Tekst świeżości (np. "NOWE: dzisiaj", "NOWE: 1 dzień temu",
        "2 dni temu", "pojawienie: brak danych").
    """
    if days_ago is None:
        return "data pojawienia: brak danych"
    # Fragment "N dni temu" z poprawną polską odmianą.
    if days_ago == 0:
        when = "dzisiaj"
    elif days_ago == 1:
        when = "1 dzień temu"
    else:
        when = f"{days_ago} dni temu"
    return f"NOWE: {when}" if is_new else when


def freshness_class(days_ago: Optional[int], is_new: bool) -> str:
    """Zwraca klasę CSS znacznika świeżości oferty.

    Args:
        days_ago: ile dni temu pojawiła się oferta.
        is_new: czy oferta jest nowa/nieoglądana.

    Returns:
        Klasę CSS: 'fresh-new' (nowa), 'fresh-recent' (≤7 dni), 'fresh-old'.
    """
    if is_new:
        return "fresh-new"
    if days_ago is not None and days_ago <= 7:
        return "fresh-recent"
    return "fresh-old"


def classify_category(raw_category: Optional[str]) -> Tuple[str, int]:
    """Mapuje surową kategorię jednostki na ładną etykietę i priorytet.

    Args:
        raw_category: kategoria zapisana przy jednostce (z units.json) lub None.

    Returns:
        Krotka (etykieta wyświetlana, priorytet sortowania kategorii).
    """
    if raw_category:
        lowered = raw_category.lower()
        for fragment, label, priority in CATEGORY_PRIORITY:
            if fragment in lowered:
                return label, priority
    return DEFAULT_LABEL, DEFAULT_PRIORITY


def days_until(deadline: Optional[date]) -> Optional[int]:
    """Liczy liczbę dni od dziś do terminu składania.

    Args:
        deadline: data terminu lub None.

    Returns:
        Liczbę dni (może być ujemna, gdy termin minął) albo None.
    """
    if deadline is None:
        return None
    return (deadline - date.today()).days


def urgency_class(days: Optional[int]) -> str:
    """Zwraca klasę CSS pilności oferty wg liczby dni do terminu.

    Args:
        days: liczba dni do terminu (lub None, gdy termin nieznany).

    Returns:
        Nazwę klasy CSS: 'urgent' (≤3 dni), 'soon' (≤7), 'ok' (>7),
        'unknown' (brak terminu).
    """
    if days is None:
        return "unknown"
    if days <= 3:
        return "urgent"
    if days <= 7:
        return "soon"
    return "ok"


def is_current(offer: Dict[str, object]) -> bool:
    """Czy oferta jest aktualna (trwający, aktywny, termin nieprzeterminowany).

    Args:
        offer: rekord oferty.

    Returns:
        True, gdy ofertę należy uznać za aktualną.
    """
    if offer.get("status") != "trwajacy":
        return False
    if not offer.get("active", True):
        return False
    deadline = parse_deadline_to_date(offer.get("deadline"))
    if deadline is not None and deadline < date.today():
        return False
    return True


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


def enrich_offers(
    offers: List[Dict[str, object]],
    units: Dict[str, dict],
    last_report_at: Optional[date] = None,
) -> List[Dict[str, object]]:
    """Wzbogaca oferty o kategorię jednostki, pilność i świeżość.

    Args:
        offers: lista rekordów ofert.
        units: rekordy jednostek z units.json (dla kategorii).
        last_report_at: data ostatniego wygenerowanego raportu. Oferta jest
            uznawana za "nową/nieoglądaną", gdy jej first_seen jest nowszy
            niż ten znacznik. Gdy None (pierwszy raport) — nowe są oferty
            widziane dzisiaj.

    Returns:
        Nową listę ofert z polami: category_label, category_priority,
        deadline_date, days_left, urgency, first_seen_date, days_ago,
        is_new, freshness, freshness_cls.
    """
    enriched: List[Dict[str, object]] = []
    for offer in offers:
        unit = units.get(offer.get("unit_key") or "", {})
        raw_category = unit.get("category")
        label, priority = classify_category(raw_category)

        deadline_date = parse_deadline_to_date(offer.get("deadline"))
        days_left = days_until(deadline_date)

        # Świeżość: kiedy pierwszy raz zobaczyliśmy ofertę.
        first_seen = parse_iso_date(offer.get("first_seen"))
        days_ago = days_since(first_seen)
        if first_seen is None:
            is_new = False
        elif last_report_at is None:
            # Pierwszy raport — za nowe uznajemy oferty widziane dzisiaj.
            is_new = days_ago == 0
        else:
            # Nowe = pojawiły się po ostatnim raporcie (jeszcze nieoglądane).
            is_new = first_seen > last_report_at

        item = dict(offer)
        item["category_label"] = label
        item["category_priority"] = priority
        item["deadline_date"] = deadline_date
        item["days_left"] = days_left
        item["urgency"] = urgency_class(days_left)
        item["first_seen_date"] = first_seen
        item["days_ago"] = days_ago
        item["is_new"] = is_new
        item["freshness"] = freshness_label(days_ago, is_new)
        item["freshness_cls"] = freshness_class(days_ago, is_new)
        enriched.append(item)
    return enriched


def sort_key(offer: Dict[str, object]) -> Tuple[int, int, int, str]:
    """Klucz sortowania wewnątrz kategorii.

    Kolejność:
    1. NOWE/nieoglądane oferty na górze (is_new),
    2. wśród nowych — od najnowszej (najmniejsze days_ago pierwsze),
    3. pozostałe — wg pilności (najbliższy termin pierwszy),
    4. tytuł (stabilizacja).

    Args:
        offer: wzbogacony rekord oferty.

    Returns:
        Krotkę sortującą.
    """
    is_new = bool(offer.get("is_new"))
    # NOWE pierwsze: klucz 0 dla nowych, 1 dla reszty.
    new_rank = 0 if is_new else 1

    if is_new:
        # Wśród nowych: od najnowszej (days_ago rosnąco: 0, 1, 2...).
        days_ago = offer.get("days_ago")
        secondary = days_ago if isinstance(days_ago, int) else 10_000
    else:
        # Wśród pozostałych: wg pilności (najbliższy termin pierwszy).
        days_left = offer.get("days_left")
        secondary = days_left if isinstance(days_left, int) else 10_000

    title = str(offer.get("title") or "")
    priority = int(offer.get("category_priority", DEFAULT_PRIORITY))
    return (priority, new_rank, secondary, title)


def group_by_category(
    offers: List[Dict[str, object]],
) -> List[Tuple[str, List[Dict[str, object]]]]:
    """Grupuje oferty po kategorii, zachowując priorytet i sortowanie.

    Args:
        offers: wzbogacone i posortowane oferty.

    Returns:
        Listę krotek (etykieta kategorii, lista ofert), w kolejności
        priorytetu kategorii.
    """
    groups: Dict[str, List[Dict[str, object]]] = {}
    order: Dict[str, int] = {}
    for offer in offers:
        label = str(offer.get("category_label", DEFAULT_LABEL))
        groups.setdefault(label, []).append(offer)
        order[label] = int(offer.get("category_priority", DEFAULT_PRIORITY))

    # Sortujemy kategorie po priorytecie, a przy równym — alfabetycznie.
    ordered_labels = sorted(groups, key=lambda lbl: (order[lbl], lbl))
    return [(label, groups[label]) for label in ordered_labels]


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


def build_markdown(
    grouped: List[Tuple[str, List[Dict[str, object]]]],
    details: Dict[str, Dict[str, object]],
    total: int,
) -> str:
    """Buduje treść raportu w formacie Markdown (pogrupowaną po kategoriach).

    Args:
        grouped: oferty pogrupowane po kategorii (posortowane).
        details: mapa klucz oferty -> szczegóły (z offer_details.json).
        total: łączna liczba ofert w raporcie.

    Returns:
        Łańcuch z treścią Markdown.
    """
    lines: List[str] = []
    lines.append("# Raport ofert pracy — BIP Kraków")
    lines.append("")
    lines.append(f"Wygenerowano: {bc.now_iso()}")
    lines.append("")
    lines.append(f"Liczba ofert w raporcie: **{total}**")
    lines.append("")
    lines.append("Oferty pogrupowane po kategorii; wewnątrz — NOWE "
                 "(nieoglądane) na górze od najnowszych, potem reszta wg "
                 "pilności (najbliższy termin składania).")
    lines.append("")

    for label, offers in grouped:
        lines.append(f"## {label} ({len(offers)})")
        lines.append("")
        for offer in offers:
            title = offer.get("title") or "(bez tytułu)"
            unit_name = offer.get("unit_name") or ""
            ref = offer.get("ref_number") or "brak"
            detail_url = offer.get("detail_url") or ""

            # Prefiks NOWE przy tytule dla ofert nieoglądanych.
            new_prefix = "🆕 " if offer.get("is_new") else ""
            lines.append(f"### {new_prefix}{title}")
            lines.append("")
            lines.append(f"- Jednostka: {unit_name}")
            lines.append(f"- Pojawiło się: **{offer.get('freshness')}**")
            lines.append(f"- Termin składania: **{deadline_label(offer)}**")
            lines.append(f"- Nr referencyjny: {ref}")
            if detail_url:
                lines.append(f"- Szczegóły: [{detail_url}]({detail_url})")
            lines.append("")

            key = f"nab:{offer['nab_id']}" if offer.get("nab_id") else None
            det = details.get(key) if key else None
            body = det.get("body_text") if det else None
            lines.append("**Opis:**")
            lines.append("")
            lines.append("> " + summarize_body(body).replace("\n", "\n> "))
            lines.append("")

            if det and det.get("links"):
                doc_links = [
                    lnk for lnk in det["links"]
                    if lnk.get("text") and len(lnk["text"]) > 3
                ][:10]
                if doc_links:
                    lines.append("**Odnośniki w ogłoszeniu:**")
                    lines.append("")
                    for lnk in doc_links:
                        lines.append(f"- [{lnk['text']}]({lnk['url']})")
                    lines.append("")

    return "\n".join(lines) + "\n"


# Arkusz stylów raportu HTML — kolory kategorii i pilności, karty ofert.
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
footer { text-align: center; color: var(--muted); font-size: .82em; padding: 2em 0; }
"""


def build_html(
    grouped: List[Tuple[str, List[Dict[str, object]]]],
    details: Dict[str, Dict[str, object]],
    total: int,
) -> str:
    """Buduje kolorowy, estetyczny raport HTML pogrupowany po kategoriach.

    Args:
        grouped: oferty pogrupowane po kategorii (posortowane po pilności).
        details: mapa klucz oferty -> szczegóły.
        total: łączna liczba ofert w raporcie.

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
    parts.append("<title>Raport ofert pracy — BIP Kraków</title>")
    parts.append(f"<style>{HTML_STYLE}</style></head><body>")

    # Nagłówek raportu.
    parts.append("<header><div class='wrap'>")
    parts.append("<h1>Raport ofert pracy — BIP Kraków</h1>")
    parts.append(
        f"<div class='meta'>Wygenerowano: {esc(bc.now_iso())} · "
        f"ofert w raporcie: <strong>{total}</strong></div>"
    )
    parts.append("</div></header>")

    parts.append("<div class='wrap'>")

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

    if total == 0:
        parts.append("<p>Brak ofert spełniających kryteria.</p>")

    for label, offers in grouped:
        parts.append(
            f"<h2 class='category'>{esc(label)} "
            f"<span class='count'>({len(offers)})</span></h2>"
        )
        for offer in offers:
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

            parts.append(f"<div class='offer {esc(urgency)}{is_new_cls}'>")
            parts.append(
                f"<h3>{esc(offer.get('title') or '(bez tytułu)')}"
                f"<span class='fresh {esc(fresh_cls)}'>{esc(fresh_text)}</span>"
                f"<span class='badge {esc(urgency)}'>{esc(badge_text)}</span>"
                "</h3>"
            )
            parts.append("<div class='meta'>")
            parts.append(f"{esc(offer.get('unit_name') or '')} · ")
            parts.append(
                f"Termin: <strong>{esc(deadline_label(offer))}</strong> · "
            )
            parts.append(f"Nr ref.: {esc(offer.get('ref_number') or 'brak')}")
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

    parts.append("</div>")  # .wrap
    parts.append(
        "<footer>Źródło danych: Biuletyn Informacji Publicznej Miasta "
        "Krakowa · raport wygenerowany automatycznie</footer>"
    )
    parts.append("</body></html>")
    return "\n".join(parts)


def main() -> int:
    """Punkt wejścia skryptu 5.

    Returns:
        Kod wyjścia (0 = sukces, 1 = brak datasetu ofert).
    """
    parser = argparse.ArgumentParser(
        description="Generuje raport ofert pracy (Markdown + HTML).",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--all", action="store_true",
        help="Ujmij wszystkie oferty (domyślnie tylko aktualne trwające).",
    )
    parser.add_argument(
        "--sample", type=int, default=None, metavar="N",
        help="Tryb próbny: ogranicz raport do N ofert (szybka weryfikacja "
             "prezentacji na istniejących danych).",
    )
    parser.add_argument(
        "--mark-seen", action="store_true",
        help="Zapisz znacznik 'oferty oglądane' (last_report_at) po "
             "wygenerowaniu — kolejny raport nie oznaczy ich jako NOWE.",
    )
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()

    offers_ds = bc.load_dataset(bc.OFFERS_DATASET)
    if not offers_ds["records"]:
        logging.error(
            "Brak ofert w %s — uruchom najpierw skrypty 1-3.",
            bc.OFFERS_DATASET,
        )
        return 1
    details_ds = bc.load_dataset(bc.OFFER_DETAILS_DATASET)
    units_ds = bc.load_dataset(bc.UNITS_DATASET)

    # Znacznik ostatniego raportu — służy do odróżnienia ofert NOWYCH
    # (nieoglądanych) od już prezentowanych. Zapisany w meta ofert.
    last_report_at = parse_iso_date(
        offers_ds.get("meta", {}).get("last_report_at")
    )

    # Wybór ofert do raportu.
    selected = []
    for offer in offers_ds["records"].values():
        if args.all or is_current(offer):
            selected.append(offer)

    # Wzbogacamy o kategorię, pilność i świeżość, sortujemy, grupujemy.
    enriched = enrich_offers(selected, units_ds["records"], last_report_at)
    enriched.sort(key=sort_key)

    # Tryb próbny: ograniczamy liczbę ofert do szybkiej weryfikacji wyglądu.
    if args.sample is not None:
        enriched = enriched[: args.sample]
        logging.info("Tryb próbny: ograniczono raport do %d ofert.",
                     len(enriched))

    grouped = group_by_category(enriched)

    new_count = sum(1 for o in enriched if o.get("is_new"))
    logging.info(
        "Ofert w raporcie: %d (w tym NOWYCH: %d), kategorii: %d.",
        len(enriched), new_count, len(grouped),
    )

    markdown = build_markdown(grouped, details_ds["records"], len(enriched))
    html = build_html(grouped, details_ds["records"], len(enriched))

    stamp = bc.timestamp_str()
    md_path = bc.REPORTS_DIR / f"raport_praca_{stamp}.md"
    html_path = bc.REPORTS_DIR / f"raport_praca_{stamp}.html"

    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    # Oznaczamy oferty jako "oglądane" dopiero na wyraźne życzenie
    # (--mark-seen), żeby tryb próbny ani podgląd nie "zużyły" statusu NOWE.
    if args.mark_seen and not args.sample:
        offers_ds.setdefault("meta", {})["last_report_at"] = bc.now_iso()
        bc.save_dataset(bc.OFFERS_DATASET, offers_ds)
        logging.info("Zapisano znacznik last_report_at (oferty oznaczone "
                     "jako oglądane).")

    logging.info("Zapisano raport Markdown: %s", md_path)
    logging.info("Zapisano raport HTML: %s", html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
