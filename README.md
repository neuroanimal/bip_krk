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

## Potok (pipeline) — etapy

| Skrypt | Rola | Wejście | Wyjście |
|--------|------|---------|---------|
| `1_fetch_units.py` | Lista jednostek MJO — **aktualne** (strona główna) i **archiwalne** („Archiwum BIP MJO”), z kategoriami i datami dostępności/wygaśnięcia. Wykrywa **podejrzane duplikaty** (ta sama jednostka aktywna i archiwalna → możliwy martwy link) | strona listy jednostek | `data/units.json` |
| `2_fetch_praca_links.py` | Dla każdej jednostki znajduje link **„PRACA - NOWE”**; brak linku odnotowuje jawnie. Gdy link z listy aktualnej jest **martwy (404)**, automatycznie próbuje wariantu z archiwum i zapisuje działający adres | `data/units.json` | `data/praca_links.json` |
| `3_fetch_offers.py` | Oferty ze stron poszczególnych jednostek (ścieżka zapasowa — wolna, ~400 żądań) | `data/praca_links.json` | `data/offers.json` |
| **`3b_fetch_offers_global.py`** | **Szybka ścieżka**: wszystkie nabory z jednej globalnej strony BIP (`?dok_id=104362`) — ~435 ofert w ~2 s | globalna lista naborów | `data/offers.json` |
| `src_nuzle.py` | Źródło zewnętrzne: nuzle.pl (Kraków, bez ofert nauczycielskich) | nuzle.pl | `data/offers.json` |
| `src_ofertypracy_edu.py` | Źródło zewnętrzne: ofertypracy.edu.pl przez Inertia API (Kraków, typ „Pracownik niepedagogiczny”) | API portalu | `data/offers.json` |
| `4_fetch_offer_details.py` | Szczegóły ofert, w których **nabór jest wciąż aktualny** | `data/offers.json` | `data/offer_details.json` |
| `5_generate_report.py` | Raport (Markdown + HTML): grupowanie po kategorii (Kultura i Sztuka na górze), **NOWE/nieoglądane na górze kategorii**, sortowanie po pilności, tracking klikania, sekcja diagnostyczna | datasety | `reports/raport_praca_*.md` i `.html` |
| `report_html.py` | Moduł prezentacji HTML (styl, skrypt trackingu, budowa dokumentu) | — | — |

Orchestrator `run_all.py` uruchamia wszystkie etapy po kolei. Źródła
zewnętrzne (`src_*`) są **opcjonalne** — ich awaria nie przerywa potoku.

## Znaczniki świeżości i tracking klikania

Raport pokazuje przy każdej ofercie, **kiedy się pojawiła**:

- **„NOWE: dzisiaj” / „NOWE: 1 dzień temu”** (zielony) — oferta pojawiła się
  po ostatnim raporcie i nie była jeszcze otwierana,
- **„5 dni temu”** (szary) — oferta już prezentowana/oglądana.

NOWE są sortowane **na górze każdej kategorii**, od najnowszej.

Kliknięcie w link oferty zapisuje ją jako **oglądaną** (localStorage
przeglądarki — raport jest plikiem offline, bez serwera). Taka karta zostaje
wygaszona z przekreślonym tytułem i znacznikiem „oglądane <data>”. W pasku
narzędzi są: licznik nieprzejrzanych, „Oznacz wszystkie jako przejrzane”,
„Eksportuj stan (clicks.json)” i „Wyczyść historię”.

Znacznik „oglądane” z pliku `data/clicks.json` (eksport z raportu) wpływa
na oznaczanie NOWE — oferta raz otwarta przestaje być nowa.

## Diagnostyka — nic nie ginie po cichu

Każde nieudane pobranie, brak oczekiwanego elementu i niedopasowanie rekordu
jest notowane w `data/failures.json` (etap, klucz, URL, powód, licznik
powtórzeń, `first_seen`/`last_seen`, `resolved`). Raport HTML ma zwijaną
sekcję **„Diagnostyka pobierania”** z tymi zgłoszeniami.

Najważniejsze powody:

| Powód | Znaczenie |
|-------|-----------|
| `dead_link_fixed_from_archive` | Link z listy aktualnej BIP był martwy; użyto działającego adresu z archiwum |
| `possible_stale_link` | Ta sama jednostka występuje jako aktywna i archiwalna — link aktualny może być martwy |
| `unit_in_current_and_archive` | Jednostka wpisana w obu listach (możliwa trwająca migracja) |
| `http_404`, `timeout`, `empty_response` | Strona nie odpowiada |
| `no_praca_link` | Jednostka bez zakładki „PRACA - NOWE” |
| `unit_not_matched` | Oferta z globalnej listy bez dopasowanej jednostki (lista jednostek nieaktualna) |

**Potwierdzony przypadek:** `slug:PK133` i `slug:SP137` z listy aktualnej BIP
zwracają **404**, a działające adresy (`?bip_id=371`, `?bip_id=54`) są w
archiwum — wraz z zakładką „PRACA - NOWE”. Skrypt 2 odzyskuje je automatycznie.

## Tryb próbny

Pełny przebieg obchodzi ~400 stron jednostek (~45 min). Tryb próbny daje
szybką weryfikację (ok. **30 s**):

```
python run_all.py --sample 8          # cały potok na próbce
python 5_generate_report.py --sample 20   # tylko raport z istniejących danych
```

Tryb próbny **nie wygasza** rekordów (nieodwiedzone jednostki nie są
„zniknięte”) i nie zużywa statusu NOWE.

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
