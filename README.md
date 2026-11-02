# BIP Kraków — scraper ofert pracy (dwa profile zawodowe)

Zestaw skryptów w Pythonie, które codziennie zbierają oferty pracy z
Biuletynu Informacji Publicznej Miasta Krakowa i budują lokalny dataset
zgodnie z zasadą **„collect data once, make it usable anytime”** — dane nie
są nadpisywane, lecz aktualizowane, z zachowaniem historii dostępności
(daty pojawienia się `first_seen` / aktywności `active` oraz daty wygaśnięcia
`inactive_since`).

Skrypty działają identycznie na **Windows** i na **Linux/WSL** (używają
wyłącznie `pathlib`, bez twardo zakodowanych ścieżek, oraz `sys.executable`
w orchestratorze).

## Dwa profile zawodowe — jeden kod, osobne dane

Aplikacja obsługuje **dwa profile**, wybierane przełącznikiem `--profile`:

| Profil | Czego szuka | Dane i raporty |
|--------|-------------|----------------|
| `kultura` (**domyślny**) | kultura, sztuka, grafika, animacja, edukacja kulturalna | `data/`, `reports/` |
| `it` | Applied Data Science, AI Engineering, Python, backend/JEE, full-stack, mobile | `data_it/`, `reports_it/` |

```
python run_all.py                  # profil kultury (jak dotychczas)
python run_all.py --profile it     # profil danych i AI
```

W wersji `.exe` profil wybiera się argumentem — albo gotowym plikiem
`.bat` do dwukliku:

```
bip_krk_raport.exe                 # profil kultury
bip_krk_raport.exe --profile it    # profil danych i AI

raport_kultura.bat                 # dwuklik: profil kultury
raport_it.bat                      # dwuklik: profil danych i AI
```

**Dlaczego jeden kod, a nie druga aplikacja:** wspólnej mechaniki jest
~4,5 tys. linii (HTTP z retry, dziennik niepowodzeń, `active/inactive`,
snapshoty, HTML raportu z trackingiem klikania) — kopia znaczyłaby dwa
miejsca do poprawiania każdego błędu. Dodatkowo **część źródeł obsługuje
oba profile**: nofluffjobs ma i „Social Media Graphic Designer”, i 147
ofert data/AI w Krakowie; CBOP jedno i drugie.

**Dlaczego osobne katalogi:** wspólny dataset znaczyłby, że w raporcie
żony pojawia się 200 ofert IT w sekcji „pozostałe” — dokładnie ten szum,
przed którym broni cały projekt. Profil domyślny używa katalogów **bez
sufiksu**, więc dotychczasowe dane i zbudowany `.exe` działają bez zmian.

Każdy etap potoku jest przypisany do profili, których dotyczy
(`STEP_PROFILES` w `run_all.py`). Profil `it` wykonuje **5 etapów z 13** —
pomija obchód ~550 jednostek BIP miasta (szkoły, żłobki, przedszkola),
który dla niego nie daje ani jednej trafnej oferty. Pełny przebieg profilu
IT trwa ~25 s, profilu kultury ~15 min.

Pominięty jest też etap 4 (szczegóły ogłoszeń): zmierzone na 219 ofertach
IT dało 191 rekordów i **zero z czytelną treścią**, bo nofluffjobs
i bulldogjob to aplikacje JavaScript. Opis mamy już z API.

### Dodanie trzeciego profilu

Jeden plik w `profiles/` (kontrakt opisuje `profiles/__init__.py`) i wpis
w `profiles.AVAILABLE`. Logika oceniania (`profile_match.py`) jest wspólna
— poprawka w niej, jak kontekstowe rozpoznawanie homonimów, działa od razu
dla wszystkich profili.

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
| **`src_jooble.py`** | Źródło zewnętrzne: **jooble.org przez oficjalne REST API** (wymaga klucza) — agreguje też portale, które same blokują odczyt | API z kluczem | `data*/offers.json` |
| **`src_pracujwkulturze.py`** | Źródło zewnętrzne: **pracujwkulturze.nck.pl** (Narodowe Centrum Kultury) — instytucje kultury z całej Polski, z taksonomią obszarów (sztuka, edukacja, grafika, muzeum, nowe media…) | API odkryte | `data/offers.json` |
| `src_kultura_instytucje.py` | Źródło zewnętrzne: **instytucje kultury poza BIP miasta** (Muzeum Narodowe, Zamek Królewski na Wawelu, Teatr Słowackiego, Cricoteka, Wojewódzka Biblioteka Publiczna) — BIP Krakowa obejmuje tylko jednostki miejskie | strony instytucji | `data/offers.json` |
| `src_nofluffjobs.py` | Źródło zewnętrzne: nofluffjobs.com — **oferty dla grafika/designera** w Krakowie (luka, której nie pokrywa BIP ani nuzle) | API portalu | `data/offers.json` |
| **`src_cbop.py`** | Źródło zewnętrzne: **CBOP — oficjalna rządowa baza urzędów pracy** (oferty.praca.gov.pl). Obejmuje pracodawców nieobecnych w BIP, m.in. **ASP w Krakowie** | API portalu (odkryte) | `data/offers.json` |
| `src_remote_intl.py` | Źródło zewnętrzne: **zagraniczne oferty zdalne dostępne z Polski** — role kreatywne otwarte na „Europe/EMEA/Worldwide” albo wymieniające Kraków/Polskę | RSS + API | `data/offers.json` |
| `check_institution.py` | Narzędzie badawcze: sprawdza, czy kandydat ma scrapowalną stronę pracy (próbuje `/praca`, `/kariera`, `/oferty-pracy`…) — używane PRZED dodaniem do listy źródeł | adres instytucji | wydruk diagnostyczny |
| `profile_match.py` | Ocena dopasowania oferty do profilu (kultura, sztuka, grafika, animacja, edukacja kulturalna) | — | — |
| `4_fetch_offer_details.py` | Szczegóły ofert, w których **nabór jest wciąż aktualny** | `data/offers.json` | `data/offer_details.json` |
| `5_generate_report.py` | Raport (Markdown + HTML): grupowanie po kategorii (Kultura i Sztuka na górze), **NOWE/nieoglądane na górze kategorii**, sortowanie po pilności, tracking klikania, sekcja diagnostyczna | datasety | `reports/raport_praca_*.md` i `.html` |
| `report_html.py` | Moduł prezentacji HTML (styl, skrypt trackingu, budowa dokumentu) | — | — |
| `report_map.py` | **Mapa ofert** offline (SVG, granice dzielnic z OSM) — kropki, dom, okrąg promienia | `krakow_districts.json` | — |
| `dedupe.py` | **Duplikaty i podobne oferty**: ta sama oferta z kilku źródeł → jedna karta („także na: …”), podobne → „+ N podobnych” do rozwinięcia | — | — |
| `geo.py` | **Odległość od domu**: dzielnice Krakowa, geokodowanie miejscowości (Nominatim), haversine | — | `data*/geo_cache.json` |
| `offer_lang.py` | Rozpoznawanie **języka ogłoszenia** (polski / angielski) | — | — |
| `report_controls.py` | Paski sterowania raportu (język, geografia, filtry, sortowanie) | — | — |
| `salary.py` | Normalizacja **wynagrodzeń** do PLN/mies. (kurs z API NBP) — do sortowania | — | — |
| `contract_type.py` | Rozpoznawanie **rodzaju umowy** (UoP / UZ / B2B / dzieło) — wspólne dla źródeł | — | — |
| `report_script.py` | Skrypt przeglądarki raportu: tracking klikania i filtrowanie | — | — |
| `report_stats.py` | Statystyki i **wykresy SVG** do pasków bocznych raportu | — | — |

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
| **jooble.org** | ✅ **dodany przez oficjalne REST API** (klucz na zgłoszenie). Strona, RSS, a nawet dokumentacja `/api/about` dają 403, sitemap zawiera tylko numeryczne ID bez tytułu i miasta — API jest jedyną drogą |
| `indeed.pl`, `useme.com` | ❌ 403 |
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

## Oferty zagraniczne — Kraków stacjonarnie lub Polska zdalnie

Osobne badanie (2026-10-15). Zagraniczne firmy rekrutują na stanowiska
kreatywne zdalnie i Polska mieści się w ich zasięgu — ale **prawie nigdy
nie wymieniają jej wprost**, tylko piszą „Europe”, „EMEA” albo „Anywhere
in the World”. Dlatego oferta wchodzi do raportu, gdy jest rolą kreatywną
**oraz** albo wymienia Kraków/Polskę (`Kraków, Krakow, Cracow, Cracovia,
Poland, Polska, Polen, Polonia`), albo ma lokalizację otwartą na Europę.
Powód dopasowania widać w nazwie pracodawcy („otwarte: EMEA”).

| Portal | Wynik |
|--------|-------|
| **weworkremotely.com** (RSS design) | ✅ **dodany — najczystsze źródło**: 30 ofert, wszystkie faktycznie designerskie, pole `region` wprost podaje zasięg |
| **remoteok.com** (API) | ✅ **dodany** — ~100 ofert; parametr `?tags=design` jest ignorowany, więc role filtrujemy sami |
| `remotive.com` | ❌ darmowe API **ignoruje `category=design`** i zwraca stałą próbkę 15 ofert bez ani jednej z kategorii Design (pierwsza to „Remote Office Assistant”). Slug `design` jest poprawny — potwierdzony w `/api/remote-jobs/categories` — więc to limit darmowego planu |
| **EURES** (oficjalny portal UE) | ❌ API działa (`POST /eures/api/jv-searchengine/public/jv-search/search`, kod NUTS `PL21` = Małopolskie), ale na 79 ofert dla „graphic designer” w Polsce tylko **2 były obcojęzyczne**, a jedyna obcojęzyczna z Krakowem to niemiecka oferta sprzedażowa. Przyczyna: EURES agreguje krajowe urzędy pracy, więc duplikuje CBOP |
| `behance.net/joblist` | ❌ 403 |
| `dribbble.com/jobs` | ❌ odpowiada 200, ale bez API — wymagałby parsowania zmiennego HTML |

**Ograniczenia tego źródła, o których trzeba wiedzieć:** to firmy
komercyjne, często współpraca B2B zamiast umowy o pracę — więc bez
stabilności budżetówki. Wymagany biegły angielski, także pisany. Przewaga
ofert dotyczy designu produktowego i UX, nie grafiki warsztatowej — dlatego
`profile_match` celowo **nie** uznaje „UX/Product/Game Designer” za
dopasowanie, a uznaje „Graphic Designer”, „Brand Design” i „Education
Designer”.

## Paski boczne: statystyki i wykresy

Raport ma układ trzykolumnowy: **liczby po lewej**, treść w środku,
**wykresy po prawej**. Przy wąskim ekranie i przy druku paski schodzą pod
treść (reguły `@media`), więc nic się nie ucina.

Lewy pasek: ile ofert, ile dopasowanych (mocnych i słabych), ile NOWYCH,
ile pilnych (termin ≤ 7 dni), ile już oglądanych, oraz rozkład po źródłach.
Prawy pasek: dopasowanie do profilu (pierścień), oferty po źródle
(słupki), terminy (pierścień), napływ ofert w ostatnich 14 dniach.

**Wykresy są wbudowanym SVG liczonym w Pythonie, bez biblioteki.** Powód:
raport to pojedynczy plik otwierany lokalnie, często bez internetu —
biblioteka z CDN dawałaby puste prostokąty, a dołączona lokalnie dokładałaby
kilkaset kilobajtów do każdego raportu. Statyczne SVG działa offline, bez
JavaScriptu i skaluje się przy druku. Cena: brak interaktywności, co jest
tu akceptowalne — wykres ma odpowiedzieć „czego jest dużo i skąd to jest”.

## Każda oferta raz — duplikaty, podobne i oferty spoza profilu

Zarzut adresatki: „skrypt powiela po 3 razy dużo ogłoszeń i wrzuca też
sprzątaczki”. Pomiar raportu potwierdził go i wskazał **cztery** przyczyny:

| Przyczyna | Skala | Naprawa |
|-----------|-------|---------|
| oferta z sekcji „Dla Ciebie” powtórzona w swojej kategorii | 65 kart podwójnie | kategorie zawierają już **tylko oferty spoza profilu** i są **zwinięte** |
| ta sama oferta w kilku źródłach (CBOP + jooble, Wawel + pracujwkulturze) | 18 kopii | `dedupe.py`: jedna karta, pod nią „Ta sama oferta także na: …” z linkami |
| jedno ogłoszenie w wariantach regionalnych („…woj. Śląskie / Małopolskie / Cała Polska”) | do 12 kart | grupa: jedna karta + „+ N podobnych” do rozwinięcia |
| stare rekordy, których nikt nie wygasił (m.in. „Sprzątaczka — zastępstwo” z 22.09) | 16 | bezpiecznik świeżości: oferta niewidziana przez żadne źródło od 7 dni nie trafia do raportu |

**Duplikat a podobna oferta** — to różnica, którą łatwo zepsuć:

- **duplikat** = ta sama oferta (prawie identyczny tytuł i ten sam
  pracodawca) z różnych źródeł → łączymy w jedną kartę;
- dwa ogłoszenia **z tego samego portalu** to zwykle dwa etaty
  („Młodszy bibliotekarz” i „Młodszy bibliotekarz na zastępstwo”) — nie
  łączymy ich, tylko grupujemy jako podobne. Wyjątek: agregatory
  (jooble, nuzle) potrafią opublikować ten sam wpis kilka razy;
- **podobne u różnych pracodawców** wymagają tytułu identycznego po
  normalizacji. Przy luźniejszym progu „Senior Python Developer (Django)”
  i „(AWS)” lądowały pod jedną kartą, choć to osobne propozycje pracy.

**Pułapka, która kosztowała jedną wersję:** łączenie przechodnie (A~B,
B~C ⇒ A+C) sprawiło, że „Senior Python Developer” wchłonął **92 oferty od
31 firm**. Grupy są teraz „gwiazdami”: członkiem zostaje tylko oferta
podobna bezpośrednio do karty głównej.

Na wierzchu grupy zawsze stoi najlepsze dopasowanie do profilu, a dopiero
potem lepsze źródło (z terminem i pełnym opisem przed agregatorem) — mocne
trafienie nie może się schować pod „+ N podobnych”.

## Mocniejsze profilowanie (wersja z 21.10)

Ocena ogłoszeń zebranych przez nowe źródła pokazała, że dawna lista
wykluczeń zawsze była o krok z tyłu — pytała „czy to sport?”, zamiast
„czy to kultura?”. Zmiany:

- **ogólne rdzenie wymagają kontekstu**: „instruktor”, „animator”,
  „warsztat”, „event”, „trener” liczą się jako rdzeń profilu tylko wtedy,
  gdy w tytule albo nazwie pracodawcy jest kontekst kulturalny (kultura,
  plastyka, sztuka, teatr, muzeum, biblioteka, świetlica, klub…). Bez tego
  „DLA CIEBIE” dostawali instruktorzy sportów walki, nauki jazdy,
  robotyki i „Instruktor Maszyn”. „Zajęcia dla dzieci” bez kontekstu
  kultury dają najwyżej „może pasować”;
- **pracodawca rozpoznawany jako słowo, po samej nazwie**: „teatr”
  pasowało do „Dziennik **Teatr**alny” i do dopisku lokalizacji „…gdzie
  znajduje się teatr”, więc gazeta zatrudniająca recenzentów uchodziła
  za teatr;
- **staż, praktyki, wolontariat, konkurs na dyrektora, sprzedaż** —
  degradowane do „może pasować”, ale liczone **tylko z tytułu**: w opisie
  „staż” to zwykle „staż pracy”, a „praktyk” — „doświadczenie
  praktyczne”, co degradowało ofertę ASP i Klub Dukat;
- **wykluczone**: technika sceniczna (realizator, oświetlenie, akustyk),
  śpiew (przesłuchania, tenor, chór), obsługa klienta i moderacja treści,
  wymóg obcego języka w tytule („…with Czech”), UX w krótkiej postaci;
- **składanie znaków** (`ą→a`, `ł→l`) po obu stronach porównania — jeden
  wzorzec obsługuje pisownię z ogonkami i bez, zamiast dublowania list.

W raporcie sekcja „Dla Ciebie” ma **mocne trafienia na górze**, a „może
pasować” pod osobnym śródtytułem z wyjaśnieniem, co jest zastrzeżeniem.

Efekt na danych z 21.10: mocnych trafień 45 → 19, i to są te właściwe
(ASP, Klub Dukat, Wawel, plastyk, grafik, nauczyciel grafiki, social media).

### Testy regresji

```
python -m unittest discover -s tests -v
```

`tests/test_profile_match.py` zawiera ~40 **realnych ofert z danych** —
każdą, która kiedyś była oceniona źle, i każdą, której poprawna ocena jest
warunkiem sensu raportu — z komentarzem, co poszło nie tak.
`tests/test_dedupe.py` sprawdza duplikaty, grupowanie i brak łańcuchowania.
Zmiana w ocenie, która psuje którykolwiek przypadek, jest widoczna od razu.

## Dokładna lokalizacja oferty

Gdy źródło podaje tylko „Kraków”, wcześniej liczyliśmy odległość do
centrum — Klub Dukat (Nowa Huta) wychodził jako 5,5 km od Bronowic.
Teraz `geo.locate_offer` szuka punktu w kolejności: współrzędne z API →
**adres z treści** („os. Zgody 1”) → **siedziba instytucji** („Teatr
Groteska, Kraków”) → dzielnica w tekście → samo miasto. Wyniki adresowe
są sprawdzane (≤ 30 km od miasta oferty), żeby imiennik z innego
województwa nie udawał lokalizacji. Na karcie widać odległość od
wybranej dzielnicy; „≈” oznacza punkt przybliżony (tylko miasto lub
dzielnica).

Klub Dukat ma teraz poprawne **11,6 km** — i przy promieniu 10 km jest
ukryty, zgodnie z decyzją użytkownika („to za daleko”).

Dwie poprawki wcześniejszej metody: „Kraków” bez dzielnicy to **Rynek**,
a nie centroid obszaru z Nominatim (50.047, 19.997 — 10,0 km od Bronowic,
przez co kilka ofert stało dokładnie na granicy promienia); a geokodowanie
miast działa **bez** ograniczenia do Polski — z nim „Berlin” trafiał do
polskiej wsi Berlin pod Rzeszowem.

## Mapa ofert

Nad listą jest mapa Krakowa z ofertami. **Działa bez internetu**: podkład
to granice 18 dzielnic wbudowane w raport jako SVG (`krakow_districts.json`,
~20 kB), a nie kafelki z sieci — zwykła mapa internetowa pokazałaby offline
szary prostokąt. Granice pobiera raz `tools/build_district_map.py`
(Overpass → identyfikatory relacji dzielnic, Nominatim → geometria);
uruchamiać ponownie tylko przy zmianie podziału miasta.

- **kropka** = miejsce oferty, **wielkość** = liczba ofert w tym miejscu,
- **kolor** = najlepsze dopasowanie (zielony / bursztynowy / szary),
  a **pusty środek** = punkt przybliżony (tylko dzielnica) — żeby
  informacja nie zależała wyłącznie od koloru,
- **pulsuje** = jest tam oferta NOWA (wyłączone przy `prefers-reduced-motion`),
- **dom** i **okrąg promienia** podążają za wyborem dzielnicy i suwakiem,
- **kliknięcie** kropki zawęża listę do ofert z tego miejsca.

Mapa pokazuje dokładnie to, co lista — te same filtry. Oferty, dla których
źródło podało tylko „Kraków”, **nie dostają kropki na Rynku** (przy pomiarze
69 ofert w jednym punkcie dawało jedną wielką, nic nieznaczącą kropkę) —
liczy je osobny opis pod mapą.

Pułapka z pierwszej wersji: poziom dopasowania mapowany przez
`RANK[poziom] || 2` — a `RANK.strong` to `0`, więc `0 || 2` dawało `2`
i wszystkie mocne trafienia rysowały się jako szare.

## Wymiar etatu

Oferta z Klubu Dukat to **¼ etatu za 1450–1650 zł** — bez tej informacji
wyglądała na najgorzej płatną w raporcie, a w przeliczeniu na pełny etat to
~5800 zł. Karta pokazuje odznakę wymiaru i kwotę „≈ … PLN na pełny etat”,
a **sortowanie po wynagrodzeniu używa wartości przeliczonej** (tylko dla
kwot miesięcznych — stawka godzinowa nie zależy od wymiaru).

Rozpoznawane zapisy: „0,5 etatu”, „¼ etatu”, „1/2 etatu”, „pół etatu”,
pensum „etat: 9/18”, „niepełny etat”. **Pułapka:** „3 etaty” i „5 etatów”
w ogłoszeniach BIP to **liczba stanowisk**, nie wymiar — naiwny wzorzec
uznałby je za trzykrotny etat.

## Status „aplikowałam”

Przycisk na każdej karcie, osobny od „oglądane”: oglądanie to przejrzenie,
aplikowanie to decyzja, której efekt trwa tygodniami. Karta zmienia kolor
obramowania, a filtr **„Status”** pozwala schować oferty, na które już
wysłano CV. Stan zapisuje przeglądarka (`BIP_KRK_APPLIED`, osobno od
kliknięć, więc „Wyczyść historię” go nie kasuje) i trafia do eksportu
`clicks.json` — po wczytaniu przy kolejnym raporcie przechodzi na inny
komputer.

## „Specjalista ds. promocji” — budżetowa nazwa social mediów

Analiza rynku (21.10) pokazała, że instytucje publiczne prawie nie piszą
„social media” — piszą **„specjalista ds. promocji / komunikacji”**. Fraza
jest więc w zapytaniach jooble i CBOP, a w profilu kwalifikuje jako rdzeń
**tylko z kontekstem kultury** (muzeum, teatr, dom kultury…); w urzędzie
gminy daje „może pasować”, a „promocja sprzedaży” i promotorzy w sklepach
są wykluczeni. Od razu wyłowiło „Specjalista ds. promocji” w Teatrze
Groteska.

## LinkedIn — sprawdzone, nie dodane

Sprawdzone 21.10, bo adresatka słusznie zauważyła, że pracodawcy wystawiają
tam ogłoszenia:

- **Brak API do wyszukiwania ofert.** Oficjalne Job Posting API służy
  wyłącznie do **publikowania** ogłoszeń przez systemy ATS, i to tylko
  partnerom po umowie. Dokumentacja Microsoft Learn: *„We are currently
  not accepting new partnerships for LinkedIn's Job Posting API”* oraz
  *„The use of these APIs is restricted to those developers approved by
  LinkedIn”*. Klucza „na prośbę”, jak w jooble, nie ma.
- **Brak serwera MCP** dla ofert pracy.
- Istnieje **nieoficjalny** endpoint gościa, z którego korzysta publiczna
  strona wyszukiwania (`/jobs-guest/jobs/api/seeMoreJobPostings/search`) —
  odpowiada bez logowania. Ale `robots.txt` LinkedIn **wprost go zabrania**
  (`Disallow: /jobs-guest/`), a regulamin zakazuje automatycznego
  pobierania. Dlatego **nie jest w potoku** — to decyzja o ryzyku konta
  i zgodności z regulaminem, nie o technice.

**Legalna droga:** alert e-mail z zapisanego wyszukiwania na LinkedIn
(np. „grafik”, „animator kultury”, Kraków + 10 km). Częściowo LinkedIn
pokrywa też jooble, który agreguje ogłoszenia z wielu portali.

## Zasięg geograficzny — Kraków i okolica

W raporcie były oferty z Gorlic i Tarnowa — formalnie „małopolskie”, ale
**103 i 90 km** od Krakowa. Dlatego nad listą są dwa elementy:

- **Miejsce wyjazdu** — lista 18 dzielnic Krakowa, domyślnie **Bronowice**,
- **Promień poza Krakowem** — suwak w km, domyślnie **10 km**.

Promień liczy się od domu i dotyczy **wszystkich** ofert, także
krakowskich. Przełącznik **„Kraków zawsze”** jest **domyślnie wyłączony**
— to decyzja użytkownika: 18,5 km (Bronowice → Nowa Huta) jest realnie za
daleko, więc dobrze, że promień 10 km to ucina. Przełącznik zostaje jako
wyjście awaryjne: gdy w bliskich dzielnicach nic nie ma, jedno kliknięcie
pokazuje cały Kraków.

**Co odsiewa promień 10 km** (zmierzone): 30 ofert spoza zasięgu, m.in.
Rzeszów 153 km, Lipinki 111 km, Biecz 106 km, Kielce 100 km, Gorlice
103 km. W zasięgu zostaje 101 ofert z rozpoznaną lokalizacją.

**Ograniczenie, o którym trzeba wiedzieć:** gdy źródło podaje tylko
„Kraków” bez dzielnicy (tak robi pracujwkulturze), odległość liczymy do
**centrum miasta**. Dlatego oferta z Klubu Dukat (faktycznie Nowa Huta)
wypada jako ~5,5 km od Bronowic, a nie 18,5 km. Precyzja wewnątrz miasta
jest więc ograniczona danymi źródła, nie metodą.

**Odległość liczy przeglądarka**, więc przesunięcie suwaka albo zmiana
dzielnicy działa natychmiast, bez generowania raportu od nowa. Jest to
odległość **w linii prostej**, nie czas dojazdu — 10 km przez centrum
bywa dłuższe niż 25 km trasą wylotową. Oferty **bez rozpoznanej
lokalizacji nie są ukrywane**: brak danych nie może znaczyć „odrzuć”.

Współrzędne: CBOP podaje je wprost w API, pozostałe miejscowości
geokoduje **Nominatim** (OpenStreetMap, 1 zapytanie/s, własny
`User-Agent`) z zapisem w `data*/geo_cache.json` — każda miejscowość
pytana jest raz w życiu. Zapytania są ograniczone do Polski
(`countrycodes=pl`); bez tego „Berlin” z oferty zagranicznej trafiał do
polskiej wsi o tej nazwie i udawał lokalizację w zasięgu.

## Język ogłoszeń i język interfejsu

W prawym górnym rogu są dwie małe kontrolki (celowo małe — nie mają
zajmować ekranu):

- **PL / EN po lewej** — które ogłoszenia brać pod uwagę. Domyślnie
  **tylko polskie**; angielskie włącza przycisk „EN”.
- **flagi po prawej** — język napisów raportu (polski domyślnie).
  Tłumaczone są wyłącznie etykiety sterowania; treść ogłoszeń zostaje
  w oryginale, bo to dane, nie interfejs.

Język ogłoszenia rozpoznaje `offer_lang.py`, bo **żadne źródło go nie
podaje**: liczy polskie znaki diakrytyczne (dwa i więcej to mocny sygnał —
jeden może być nazwą „Kraków” w tekście angielskim), polskie i angielskie
słowa funkcyjne, a przy remisie rozstrzyga pochodzenie ze źródła.

## Etykiety obszarów — co jest brane pod uwagę

Pasek **„Obszary”** pokazuje klikalnymi etykietami, co zdecydowało
o dopasowaniu (grafika/design, animacja kultury, media społecznościowe,
edukacja kulturalna…) wraz z liczbą ofert. Wyłączenie etykiety ukrywa
oferty, które trafiły tylko przez nią.

Etykiety pochodzą z `profile_tags` wyliczonych przy ocenie, a nie
z osobnej listy — dzięki temu pokazują realną zawartość raportu.

**Zmiany na prośbę adresatki:** dodane „wychowawca w świetlicy”,
„organizacja imprez” i **media społecznościowe** (osobny obszar);
usunięte **UI/UX** — zarówno z wyszukiwań w nofluffjobs, jak i z oceny
(„w tym nie siedzę i nie mam wiedzy”).

### Dwie pułapki odmiany, które trzeba było obsłużyć

- „organizacj**i** imprez” nie pasuje do wzorca „organizacj imprez”, więc
  rdzeń `imprez` stoi osobno;
- „wychowawca” był wcześniej **wykluczony** jako zawód nauczycielski —
  po dodaniu świetlic wykluczenie zawężono do „nauczyciel przedmiotu”.

## Filtrowanie raportu i rodzaj umowy

Nad listą ofert jest pasek filtrów działający **natychmiast, bez
przeładowania i bez internetu** — raport jest plikiem statycznym, więc
wszystkie oferty są w HTML, a filtr tylko ukrywa karty.

Filtrować można po **rodzaju umowy**, **dopasowaniu do profilu**
i **źródle**. W obrębie jednej grupy działa suma (wyłączenie B2B zostawia
UoP i UZ), a między grupami iloczyn („UoP” + „DLA CIEBIE” = oferty
spełniające oba warunki). Przycisk **„Pokaż wszystkie”** zdejmuje filtry.

### Rodzaje umów — rozdzielone, nie łącznie

| Odznaka | Znaczenie |
|---------|-----------|
| **UoP** (zielona) | umowa o pracę — staż pracy, ZUS, urlop, zdolność kredytowa |
| **UZ** (żółta) | umowa zlecenie |
| **B2B** (niebieska) | własna działalność (JDG) albo przez pośrednika |
| **dzieło** (fioletowa) | umowa o dzieło — realna przy warsztatach i pojedynczych realizacjach |
| umowa nieznana | ogłoszenie nie podaje rodzaju |

To trzy różne sytuacje prawne i finansowe, więc łączenie ich w „inne niż
UoP” zacierałoby najważniejszą różnicę. Oferta może dopuszczać kilka form
naraz (bulldogjob często „UoP albo B2B”) — wtedy ma kilka odznak i pojawia
się przy każdym z tych filtrów.

**Skąd wiemy, jaka umowa:** CBOP podaje ją wprost (`rodzajUmowy`),
nofluffjobs ma `salary.type` (`b2b`/`permanent`), bulldogjob trzy flagi,
arc.dev `jobType`. BIP nie ma takiego pola — tam rozpoznajemy z treści
ogłoszenia, co działa w 61 z 440 przypadków; pozostałe zostają jako
**„umowa nieznana”** i są osobną pozycją filtra. Nie zakładamy UoP tylko
dlatego, że to sektor publiczny — nabory na instruktorów w ośrodkach
kultury bywają na zlecenie (w danych: 3 takie oferty).

Dla ofert zagranicznych rodzaj umowy jest **przybliżony**: ani
weworkremotely, ani remoteok nie mają na niego pola, a angielskie
„contract” nie jest polskim rodzajem umowy.

## Sortowanie po wynagrodzeniu — i czego ta liczba nie znaczy

Obok sortowania **po pilności** (domyślne) i **po dopasowaniu** jest
sortowanie **po wynagrodzeniu**. Przycisk pojawia się tylko wtedy, gdy
w raporcie są oferty z podaną kwotą, a licznik przy nim mówi ile.

Żeby dało się je uszeregować, kwoty są przeliczane na **PLN miesięcznie**
(kurs z oficjalnego API NBP, pobierany raz na przebieg i zapisywany
w `data*/rates.json`, więc raport generuje się też bez internetu).

**To wartość orientacyjna, nie porównanie zarobków.** Zestawia rzeczy
nieporównywalne:

- **B2B podaje się zwykle netto, UoP brutto** — przy tej samej kwocie B2B
  jest korzystniejsze podatkowo, ale bez urlopu i ZUS-u pracodawcy,
- stawka godzinowa przeliczana jest przez **168 h/mies.** (21 dni × 8 h),
  co zakłada pełne obłożenie,
- kurs walut jest z dnia pobrania.

Dlatego na karcie widać **kwotę źródłową** („20 000–25 000 PLN/mies.”,
„30–45 USD/h”), a przeliczenie służy wyłącznie kolejności. Oferty bez
podanej kwoty trafiają **na koniec** listy, nie na początek — „brak
danych” nie może wyglądać jak „zarobki zerowe”.

Skąd kwoty: nofluffjobs podaje widełki wprost (`salary.from/to`), arc.dev
stawkę godzinową lub roczną w USD, CBOP tekstem („od 10 000 PLN”).
**bulldogjob ukrywa kwoty** na liście (`money: null`, `showSalary: false`),
a BIP ich nie ma.

### Pułapka językowa w rozpoznawaniu

Polska alternacja spółgłoskowa: „etat” odmienia się na „eta**c**ie”, więc
wzorzec `etat\w*` nie łapał „praca na etacie”. Rdzeń musi dopuszczać obie
postaci (`eta[tc]`), a przy tym nie łapać „etapu rekrutacji”.

## Klucz API jooble — poza repozytorium

jooble wymaga klucza partnerskiego (darmowy, **limit 500 wyszukiwań**).
Klucz jest **sekretem i nie ma go w kodzie** — wczytujemy go w kolejności:

1. zmienna środowiskowa `JOOBLE_API_KEY`,
2. plik `jooble.key` w katalogu projektu (jedna linia, dopisany
   do `.gitignore`).

Bez klucza etap kończy się spokojnie i tylko odnotowuje brak w dzienniku
— to źródło opcjonalne.

**Oszczędzanie limitu:** każde wywołanie API to jedno wyszukiwanie, więc
pytamy tylko o cztery frazy na przebieg i nie stronicujemy (30 ofert na
frazę). To ~125 uruchomień, czyli kwartał codziennego użycia. Zużycie
liczymy lokalnie w `data*/jooble_usage.json` i ostrzegamy po 400
zapytaniach; licznik jest **przybliżeniem** — nie wie o zapytaniach
spoza narzędzia.

### Pułapka: „instruktor” w jooble to głównie sport

Fraza „instruktor” w ogólnym agregatorze ściąga instruktorów **fitness,
pływania, OCR i tańca** — wymagają sprawności i uprawnień spoza tego
profilu, więc są wykluczone po tytule.

Osobny przypadek: „Nauczyciel-Instruktor” w **Młodzieżowym Domu Kultury
Fort 49** — pracodawca właściwy, ale opis podaje „Zawód: instruktor
sportu”. Taka oferta nie jest wykluczana, tylko **degradowana do „może
pasować”**: instytucja się zgadza, więc decyzję zostawiamy człowiekowi.

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
├── src_remote_intl.py           # źródło: zagraniczne oferty zdalne
├── check_institution.py         # narzędzie: badanie kandydatów na źródła
├── profile_match.py             # LOGIKA dopasowania (wspólna dla profili)
├── profiles/                    # DEFINICJE profili
│   ├── __init__.py              #   rejestr + kontrakt profilu
│   ├── kultura.py               #   kultura, sztuka, grafika
│   └── it.py                    #   dane, AI, backend
├── src_bulldogjob.py            # źródło: oferty IT (profil it)
├── src_arc_dev.py               # źródło: zdalne zlecenia dev
├── report_stats.py              # statystyki + wykresy SVG (paski boczne)
├── report_script.py             # skrypt przeglądarki (tracking + filtry)
├── contract_type.py             # rozpoznawanie rodzaju umowy
├── salary.py                    # normalizacja wynagrodzeń (kurs NBP)
├── report_map.py                # mapa ofert (SVG offline)
├── krakow_districts.json        # granice 18 dzielnic (© OSM, ODbL)
├── tools/build_district_map.py  # jednorazowe pobranie granic dzielnic
├── dedupe.py                    # duplikaty i grupowanie podobnych ofert
├── geo.py                       # odległość od domu, dzielnice Krakowa
├── tests/                       # testy regresji (python -m unittest)
├── offer_lang.py                # język ogłoszenia (pl/en)
├── report_controls.py           # paski sterowania raportu
├── src_pracujwkulturze.py       # źródło: portal NCK „Pracuj w kulturze”
├── src_jooble.py                # źródło: jooble przez oficjalne API
├── 4_fetch_offer_details.py
├── 5_generate_report.py
├── run_all.py               # orchestrator całego potoku (--sample dla próbki)
├── run_report.py            # punkt wejścia .exe (potok + otwarcie raportu)
├── bip_krk.spec             # konfiguracja PyInstaller
├── build_exe.bat            # budowanie .exe (Windows)
├── raport_kultura.bat       # dwuklik: raport profilu kultury
├── raport_it.bat            # dwuklik: raport profilu danych/AI
├── .pylintrc                # konfiguracja lintera (10.00/10)
├── data/                    # datasety profilu kultury (+ failures, clicks)
├── snapshots/               # surowe zrzuty profilu kultury
├── reports/                 # raporty profilu kultury (.md + .html)
├── data_it/                 # datasety profilu IT
├── snapshots_it/            # surowe zrzuty profilu IT
└── reports_it/              # raporty profilu IT
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
