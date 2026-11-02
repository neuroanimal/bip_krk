#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy regresji oceny dopasowania do profilu.

Każdy przypadek tutaj to **realna oferta z danych**, która kiedyś była
oceniona źle (fałszywe trafienie albo przegapione), albo oferta, której
poprawna ocena jest warunkiem sensu raportu. Komentarz przy przypadku mówi,
co poszło nie tak — żeby przy kolejnej zmianie logiki było widać, czego
nie wolno zepsuć.

Uruchomienie::

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import profile_match as pm  # noqa: E402  pylint: disable=wrong-import-position

STRONG, WEAK, NONE = "strong", "weak", "none"

# (tytuł, opis, pracodawca, oczekiwany poziom, dlaczego)
KULTURA_CASES = [
    # --- muszą być mocne: rdzeń profilu ---
    ("GRAFIK/GRAFICZKA", "", "Teatr Groteska", STRONG, "rdzeń: grafika"),
    ("Grafik/czka", "", "kontakt przez PUP", STRONG, "rdzeń: grafika"),
    ("Plastyk K/M (O)", "", "SIGMA-GLASS", STRONG, "rdzeń: plastyka"),
    ("Edukator / Edukatorka", "", "Zamek Królewski na Wawelu", STRONG,
     "edukacja muzealna"),
    ("Asystent/asystentka w grupie pracowników badawczo-dydaktycznych",
     "Katedra grafiki", "Akademia Sztuk Pięknych w Krakowie", STRONG,
     "ogólny tytuł, ale ASP — preferowany pracodawca"),
    ("Instruktor/Instruktorka – organizujący/a działalność w Klubie Dukat",
     "", "Ośrodek Kultury Kraków-Nowa Huta", STRONG,
     "oferta, której raportowi brakowało"),
    ("Instruktor zajęć plastycznych", "", "Dom Kultury", STRONG,
     "instruktor w kontekście plastycznym"),
    ("Wychowawca w świetlicy szkolnej", "", "Szkoła Podstawowa", STRONG,
     "prośba adresatki: świetlice"),
    ("Specjalista ds. organizacji imprez", "", "Centrum Kultury Podgórza",
     STRONG, "prośba adresatki: imprezy; odmiana organizacji"),
    ("Specjalista ds. mediów społecznościowych", "", "Muzeum", STRONG,
     "prośba adresatki: media społecznościowe"),
    ("Social Media Graphic Designer", "", "BLUEBINARY", STRONG,
     "grafika + social media"),
    ("Senior Graphic Designer", "", "BBE Marketing", STRONG,
     "angielski odpowiednik grafika"),
    ("Asystent/asystentka w grupie pracowników badawczo-dydaktycznych",
     "Katedra Grafiki Warsztatowej; wymagany staż pracy 2 lata, "
     "doświadczenie praktyczne",
     "Akademia Sztuk Pięknych w Krakowie", STRONG,
     "'staż pracy' w opisie to NIE staż — degradował najlepszą ofertę"),
    ("Specjalista ds. promocji", "", "Muzeum Narodowe w Krakowie", STRONG,
     "budżetowa nazwa roli social media — wniosek z analizy rynku"),
    ("Specjalista ds. komunikacji i promocji", "",
     "Centrum Kultury Podgórza", STRONG, "promocja w instytucji kultury"),
    # --- degradowane: wiarygodne, ale z zastrzeżeniem ---
    ("Referent ds. promocji", "", "Urząd Gminy Zabierzów", WEAK,
     "budżetówka, ale nie kultura"),
    ("Staż – Projektant_ka Graficzny_a", "", "Fundacja", WEAK,
     "staż w tytule: bez stabilnego zatrudnienia"),
    ("Kandydat/kandydatka na stanowisko dyrektora Domu Kultury",
     "animacja kultury, organizacja wydarzeń, warsztaty artystyczne",
     "Dom Kultury Białogon", WEAK, "konkurs na dyrektora"),
    ("Instruktor zajęć dla dzieci", "", "Edwings", WEAK,
     "zajęcia dla dzieci bez kontekstu kultury — najwyżej 'może pasować'"),
    ("Instruktor terapii zajęciowej (K/M)", "",
     "Fundacja Warsztat Terapii Zajęciowej", WEAK, "wymaga kursu terapii"),
    ("Nauczyciel-Instruktor (k/m)", "Zawód: instruktor sportu",
     "Młodzieżowy Dom Kultury Fort 49", WEAK,
     "dom kultury właściwy, ale sport w opisie"),
    # --- muszą odpaść: fałszywe trafienia z historii projektu ---
    ("Zbrojarz warsztatowy K/M", "", "ACERO SYSTEM", NONE,
     "słowo 'warsztat' w znaczeniu produkcyjnym"),
    ("LEKARZ PSYCHIATRA", "", "Poradnia Psychologiczno-Pedagogiczna", NONE,
     "trafienie przez nazwę placówki"),
    ("Osoba sprzątająca", "", "Muzeum Narodowe w Krakowie", NONE,
     "sprzątanie w dobrej instytucji to nadal sprzątanie"),
    ("Sprzątaczka - zastępstwo na czas nieobecności", "", "Szkoła", NONE,
     "zarzut adresatki"),
    ("Główny księgowy", "", "Teatr im. Słowackiego", NONE, "księgowość"),
    ("ELASTYCZNY GRAFIK - hostessa", "elastyczny grafik pracy", "klub",
     NONE, "homonim: grafik = harmonogram"),
    ("Senior UX Designer", "", "Mindbox", NONE, "prośba: bez UI/UX"),
    ("Product Designer", "", "Keepit", NONE, "prośba: bez UI/UX"),
    ("Instruktor Fitness / Instruktorka Fitness", "", "Well Fitness", NONE,
     "sport"),
    ("Poszukujemy instruktora pływania Kraków", "", "basen", NONE, "sport"),
    ("Instruktor / Instruktorka Sportów Walki", "", "klub", NONE,
     "sport — przeoczony przez listę fraz"),
    ("Praca, zatrudnię instruktora nauki jazdy kat. B", "", "OSK", NONE,
     "odmiana: 'instruktora nauki jazdy'"),
    ("Pracownik Mobilny - Inżynier Serwisu / Instruktor Maszyn", "",
     "firma", NONE, "instruktor techniczny"),
    ("Recenzent teatralny", "recenzje spektakli, sztuka, artyści",
     "Dziennik Teatralny", WEAK,
     "'teatr' w nazwie gazety udawał teatr i dawał STRONG; opis o sztuce "
     "uczciwie zostawia 'może pasować'"),
    ("Recenzent teatralny", "recenzje",
     "Dziennik Teatralny (Wszystkie miejscowości, w których znajduje się "
     "teatr)", NONE, "'teatr' w dopisku lokalizacji, nie w nazwie; "
     "sam opis 'recenzje' nie ma treści z profilu"),
    ("Przesłuchania: Głos tenorowy | Chór Polskiego Radia", "", "ECM",
     NONE, "śpiew — inna dziedzina"),
    ("Nauczyciel matematyki", "", "Szkoła", NONE, "nauczanie przedmiotu"),
    ("Specjalista ds. promocji sprzedaży", "", "Hurtownia X", NONE,
     "promocja handlowa"),
    ("Pracownik ds. promocji", "", "Sklep sportowy", NONE,
     "promocja bez kontekstu kultury"),
    ("Customer Success Content Reviewer with Czech",
     "Czym będziesz się zajmować: media społecznościowe", "TP Polska",
     NONE, "obsługa klienta z wymogiem czeskiego"),
    ("Realizatorka/realizator oświetlenia", "sztuka, teatr",
     "Teatr im. Witkiewicza w Zakopanem", NONE, "technika sceniczna"),
    ("Education Designer: UX, UI, and AI", "", "IxDF", NONE,
     "UX w krótkiej postaci"),
    ("Data Scientist", "Python", "deepsense.ai", NONE, "inny profil"),
]

IT_CASES = [
    ("Senior Data Scientist", "Python, ML, SQL", "deepsense.ai", STRONG, ""),
    ("Data Engineer", "Spark, Airflow, AWS", "XTB", STRONG, ""),
    ("AI Engineer", "LLM, Python", "Mindbox", STRONG, ""),
    ("Software Engineer (Machine Learning - MLOps)", "", "Tesco", STRONG,
     ""),
    ("Senior Java Developer", "Spring Boot, JEE", "Luxoft", STRONG, ""),
    ("Android Developer", "Kotlin", "Grid Dynamics", STRONG, ""),
    ("Programista-Operator CNC K/M", "", "firma", NONE, "automatyka"),
    ("IT Recruiter", "Python, Java", "agencja", NONE, "rekrutacja"),
    ("Analityk kredytowy", "analiza danych kredytowych SQL", "bank", NONE,
     "homonim analityk"),
    ("GRAFIK/GRAFICZKA", "", "Teatr Groteska", NONE, "inny profil"),
]


class ProfileRegressionTest(unittest.TestCase):
    """Sprawdza, że ocena każdego znanego przypadku się nie zmieniła."""

    def _check(self, profile: str, cases) -> None:
        """Wspólna pętla — każdy przypadek jako osobny subTest."""
        pm.set_profile(profile)
        for title, body, employer, expected, why in cases:
            with self.subTest(title=title):
                level = pm.score_offer(title, body, employer)["profile_level"]
                self.assertEqual(level, expected,
                                 f"{title!r} @ {employer!r}: {why}")

    def test_kultura(self) -> None:
        """Profil kultury: rdzeń, degradacje i znane fałszywe trafienia."""
        self._check("kultura", KULTURA_CASES)

    def test_it(self) -> None:
        """Profil danych i AI."""
        self._check("it", IT_CASES)


if __name__ == "__main__":
    unittest.main()
