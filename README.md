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
| `src_kultura_instytucje.py` | Źródło zewnętrzne: **instytucje kultury poza BIP miasta** (Muzeum Narodowe, Zamek Królewski na Wawelu, Teatr Słowackiego, Cricoteka, Wojewódzka Biblioteka Publiczna) — BIP Krakowa obejmuje tylko jednostki miejskie | strony instytucji | `data/offers.json` |
| `src_nofluffjobs.py` | Źródło zewnętrzne: nofluffjobs.com — **oferty dla grafika/designera** w Krakowie (luka, której nie pokrywa BIP ani nuzle) | API portalu | `data/offers.json` |
| **`src_cbop.py`** | Źródło zewnętrzne: **CBOP — oficjalna rządowa baza urzędów pracy** (oferty.praca.gov.pl). Obejmuje pracodawców nieobecnych w BIP, m.in. **ASP w Krakowie** | API portalu (odkryte) | `data/offers.json` |
| `check_institution.py` | Narzędzie badawcze: sprawdza, czy kandydat ma scrapowalną stronę pracy (próbuje `/praca`, `/kariera`, `/oferty-pracy`…) — używane PRZED dodaniem do listy źródeł | adres instytucji | wydruk diagnostyczny |
| `profile_match.py` | Ocena dopasowania oferty do profilu (kultura, sztuka, grafika, animacja, edukacja kulturalna) | — | — |
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

## Dopasowanie do profilu — sekcja „Dla Ciebie”

Wśród kilkuset ofert trafne tonęły, więc raport wyglądał, jakby zawierał
„głównie administrację i sprzątanie”. Dlatego **na samej górze raportu** jest
wyróżniona sekcja z ofertami dopasowanymi do profilu:

- kultura i sztuka (malarstwo, grafika warsztatowa),
- grafika komputerowa, graphic design, DTP,
- animacja kultury, warsztaty dla wszystkich grup wiekowych,
- edukacja muzealna/kulturalna, pedagogika,
- konserwacja i opieka nad zbiorami.

Odznaka **DLA CIEBIE** = mocne trafienie (słowo kluczowe w tytule),
**może pasować** = trafienie słabsze. Pod kartą widać, do czego pasuje.
Jawnie pominięte: sprzątanie, ochrona, kierowca, księgowość, IT, zawody
medyczne, nauczyciel przedmiotu.

Zwijana lista **„Niedawno zamknięte oferty z profilu”** pokazuje trafienia,
których termin minął (do 60 dni) — nie da się już aplikować, ale podpowiadają,
jakie stanowiska i w jakich instytucjach realnie się pojawiają.

### Pułapki językowe, które trzeba było obsłużyć

- **„grafik”** to po polsku zarówno zawód, jak i harmonogram pracy. Lista
  fraz zawiodła (złapała „Tancerkę w klubie”, bo w opisie było „decydować
  o swoim grafiku”), więc znaczenie rozstrzygamy **kontekstowo** — w oknie
  ±45 znaków szukamy słów typu *elastyczn, swoim, zmianow, godzin*.
- **nazwa instytucji** myliła dopasowanie: „Poradnia Psychologiczno-
  **Pedagogiczna**” powodowała trafienia dla „LEKARZ PSYCHIATRA” i
  „Referent”. Takie frazy typu placówki są usuwane przed oceną.
- **obszary rdzeniowe vs wspierające**: sama nazwa „muzeum” w opisie nie
  kwalifikuje oferty — wymagane jest trafienie w obszarze rdzeniowym
  (grafika, sztuka, animacja, edukacja kulturalna, konserwacja). Bez tego
  podziału dopasowań było 96 zamiast 27, z czego wiele błędnych.

## Gdzie są oferty dla grafika — co sprawdzono

Osobne badanie (2026-10-14), bo w BIP i nuzle ofert dla grafika praktycznie
nie ma. Wnioski warto znać, zanim ktoś spróbuje dodać kolejny portal:

| Portal | Wynik |
|--------|-------|
| **oferty.praca.gov.pl (CBOP)** | ✅ **dodany — najlepsze źródło poza BIP**: 13 ofert w Małopolsce, w tym „Grafik/czka”, „Grafik komputerowy”, „Plastyk”, oraz **asystent w Katedrze grafiki ASP** (5600 zł). Oficjalna baza wszystkich urzędów pracy (17,5 tys. ofert w kraju) |
| **nofluffjobs.com** | ✅ **dodany** — 8 ofert UX + „Social Media Graphic Designer” w Krakowie, czyste API JSON |
| `pracuj.pl`, `olx.pl` | ❌ Cloudflare blokuje **wszystko**, także `robots.txt` i `sitemap.xml` (403) |
| `jooble.org`, `indeed.pl`, `useme.com` | ❌ 403 |
| `praca.pl` | ❌ **pułapka**: pisze „Nie znaleźliśmy ofert”, a pokazuje karty „Grafik / Graficzka” — wszystkie **z Łodzi** |
| `aplikuj.pl` | ❌ filtr frazy nie działa — pod `/praca/krakow/grafik` są ogłoszenia dla magazynierów |
| `nabory.kprm.gov.pl` (służba cywilna) | ❌ czytelne (`Ad[id_province]=1397`, `Ad[id_city]=92`), ale **0 ofert dla „grafik” w Krakowie**; krakowskie nabory to administracja (Izba Skarbowa, Komenda Policji, inspektoraty) |
| `justjoin.it` | ❌ 503 |
| `rocketjobs.pl` | ❌ renderowanie po stronie klienta, brak `__NEXT_DATA__` |

**Wniosek:** komercyjny rynek ofert dla grafików jest na portalach
zablokowanych (pracuj.pl, OLX) i w grupach na Facebooku — tam trzeba szukać
ręcznie albo ustawić alert e-mail na pracuj.pl. Natomiast dla profilu
„kultura + budżetówka” pokrycie jest teraz dobre: **CBOP** (urzędy pracy,
w tym ASP), BIP miasta, instytucje kultury.

### Dlaczego CBOP okazał się najcenniejszy

To oficjalna baza wszystkich powiatowych urzędów pracy. Dowód wartości:
oferta **asystenta w grupie badawczo-dydaktycznej w Katedrze grafiki ASP**
(od 5600 zł) — a strona `asp.krakow.pl/praca` była przy badaniu **pusta**,
bo ASP ogłasza się przez CBOP, nie u siebie.

API nie jest publicznie opisane. Endpoint (`/portal-api/v3/`) udało się
znaleźć, uruchamiając portal w headless Chrome z `--log-net-log`
i czytając przechwycone adresy; nazwy pól filtra pochodzą z leniwie
ładowanego modułu `chunk-GKCIW4KD.js`. Szczegóły i pułapki (pole
`miejscowosci` psujące odpowiedź, stronicowanie tylko przez query string)
są opisane w docstringu `src_cbop.py`.

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
├── bip_common.py            # wspólne: HTTP z retry+powody błędów, ścieżki,
│                            #   JSON, active/inactive, dziennik niepowodzeń
├── report_html.py           # prezentacja HTML: styl, tracking klikania, build_html
├── 1_fetch_units.py
├── 2_fetch_praca_links.py
├── 3_fetch_offers.py
├── 3b_fetch_offers_global.py    # szybka ścieżka (cała lista naborów BIP)
├── src_nuzle.py                 # źródło: nuzle.pl
├── src_ofertypracy_edu.py       # źródło: ofertypracy.edu.pl
├── src_kultura_instytucje.py    # źródło: instytucje kultury poza BIP
├── src_nofluffjobs.py           # źródło: oferty dla grafika/designera
├── src_cbop.py                  # źródło: CBOP (oficjalna baza urzędów pracy)
├── check_institution.py         # narzędzie: badanie kandydatów na źródła
├── profile_match.py             # dopasowanie do profilu zawodowego
├── 4_fetch_offer_details.py
├── 5_generate_report.py
├── run_all.py               # orchestrator całego potoku (--sample dla próbki)
├── run_report.py            # punkt wejścia .exe (potok + otwarcie raportu)
├── bip_krk.spec             # konfiguracja PyInstaller
├── build_exe.bat            # budowanie .exe (Windows)
├── .pylintrc                # konfiguracja lintera (10.00/10)
├── data/                    # „żywe” datasety + failures.json, clicks.json
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
