# BIP Kraków — scraper ofert pracy

Zestaw skryptów w Pythonie, które codziennie zbierają oferty pracy z
Biuletynu Informacji Publicznej Miasta Krakowa i budują lokalny dataset
zgodnie z zasadą **„collect data once, make it usable anytime”** — dane nie
są nadpisywane, lecz aktualizowane, z zachowaniem historii dostępności
(daty pojawienia się `first_seen` / aktywności `active` oraz daty wygaśnięcia
`inactive_since`).

Skrypty działają identycznie na **Windows** i na **Linux/WSL** (używają
wyłącznie `pathlib`, bez twardo zakodowanych ścieżek, oraz `sys.executable`
w orchestratorze).

## Wymagania

- Python 3.8+ (testowane na 3.13)
- Biblioteki: `requests`, `beautifulsoup4`

Instalacja (Windows i Linux tak samo):

```
python -m pip install requests beautifulsoup4
```

## Ustalenia dot. źródła danych

Serwis BIP Kraków **nie udostępnia XML/JSON/CSV** — parametry typu
`format=xml`/`format=json` są ignorowane i strona zawsze zwraca HTML.
Dlatego wszystkie skrypty parsują HTML (BeautifulSoup). Gdyby w przyszłości
pojawił się format strukturalny, kod wystarczy rozszerzyć w warstwie parsowania.

Jednostki są linkowane dwojako: bezpośrednio (`?bip_id=28`) lub „ładnym”
slugiem (`/GUP`, który przekierowuje na właściwy `bip_id`). Oba warianty są
obsługiwane.

## Potok (pipeline) — 5 etapów

| Skrypt | Rola | Wejście | Wyjście |
|--------|------|---------|---------|
| `1_fetch_units.py` | Lista jednostek MJO — **aktualne** (strona główna) i **archiwalne** („Archiwum BIP MJO”), z datami dostępności/wygaśnięcia | strona listy jednostek | `data/units.json` |
| `2_fetch_praca_links.py` | Dla każdej jednostki znajduje link **„PRACA - NOWE”**; brak linku odnotowuje jawnie (`has_praca_link: false`) | `data/units.json` | `data/praca_links.json` |
| `3_fetch_offers.py` | Pobiera oferty z sekcji strony pracy: `NABORY TRWAJĄCE` (aktualne), `ZAKOŃCZONO PRZYJMOWANIE ZGŁOSZEŃ`, `NABORY ZAKOŃCZONE` — z linkami do szczegółów, nr ref. i terminem | `data/praca_links.json` | `data/offers.json` |
| `4_fetch_offer_details.py` | Wchodzi w szczegóły ofert, w których **nabór jest wciąż aktualny** (status trwający + termin nieprzeterminowany) i pobiera pełną treść oraz odnośniki | `data/offers.json` | `data/offer_details.json` |
| `5_generate_report.py` | Generuje raport (Markdown + HTML) z opisem ofert i linkami do szczegółów; **grupuje po kategorii** (Kultura i Sztuka na górze), a wewnątrz **sortuje po pilności** (najbliższy termin pierwszy); HTML jest kolorowy, z oznaczeniem pilności | datasety ofert i szczegółów | `reports/raport_praca_*.md` i `.html` |

Orchestrator `run_all.py` uruchamia wszystkie etapy po kolei.

## Uruchomienie

Cały potok naraz:

```
python run_all.py
```

Albo etapami:

```
python 1_fetch_units.py
python 2_fetch_praca_links.py
python 3_fetch_offers.py
python 4_fetch_offer_details.py
python 5_generate_report.py
```

Przydatne opcje (do testów i sterowania zakresem):

- `--verbose` — szczegółowe logi (dostępne we wszystkich skryptach),
- `--limit N` — ogranicza liczbę przetwarzanych elementów (skrypty 2, 3, 4),
- `--only-active` — tylko aktywne jednostki/linki (skrypty 2, 3),
- `--include-all` — pobierz szczegóły wszystkich ofert, nie tylko trwających (skrypt 4),
- `--all` — raport ze wszystkich ofert, nie tylko aktualnych (skrypt 5).

## Struktura katalogów

```
bip_krk/
├── bip_common.py            # wspólne: HTTP z retry, ścieżki, JSON, active/inactive
├── 1_fetch_units.py
├── 2_fetch_praca_links.py
├── 3_fetch_offers.py
├── 4_fetch_offer_details.py
├── 5_generate_report.py
├── run_all.py               # orchestrator całego potoku
├── .pylintrc                # konfiguracja lintera (10.00/10)
├── data/                    # „żywe” datasety (aktualizowany stan wiedzy)
├── snapshots/               # surowe zrzuty z timestampem (historia „collect once”)
└── reports/                 # wygenerowane raporty (.md + .html)
```

## Model danych — active / inactive

Każdy rekord w datasetach ma jednolite pola śledzące dostępność:

- `first_seen` — kiedy po raz pierwszy zaobserwowano rekord,
- `last_seen` — ostatnie zaobserwowanie,
- `active` — czy rekord był obecny w ostatnim przebiegu,
- `inactive_since` — data wygaśnięcia (gdy zniknął); `null`, gdy aktywny.

Rekordy **nigdy nie są usuwane**. Gdy stary link/oferta „wróci do łask”,
zostaje automatycznie reaktywowany (`active=true`, `inactive_since=null`).
Archiwalne jednostki z „Archiwum BIP MJO” są zapisywane od razu jako
nieaktywne, chyba że są też obecne na liście aktualnej.

## Wersja .exe dla Windows (bez instalacji Pythona u użytkownika)

Można spakować cały potok w pojedynczy plik `bip_krk_raport.exe`, który
pobiera dane i **od razu otwiera raport za dziś** w przeglądarce. Gotowy
`.exe` nie wymaga zainstalowanego Pythona.

**Ograniczenie:** PyInstaller buduje plik wykonywalny dla platformy, na
której działa — dlatego `.exe` dla Windows trzeba **zbudować na Windows**
(nie z WSL/Linux, bo powstałby plik dla Linuksa). Python jest potrzebny
tylko na maszynie budującej, jednorazowo.

Kroki (w Windows, w katalogu projektu):

1. Zainstaluj Pythona (python.org) — tylko do zbudowania.
2. Uruchom `build_exe.bat` (dwuklik lub w `cmd`). Skrypt zainstaluje
   `requests`, `beautifulsoup4`, `pyinstaller` i zbuduje plik.
3. Wynik: `dist\bip_krk_raport.exe`.

Uruchomienie: kliknij dwukrotnie `dist\bip_krk_raport.exe`. Wykona etapy
1–5 (widoczne logi w oknie konsoli), a na końcu otworzy najnowszy raport
HTML w domyślnej przeglądarce. Datasety i raporty zapisują się obok pliku
`.exe` (katalogi `data/`, `snapshots/`, `reports/`).

Pliki związane z budowaniem:

- `run_report.py` — punkt wejścia dla `.exe`: uruchamia potok w jednym
  procesie (importuje etapy) i otwiera raport,
- `bip_krk.spec` — konfiguracja PyInstaller (onefile),
- `build_exe.bat` — skrypt budujący dla Windows.

## Codzienne uruchamianie

- **Windows** — Harmonogram zadań (Task Scheduler): akcja „Uruchom program”,
  program `python`, argumenty `run_all.py`, katalog startowy = ten katalog.
- **Linux/WSL** — cron, np. codziennie o 6:00:

  ```
  0 6 * * * cd /sciezka/do/bip_krk && python3 run_all.py >> cron.log 2>&1
  ```
