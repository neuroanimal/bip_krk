#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wykrywanie duplikatów i grupowanie podobnych ofert.

PROBLEM — ZMIERZONY, NIE ZGADNIĘTY
----------------------------------
Adresatka: „ten skrypt powiela po 3 razy dużo ogłoszeń”. Pomiar raportu
pokazał trzy niezależne źródła powtórzeń:

1. **ta sama oferta w kilku źródłach** — agregator (jooble) zbiera
   ogłoszenia, które mamy też bezpośrednio: „Nauczyciel-Instruktor” MDK
   Fort 49 był w CBOP i dwukrotnie w jooble; „Edukator / Edukatorka”
   Wawelu w instytucjach kultury i w pracujwkulturze;
2. **jedno ogłoszenie rozpisane na warianty** — „Koordynator ds.
   Organizacji Widowni i Logistyki – praca mobilna woj. Małopolskie /
   Śląskie / Podkarpackie / Cała Polska…”: 12 kart jednej firmy;
3. **powtórzenie w samym raporcie** — oferta dopasowana do profilu była
   pokazywana w sekcji „Dla Ciebie” ORAZ w swojej kategorii (65 kart
   dwukrotnie). To naprawia ``report_html``, nie ten moduł.

DWA POZIOMY
-----------
* **DUPLIKAT** — ta sama oferta: bardzo podobny tytuł i ten sam
  pracodawca (albo pracodawca nieznany po jednej stronie). Łączymy w JEDNĄ
  kartę, a pozostałe źródła wymieniamy jako „także na: …” — z linkami,
  bo w różnych portalach bywa różny zakres informacji.
* **PODOBNE** — różne oferty tego samego rodzaju: ten sam tytuł u innego
  pracodawcy albo warianty jednego ogłoszenia. Pokazujemy jedną kartę,
  a resztę chowamy pod rozwijanym „+ N podobnych”, żeby można było
  sprawdzić dokładniej, ale żeby nie zalewały listy.

PODOBIEŃSTWO TYTUŁÓW
--------------------
Miara Jaccarda na zbiorach rdzeni słów, po:

* złożeniu znaków (``ą→a``, ``ł→l``) — „PIELĘGNIARKA” = „pielegniarka”,
* usunięciu oznaczeń płci i formy (``(K/M)``, ``/ka``, ``k/m/x``),
* odcięciu dopisku regionu po myślniku („– praca mobilna woj. Śląskie”),
* odrzuceniu słów bez treści („stanowisko”, „osoba”, „etatu”),
* przycięciu słów do 5 liter — tani zamiennik lematyzacji, który zrównuje
  „instruktor” z „instruktora”, „grafik” z „grafika”.

Celowo **bez** odległości edycyjnej po całych tytułach: „Nauczyciel
grafiki” i „Nauczyciel fizyki” różnią się jedną literą rdzenia, a to
zupełnie różne oferty.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, FrozenSet, List, Sequence

# Progi podobieństwa (Jaccard na rdzeniach słów tytułu).
DUP_TITLE = 0.8       # duplikat: tytuł prawie identyczny...
DUP_EMPLOYER = 0.5    # ...i ten sam pracodawca
# Podobne u RÓŻNYCH pracodawców wymagają tytułu IDENTYCZNEGO po
# normalizacji. Przy 0.8 „Senior Python Developer (Django)” i „Senior
# Python Developer (AWS)” u różnych firm lądowały pod jedną kartą, a to
# osobne propozycje pracy, które należy widzieć. Identyczny tytuł
# („Instruktor terapii zajęciowej” w trzech fundacjach) — grupujemy.
SIMILAR_TITLE = 1.0
VARIANT_TITLE = 0.5   # warianty: luźniej podobny tytuł...
VARIANT_EMPLOYER = 0.8  # ...ale wyraźnie ten sam pracodawca

# Długość rdzenia słowa (patrz docstring modułu).
STEM_LEN = 5

# Słowa bez treści — nie świadczą o podobieństwie ofert.
STOPWORDS: FrozenSet[str] = frozenset({
    "k", "m", "x", "f", "d", "w", "o", "z", "i", "a", "na", "do", "ds",
    "oraz", "dla", "lub", "the", "and", "of", "for", "osoba", "stanowisko",
    "stanow", "etatu", "etat", "praca", "pracy", "oferta", "nabor",
    "kandydat", "kandydatka", "zastepstwo", "umowa", "umowe", "ka", "ki",
})

# Dopisek regionu po myślniku — wariant tego samego ogłoszenia.
REGION_TAIL = re.compile(
    r"\s[–—-]\s.*(woj\.|wojewodztw|krakow|polska|praca mobilna|zdaln"
    r"|okolic|remote).*$")

# Oznaczenia płci i formy.
GENDER = re.compile(r"\((?:k|m|x|f|d|w)(?:/[kmxfdw])*\)|\b[kmxfdw](?:/[kmxfdw])+\b")

# Pracodawca nieznany albo zastępczy — nie przeszkadza w uznaniu duplikatu.
GENERIC_EMPLOYERS: FrozenSet[str] = frozenset({
    "", "kontakt przez pup", "jooble org", "nuzle pl", "cbop urzedy pracy",
    "arc dev klient nieujawniony",
})

# Źródła, które same z siebie potrafią opublikować ten sam wpis kilka
# razy (agregatory i serwisy ogłoszeniowe). Dla pozostałych para z jednego
# źródła nie jest duplikatem — patrz :func:`deduplicate`.
AGGREGATORS: FrozenSet[str] = frozenset({"jooble", "nuzle"})

# Kolejność poziomów dopasowania (mniejsza = lepsza).
LEVEL_ORDER: Dict[str, int] = {"strong": 0, "weak": 1, "none": 2}

# Pierwszeństwo źródeł przy wyborze karty głównej duplikatu. Wyżej stoją
# źródła z terminem i pełnym opisem; agregator (jooble) na końcu, bo
# zwykle ma tylko streszczenie i nie podaje terminu.
SOURCE_PRIORITY: Dict[str, int] = {
    "pracujwkulturze": 0, "bip_global": 1, "bip_unit": 1,
    "kultura_instytucje": 2, "cbop": 3, "nofluffjobs": 4, "bulldogjob": 4,
    "arc_dev": 5, "remote_intl": 6, "nuzle": 7, "jooble": 9,
}


def _fold(text: str) -> str:
    """Małe litery, bez ogonków, ze zbitymi spacjami.

    Args:
        text: dowolny tekst.

    Returns:
        Tekst złożony.
    """
    lowered = str(text or "").lower().replace("ł", "l")
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def title_key(title: str) -> FrozenSet[str]:
    """Zamienia tytuł oferty na zbiór rdzeni słów do porównania.

    Args:
        title: tytuł oferty.

    Returns:
        Zbiór rdzeni (pusty, gdy tytuł nie ma treści).
    """
    text = _fold(title)
    text = REGION_TAIL.sub("", text)
    text = GENDER.sub(" ", text)
    # Treści nawiasów NIE wycinamy w całości: „(Django)” i „(AWS)” albo
    # „(¼ etatu)” niosą informację, która odróżnia oferty. Oznaczenia płci
    # usuwa już GENDER, a słowa w rodzaju „etatu”, „umowa” odpadają jako
    # STOPWORDS.
    words = re.findall(r"[a-z0-9]+", text)
    return frozenset(w[:STEM_LEN] for w in words
                     if w not in STOPWORDS and len(w) > 1)


def employer_key(unit_name: str) -> FrozenSet[str]:
    """Zamienia nazwę pracodawcy na zbiór słów do porównania.

    Odcinamy dopiski doklejane przez źródła (miasto w nawiasie, „—
    praca zdalna…”, ``[portal]``) i formy prawne spółek.

    Args:
        unit_name: nazwa jednostki z rekordu.

    Returns:
        Zbiór znaczących słów nazwy pracodawcy.
    """
    name = re.split(r"\s*[\(\[]|\s+[—–]\s+", str(unit_name or ""),
                    maxsplit=1)[0]
    text = _fold(name)
    text = re.sub(r"\b(sp|z|o|oo|sa|spolka|ograniczona|odpowiedzialnoscia"
                  r"|im|imienia)\b", " ", text)
    return frozenset(w for w in re.findall(r"[a-z0-9]+", text) if len(w) > 2)


def _jaccard(left: FrozenSet[str], right: FrozenSet[str]) -> float:
    """Miara Jaccarda dwóch zbiorów.

    Args:
        left: pierwszy zbiór.
        right: drugi zbiór.

    Returns:
        Podobieństwo w przedziale 0..1 (0 dla dwóch pustych).
    """
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _is_generic(employer: FrozenSet[str]) -> bool:
    """Czy pracodawca jest nieznany/zastępczy.

    Args:
        employer: zbiór słów nazwy pracodawcy.

    Returns:
        True dla nazw zastępczych (portal, „kontakt przez PUP”).
    """
    return " ".join(sorted(employer)) in {
        " ".join(sorted(g.split())) for g in GENERIC_EMPLOYERS} or not employer


class _UnionFind:  # pylint: disable=too-few-public-methods
    """Minimalny union-find do łączenia ofert w klastry."""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        """Zwraca reprezentanta klastra (z kompresją ścieżki)."""
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        """Łączy dwa klastry."""
        root_l, root_r = self.find(left), self.find(right)
        if root_l != root_r:
            self.parent[root_r] = root_l


def _rank(offer: Dict[str, object]) -> tuple:
    """Klucz wyboru karty głównej: lepsze źródło, potem więcej danych.

    Args:
        offer: wzbogacona oferta.

    Returns:
        Krotka sortująca (mniejsza = lepsza).
    """
    return (
        SOURCE_PRIORITY.get(str(offer.get("source") or ""), 8),
        0 if offer.get("deadline") else 1,
        0 if offer.get("salary_text") else 1,
        -int(offer.get("profile_score") or 0),
    )


def deduplicate(offers: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """Łączy duplikaty i grupuje podobne oferty.

    Zwraca listę KART GŁÓWNYCH. Każda karta główna może mieć:

    * ``also_on`` — listę ``{"source", "url"}`` duplikatów z innych źródeł
      (te nie są już osobnymi kartami),
    * ``similar`` — listę ofert podobnych (pełne rekordy, do rozwinięcia).

    Oferty, które nie mają żadnego odpowiednika, wracają bez zmian.

    Args:
        offers: wzbogacone oferty (po ocenie profilu).

    Returns:
        Lista kart głównych w kolejności wejściowej pierwszego wystąpienia.
    """
    items = list(offers)
    count = len(items)
    titles = [title_key(str(o.get("title") or "")) for o in items]
    employers = [employer_key(str(o.get("unit_name") or "")) for o in items]

    dups = _UnionFind(count)
    for i in range(count):
        if not titles[i]:
            continue
        for j in range(i + 1, count):
            if not titles[j] or _jaccard(titles[i], titles[j]) < DUP_TITLE:
                continue
            # Dwa wpisy z TEGO SAMEGO portalu źródłowego to zwykle dwa
            # osobne etaty, nie duplikat: „Młodszy bibliotekarz (na
            # zastępstwo)” i „Młodszy bibliotekarz” tej samej biblioteki to
            # różne ogłoszenia. Ten sam wpis wielokrotnie publikują tylko
            # agregatory (AGGREGATORS). Takie pary trafią niżej do grupy
            # PODOBNYCH — widoczne po rozwinięciu, a nie zlane w jedno.
            same_source = items[i].get("source") == items[j].get("source")
            if same_source and items[i].get("source") not in AGGREGATORS:
                continue
            same_employer = (_jaccard(employers[i], employers[j])
                             >= DUP_EMPLOYER)
            unknown = _is_generic(employers[i]) or _is_generic(employers[j])
            if same_employer or unknown:
                dups.union(i, j)

    # Poziom 1: duplikaty → jedna karta, reszta jako „także na”.
    clusters: Dict[int, List[int]] = {}
    for i in range(count):
        clusters.setdefault(dups.find(i), []).append(i)

    primaries: List[Dict[str, object]] = []
    primary_index: List[int] = []
    for members in clusters.values():
        # Także przy duplikatach poziom dopasowania idzie pierwszy: różne
        # źródła opisują tę samą ofertę różnie szczegółowo, więc jedna kopia
        # może zostać oceniona wyżej — i to ona ma być widoczna.
        ordered = sorted(members, key=lambda k: (
            LEVEL_ORDER.get(str(items[k].get("profile_level")), 3),
            _rank(items[k])))
        head = dict(items[ordered[0]])
        others = [items[k] for k in ordered[1:]]
        if others:
            seen = {(head.get("source"), head.get("detail_url"))}
            also = []
            for other in others:
                key = (other.get("source"), other.get("detail_url"))
                if key in seen:
                    continue
                seen.add(key)
                also.append({"source": other.get("source"),
                             "url": other.get("detail_url")})
            head["also_on"] = also
            head["duplicate_count"] = len(others)
        primaries.append(head)
        primary_index.append(ordered[0])

    # Poziom 2: podobne karty główne → jedna widoczna, reszta do rozwinięcia.
    #
    # GWIAZDA, NIE UNION-FIND — i to jest poprawka realnego błędu. Pierwsza
    # wersja łączyła podobieństwa przechodnio: A~B i B~C dawało grupę A+C,
    # choć A i C nie mają ze sobą nic wspólnego. W profilu IT „Senior
    # Python Developer” połknął w ten sposób 92 oferty od 31 firm. Teraz
    # każda grupa ma GŁOWĘ (najlepsze dopasowanie, potem najlepsze źródło),
    # a członkiem zostaje wyłącznie oferta podobna BEZPOŚREDNIO do głowy.
    def group_order(pos: int) -> tuple:
        """Kolejność wyboru głów: najlepsze dopasowanie, lepsze źródło."""
        return (LEVEL_ORDER.get(str(primaries[pos].get("profile_level")), 3),
                _rank(primaries[pos]))

    size = len(primaries)
    assigned = [False] * size
    members_of: Dict[int, List[int]] = {}
    for head_pos in sorted(range(size), key=group_order):
        if assigned[head_pos]:
            continue
        assigned[head_pos] = True
        members_of[head_pos] = []
        head_title = titles[primary_index[head_pos]]
        head_emp = employers[primary_index[head_pos]]
        if not head_title:
            continue
        for other in sorted(range(size), key=group_order):
            if assigned[other]:
                continue
            o_title = titles[primary_index[other]]
            if not o_title:
                continue
            t_sim = _jaccard(head_title, o_title)
            e_sim = _jaccard(head_emp, employers[primary_index[other]])
            if t_sim >= SIMILAR_TITLE or (t_sim >= VARIANT_TITLE
                                          and e_sim >= VARIANT_EMPLOYER):
                assigned[other] = True
                members_of[head_pos].append(other)

    # Wynik w kolejności wejścia (czyli po pilności) według pozycji głowy.
    result: List[Dict[str, object]] = []
    for head_pos in sorted(members_of):
        head = primaries[head_pos]
        if members_of[head_pos]:
            head["similar"] = [primaries[p] for p in members_of[head_pos]]
        result.append(head)
    return result
