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
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

import bip_common as bc

# Kolejność etapów potoku. Każdy zależy od wyniku poprzedniego.
PIPELINE = [
    "1_fetch_units.py",
    "2_fetch_praca_links.py",
    "3_fetch_offers.py",
    "4_fetch_offer_details.py",
    "5_generate_report.py",
]


def run_step(script: str, verbose: bool) -> int:
    """Uruchamia pojedynczy skrypt potoku jako podproces.

    Używamy ``sys.executable``, aby na Windows i Linux uruchomić dokładnie
    ten sam interpreter Pythona, którym uruchomiono orchestrator.

    Args:
        script: nazwa pliku skryptu do uruchomienia.
        verbose: gdy True, przekazuje flagę --verbose do skryptu.

    Returns:
        Kod wyjścia podprocesu.
    """
    script_path = Path(__file__).resolve().parent / script
    command = [sys.executable, str(script_path)]
    if verbose:
        command.append("--verbose")
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
    args = parser.parse_args()

    bc.setup_logging(args.verbose)
    bc.ensure_dirs()

    for script in PIPELINE:
        code = run_step(script, args.verbose)
        if code != 0:
            logging.error("Etap %s zakończył się błędem (kod %d) — przerywam.",
                          script, code)
            return code

    logging.info("Cały potok zakończony sukcesem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
