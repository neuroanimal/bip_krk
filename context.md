# Kontekst projektu — Szukanie Pracy (BIP Kraków)

> Wyodrębniono z połączonej sesji kiro-cli `4fda0b63-…` (pary history 0–95).
> Pełny transkrypt: `transcript.md`, surowy zapis: `session.jsonl`.
> Workspace: `~/repo/github/bip_krk/` (WSL); wersja produkcyjna na Windows w `C:\bip_krk\`.

## Cel

Narzędzie, które przeszukuje Biuletyn Informacji Publicznej miasta Kraków
(bip.krakow.pl) pod kątem **nowych ofert pracy** (głównie dla żony użytkownika).
Zasada „collect data once, make it usable anytime” — codzienne powiększanie
datasetu o zmiany, z datami dostępności (`active`) / wygaśnięcia (`inactive`).
Potok ma działać także na **Windows bez instalacji Pythona** (budowany jako `.exe`).

## Architektura potoku (Python, stdlib + requests + bs4, ścieżki przez `pathlib`)

| Plik | Rola |
|---|---|
| `bip_common.py` | wspólne: sesja HTTP z retry, ścieżki (Windows+Linux), zapis/odczyt JSON, logika `first_seen`/`last_seen`/`active`/`inactive_since`, snapshoty z timestampem |
| `1_fetch_units.py` | jednostki z listy głównej (**aktywne**) + „Archiwum BIP MJO” (**nieaktywne**); oba warianty linków `?bip_id=N` i slug `/GUP`. Wynik: 409 aktualnych + 139 archiwalnych = 548 |
| `2_fetch_praca_links.py` | znajduje link „PRACA - NOWE” (`?bip_id=N&dok_id=M`); brak linku zapisywany jawnie jako `has_praca_link: false` |
| `3_fetch_offers.py` | parsuje 3 sekcje (`NABORY TRWAJĄCE` → status `trwajacy`, `ZAKOŃCZONO PRZYJMOWANIE`, `NABORY ZAKOŃCZONE`); tytuł, link do detali (`nab_id`), nr ref., termin. Puste sekcje też są daną |
| `4_fetch_offer_details.py` | wchodzi w detale **tylko trwających i nieprzeterminowanych** naborów; treść z właściwego kontenera (pomija menu/cookies) + odnośniki |
| `5_generate_report.py` | raport w **Markdown + HTML** z opisem i klikalnymi linkami do szczegółów |
| `run_all.py` | orchestrator całego potoku (używa `sys.executable` dla przenośności) |
| `run_report.py` | punkt wejścia dla `.exe`: uruchamia potok 1–5 w jednym procesie (etapy z cyfrą w nazwie ładowane przez `importlib`, bo `import 1_fetch_units` jest niedozwolony), na końcu otwiera najnowszy raport HTML w przeglądarce; obsługuje `sys._MEIPASS` |
| `.pylintrc`, `README.md`, `bip_krk.spec`, `build_exe.bat` | konfiguracja/build (`.pylintrc` globalnie wyłącza `invalid-name` dla nazw z cyframi, `too-many-locals`, `duplicate-code`, `line-too-long`) |

Wszystko: Pylint 10.00/10. Testowane: skrypty 1 i 2 na pełnym zbiorze, 3/4/5 na
`--limit` (żeby nie obciążać serwera ~400 żądaniami). Pełny przebieg: `python run_all.py`.
Stan danych w jednym z przebiegów: 48 ofert, 8 aktywnych trwających naborów.

## Build .exe (Windows)

- Budowany PyInstalerem wg `bip_krk.spec` + `build_exe.bat` (plik `.bat` wymaga
  CRLF; pliki `.py` działają z LF).
- **Rozwiązany bug `_MEIPASS`**: `PROJECT_ROOT = Path(__file__).resolve().parent`
  w spakowanym `.exe` wskazywało na tymczasowy `_MEI…`, więc `data/`, `snapshots/`,
  `reports/` lądowały w koszu. Fix: wykrywać `sys._MEIPASS` / lokalizację `.exe`,
  żeby katalogi powstawały **obok** `.exe`.
- Zalecenie: trzymać `bip_krk_raport.exe` bezpośrednio w `C:\bip_krk\` i uruchamiać
  stamtąd — wtedy `data\`, `snapshots\`, `reports\` powstają w `C:\bip_krk\`.

## Na czym stanęliśmy (sesja urwana w połowie tury 6)

Ostatnie polecenie: **dodać do raportu grupowanie po kategoriach i kolory**.
- Kategoria/podkategoria pobierana z nagłówków listy jednostek: `<h2>`/`<h3>`
  (Edukacja, Pomoc społeczna i zdrowie, Kultura, Zdrowie, Inne podmioty, Spółki
  miejskie) oraz `<h4>` (Żłobki, Domy Dziecka). Jednostka = linki występujące
  **po** nagłówku aż do następnego.
- Zaczęto przepisywać `parse_units_from_html` w `1_fetch_units.py` na skan liniowy
  (`find_all([...])` z zachowaniem kolejności), śledzący bieżącą kategorię/podkategorię,
  i dodawać pola `category`/`subcategory` do rekordu jednostki.
- Następnie `5_generate_report.py` miał grupować po kategorii z priorytetem
  **Kultura i Sztuka na górze**, wewnątrz po dacie (najpilniejsze = najbliższy
  termin pierwszy), kategorię oferty łącząc z `units.json` po `unit_key`.
- Drobiazgi do dopracowania: nagłówek „Spółki miejskie -zobacz więcej” zawiera
  tekst linku (do oczyszczenia); „Instytucje kultury” vs „Kultura” to dwie
  kategorie kulturowe.

## TODO (po wznowieniu)

1. Dokończyć przypisanie `category`/`subcategory` w `1_fetch_units.py` i uruchomić
   skrypt 1, sprawdzając czy kategorie się przypisały.
2. Przepisać `5_generate_report.py`: grupowanie po kategorii (Kultura na górze) →
   wewnątrz po dacie; kolorowy, estetyczny HTML.
3. Rozważyć codzienny harmonogram (`run_all.py` jako automat / Task Scheduler na
   Windows) — „collect data once”.

## Pierwszy krok po wznowieniu

`ls` w `~/repo/github/bip_krk/`, potem `python3 run_all.py` (lub skrypty 1→5 z
`--limit`) żeby potwierdzić, że potok działa, i wrócić do przebudowy skryptu 5.
