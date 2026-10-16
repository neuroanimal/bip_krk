#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orchestrator — uruchamia cały potok scrapujący po kolei (1..5).

Wygodne do codziennego uruchamiania (np. z Harmonogramu zadań Windows lub
z crona na Linux). Wykonuje kolejno pięć skryptów potoku; przerywa, gdy
któryś zwróci błąd. Dzięki zasadzie "collect data once, make it usable
anytime" każde uruchomienie powiększa datasety o zmiany, zachowując historię.

Uruchomienie (Windows i Linux identycznie):

    python run_all.py
    python run_all.py --verbose
    python run_all.py --sample 15   # tryb próbny: tylko 15 jednostek, szybko
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import bip_common as bc

# Kolejność etapów potoku. Każdy zależy od wyniku poprzedniego.
#
# 3b (globalna lista naborów BIP) zastępuje w praktyce chodzenie po stronach
# jednostek: jedno żądanie daje wszystkie ~435 naborów. Etapy 2 i 3
# (per jednostka) pozostają, bo wychwytują jednostki publikujące wyłącznie
# u siebie — ale są wolne (~400 żądań), więc w trybie próbnym są ograniczane.
#
# src_* to dodatkowe źródła poza BIP (filtr: Kraków, bez ofert
# nauczycielskich). Ich błędy nie przerywają potoku — są tylko uzupełnieniem.
PIPELINE = [
    "1_fetch_units.py",
    "2_fetch_praca_links.py",
    "3_fetch_offers.py",
    "3b_fetch_offers_global.py",
    "src_nuzle.py",
    "src_ofertypracy_edu.py",
    "src_kultura_instytucje.py",
    "src_nofluffjobs.py",
    "src_cbop.py",
    "src_remote_intl.py",
    "src_bulldogjob.py",
    "4_fetch_offer_details.py",
    "5_generate_report.py",
]

# Etapy opcjonalne — ich niepowodzenie nie przerywa całego potoku
# (zewnętrzny portal może być chwilowo niedostępny).
OPTIONAL_STEPS = {"src_nuzle.py", "src_ofertypracy_edu.py",
                  "src_kultura_instytucje.py", "src_nofluffjobs.py",
                  "src_cbop.py", "src_remote_intl.py",
                  "src_bulldogjob.py"}

# Które etapy mają sens dla którego PROFILU.
#
# Bez tego podziału profil danych/AI obchodziłby ~550 jednostek BIP miasta
# (szkoły, żłobki, przedszkola) i instytucje kultury, co trwa ~20 minut
# i nie daje ani jednej trafnej oferty. A profil kultury pobierałby
# bulldogjob (same stanowiska programistyczne).
#
# Etapy obsługujące OBA profile przyjmują ``--profile`` i same dobierają
# zapytania — tak robią nofluffjobs (grafika vs dane) i CBOP.
STEP_PROFILES = {
    "1_fetch_units.py": {"kultura"},
    "2_fetch_praca_links.py": {"kultura"},
    "3_fetch_offers.py": {"kultura"},
    "3b_fetch_offers_global.py": {"kultura"},
    "src_nuzle.py": {"kultura"},
    "src_ofertypracy_edu.py": {"kultura"},
    "src_kultura_instytucje.py": {"kultura"},
    "src_remote_intl.py": {"kultura", "it"},
    "src_nofluffjobs.py": {"kultura", "it"},
    "src_cbop.py": {"kultura", "it"},
    "src_bulldogjob.py": {"it"},
    # Etap 4 pobiera treść ogłoszenia z jego strony — ma sens tylko dla
    # BIP, gdzie strona oferty to statyczny HTML. Źródła profilu IT
    # (nofluffjobs, bulldogjob) to aplikacje JavaScript: zmierzone na
    # 219 ofertach dało 191 rekordów szczegółów i ZERO z czytelną treścią,
    # kosztem ~6 minut i tyluż żądań. Opis i tak mamy z API w raw_text.
    "4_fetch_offer_details.py": {"kultura"},
    "5_generate_report.py": {"kultura", "it"},
}

# Etapy, które przyjmują przełącznik ``--profile``. Etapy wyłącznie
# „kulturowe” go nie znają (nie mają po co), więc nie wolno im go podać.
PROFILE_AWARE = {"src_nofluffjobs.py", "src_cbop.py", "src_remote_intl.py",
                 "src_bulldogjob.py", "4_fetch_offer_details.py",
                 "5_generate_report.py"}


def sample_args(script: str, sample: int) -> List[str]:
    """Zwraca argumenty trybu próbnego dla danego etapu potoku.

    Tryb próbny ma dać szybki pełny przebieg na małej próbce, aby zweryfikować
    działanie bez czekania na ~400 żądań. Etapy 2/3/4 ograniczamy przez
    ``--limit`` (liczba jednostek/ofert), etap 5 przez ``--sample`` (liczba
    ofert w raporcie). Etap 1 (lista jednostek) jest szybki i pobiera całość,
    aby kategorie były kompletne.

    Args:
        script: nazwa pliku etapu.
        sample: rozmiar próbki.

    Returns:
        Listę dodatkowych argumentów wiersza poleceń dla etapu.
    """
    if script in ("2_fetch_praca_links.py", "3_fetch_offers.py",
                  "4_fetch_offer_details.py"):
        return ["--limit", str(sample)]
    if script == "5_generate_report.py":
        return ["--sample", str(sample)]
    # Źródła zewnętrzne: nuzle pobiera jedną stronę (bez paginacji w URL),
    # więc w trybie próbnym nic nie trzeba ograniczać; portal oświatowy
    # filtruje po Krakowie i tak. 3b to jedno żądanie — zostawiamy w całości.
    return []


def run_step(script: str, verbose: bool,
             sample: Optional[int] = None,
             profile: str = "") -> int:
    """Uruchamia pojedynczy skrypt potoku jako podproces.

    Używamy ``sys.executable``, aby na Windows i Linux uruchomić dokładnie
    ten sam interpreter Pythona, którym uruchomiono orchestrator.

    Args:
        script: nazwa pliku skryptu do uruchomienia.
        verbose: gdy True, przekazuje flagę --verbose do skryptu.
        sample: rozmiar próbki trybu próbnego (None = pełny przebieg).
        profile: profil zawodowy; przekazywany tylko etapom z
            :data:`PROFILE_AWARE` (pozostałe nie znają tej opcji).

    Returns:
        Kod wyjścia podprocesu.
    """
    script_path = Path(__file__).resolve().parent / script
    command = [sys.executable, str(script_path)]
    if profile and script in PROFILE_AWARE:
        command.extend(["--profile", profile])
    if verbose:
        command.append("--verbose")
    if sample is not None:
        command.extend(sample_args(script, sample))
    logging.info("=== Uruchamiam: %s ===", script)
    result = subprocess.run(command, check=False)
    return result.returncode


def main() -> int:
    """Punkt wejścia orchestratora.

    Returns:
        0 gdy cały potok się powiódł, w przeciwnym razie kod błędu etapu.
    """
    parser = argparse.ArgumentParser(
        description="Uruchamia cały potok scrapujący (skrypty 1-5).",
    )
    parser.add_argument("--verbose", action="store_true", help="Logi DEBUG.")
    parser.add_argument(
        "--sample", type=int, default=None, metavar="N",
        help="Tryb próbny: przetwarzaj tylko N jednostek/ofert (szybka "
             "weryfikacja całego potoku bez pełnego pobierania).",
    )
    bc.add_profile_argument(parser)
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.use_profile(args.profile)
    bc.ensure_dirs()

    steps = [s for s in PIPELINE
             if args.profile in STEP_PROFILES.get(s, {args.profile})]
    skipped = [s for s in PIPELINE if s not in steps]
    logging.info("Profil: %s — etapów do wykonania: %d z %d.",
                 args.profile, len(steps), len(PIPELINE))
    if skipped:
        logging.info("Pominięte (nie dotyczą tego profilu): %s",
                     ", ".join(skipped))

    if args.sample is not None:
        logging.info("TRYB PRÓBNY: próbka = %d (szybki przebieg).",
                     args.sample)

    for script in steps:
        code = run_step(script, args.verbose, args.sample, args.profile)
        if code != 0:
            if script in OPTIONAL_STEPS:
                # Zewnętrzne źródło zawiodło — notujemy i idziemy dalej,
                # bo BIP (główne źródło) jest niezależny od tych portali.
                logging.warning(
                    "Etap opcjonalny %s zakończył się błędem (kod %d) — "
                    "kontynuuję potok.", script, code,
                )
                continue
            logging.error("Etap %s zakończył się błędem (kod %d) — przerywam.",
                          script, code)
            return code

    logging.info("Cały potok zakończony sukcesem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
