#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy wykrywania duplikatów i grupowania podobnych ofert.

Przypadki pochodzą z prawdziwych danych, które adresatka widziała jako
„powielone po 3 razy” (patrz docstring modułu ``dedupe``).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dedupe  # noqa: E402  pylint: disable=wrong-import-position


def offer(title, employer, source="pracujwkulturze", level="strong",
          url=None):
    """Buduje minimalny rekord oferty do testu."""
    return {"title": title, "unit_name": employer, "source": source,
            "profile_level": level, "detail_url": url or f"{source}/{title}",
            "nab_id": f"{source}-{title}-{employer}"}


class DedupeTest(unittest.TestCase):
    """Duplikaty łączymy, podobne grupujemy, różne zostawiamy osobno."""

    def test_same_offer_from_aggregator_is_merged(self) -> None:
        """CBOP + 2x jooble tej samej oferty MDK → jedna karta."""
        result = dedupe.deduplicate([
            offer("Nauczyciel-Instruktor (k/m)",
                  "Młodzieżowy Dom Kultury Fort 49 Krzesławice (Kraków)",
                  "cbop"),
            offer("Nauczyciel-Instruktor (k/m)",
                  "Młodzieżowy Dom Kultury Fort 49 Krzesławice (Kraków) "
                  "[jooble.org]", "jooble"),
            offer("NAUCZYCIEL-INSTRUKTOR (K/M)",
                  "Młodzieżowy Dom Kultury Fort 49 Krzesławice", "jooble",
                  url="jooble/inny"),
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source"], "cbop",
                         "karta główna z lepszego źródła, nie z agregatora")
        self.assertEqual(result[0]["duplicate_count"], 2)

    def test_regional_variants_are_grouped(self) -> None:
        """12 wariantów regionalnych jednego ogłoszenia → 1 + podobne."""
        firm = "Agencja Art-Rekl. Bede Productions"
        variants = [f"Koordynator ds. Organizacji Widowni i Logistyki – "
                    f"praca mobilna woj. {r}"
                    for r in ("Małopolskie", "Śląskie", "Podkarpackie")]
        variants.append("Koordynator ds. Organizacji Widowni i Logistyki – "
                        "praca mobilna Cała Polska")
        result = dedupe.deduplicate([offer(v, firm) for v in variants])
        self.assertEqual(len(result), 1)

    def test_same_title_other_employer_is_similar_not_merged(self) -> None:
        """Ten sam tytuł, inny pracodawca → osobne oferty, ale zgrupowane."""
        result = dedupe.deduplicate([
            offer("Instruktor terapii zajęciowej (K/M)",
                  "BONIFRATERSKA FUNDACJA DOBROCZYNNA", "cbop", "weak"),
            offer("Instruktor terapii zajęciowej (k/m)",
                  "Fundacja im. Brata Alberta", "cbop", "weak"),
        ])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["similar"]), 1,
                         "druga oferta do rozwinięcia, nie zgubiona")
        self.assertNotIn("also_on", result[0],
                         "różni pracodawcy to nie duplikat")

    def test_same_portal_two_posts_are_similar_not_merged(self) -> None:
        """Dwa ogłoszenia tej samej biblioteki w jednym portalu → osobne."""
        lib = "Biblioteka Kraków (Kraków)"
        result = dedupe.deduplicate([
            offer("Młodszy bibliotekarz (umowa na zastępstwo) (M/K)", lib),
            offer("Młodszy bibliotekarz (M/K)", lib),
        ])
        self.assertEqual(len(result), 1)
        self.assertNotIn("also_on", result[0])
        self.assertEqual(len(result[0]["similar"]), 1)

    def test_one_letter_difference_stays_separate(self) -> None:
        """'grafiki' vs 'fizyki' — różne oferty mimo podobnego zapisu."""
        result = dedupe.deduplicate([
            offer("Nauczyciel grafiki", "Szkoła A"),
            offer("Nauczyciel fizyki", "Szkoła B"),
        ])
        self.assertEqual(len(result), 2)

    def test_strong_match_is_never_hidden_under_weak(self) -> None:
        """W grupie podobnych na wierzchu jest najlepsze dopasowanie."""
        result = dedupe.deduplicate([
            offer("Edukator muzealny", "Muzeum Etnograficzne", "jooble",
                  "weak"),
            offer("Edukator muzealny", "Muzeum Narodowe", "jooble",
                  "strong"),
        ])
        self.assertEqual(result[0]["profile_level"], "strong")

    def test_different_offers_untouched(self) -> None:
        """Brak odpowiedników → wynik równy wejściu."""
        result = dedupe.deduplicate([
            offer("GRAFIK/GRAFICZKA", "Teatr Groteska"),
            offer("Edukator / Edukatorka", "Zamek Królewski na Wawelu"),
        ])
        self.assertEqual(len(result), 2)
        self.assertTrue(all("similar" not in r and "also_on" not in r
                            for r in result))


if __name__ == "__main__":
    unittest.main()


class NoChainingTest(unittest.TestCase):
    """Grupowanie podobnych nie może łączyć przechodnio (A~B~C)."""

    def test_python_titles_from_many_firms_stay_visible(self) -> None:
        """Różne oferty 'Python Developer' w różnych firmach — osobno."""
        offers = [
            offer("Senior Python Developer (Django)", "Addepto",
                  "nofluffjobs"),
            offer("Senior Python Developer (AWS)", "Antal", "nofluffjobs"),
            offer("Python Developer (AI / LLM)", "Diagnostyka",
                  "nofluffjobs"),
            offer("Senior Python Engineer", "Astek Polska", "nofluffjobs"),
        ]
        self.assertEqual(len(dedupe.deduplicate(offers)), 4)

    def test_chain_is_broken(self) -> None:
        """Wariant A~B u jednej firmy i B~C u drugiej nie łączy A z C."""
        result = dedupe.deduplicate([
            offer("Grafik komputerowy DTP", "Drukarnia X"),
            offer("Grafik komputerowy", "Drukarnia X"),
            offer("Grafik komputerowy", "Agencja Y"),
            offer("Grafik", "Agencja Y"),
        ])
        sizes = sorted(1 + len(r.get("similar", [])) for r in result)
        self.assertLessEqual(max(sizes), 3,
                             "żadna grupa nie może wchłonąć wszystkich")
