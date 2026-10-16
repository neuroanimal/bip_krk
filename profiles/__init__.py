#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pakiet profili zawodowych — definicje „co pasuje do kogo”.

PO CO ROZDZIELENIE
------------------
Projekt powstał dla jednego profilu (kultura i sztuka). Gdy doszedł drugi
(dane i AI), były dwie drogi: skopiować całą aplikację do osobnego
katalogu albo wydzielić to, co profilowe. Kopia znaczyłaby dwa miejsca do
poprawiania każdego błędu w ~4,5 tys. linii wspólnej mechaniki (HTTP
z retry, dziennik niepowodzeń, active/inactive, snapshoty, HTML raportu),
a przy tym część źródeł obsługuje OBA profile — nofluffjobs ma zarówno
„Social Media Graphic Designer”, jak i 56 unikalnych ofert data
w Krakowie, a CBOP jedno i drugie.

Dlatego: **jedna aplikacja, wiele profili, osobne dane i raporty.**
Profil wybiera się przełącznikiem ``--profile``; domyślny to ``kultura``,
więc dotychczasowe uruchomienia działają bez zmian.

KONTRAKT PROFILU
----------------
Moduł profilu musi udostępniać:

``LABEL``                nazwa wyświetlana w raporcie,
``SLUG``                 identyfikator (katalogi danych, nazwy plików),
``DESCRIPTION``          zdanie pod nagłówkiem sekcji dopasowań,
``PROFILE_KEYWORDS``     lista ``(obszar, waga, (frazy...))``,
``CORE_AREAS``           obszary, które mogą samodzielnie kwalifikować,
``EXCLUDE_KEYWORDS``     frazy odejmujące punkty (liczone z tytułu),
``DEMOTE_KEYWORDS``      frazy ograniczające poziom do „może pasować”,
``PREFERRED_EMPLOYERS``  pracodawcy, przy których ogólny tytuł wystarcza,
``SCHEDULE_CONTEXT_WORDS`` słowa rozstrzygające homonim profilu,
``INSTITUTION_NOISE``    frazy typu placówki, usuwane przed oceną,
``SCORE_STRONG``, ``SCORE_WEAK``  progi poziomów dopasowania.

Dodanie trzeciego profilu = jeden plik tutaj i wpis w ``AVAILABLE``.
"""

from types import ModuleType
from typing import Dict

from . import it as _it
from . import kultura as _kultura

# Dostępne profile, po slugu.
AVAILABLE: Dict[str, ModuleType] = {
    _kultura.SLUG: _kultura,
    _it.SLUG: _it,
}

# Profil domyślny — zachowuje zachowanie z czasów jednego profilu.
DEFAULT = _kultura.SLUG


def get(slug: str) -> ModuleType:
    """Zwraca moduł profilu o podanym slugu.

    Args:
        slug: identyfikator profilu (np. ``kultura``, ``it``).

    Returns:
        Moduł profilu.

    Raises:
        KeyError: gdy profil o takim slugu nie istnieje — z listą
            dostępnych, żeby literówka w ``--profile`` była od razu
            czytelna.
    """
    try:
        return AVAILABLE[slug]
    except KeyError as exc:
        known = ", ".join(sorted(AVAILABLE))
        raise KeyError(
            f"nieznany profil '{slug}'; dostępne: {known}") from exc
