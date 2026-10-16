#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Punkt wejścia dla wersji spakowanej do pliku .exe (PyInstaller).

Ten skrypt jest przeznaczony do uruchamiania jako pojedynczy plik
wykonywalny w Windows (bez zainstalowanego Pythona). Wykonuje cały potok
scrapujący (etapy 1-5), a następnie automatycznie otwiera świeżo
wygenerowany raport HTML w domyślnej przeglądarce — dzięki temu po
podwójnym kliknięciu w .exe użytkownik od razu widzi raport za dziś.

Różnica względem ``run_all.py``: tam etapy uruchamiane są jako osobne
podprocesy (``python 1_fetch_units.py`` itd.), co w spakowanym .exe nie
zadziała (nie ma osobnego interpretera ani plików .py obok). Tutaj
importujemy moduły etapów i wołamy ich funkcje ``main()`` w tym samym
procesie.

UWAGA dot. nazw modułów: pliki etapów zaczynają się od cyfry
(``1_fetch_units.py``), więc nie można ich zaimportować zwykłym
``import 1_fetch_units``. Używamy ``importlib`` z jawną ścieżką.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
import webbrowser
from pathlib import Path
from types import ModuleType
from typing import List, Optional

# Katalog z modułami projektu musi być na ścieżce importu PRZED pierwszym
# importem własnych modułów. W spakowanym .exe (PyInstaller onefile) pliki
# źródłowe lądują w katalogu tymczasowym ``sys._MEIPASS``, a moduły etapów
# są dołączone jako dane (``datas`` w .spec), więc nie trafiają tam
# automatycznie. Bez tego etap 5 nie zaimportuje ``report_html``.
_HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import bip_common as bc  # noqa: E402  (po ustawieniu sys.path)

# Kolejność etapów potoku (ta sama co w run_all.py).
#
# 3b (globalna lista naborów BIP) daje komplet ofert jednym żądaniem;
# etapy 2 i 3 chodzą po stronach jednostek i wychwytują te, które publikują
# nabory wyłącznie u siebie. src_* to źródła poza BIP.
PIPELINE_MODULES = [
    "1_fetch_units",
    "2_fetch_praca_links",
    "3_fetch_offers",
    "3b_fetch_offers_global",
    "src_nuzle",
    "src_ofertypracy_edu",
    "src_kultura_instytucje",
    "src_nofluffjobs",
    "src_cbop",
    "src_remote_intl",
    "src_bulldogjob",
    "4_fetch_offer_details",
    "5_generate_report",
]

# Etapy, których niepowodzenie NIE przerywa potoku — zewnętrzny portal może
# być chwilowo niedostępny, a raport ma powstać na danych z BIP.
OPTIONAL_MODULES = {"src_nuzle", "src_ofertypracy_edu",
                    "src_kultura_instytucje", "src_nofluffjobs",
                    "src_cbop", "src_remote_intl",
                    "src_bulldogjob"}


def _base_dir() -> Path:
    """Zwraca katalog bazowy, w którym leżą moduły etapów potoku.

    W spakowanym .exe (PyInstaller onefile) pliki źródłowe są rozpakowywane
    do katalogu tymczasowego wskazywanego przez ``sys._MEIPASS``. Poza .exe
    (zwykłe uruchomienie) używamy katalogu tego pliku.

    Returns:
        Ścieżkę do katalogu z modułami etapów.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def load_stage(module_name: str) -> ModuleType:
    """Ładuje moduł etapu potoku po nazwie pliku (obsługuje nazwy z cyfrą).

    Przed załadowaniem upewniamy się, że katalog z modułami jest w
    ``sys.path``. Jest to konieczne w spakowanym .exe: etap 5 importuje
    ``report_html`` ZWYKŁYM importem, a moduły etapów są dołączone jako
    pliki danych (``datas`` w .spec), więc nie trafiają automatycznie na
    ścieżkę importu.

    Args:
        module_name: nazwa modułu bez rozszerzenia (np. '1_fetch_units').

    Returns:
        Załadowany obiekt modułu.

    Raises:
        ImportError: gdy pliku modułu nie da się znaleźć lub załadować.
    """
    base = _base_dir()
    base_str = str(base)
    if base_str not in sys.path:
        sys.path.insert(0, base_str)

    path = base / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Nie można załadować modułu: {path}")
    module = importlib.util.module_from_spec(spec)
    # Rejestrujemy w sys.modules, aby ewentualne wzajemne importy działały.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def find_latest_html_report() -> Optional[Path]:
    """Znajduje najnowszy wygenerowany raport HTML w katalogu reports/.

    Returns:
        Ścieżkę do najnowszego pliku .html albo ``None``, gdy brak raportów.
    """
    reports = sorted(
        bc.REPORTS_DIR.glob("raport_praca_*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return reports[0] if reports else None


def main() -> int:
    """Uruchamia cały potok i otwiera raport HTML w przeglądarce.

    Returns:
        0 przy sukcesie; kod błędu etapu, gdy któryś zawiedzie.
    """
    bc.setup_logging(verbose=False)
    bc.ensure_dirs()

    # Podmieniamy argv, aby argparse w modułach etapów nie zobaczył
    # ewentualnych argumentów przekazanych do .exe (uruchamiamy z domyślnymi).
    original_argv = sys.argv
    for module_name in PIPELINE_MODULES:
        logging.info("=== Etap: %s ===", module_name)
        sys.argv = [f"{module_name}.py"]  # brak dodatkowych flag
        code = 1
        try:
            module = load_stage(module_name)
            code = module.main()
        except Exception as error:  # pylint: disable=broad-exception-caught
            # Wyjątek w etapie opcjonalnym (np. zmiana API portalu) nie może
            # przerwać całego raportu — logujemy i idziemy dalej.
            logging.error("Etap %s zgłosił wyjątek: %s: %s",
                          module_name, type(error).__name__, error)
        finally:
            sys.argv = original_argv

        if code != 0:
            if module_name in OPTIONAL_MODULES:
                logging.warning(
                    "Etap opcjonalny %s nie powiódł się (kod %d) — "
                    "kontynuuję potok.", module_name, code,
                )
                continue
            logging.error("Etap %s zwrócił błąd (kod %d) — przerywam.",
                          module_name, code)
            _pause_on_exit()
            return code

    # Otwieramy najnowszy raport HTML w domyślnej przeglądarce.
    report = find_latest_html_report()
    if report is not None:
        logging.info("Otwieram raport w przeglądarce: %s", report)
        webbrowser.open(report.resolve().as_uri())
    else:
        logging.warning("Nie znaleziono raportu HTML do otwarcia.")

    _pause_on_exit()
    return 0


def _pause_on_exit() -> None:
    """Zatrzymuje okno konsoli po zakończeniu (wygoda w Windows).

    Gdy .exe uruchomiono podwójnym kliknięciem, okno konsoli zniknęłoby
    natychmiast po zakończeniu. Krótka pauza pozwala odczytać komunikaty.
    """
    try:
        logging.info("Gotowe. Okno zamknie się za 5 sekund…")
        time.sleep(5)
    except KeyboardInterrupt:  # użytkownik zamknął wcześniej
        pass


# Nazwa modułu bip_common musi być dostępna dla ładowanych etapów.
# (etapy robią `import bip_common as bc` — w .exe jest on dołączony)
_UNUSED_KEEP_IMPORTS: List[object] = [bc]

if __name__ == "__main__":
    raise SystemExit(main())
