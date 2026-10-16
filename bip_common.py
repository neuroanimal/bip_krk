#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wspólne narzędzia dla skryptów scrapujących BIP Kraków (praca).

Ten moduł zawiera funkcje współdzielone przez wszystkie pięć skryptów
potoku ("pipeline"):

* konfiguracja ścieżek (działa tak samo na Windows i na Linux/WSL dzięki
  ``pathlib`` — brak twardo zakodowanych separatorów ``/`` lub ``\\``),
* sesja HTTP z nagłówkiem User-Agent oraz automatycznym ponawianiem prób
  (retry) przy błędach sieciowych/5xx,
* wczytywanie i zapisywanie plików JSON w UTF-8 (polskie znaki),
* pomocnicze funkcje czasu (znacznik czasu ISO 8601 z lokalną strefą),
* logika "collect data once, make it usable anytime": rekordy w datasetach
  są aktualizowane, a nie nadpisywane — zachowujemy ``first_seen``,
  ``last_seen`` oraz status ``active`` / datę wygaśnięcia ``inactive_since``.

Zależności zewnętrzne: ``requests`` oraz ``beautifulsoup4`` (bs4).
Instalacja (Windows i Linux identycznie):

    python -m pip install requests beautifulsoup4
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urljoin

import requests

# --- Stałe konfiguracyjne -------------------------------------------------

# Bazowy adres serwisu BIP Miasta Krakowa. Wszystkie linki względne
# (np. "?bip_id=28&nab_id=15952") są rozwijane względem tego adresu.
BASE_URL = "https://www.bip.krakow.pl/"

# Strona z listą miejskich jednostek organizacyjnych (MJO) — punkt startowy
# skryptu 1. "mmi=9584" to identyfikator konkretnego widoku listy jednostek.
UNITS_LIST_URL = "https://www.bip.krakow.pl/?bip_id=1&mmi=9584"

# Katalog główny projektu — miejsce, w którym zapisujemy datasety i raporty.
#
# Rozróżniamy dwa tryby uruchomienia:
# 1) Zwykły skrypt Pythona — katalog tego pliku (Path(__file__).parent).
# 2) Spakowany .exe (PyInstaller) — WYKRYWAMY po atrybucie sys.frozen.
#    Wtedy Path(__file__) wskazuje na tymczasowy katalog _MEIPASS, który
#    PyInstaller kasuje przy zamknięciu — zapisywanie tam oznaczałoby utratę
#    danych i raportów po każdym uruchomieniu. Dlatego w trybie .exe używamy
#    katalogu, w którym leży sam plik .exe (Path(sys.executable).parent), aby
#    data/, snapshots/ i reports/ powstawały OBOK .exe i były trwałe.
def _resolve_project_root() -> Path:
    """Zwraca katalog na dane/raporty, odporny na tryb PyInstaller.

    Returns:
        Katalog obok .exe (gdy uruchomiono jako spakowany plik) albo katalog
        źródła (gdy uruchomiono jako zwykły skrypt Pythona).
    """
    if getattr(sys, "frozen", False):
        # Uruchomiono jako .exe — dane mają leżeć obok pliku wykonywalnego.
        return Path(sys.executable).resolve().parent
    # Zwykłe uruchomienie skryptu — katalog tego modułu.
    return Path(__file__).resolve().parent


PROJECT_ROOT = _resolve_project_root()

# Profil domyślny — musi zgadzać się z ``profiles.DEFAULT``. Nie importujemy
# pakietu ``profiles``, żeby nie tworzyć zależności cyklicznej (profile nie
# potrzebują bip_common, ale etapy importują oba).
DEFAULT_PROFILE = "kultura"

# Katalog z "żywymi" datasetami (aktualizowany stan wiedzy).
DATA_DIR = PROJECT_ROOT / "data"

# Katalog na surowe zrzuty (snapshoty) — każdy przebieg zapisuje kopię
# z datą, aby móc odtworzyć historię ("collect once").
SNAPSHOTS_DIR = PROJECT_ROOT / "snapshots"

# Katalog na wygenerowane raporty (skrypt 5).
REPORTS_DIR = PROJECT_ROOT / "reports"

# Nazwy plików datasetów (jeden na etap potoku).
UNITS_DATASET = DATA_DIR / "units.json"                # skrypt 1
PRACA_LINKS_DATASET = DATA_DIR / "praca_links.json"    # skrypt 2
OFFERS_DATASET = DATA_DIR / "offers.json"              # skrypt 3
OFFER_DETAILS_DATASET = DATA_DIR / "offer_details.json"  # skrypt 4

# Stan "klikniętych/oglądanych" ofert — tracking klikania z raportu HTML.
# Raport jest statycznym plikiem otwieranym lokalnie (bez serwera), więc
# kliknięcia zapisuje przeglądarka w localStorage. Ten plik służy do
# zaimportowania tego stanu z powrotem do datasetu (eksport z raportu),
# aby informacja "to już oglądałem" przetrwała regenerację raportu.
CLICKS_DATASET = DATA_DIR / "clicks.json"

# Dziennik niepowodzeń pobierania/parsowania — wspólny dla wszystkich etapów.
# Zasada: nic nie ginie po cichu. Każde nieudane pobranie (404, timeout,
# pusta strona), brak oczekiwanego elementu albo niedopasowanie rekordu jest
# tu notowane z datą, etapem, adresem i powodem. Dzięki temu widać np. martwe
# linki, które BIP zostawił na liście aktualnej po przeniesieniu jednostki
# do archiwum.
FAILURES_DATASET = DATA_DIR / "failures.json"


def use_profile(slug: str) -> None:
    """Przestawia ścieżki danych i raportów na wskazany profil.

    Jedna aplikacja obsługuje kilka profili zawodowych (patrz pakiet
    ``profiles``), a każdy potrzebuje WŁASNYCH datasetów i raportów.
    Wspólny worek byłby błędem: raport dla profilu kultury pokazywałby
    kilkaset ofert IT w sekcji „pozostałe”, a to dokładnie ten szum, przed
    którym broni cały projekt.

    **Zgodność wstecz jest tu celowa i ważna**: profil domyślny
    (``kultura``) używa katalogów BEZ sufiksu — ``data/``, ``reports/``,
    ``snapshots/`` — czyli dokładnie tych, w których leżą dotychczasowe
    dane i na które wskazuje zbudowany wcześniej ``.exe``. Nic nie trzeba
    przenosić ani budować od nowa. Pozostałe profile dostają sufiks:
    ``data_it/``, ``reports_it/``, ``snapshots_it/``.

    Funkcję trzeba wywołać PRZED pierwszym użyciem ścieżek — robią to
    etapy potoku na początku ``main()``, zaraz po odczytaniu argumentów.

    Args:
        slug: identyfikator profilu (np. ``kultura``, ``it``).
    """
    global DATA_DIR, SNAPSHOTS_DIR, REPORTS_DIR  # pylint: disable=global-statement
    global UNITS_DATASET, PRACA_LINKS_DATASET  # pylint: disable=global-statement
    global OFFERS_DATASET, OFFER_DETAILS_DATASET  # pylint: disable=global-statement
    global CLICKS_DATASET, FAILURES_DATASET  # pylint: disable=global-statement

    suffix = "" if slug == DEFAULT_PROFILE else f"_{slug}"
    DATA_DIR = PROJECT_ROOT / f"data{suffix}"
    SNAPSHOTS_DIR = PROJECT_ROOT / f"snapshots{suffix}"
    REPORTS_DIR = PROJECT_ROOT / f"reports{suffix}"

    UNITS_DATASET = DATA_DIR / "units.json"
    PRACA_LINKS_DATASET = DATA_DIR / "praca_links.json"
    OFFERS_DATASET = DATA_DIR / "offers.json"
    OFFER_DETAILS_DATASET = DATA_DIR / "offer_details.json"
    CLICKS_DATASET = DATA_DIR / "clicks.json"
    FAILURES_DATASET = DATA_DIR / "failures.json"


def add_profile_argument(parser) -> None:
    """Dodaje do parsera wspólny przełącznik ``--profile``.

    Trzymamy to w jednym miejscu, żeby wszystkie etapy opisywały opcję
    identycznie i żeby dodanie profilu nie wymagało edycji kilkunastu
    plików.

    Args:
        parser: instancja ``argparse.ArgumentParser``.
    """
    parser.add_argument(
        "--profile", default=DEFAULT_PROFILE,
        help=("Profil zawodowy: 'kultura' (domyślny — kultura, sztuka, "
              "grafika) albo 'it' (dane, AI, backend). Wybiera osobne "
              "katalogi danych i raportów."),
    )

# Nagłówek User-Agent — serwis odpowiada poprawnie na "przeglądarkowy" UA.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36 bip-krk-praca-scraper/1.0"
)

# Parametry ponawiania prób pobierania.
HTTP_TIMEOUT = 30          # sekundy na pojedyncze żądanie
HTTP_RETRIES = 3           # liczba prób przy błędzie
HTTP_RETRY_BACKOFF = 2.0   # mnożnik opóźnienia między próbami (sekundy)

# Uprzejma przerwa między kolejnymi żądaniami, aby nie obciążać serwera.
POLITE_DELAY = 0.5


def setup_logging(verbose: bool = False) -> None:
    """Konfiguruje logowanie na stdout w czytelnym formacie.

    Args:
        verbose: gdy True, ustawia poziom DEBUG; w przeciwnym razie INFO.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def now_iso() -> str:
    """Zwraca bieżący czas jako łańcuch ISO 8601 z lokalną strefą czasową.

    Używamy ``astimezone()`` bez argumentu, aby otrzymać lokalną strefę
    systemu — działa identycznie na Windows i Linux.
    """
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_str() -> str:
    """Zwraca dzisiejszą datę jako 'YYYY-MM-DD' (do nazw snapshotów)."""
    return datetime.now().strftime("%Y-%m-%d")


def timestamp_str() -> str:
    """Zwraca znacznik 'YYYY-MM-DD_HHMMSS' bezpieczny w nazwach plików.

    Dwukropki nie są dozwolone w nazwach plików na Windows, więc godzinę
    zapisujemy bez separatorów.
    """
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def ensure_dirs() -> None:
    """Tworzy katalogi projektu, jeśli jeszcze nie istnieją."""
    for directory in (DATA_DIR, SNAPSHOTS_DIR, REPORTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def build_session() -> requests.Session:
    """Buduje sesję ``requests`` ze wspólnym nagłówkiem User-Agent.

    Zwracana sesja utrzymuje połączenia (keep-alive), co przyspiesza
    pobieranie wielu stron z tej samej domeny.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch(session: requests.Session, url: str) -> Optional[str]:
    """Pobiera zawartość strony jako tekst, z ponawianiem prób.

    Args:
        session: sesja HTTP zbudowana przez :func:`build_session`.
        url: pełny lub względny adres (względny jest rozwijany do
            :data:`BASE_URL`).

    Returns:
        Treść odpowiedzi jako tekst (UTF-8) lub ``None``, jeśli wszystkie
        próby zawiodły.
    """
    # Rozwijamy adresy względne (np. "?bip_id=28&nab_id=...") do pełnych.
    full_url = urljoin(BASE_URL, url)

    last_error: Optional[Exception] = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = session.get(full_url, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            # Serwis deklaruje UTF-8; wymuszamy je, by uniknąć złego
            # zgadywania kodowania przez requests przy braku charset.
            response.encoding = response.apparent_encoding or "utf-8"
            time.sleep(POLITE_DELAY)  # uprzejma przerwa między żądaniami
            return response.text
        except requests.RequestException as error:  # sieć / 4xx / 5xx
            last_error = error
            wait = HTTP_RETRY_BACKOFF * attempt
            logging.warning(
                "Próba %d/%d nieudana dla %s: %s (ponawiam za %.1fs)",
                attempt, HTTP_RETRIES, full_url, error, wait,
            )
            time.sleep(wait)

    logging.error("Nie udało się pobrać %s: %s", full_url, last_error)
    return None


def load_dataset(path: Path) -> Dict[str, Any]:
    """Wczytuje dataset JSON z dysku; zwraca pusty szkielet, gdy brak pliku.

    Struktura datasetu jest ujednolicona:

        {
            "meta": {"created": <iso>, "updated": <iso>},
            "records": { <klucz>: <rekord>, ... }
        }

    Args:
        path: ścieżka do pliku JSON.

    Returns:
        Słownik datasetu (zawsze z kluczami "meta" i "records").
    """
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        # Zabezpieczenie na wypadek starszego/uszkodzonego pliku.
        data.setdefault("meta", {})
        data.setdefault("records", {})
        return data
    return {"meta": {"created": now_iso(), "updated": None}, "records": {}}


def save_dataset(path: Path, data: Dict[str, Any]) -> None:
    """Zapisuje dataset JSON w UTF-8 z wcięciami (czytelny diff w git).

    Args:
        path: ścieżka docelowa.
        data: słownik datasetu do zapisania.
    """
    data.setdefault("meta", {})
    data["meta"]["updated"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")  # końcowy newline (przyjazny dla git)


def save_snapshot(name: str, payload: Any) -> Path:
    """Zapisuje surowy snapshot z timestampem w nazwie ("collect once").

    Snapshoty nigdy nie są nadpisywane — każdy przebieg tworzy nowy plik,
    dzięki czemu można odtworzyć dokładny stan strony z danego dnia i godziny.

    Args:
        name: przedrostek nazwy (np. "units", "praca_links").
        payload: dane do zapisania (serializowalne do JSON).

    Returns:
        Ścieżkę do zapisanego pliku snapshotu.
    """
    ensure_dirs()
    path = SNAPSHOTS_DIR / f"{name}_{timestamp_str()}.json"
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    logging.info("Zapisano snapshot: %s", path)
    return path


def upsert_record(
    records: Dict[str, Any],
    key: str,
    fields: Dict[str, Any],
    seen_now: str,
) -> Dict[str, Any]:
    """Wstawia lub aktualizuje rekord, śledząc first_seen/last_seen/active.

    To serce zasady "collect data once, make it usable anytime". Jeśli
    rekord jest nowy — zapisujemy ``first_seen``. Jeśli już istniał —
    aktualizujemy pola i ``last_seen`` oraz (gdy był nieaktywny) reaktywujemy
    go, czyszcząc ``inactive_since`` (stare linki mogą "wrócić do łask").

    Args:
        records: słownik wszystkich rekordów danego datasetu.
        key: unikalny klucz rekordu (np. bip_id jednostki lub URL oferty).
        fields: pola merytoryczne rekordu (nadpisują poprzednie wartości).
        seen_now: znacznik czasu bieżącego przebiegu (:func:`now_iso`).

    Returns:
        Zaktualizowany (lub nowo utworzony) rekord.
    """
    existing = records.get(key)
    if existing is None:
        # Nowy rekord — po raz pierwszy widziany w tym przebiegu.
        record: Dict[str, Any] = dict(fields)
        record["first_seen"] = seen_now
        record["last_seen"] = seen_now
        record["active"] = True
        record["inactive_since"] = None
        records[key] = record
        return record

    # Rekord już istniał — aktualizujemy pola merytoryczne.
    existing.update(fields)
    existing["last_seen"] = seen_now
    if not existing.get("active", True):
        # Link/oferta wróciły "do łask" — reaktywujemy.
        logging.info("Reaktywacja rekordu (wrócił do łask): %s", key)
        existing["active"] = True
        existing["inactive_since"] = None
    return existing


def deactivate_missing(
    records: Dict[str, Any],
    seen_keys: Iterable[str],
    seen_now: str,
) -> int:
    """Oznacza jako nieaktywne rekordy, których nie widziano w tym przebiegu.

    Nie usuwamy rekordów — zgodnie z "collect once" zachowujemy je z datą
    wygaśnięcia ``inactive_since``, aby zbudować pełną historię dostępności.

    Args:
        records: słownik wszystkich rekordów.
        seen_keys: klucze zaobserwowane w bieżącym przebiegu.
        seen_now: znacznik czasu bieżącego przebiegu.

    Returns:
        Liczbę rekordów świeżo oznaczonych jako nieaktywne.
    """
    seen = set(seen_keys)
    deactivated = 0
    for key, record in records.items():
        if key not in seen and record.get("active", True):
            record["active"] = False
            record["inactive_since"] = seen_now
            deactivated += 1
            logging.info("Oznaczono jako nieaktywny (wygasł): %s", key)
    return deactivated


def record_failure(stage: str, key: str, url: str, reason: str,
                   detail: str = "") -> None:
    """Notuje niepowodzenie pobierania/parsowania w dzienniku failures.json.

    Zasada: **nic nie ginie po cichu**. Wcześniej nieudane pobrania były tylko
    logowane ostrzeżeniem i porzucane, więc po przebiegu nie było śladu, czego
    nie udało się pobrać. Teraz każde takie zdarzenie jest zapisywane trwale,
    z licznikiem powtórzeń — co pozwala wychwycić systematyczne problemy, np.
    martwy link pozostawiony przez BIP na liście aktualnej po przeniesieniu
    jednostki do archiwum.

    Rekordy są kumulowane po kluczu ``stage|key|reason``: powtórzenie tego
    samego problemu zwiększa licznik i aktualizuje ``last_seen`` zamiast
    tworzyć duplikat.

    Args:
        stage: etap potoku (np. '2_praca_links', '3b_global').
        key: klucz rekordu, którego dotyczy problem (np. 'bip_id:474').
        url: adres, który zawiódł.
        reason: krótki kod powodu ('fetch_failed', 'no_praca_link',
            'unit_not_matched', 'parse_empty').
        detail: dodatkowy opis (opcjonalny).
    """
    data = load_dataset(FAILURES_DATASET)
    records = data["records"]
    now = now_iso()
    record_key = f"{stage}|{key}|{reason}"

    existing = records.get(record_key)
    if existing is None:
        records[record_key] = {
            "stage": stage,
            "key": key,
            "url": url,
            "reason": reason,
            "detail": detail,
            "first_seen": now,
            "last_seen": now,
            "count": 1,
            "resolved": False,
        }
    else:
        existing["last_seen"] = now
        existing["count"] = int(existing.get("count", 0)) + 1
        existing["url"] = url
        if detail:
            existing["detail"] = detail
        existing["resolved"] = False

    save_dataset(FAILURES_DATASET, data)
    logging.warning("[NIEPOWODZENIE %s] %s (%s) — %s", stage, key, reason, url)


def clear_failure(stage: str, key: str, reason: str) -> None:
    """Oznacza wcześniejsze niepowodzenie jako rozwiązane (gdy już działa).

    Nie usuwamy rekordu — zachowujemy historię problemu, ustawiając
    ``resolved: true``. Dzięki temu widać, że coś było zepsute i zostało
    naprawione (np. BIP poprawił link).

    Args:
        stage: etap potoku.
        key: klucz rekordu.
        reason: kod powodu.
    """
    data = load_dataset(FAILURES_DATASET)
    record_key = f"{stage}|{key}|{reason}"
    record = data["records"].get(record_key)
    if record is not None and not record.get("resolved"):
        record["resolved"] = True
        record["resolved_at"] = now_iso()
        save_dataset(FAILURES_DATASET, data)
        logging.info("[NAPRAWIONE %s] %s (%s)", stage, key, reason)


def fetch_with_reason(session: requests.Session,
                      url: str) -> Tuple[Optional[str], Optional[str]]:
    """Pobiera stronę, zwracając treść ORAZ powód niepowodzenia.

    Odmiana :func:`fetch`, która pozwala wywołującemu zanotować konkretny
    powód błędu (kod HTTP, timeout, pusta odpowiedź) w dzienniku niepowodzeń.

    Args:
        session: sesja HTTP.
        url: adres (pełny lub względny).

    Returns:
        Krotkę (treść, powód). Przy sukcesie powód jest None; przy błędzie
        treść jest None, a powód opisuje przyczynę (np. 'http_404').
    """
    full_url = urljoin(BASE_URL, url)
    last_reason: Optional[str] = None

    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = session.get(full_url, timeout=HTTP_TIMEOUT)
            if response.status_code >= 400:
                last_reason = f"http_{response.status_code}"
                # Błędy 4xx (np. 404) nie mają sensu ponawiać.
                if 400 <= response.status_code < 500:
                    return None, last_reason
                raise requests.HTTPError(last_reason)
            response.encoding = response.apparent_encoding or "utf-8"
            text = response.text
            time.sleep(POLITE_DELAY)
            if not text or not text.strip():
                return None, "empty_response"
            return text, None
        except requests.Timeout:
            last_reason = "timeout"
        except requests.RequestException as error:
            last_reason = last_reason or f"request_error:{type(error).__name__}"
        wait = HTTP_RETRY_BACKOFF * attempt
        logging.warning("Próba %d/%d nieudana dla %s (%s) — ponawiam za %.1fs",
                        attempt, HTTP_RETRIES, full_url, last_reason, wait)
        time.sleep(wait)

    return None, last_reason or "unknown_error"


def load_json(path: Path) -> Optional[Any]:
    """Wczytuje dowolny plik JSON; zwraca None, gdy pliku nie ma.

    Odmiana :func:`load_dataset` dla plików, które nie mają struktury
    meta/records — np. ``clicks.json`` wyeksportowany z raportu HTML.

    Args:
        path: ścieżka do pliku JSON.

    Returns:
        Zdeserializowane dane albo None, gdy plik nie istnieje lub jest
        uszkodzony.
    """
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as error:
        logging.warning("Nie udało się wczytać %s: %s", path, error)
        return None
