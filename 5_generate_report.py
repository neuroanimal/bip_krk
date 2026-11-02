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
import logging
import re
from datetime import date
from typing import Dict, List, NamedTuple, Optional, Tuple

import bip_common as bc
import contract_type as ct
import dedupe
import geo
import offer_lang
import profile_match
import report_stats
import salary as sal
from profile_match import score_offer
from report_html import (ReportMeta, build_html, deadline_label,
                         summarize_body)

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
    # Kategorie z zewnętrznych źródeł (podpowiedź z pola category_hint).
    ("oświata", "Oświata — stanowiska niepedagogiczne", 2),
    ("komercyjne", "Oferty komercyjne (poza BIP)", 9),
]

# Priorytet i etykieta dla kategorii nierozpoznanej.
DEFAULT_PRIORITY = 99
DEFAULT_LABEL = "Pozostałe"

# Polityka sekcji „niedawno zamknięte trafienia z profilu”:
# ile dni po terminie oferta jest jeszcze warta pokazania (orientacyjnie)
# i ile takich pozycji maksymalnie wypisać, żeby nie zalać raportu.
CLOSED_MATCH_MAX_DAYS = 60
CLOSED_MATCH_LIMIT = 12

# Ile dni oferta może nie być widziana przez żadne źródło, zanim przestanie
# trafiać do raportu (patrz ``is_current``). Tydzień wystarcza, żeby
# chwilowa awaria portalu nie wygasiła ofert, a zarazem żeby stare rekordy
# nie wisiały miesiącami.
MAX_STALE_DAYS = 7


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

    Oferty z zewnętrznych źródeł (nuzle.pl) nie podają terminu składania —
    dla nich decyduje sam fakt, że ogłoszenie jest nadal obecne na portalu
    (``active``). Nie odrzucamy ich tylko dlatego, że nie znamy terminu.

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
    # Bezpiecznik świeżości: oferta, której żadne źródło nie widziało od
    # MAX_STALE_DAYS dni, nie trafia do raportu, nawet jeśli wciąż ma
    # ``active=True``.
    #
    # Powód, znaleziony w danych: 16 rekordów z 22.09 (bez pola
    # ``source``, z czasów przed rozdzieleniem źródeł) nigdy nie zostało
    # wygaszonych, bo każde źródło wygasza WYŁĄCZNIE swoje rekordy,
    # a tych nie posiadało żadne. Wśród nich była „Sprzątaczka —
    # zastępstwo”, którą adresatka słusznie wytknęła. Flaga ``active``
    # zależy od poprawności każdego źródła z osobna; data ostatniego
    # zobaczenia jest niezależna od nich wszystkich.
    last_seen = parse_deadline_to_date(str(offer.get("last_seen") or "")[:10])
    if last_seen is not None and (date.today() - last_seen).days > MAX_STALE_DAYS:
        return False
    return True




class EnrichContext(NamedTuple):
    """Dane pomocnicze do wzbogacania ofert.

    Zgrupowane w jedną strukturę, bo podróżują razem i bez tego
    ``enrich_offers`` miało sześć argumentów pozycyjnych — łatwo pomylić
    kolejność przy wywołaniu.

    Attributes:
        last_report_at: data poprzedniego raportu (do znaczników NOWE).
        clicked_ids: identyfikatory ofert już oglądanych.
        rates: kursy walut do przeliczenia wynagrodzeń.
        coords: mapa ``miejscowość -> (lat, lon)`` do liczenia odległości.
        session: sesja HTTP do dokładnego geokodowania (None = tylko
            pamięć podręczna, bez zapytań).
        geo_cache: pamięć podręczna geokodowania (modyfikowana w miejscu).
    """

    last_report_at: Optional[date] = None
    clicked_ids: Optional[set] = None
    rates: Optional[Dict[str, float]] = None
    coords: Optional[Dict[str, tuple]] = None
    session: Optional[object] = None
    geo_cache: Optional[Dict[str, object]] = None


def enrich_offers(
    offers: List[Dict[str, object]],
    units: Dict[str, dict],
    context: Optional[EnrichContext] = None,
) -> List[Dict[str, object]]:
    """Wzbogaca oferty o kategorię jednostki, pilność i świeżość.

    Args:
        offers: lista rekordów ofert.
        units: rekordy jednostek z units.json (dla kategorii).
        last_report_at: data ostatniego wygenerowanego raportu. Oferta jest
            uznawana za "nową/nieoglądaną", gdy jej first_seen jest nowszy
            niż ten znacznik. Gdy None (pierwszy raport) — nowe są oferty
            widziane dzisiaj.
        clicked_ids: zbiór nab_id ofert już KLIKNIĘTYCH przez użytkownika
            (tracking z raportu). Kliknięta oferta nie jest "nowa", bo
            użytkownik ją widział.

    Returns:
        Nową listę ofert z polami: category_label, category_priority,
        deadline_date, days_left, urgency, first_seen_date, days_ago,
        is_new, clicked, freshness, freshness_cls.
    """
    context = context or EnrichContext()
    last_report_at = context.last_report_at
    clicked_ids = context.clicked_ids or set()
    rates = context.rates or {"PLN": 1.0}
    coords = context.coords or {}
    enriched: List[Dict[str, object]] = []
    for offer in offers:
        unit = units.get(offer.get("unit_key") or "", {})
        raw_category = unit.get("category")
        # Oferty z zewnętrznych źródeł (nuzle, ofertypracy.edu.pl) nie mają
        # jednostki z BIP, więc kategorię bierzemy z podpowiedzi źródła.
        if not raw_category:
            raw_category = offer.get("category_hint")
        label, priority = classify_category(raw_category)

        deadline_date = parse_deadline_to_date(offer.get("deadline"))
        days_left = days_until(deadline_date)

        # Świeżość: kiedy pierwszy raz zobaczyliśmy ofertę.
        first_seen = parse_iso_date(offer.get("first_seen"))
        days_ago = days_since(first_seen)
        is_clicked = str(offer.get("nab_id") or "") in clicked_ids

        if is_clicked:
            # Oferta już otwarta przez użytkownika — nie jest nowa.
            is_new = False
        elif first_seen is None:
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
        item["clicked"] = is_clicked
        item["freshness"] = freshness_label(days_ago, is_new)
        item["freshness_cls"] = freshness_class(days_ago, is_new)
        # Dopasowanie do profilu zawodowego (kultura, sztuka, grafika) —
        # pozwala wydzielić w raporcie sekcję "dopasowane do profilu",
        # żeby trafne oferty nie tonęły wśród kilkuset pozostałych.
        item.update(score_offer(
            str(offer.get("title") or ""),
            str(offer.get("raw_text") or ""),
            str(offer.get("unit_name") or ""),
        ))

        # Rodzaj umowy. Źródła, które mają go w danych (CBOP, nofluffjobs,
        # bulldogjob, arc.dev), zapisały go już przy pobieraniu — wtedy go
        # nie ruszamy. Dla BIP rozpoznajemy z ``raw_text``, bo tam bywa
        # podany słownie („umowa o pracę na czas określony”, „umowa
        # zlecenie na prowadzenie zajęć”).
        #
        # Zmierzone na 440 ogłoszeniach BIP: rodzaj umowy pojawia się
        # w ``raw_text`` w 61 z nich, a w pobranych treściach ogłoszeń
        # w ZERU — dlatego nie sięgamy do ``offer_details``. Pozostałe
        # zostają jako „umowa nieznana”; nie zakładamy UoP tylko dlatego,
        # że to sektor publiczny, bo nabory na instruktorów w ośrodkach
        # kultury bywają na zlecenie.
        contracts = offer.get("contract_types")
        if not contracts:
            contracts = ct.classify(str(offer.get("raw_text") or ""))
        item["contract_types"] = contracts
        item["contract_label"] = ct.label(contracts)

        # Wynagrodzenie: pokazujemy kwotę ŹRÓDŁOWĄ, a przeliczenie na
        # PLN/miesiąc służy wyłącznie sortowaniu (patrz docstring modułu
        # ``salary`` — B2B netto/h i UoP brutto/mies. nie są porównywalne).
        item["salary_text"] = sal.describe(
            offer.get("salary_min"), offer.get("salary_max"),
            str(offer.get("salary_currency") or "PLN"),
            str(offer.get("salary_period") or "month"),
        )
        # Geografia: najdokładniejszy dostępny punkt oferty — współrzędne
        # z API, adres z treści, siedziba instytucji, dzielnica, a dopiero
        # na końcu samo miasto (patrz ``geo.locate_offer``). Poziom
        # dokładności trafia do raportu, żeby było widać, co jest pewne.
        city = (geo.clean_place(offer.get("offer_city") or "")
                or geo.city_from_unit_name(offer.get("unit_name") or ""))
        item["offer_city"] = city
        point, precision = geo.locate_offer(
            offer, city, (coords or {}).get(city),
            context.session, context.geo_cache)
        item["lat"], item["lon"] = point if point else (None, None)
        item["geo_precision"] = precision
        # Flaga „w Krakowie” zasila przełącznik „Kraków zawsze”
        # (domyślnie wyłączony — promień obowiązuje też w mieście).
        item["in_city"] = bool(re.search(r"krak[oó]w|cracow", city,
                                         re.IGNORECASE))

        # Język ogłoszenia (domyślnie raport pokazuje tylko polskie).
        item["lang"] = offer_lang.detect(
            f"{offer.get('title') or ''} {offer.get('raw_text') or ''}",
            str(offer.get("source") or ""),
        )

        item["salary_pln"] = sal.to_pln_month(
            offer.get("salary_min"), offer.get("salary_max"),
            str(offer.get("salary_currency") or "PLN"),
            str(offer.get("salary_period") or "month"),
            rates,
        )

        # Wymiar etatu i płaca w przeliczeniu na pełny etat. Przeliczamy
        # TYLKO kwoty miesięczne — stawka godzinowa jest już niezależna od
        # wymiaru. Sortowanie po płacy używa wartości przeliczonej, żeby
        # „¼ etatu za 1500 zł” nie wyglądało na gorszą ofertę od „pełnego
        # etatu za 4000 zł” (patrz komentarz przy ``salary.fte``).
        fraction, fte_label = sal.fte(
            f"{offer.get('title') or ''} {offer.get('raw_text') or ''}")
        item["fte"] = fraction
        item["fte_label"] = fte_label
        item["salary_pln_fte"] = None
        period = str(offer.get("salary_period") or "month").lower()
        if fraction and item["salary_pln"] and period.startswith("month"):
            item["salary_pln_fte"] = int(round(item["salary_pln"] / fraction))
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
def collect_recent_closed_matches(
    all_records: Dict[str, dict],
    units: Dict[str, dict],
    clicked_ids: set,
    shown_keys: set,
    rates: Optional[Dict[str, float]] = None,
) -> List[Dict[str, object]]:
    """Zbiera niedawno zamknięte oferty pasujące do profilu.

    Po co: raport domyślnie pokazuje tylko oferty aktualne, więc trafienia
    z profilu, których termin minął, znikają bez śladu. A one mają wartość
    orientacyjną — pokazują, jakie stanowiska w tym profilu się pojawiają
    i w jakich instytucjach, co podpowiada, gdzie pilnować ogłoszeń.

    Bierzemy oferty, które: pasują do profilu, NIE są już w raporcie
    (bo po terminie), a ich termin minął nie dawniej niż
    :data:`CLOSED_MATCH_MAX_DAYS` dni.

    Args:
        all_records: wszystkie rekordy ofert z datasetu.
        units: rekordy jednostek (dla kategorii).
        clicked_ids: zbiór nab_id ofert już klikniętych.
        shown_keys: nab_id ofert już pokazanych w raporcie (pomijamy je).
        rates: kursy walut do przeliczenia wynagrodzeń.

    Returns:
        Listę wzbogaconych ofert, od najświeżej zamkniętych.
    """
    today = date.today()
    candidates: List[Tuple[int, Dict[str, object]]] = []

    for record in all_records.values():
        if str(record.get("nab_id")) in shown_keys:
            continue
        deadline = parse_deadline_to_date(record.get("deadline"))
        if deadline is None or deadline >= today:
            continue  # bez terminu albo jeszcze aktualna
        days_past = (today - deadline).days
        if days_past > CLOSED_MATCH_MAX_DAYS:
            continue
        match = score_offer(
            str(record.get("title") or ""),
            str(record.get("raw_text") or ""),
            str(record.get("unit_name") or ""),
        )
        if match["profile_level"] == "none":
            continue
        candidates.append((days_past, record))

    candidates.sort(key=lambda pair: pair[0])
    selected = [record for _days, record in candidates[:CLOSED_MATCH_LIMIT]]
    # Wzbogacamy tak samo jak oferty raportu, aby karty wyglądały spójnie.
    return enrich_offers(selected, units, EnrichContext(
        clicked_ids=clicked_ids, rates=rates))


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
    bc.add_profile_argument(parser)
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    # Kolejność jest istotna: najpierw przestawiamy ścieżki i profil
    # oceniania, a dopiero potem czytamy jakikolwiek dataset — inaczej
    # wczytalibyśmy dane innego profilu.
    bc.use_profile(args.profile)
    try:
        profile = profile_match.set_profile(args.profile)
    except KeyError as exc:
        logging.error("%s", exc)
        return 1
    logging.info("Profil: %s", profile.LABEL)
    bc.ensure_dirs()

    # Kursy walut do SORTOWANIA po wynagrodzeniu. Pobieramy raz na raport;
    # gdy nie ma sieci, moduł użyje zapisanych albo zapasowych (patrz
    # docstring ``salary.fetch_rates``), więc raport zawsze się wygeneruje.
    session = bc.build_session()
    rates = sal.fetch_rates(session)

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

    # Stan klikniętych ofert (tracking z raportu HTML, wyeksportowany do
    # data/clicks.json). Oferta kliknięta nie jest już "nowa", nawet jeśli
    # pojawiła się po ostatnim raporcie — użytkownik ją widział.
    clicks = bc.load_json(bc.CLICKS_DATASET) or {}
    clicked_ids = set((clicks.get("clicked") or {}).keys())
    # Oferty, na które użytkownik już aplikował (przycisk „aplikowałam”
    # w raporcie, eksportowany razem ze stanem klikania). Zapisujemy je
    # w rekordach jako ``applied_at``, żeby status przetrwał regenerację
    # raportu i przeniesienie na inną przeglądarkę.
    applied = clicks.get("applied") or {}
    if clicked_ids:
        logging.info("Wczytano stan klikania: %d ofert już oglądanych.",
                     len(clicked_ids))

    # Wybór ofert do raportu.
    selected = []
    for offer in offers_ds["records"].values():
        if args.all or is_current(offer):
            when = applied.get(str(offer.get("nab_id") or ""))
            if when:
                offer = dict(offer, applied_at=when)
            selected.append(offer)

    # Wzbogacamy o kategorię, pilność i świeżość, sortujemy, grupujemy.
    # Geokodujemy miejscowości ofert (raz na miejscowość w życiu —
    # wynik ląduje w data*/geo_cache.json).
    places = {geo.clean_place(r.get("offer_city") or "")
              or geo.city_from_unit_name(r.get("unit_name") or "")
              for r in selected}
    coords = geo.geocode_places(places, session)

    geo_cache = geo.load_cache()
    enriched = enrich_offers(selected, units_ds["records"], EnrichContext(
        last_report_at=last_report_at, clicked_ids=clicked_ids,
        rates=rates, coords=coords, session=session, geo_cache=geo_cache))
    geo.save_cache(geo_cache)
    enriched.sort(key=sort_key)

    # Duplikaty i podobne oferty: jedna karta zamiast kilku. Robimy to PO
    # sortowaniu, żeby kolejność kart głównych pozostała po pilności,
    # i PRZED grupowaniem po kategoriach, żeby duplikat z innej kategorii
    # nie wracał drugą drogą. Szczegóły i pomiary w docstringu ``dedupe``.
    before = len(enriched)
    enriched = dedupe.deduplicate(enriched)
    logging.info("Duplikaty i podobne: %d ofert -> %d kart głównych.",
                 before, len(enriched))

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
    # Dziennik niepowodzeń — sekcja diagnostyczna w raporcie HTML.
    failures_ds = bc.load_dataset(bc.FAILURES_DATASET)

    # Niedawno zamknięte trafienia z profilu — wartość orientacyjna: pokazują,
    # jakie stanowiska w tym profilu realnie się pojawiają i w jakich
    # instytucjach. Bierzemy oferty NIE ujęte w raporcie (bo po terminie),
    # które pasują do profilu i pojawiły się w ostatnich tygodniach.
    recent_closed = collect_recent_closed_matches(
        offers_ds["records"], units_ds["records"], clicked_ids,
        shown_keys={str(o.get("nab_id")) for o in enriched},
        rates=rates,
    )
    if recent_closed:
        logging.info("Niedawno zamkniętych trafień z profilu: %d",
                     len(recent_closed))

    html = build_html(
        grouped, details_ds["records"], len(enriched),
        ReportMeta(failures=failures_ds.get("records"),
                   recent_closed=recent_closed,
                   profile_label=profile.LABEL,
                   profile_description=profile.DESCRIPTION,
                   # Statystyki liczą OFERTY, nie karty: karta główna plus
                   # schowane pod nią podobne (duplikaty są już jedną ofertą).
                   stats=report_stats.collect_stats(
                       [o for head in enriched
                        for o in [head, *(head.get("similar") or [])]])),
    )

    stamp = bc.timestamp_str()
    # Nazwa pliku zawiera slug profilu, żeby raporty obu profili dały się
    # trzymać razem bez pomyłki (dla profilu domyślnego zostaje stara
    # nazwa — tak, by nie zmieniać tego, co użytkownik już zna).
    tag = "" if args.profile == bc.DEFAULT_PROFILE else f"_{args.profile}"
    md_path = bc.REPORTS_DIR / f"raport_praca{tag}_{stamp}.md"
    html_path = bc.REPORTS_DIR / f"raport_praca{tag}_{stamp}.html"

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
