#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy rozpoznawania wymiaru etatu i normalizacji wynagrodzeń.

Przypadki z prawdziwych ogłoszeń; najważniejsza pułapka: „3 etaty” to
liczba stanowisk, a nie wymiar.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import salary  # noqa: E402  pylint: disable=wrong-import-position

FTE_CASES = [
    ("Instruktor – Klub Dukat (¼ etatu)", 0.25),
    ("Psycholog - 0,5 etatu (pensum 10 godzin)", 0.5),
    ("Referent - 0,75 etatu 30 godz. tygodniowo", 0.75),
    ("Koordynator projektów kulturalnych 1/2 etatu", 0.5),
    ("pół etatu", 0.5),
    ("etat: 9/18 wykształcenie wyższe", 0.5),
    ("etat: 18/18", None),
    ("Kontroler biletów - 3 etaty", None),
    ("Kontroler ruchu - 5 etatów", None),
    ("Inspektor nadzoru - 1 etat", None),
    ("pełny etat", None),
]


class FteTest(unittest.TestCase):
    """Wymiar etatu: ułamki, pensum, liczba stanowisk."""

    def test_fractions(self) -> None:
        """Każdy zapis z danych daje oczekiwany ułamek."""
        for text, expected in FTE_CASES:
            with self.subTest(text=text):
                self.assertEqual(salary.fte(text)[0], expected)

    def test_partial_without_fraction(self) -> None:
        """„niepełny etat” bez liczby — oznaczony, ułamek nieznany."""
        self.assertEqual(salary.fte("stawka godzinowa niepełny etat"),
                         (None, "niepełny etat"))


class PayTest(unittest.TestCase):
    """Przeliczanie kwot na PLN/miesiąc."""

    RATES = {"PLN": 1.0, "USD": 4.0}

    def test_text_amount_from_string_fields(self) -> None:
        """pracujwkulturze podaje kwoty jako tekst („1450”)."""
        self.assertEqual(salary.to_pln_month("1450", "1650", "PLN", "month",
                                             self.RATES), 1450)

    def test_hourly_usd(self) -> None:
        """Stawka godzinowa USD przez 168 h."""
        self.assertEqual(salary.to_pln_month(30, 45, "USD", "hour",
                                             self.RATES), 30 * 4 * 168)

    def test_year_is_not_an_amount(self) -> None:
        """„od 2026 roku” nie jest kwotą."""
        self.assertEqual(salary.parse_from_text("umowa od 2026 roku")[0],
                         None)


if __name__ == "__main__":
    unittest.main()
