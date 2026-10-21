#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalizacja WYNAGRODZEŃ do jednej miary — żeby dało się sortować.

PROBLEM
-------
Każde źródło podaje kwoty inaczej, a część wcale:

====================  =====================================================
``nofluffjobs``       ``salary.from/to`` + ``currency`` + ``period``
                      (w badaniu zawsze ``PLN`` / ``Month``) — dane czyste
``arc_dev``           ``minHourlyRate``/``maxHourlyRate`` w **USD/h**, albo
                      ``minAnnualSalary``/``maxAnnualSalary`` w **USD/rok**
``cbop``              pole tekstowe, np. „od 10 000 PLN Zgodnie z ogólnie
                      obowiązującymi przepisami…”
``bulldogjob``        **brak kwot** — ``denominatedSalaryLong.money`` jest
                      ``null`` dla wszystkich ofert z listy (portal ukrywa
                      widełki, ``showSalary: false``)
``bip_global``, BIP   brak
``remote_intl``       brak
====================  =====================================================

Dlatego sortowanie potrzebuje JEDNEJ liczby na ofertę: przeliczamy
wszystko na **PLN miesięcznie**.

CZEGO TA LICZBA NIE ZNACZY — i trzeba to wiedzieć
-------------------------------------------------
To wartość **orientacyjna, do uszeregowania ofert**, a nie porównanie
zarobków. Zestawia bowiem rzeczy nieporównywalne:

* **B2B podaje się zwykle netto, UoP brutto** — przy tej samej kwocie
  B2B jest realnie korzystniejsze podatkowo, ale bez urlopu i ZUS-u
  pracodawcy;
* stawka godzinowa przeliczana jest przez **168 h/miesiąc** (21 dni × 8 h),
  co zakłada pełne obłożenie — przy kontrakcie bywa inaczej;
* kurs walut jest z dnia pobrania.

Dlatego w raporcie pokazujemy **kwotę źródłową** (tak jak ją podał
portal), a przeliczenie służy wyłącznie kolejności sortowania.

KURS WALUT
----------
Z oficjalnego API NBP (``api.nbp.pl``, tabela A, bez klucza). Pobierany
raz na przebieg i zapisywany w ``data*/rates.json``, żeby raport dał się
wygenerować także bez internetu (wtedy używamy ostatniego znanego kursu,
a w ostateczności wartości zapasowej :data:`FALLBACK_RATES`).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional, Tuple

import bip_common as bc

NBP_URL = "https://api.nbp.pl/api/exchangerates/rates/a/{code}/?format=json"

# Waluty, dla których pobieramy kurs (reszta trafi na kurs 1.0 i zostanie
# odnotowana w logu).
CURRENCIES: Tuple[str, ...] = ("USD", "EUR", "GBP")

# Kursy zapasowe — używane TYLKO, gdy nie ma ani sieci, ani zapisanego
# pliku. Celowo przybliżone i jawnie oznaczone, żeby nikt nie wziął ich
# za aktualne. Stan: październik 2026.
FALLBACK_RATES: Dict[str, float] = {"PLN": 1.0, "USD": 3.90, "EUR": 4.25,
                                    "GBP": 5.05}

# Godziny miesięcznie przy przeliczaniu stawki godzinowej (21 dni × 8 h).
HOURS_PER_MONTH = 168

# Rozpoznawanie kwot w tekście. Polskie liczby mają spacje jako separator
# tysięcy („10 000 PLN”), a czasem spację nierozdzielającą (U+00A0).
AMOUNT_RE = re.compile(
    r"(\d[\d\s\u00a0]{2,})\s*(?:-|–|do)?\s*(\d[\d\s\u00a0]{2,})?\s*"
    r"(pln|zł|zl|usd|eur|gbp)",
    re.IGNORECASE,
)

# Normalizacja nazw okresu na mnożnik do miesiąca.
PERIOD_FACTORS: Dict[str, float] = {
    "month": 1.0, "monthly": 1.0, "mies": 1.0,
    "year": 1.0 / 12, "annual": 1.0 / 12, "rok": 1.0 / 12,
    "hour": float(HOURS_PER_MONTH), "hourly": float(HOURS_PER_MONTH),
    "godz": float(HOURS_PER_MONTH), "day": 21.0, "daily": 21.0,
}


def fetch_rates(session=None) -> Dict[str, float]:
    """Pobiera kursy walut z NBP, z zapisem na dysk i wartościami zapasowymi.

    Args:
        session: sesja HTTP; gdy None, próbujemy tylko odczytu z dysku.

    Returns:
        Mapę ``kod waluty -> kurs do PLN`` (zawsze zawiera ``PLN: 1.0``).
    """
    path = bc.DATA_DIR / "rates.json"
    stored = bc.load_dataset(path) if path.exists() else {"records": {}}
    rates: Dict[str, float] = {"PLN": 1.0}

    fetched = False
    if session is not None:
        for code in CURRENCIES:
            try:
                response = session.get(NBP_URL.format(code=code.lower()),
                                       timeout=bc.HTTP_TIMEOUT)
                if response.status_code != 200:
                    continue
                payload = response.json()
                rates[code] = float(payload["rates"][0]["mid"])
                fetched = True
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.warning("Kurs %s niedostępny: %s", code, exc)

    if fetched:
        bc.save_dataset(path, {"records": {"rates": rates}})
        logging.info("Kursy NBP: %s", ", ".join(
            f"{k}={v:.4f}" for k, v in sorted(rates.items()) if k != "PLN"))
        return rates

    saved = (stored.get("records") or {}).get("rates")
    if isinstance(saved, dict) and saved:
        logging.info("Używam zapisanych kursów (brak połączenia z NBP).")
        return {str(k): float(v) for k, v in saved.items()}

    logging.warning("Brak kursów z NBP i na dysku — używam przybliżonych "
                    "wartości zapasowych.")
    return dict(FALLBACK_RATES)


def parse_from_text(text: str) -> Tuple[Optional[float], Optional[float],
                                        str]:
    """Wyłuskuje widełki wynagrodzenia z tekstu ogłoszenia.

    Args:
        text: dowolny tekst (np. pole ``wynagrodzenie`` z CBOP).

    Returns:
        Krotkę (dolna kwota, górna kwota, kod waluty); wartości None, gdy
        nie rozpoznano.
    """
    if not text:
        return None, None, ""
    found = AMOUNT_RE.search(text)
    if not found:
        return None, None, ""

    def number(raw: Optional[str]) -> Optional[float]:
        """Zamienia zapis z separatorami spacji na liczbę."""
        if not raw:
            return None
        digits = re.sub(r"[\s\u00a0]", "", raw)
        try:
            value = float(digits)
        except ValueError:
            return None
        # Odrzucamy śmieci typu „2026” (rok) albo kwoty absurdalnie małe.
        return value if 100 <= value <= 10_000_000 else None

    low = number(found.group(1))
    high = number(found.group(2))
    unit = found.group(3).upper()
    currency = "PLN" if unit in ("ZŁ", "ZL", "PLN") else unit
    return low, high, currency


def _as_number(value: object) -> Optional[float]:
    """Zamienia wartość pola na liczbę, tolerując łańcuchy.

    Źródła nie są spójne: nofluffjobs podaje ``20000.0`` (liczba),
    a pracujwkulturze ``"1450"`` (tekst) — bez tej konwersji formatowanie
    kwoty wywalało się z ``TypeError: type str doesn't define __round__``.

    Args:
        value: wartość z rekordu oferty.

    Returns:
        Liczbę albo None, gdy pole jest puste lub nienumeryczne.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = re.sub(r"[^\d.,]", "", str(value)).replace(",", ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def to_pln_month(low: Optional[float], high: Optional[float],
                 currency: str, period: str,
                 rates: Dict[str, float]) -> Optional[int]:
    """Przelicza widełki na przybliżone PLN miesięcznie.

    Do sortowania bierzemy **dolną granicę** widełek — jest bardziej
    wiarygodna niż górna, bo portale chętnie zawyżają maksimum.

    Args:
        low: dolna kwota (może być None).
        high: górna kwota (może być None).
        currency: kod waluty (``PLN``, ``USD``…).
        period: okres (``month``, ``hour``, ``year``…).
        rates: mapa kursów z :func:`fetch_rates`.

    Returns:
        Zaokrągloną kwotę w PLN/miesiąc albo None, gdy nie da się policzyć.
    """
    low, high = _as_number(low), _as_number(high)
    base = low if low is not None else high
    if base is None:
        return None

    rate = rates.get((currency or "PLN").upper())
    if rate is None:
        logging.debug("Nieznana waluta %s — pomijam przeliczenie", currency)
        return None

    factor = 1.0
    period_key = (period or "month").strip().lower()
    for name, value in PERIOD_FACTORS.items():
        if period_key.startswith(name):
            factor = value
            break

    return int(round(base * rate * factor))


def describe(low: Optional[float], high: Optional[float], currency: str,
             period: str) -> str:
    """Składa czytelny opis widełek — tak, jak podało je źródło.

    W raporcie pokazujemy właśnie to, a nie wartość przeliczoną, żeby nie
    sugerować precyzji, której tu nie ma (patrz docstring modułu).

    Args:
        low: dolna kwota.
        high: górna kwota.
        currency: kod waluty.
        period: okres.

    Returns:
        Opis typu ``20 000–25 000 PLN/mies.`` albo pusty łańcuch.
    """
    low, high = _as_number(low), _as_number(high)
    if low is None and high is None:
        return ""
    unit = {"month": "mies.", "hour": "h", "year": "rok", "day": "dzień"}
    suffix = unit.get((period or "month").strip().lower(), period or "")

    def fmt(value: Optional[float]) -> str:
        """Formatuje kwotę z odstępami tysięcy."""
        return f"{int(round(value)):,}".replace(",", " ") if value else ""

    if low is not None and high is not None and high != low:
        amount = f"{fmt(low)}–{fmt(high)}"
    else:
        amount = fmt(low if low is not None else high)
    return f"{amount} {currency.upper()}/{suffix}".strip()
