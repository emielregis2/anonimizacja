# Anonimizator dokumentów

Lokalny moduł do anonimizacji dokumentów, działający w całości offline —
żadna treść nie opuszcza komputera, na którym uruchamiasz narzędzie.
Mapowanie umożliwiające przywrócenie oryginału jest szyfrowane prawdziwym
AES (nie kodowaniem Base64).

## Szybki start

```bash
pip install -r requirements.txt
# + wymagania systemowe dla OCR — patrz requirements.txt (Tesseract, Poppler)

python app.py          # interfejs webowy z drag & drop -> http://127.0.0.1:5000
```

Na Windows: dwuklik na `start_anonimizator.bat`.

**Bez Pythona na docelowym komputerze:** patrz sekcja "Dystrybucja jako
samodzielny .exe" niżej — gotowy, spakowany `AnonimizatorGUI.exe` (~130 MB,
zawiera wszystko poza Tesseract/Poppler/opcjonalnym Trybem AI).

## Status względem 9 funkcji referencyjnego produktu

Wszystkie 9 funkcji, o które prosiłeś, są teraz zaimplementowane:

| # | Funkcja | Jak zrealizowana |
|---|---|---|
| 1 | 25+ kategorii polskich danych | 26 kategorii; 5 z sumą kontrolną (PESEL, NIP, REGON, IBAN, dowód osobisty — norma ICAO 9303) |
| 2 | PDF, DOCX, ODT, RTF, TXT + OCR skanów/obrazów | `extractors.py` — automatyczny OCR (Tesseract, lokalnie) dla stron PDF bez warstwy tekstowej oraz dla JPG/PNG. DOCX i PDF dodatkowo zachowują layout oryginału (patrz sekcja niżej) |
| 3 | Wiele plików naraz (2 tryby) | `anonimizuj_wiele_plikow(..., tryb="jedna_sprawa"/"niezalezne")` |
| 4 | Tryb Archiwum/BIP | `anonimizuj_bip(...)` — bez hasła, bez pliku mapowania, bezpowrotne |
| 5 | Raport anonimizacji (PDF z hasłem) | `generuj_raport_pdf(...)` — tabela placeholder→wartość, AES-256 w samym PDF |
| 6 | Auto-deanonimizacja (wklej odpowiedź AI) | Panel w interfejsie webowym — wklejasz tekst, tokeny wracają na żywo |
| 7 | Dowolny model AI | Naturalna właściwość — wynik to zwykły tekst; każdy plik wynikowy automatycznie niesie własny prompt instruujący AI, by nie zmieniało placeholderów (patrz sekcja niżej) |
| 8 | Wybór stylu anonimizacji | 4 style: `pelny_token`, `etykieta`, `inicjaly`, `puste` |
| 9 | Słowniki imion/miast/nazwisk, języki obce | PL: 68 183 imion + 598 476 nazwisk + 58 025 miejscowości (dane GUS/dane.gov.pl, CC0) — samodzielne wykrywanie nazwisk i miejscowości, nie tylko po kotwicy; UK/FR/SK/CZ nadal jako szkielet architektury (patrz "Znane ograniczenia") |

Uczciwie o granicach tej realizacji — patrz sekcja "Znane ograniczenia" niżej.

## Nazewnictwo i format pliku wynikowego

Plik wynikowy **zachowuje format pliku źródłowego** i dostaje przyrostek
`_anon`:

| Plik wejściowy | Plik wynikowy |
|---|---|
| `test.pdf` | `test_anon.pdf` |
| `umowa.docx` | `umowa_anon.docx` |
| `pismo.odt` | `pismo_anon.odt` |
| `notatka.rtf` | `notatka_anon.rtf` |
| `skan.png` | `skan_anon.png` (kopia oryginału, zamalowane tylko wykryte fragmenty) |
| `dokument.txt` | `dokument_anon.txt` |

Tryb Archiwum/BIP dodaje dodatkowo `_BIP`, żeby od razu było widać, że to
wersja bezpowrotna: `test_anon_BIP.pdf`.

## Style anonimizacji (funkcja 8)

| Styl | Przykład | Odwracalność |
|---|---|---|
| `pelny_token` (domyślny) | `[OSOBA_1]` | Pełna |
| `etykieta` | `Osoba A` | Pełna, czytelniejsza (np. do BIP) |
| `inicjaly` | `J. K.` / częściowa maska `50****67` | Pełna (mapowanie po wartości) |
| `puste` | `[USUNIĘTE]` | **Brak — celowo, dla maksymalnej ochrony** |

## Tryb Archiwum/BIP (funkcja 4)

```bash
python cli.py anonimizuj-bip dokument.docx --wszystko
```

Nie tworzy żadnego pliku mapowania ani hasła — dokument po anonimizacji
nie da się już NIGDZIE odtworzyć. Domyślnie używa stylu `etykieta`
(czytelniejsze dla odbiorcy publikacji niż surowe tokeny).

## Przetwarzanie wsadowe (funkcja 3)

```bash
python cli.py anonimizuj-wsadowo pismo1.docx pismo2.pdf pismo3.txt \
    --haslo "..." --wszystko --tryb jedna_sprawa
```

- `jedna_sprawa` — wspólna numeracja tokenów w obrębie wszystkich plików
  (ten sam "Jan Kowalski" dostaje ten sam token we wszystkich dokumentach)
  i jedno wspólne, zaszyfrowane mapowanie.
- `niezalezne` — każdy plik ma własną numerację i własny plik mapowania
  (jak przy pojedynczym przetwarzaniu, tylko w jednej operacji).

## Raport PDF (funkcja 5)

```bash
python cli.py anonimizuj dokument.docx --haslo "..." --wszystko --raport-pdf
```

Generuje dodatkowo czytelną tabelę (placeholder / kategoria / wartość
oryginalna) jako PDF zabezpieczony tym samym hasłem (AES-256, przez
`pypdf`). Do akt sprawy albo wglądu klienta bez odszyfrowywania `.enc`
programistycznie.

## Auto-deanonimizacja (funkcja 6)

W interfejsie webowym (`python app.py`), po anonimizacji panel po prawej
("Wklej odpowiedź AI") jest aktywny przez czas trwania sesji przeglądarki
(maks. 30 minut albo do ręcznego kliknięcia "Zamknij sesję"). Wklejasz
odpowiedź modelu AI zawierającą te same placeholdery — tokeny wracają na
prawdziwe dane automatycznie, bez ponownego podawania hasła.

Świadomy kompromis bezpieczeństwa: mapowanie tymczasowo siedzi
odszyfrowane w pamięci procesu serwera (nie na dysku), żeby ta wygoda
była w ogóle możliwa. Ponieważ serwer nasłuchuje wyłącznie na
`127.0.0.1`, ryzyko ogranicza się do tej samej maszyny. Klikaj "Zamknij
sesję" po zakończeniu pracy, jeśli to Cię niepokoi. Ten mechanizm nie jest
dostępny dla stylu `puste` (z definicji nieodwracalny) ani w trybie BIP.

## Automatyczny prompt dla AI (funkcja 7)

Każdy plik wynikowy (styl inny niż `puste`, poza trybem BIP) domyślnie
dostaje na początku treści prompt instruujący model AI, żeby nie zmieniał
placeholderów — wygenerowany dynamicznie na podstawie faktycznego
mapowania danego dokumentu (nie sztywny wzorzec zakładający jeden format
tokenu). Dzięki temu plik jest od razu samowystarczalny — przydatne przy
automatyzacji całych serii dokumentów, bo każdy plik "niesie" swój własny
prompt bez ręcznego dopisywania.

```bash
python cli.py anonimizuj dokument.docx --haslo "..." --wszystko --bez-promptu-ai
```

Znacznik `GRANICA_PROMPTU_AI` (w `anonimizator.py`) jest rozpoznawany
przez `deanonimizuj_tekst`/`deanonimizuj_plik` i automatycznie usuwany
przed przywróceniem oryginału — odtworzony dokument nie zawiera dopisku,
mimo że plik wysyłany do AI go zawierał.

## Wybór pliku z dysku (interfejs webowy)

Obok standardowego przeciągnięcia pliku do przeglądarki, przycisk
**PRZEGLĄDAJ (DYSK)** otwiera natywne okno Windows (endpoint
`/wybierz_pliki_dysk`, `tkinter.filedialog` — działa lokalnie, bo Flask
i przeglądarka są na tej samej maszynie). Dzięki temu backend zna pełną
ścieżkę pliku, czego zwykły upload w przeglądarce świadomie nie ujawnia,
i zapisuje wynik **bezpośrednio w katalogu pliku źródłowego** zamiast
tylko oferować pobranie przez przeglądarkę.

## Zachowanie layoutu oryginału (DOCX, PDF)

Domyślnie (`zachowaj_layout=True`) DOCX i PDF są anonimizowane **w miejscu**,
zamiast — jak poprzednio — wyciągnięciem czystego tekstu i zbudowaniem
zupełnie nowego dokumentu od zera. Formatowanie, tabele, obrazy, nagłówki,
stopki, kolumny i czcionki oryginału zostają nietknięte.

**DOCX** (`anonimizator/layout_docx.py`) — edycja na poziomie "runów"
(fragmentów tekstu ze wspólnym formatowaniem): wykrywamy PII na płaskim
tekście każdego akapitu, po czym podmieniamy tylko tekst odpowiednich
runów, nie ruszając ich formatowania (pogrubienia, kolory, styl, czcionka).
Obejmuje akapity głównej treści, tabele (rekurencyjnie, też zagnieżdżone),
nagłówki i stopki wszystkich sekcji.

**PDF** (`anonimizator/layout_pdf.py`) — prawdziwa redakcja przez PyMuPDF
(`add_redact_annot` + `apply_redactions`): tekst jest **faktycznie usuwany**
z warstwy tekstowej PDF, nie tylko wizualnie zasłonięty jak zwykłe
"zamalowanie" — nie da się go odzyskać przez zaznaczenie/kopiowanie ani
ponowną ekstrakcję. W miejscu redakcji wstawiany jest placeholder.

```bash
python cli.py anonimizuj dokument.docx --haslo "..." --wszystko --bez-zachowania-layoutu
```

(flaga analogiczna dla PDF; jawne wyłączenie wraca do starego trybu
"wyciągnij tekst -> zbuduj dokument od nowa" — np. do porównania albo
jeśli konkretny plik sprawia problemy).

**Ograniczenie dla PDF:** strony bez warstwy tekstowej (czyste skany) nie
mają czego zredagować tą ścieżką — nie ma na nich tekstu do wyszukania
współrzędnych. Takie strony są zgłaszane (pole `strony_bez_warstwy_tekstowej`
w wyniku, widoczne ostrzeżenie w interfejsie webowym), a nie cicho
pomijane. Docelowe rozwiązanie (OCR strony + redakcja na współrzędnych
z OCR) to naturalne rozszerzenie mechanizmu planowanego dla obrazów
JPG/PNG (patrz "Sugerowane następne kroki").

**Nowa zależność:** `pymupdf` (import jako `fitz`) — jedyna biblioteka
w projekcie z realną funkcją redakcji PDF. **Uwaga licencyjna:** PyMuPDF
jest licencjonowany dualnie — GNU AGPL v3.0 albo komercyjna licencja
Artifex. Używanie go w projekcie wewnętrznym/niekomercyjnym nie rodzi
problemu, ale **dystrybucja skompilowanej aplikacji** (np. jako .exe do
osób trzecich) pod AGPL wymagałaby udostępnienia pełnego kodu źródłowego
projektu na tej samej licencji, chyba że zostanie wykupiona licencja
komercyjna Artifex — dokładnie to samo ryzyko licencyjne, które
zidentyfikowaliśmy przy okazji audytu SBOM konkurencyjnego narzędzia
Beznazwisk (patrz notatka oceny ryzyka). Do rozważenia przed ewentualną
dystrybucją poza organizację.

## Wielojęzyczne słowniki (funkcja 9)

```python
anonimizuj_tekst(tekst, jezyki=["pl", "fr", "sk"])
```

Dostępne pakiety: `pl`, `uk`, `fr`, `sk`, `cz` (pliki w
`anonimizator/dane_slownikowe/`). Dorzucenie kolejnego języka to dodanie
plików tekstowych (`imiona_XX.txt`, `miasta_XX.txt`) — zero zmian w kodzie.

Pakiet `pl` jest oficjalnym, pełnym rejestrem (GUS/dane.gov.pl, licencja
CC0 — pełne źródła w `dane_slownikowe/ZRODLA.md`):

| Plik | Wpisów | Źródło |
|---|---|---|
| `imiona_pl.txt` | 68 183 | rejestr PESEL (osoby żyjące) |
| `nazwiska_pl.txt` | 598 476 | rejestr PESEL (osoby żyjące) |
| `miasta_pl.txt` | 58 025 | TERYT/SIMC (wykaz urzędowych nazw miejscowości) |

Nazwiska i miejscowości są wykrywane **samodzielnie** (nie tylko po
kotwicy w postaci poprzedzającego imienia) — zabezpieczone przed
fałszywymi trafieniami na początku zdania (`_na_poczatku_zdania` w
`slowniki_recognizers.py`). Świadomy kompromis: większa baza = więcej
recall, kosztem drobnego ryzyka fałszywych trafień na słowach
pokrywających się z nazwiskami odzawodowymi/odpospolitymi (np. "Kowal",
"Wilk") — uznany za akceptowalny w kontekście ochrony danych osobowych,
gdzie koszt pominięcia jest wyższy niż koszt nadmiarowego zamaskowania.

Pakiety `uk`/`fr`/`sk`/`cz` pozostają umiarkowanej wielkości (patrz
"Znane ograniczenia") — naturalny kierunek rozbudowy, jeśli dokumenty
będą zawierać więcej danych z tych krajów.

## OCR skanów i obrazów (funkcja 2)

Działa automatycznie i lokalnie (Tesseract) — nie trzeba nic włączać
ręcznie: jeśli strona PDF nie ma warstwy tekstowej (skan) albo plik to
JPG/PNG, moduł sam uruchamia rozpoznawanie tekstu. Wymaga zainstalowanego
Tesseract z pakietami `pol` + `eng` (patrz `requirements.txt` — sam model
polski słabiej rozpoznaje część znaków, np. `@`, dlatego oba pakiety
pracują razem).

## Architektura

```
plik wejściowy (+ OCR jeśli skan/obraz)
      │
      ▼
extractors.py
      │
      ▼
recognizers.py + slowniki_recognizers.py (+ jezyki) + ai_ner.py (Tryb AI)
      │
      ▼
SilnikAnonimizacji (anonimizator.py)
      │   rozstrzyga nakładające się dopasowania,
      │   generuje placeholder wg wybranego stylu,
      │   zachowuje stan między plikami (tryb "jedna_sprawa")
      ▼
   ┌──────────────┐    ┌──────────────────────┐    ┌───────────────────┐
   │ tekst .txt   │    │ mapowanie .enc        │    │ raport.pdf         │
   │ (jawny)      │    │ AES (PBKDF2+Fernet)   │    │ AES-256 (pypdf)    │
   └──────────────┘    └──────────────────────┘    └───────────────────┘
```

Wzorzec "recognizer registry" zapożyczony z architektury Microsoft
Presidio — każda kategoria to niezależny, testowalny moduł.

## Znane ograniczenia (uczciwie, żeby nie przemilczeć)

- **Recognizery słownikowe stosują lematyzację (Morfeusz2).** "Warszawy"
  (dopełniacz) dopasowuje się do wpisu "Warszawa", "Kowalskiego" do
  "Kowalski". Silnik lematyzacji działa w **odizolowanym procesie
  roboczym** (`anonimizator/morfologia_worker.py`), komunikującym się
  z resztą aplikacji przez potok stdin/stdout — nie w tym samym procesie,
  co reszta programu. To nie jest wybór dla wygody: pierwsza wersja
  (Morfeusz2 wywoływany bezpośrednio w tym samym procesie) ujawniła
  twardy, dwukierunkowy konflikt pamięciowy z PyMuPDF (crash całego
  procesu, niemożliwy do złapania przez try/except) — izolacja procesowa
  usuwa ten problem u źródła. Jeśli worker nie wystartuje (brak pakietu
  `morfeusz2`) albo padnie w trakcie, lematyzacja cicho degraduje się do
  dopasowania tylko dokładnego. Lematyzacja obejmuje tylko dopasowania
  jednowyrazowe — frazy wielowyrazowe (np. "Nowy Sącz") jej nie
  przechodzą. Tryb AI (spaCy) pozostaje uzupełnieniem dla przypadków
  spoza słownika w ogóle, nie tylko odmiany.
- **OCR jakości zależnej od skanu.** Niska rozdzielczość, pochylone
  strony czy odręczne pismo obniżają skuteczność. 300 DPI (domyślne w
  module) to rozsądny punkt startowy.
- **Zachowanie layoutu oryginału obejmuje DOCX, PDF i obrazy (JPG/PNG),
  nie wszystkie formaty.** ODT: nadal stary tryb (wyciągnij tekst → zbuduj
  dokument od nowa) — formatowanie znak-po-znaku nie jest zachowane. RTF:
  to samo, i raczej tak zostanie — `striprtf` to biblioteka wyłącznie do
  ekstrakcji, nie edycji w miejscu; realna edycja RTF wymagałaby innego
  narzędzia, nieproporcjonalny nakład względem tego, jak rzadko RTF
  pojawia się dziś w praktyce.
- **PDF: strony bez warstwy tekstowej (czyste skany) są redagowane przez
  ścieżkę OCR-fallback** (`layout_images.anonimizuj_strone_skanowana_pdf`)
  — ta sama technika bounding-boxów co dla JPG/PNG, z prawdziwym
  usunięciem oryginalnego obrazu strony (nie tylko wizualnym przykryciem).
  Trafiają na listę `strony_bez_warstwy_tekstowej` (widoczne ostrzeżenie
  w interfejsie/CLI) tylko jeśli Tesseract nie jest zainstalowany albo
  OCR nic na nich nie wykrył — nie są już cicho pomijane w żadnym z tych
  przypadków, ale warto zweryfikować ręcznie, jeśli faktycznie tam trafią.
- **Styl `puste` jest odwracalny wyłącznie do celów raportu/audytu** —
  nie da się z niego automatycznie przywrócić tekstu (to zamierzone).
- **Auto-deanonimizacja trzyma mapowanie w pamięci serwera** przez czas
  trwania sesji — patrz kompromis opisany wyżej.
- **Słowniki obcojęzyczne (UK/FR/SK/CZ) są nadal umiarkowanej wielkości**
  (kilkadziesiąt–150 pozycji) — solidny szkielet architektury
  wielojęzycznej, nie kompletna baza danych jak pakiet `pl`. Łatwo
  rozszerzyć, podmieniając pliki w `dane_slownikowe/` (patrz
  `ZRODLA.md` po wzór dokumentacji źródła danych).
- ~~Tryb wsadowy "jedna sprawa" nie wspiera jeszcze zachowania layoutu~~ —
  **rozwiązane.** DOCX/PDF/JPG/PNG w trybie "jedna sprawa" są teraz
  edytowane w miejscu tak samo jak przy pojedynczym pliku, a jedna,
  współdzielona instancja `SilnikAnonimizacji` przechodzi kolejno przez
  wszystkie pliki sprawy, więc numeracja tokenów zostaje spójna nawet
  w partiach mieszających formaty (np. DOCX + TXT tej samej sprawy).
  Pliki bez wsparcia layoutu (np. `.txt`, `.rtf`) nadal korzystają ze
  starej ścieżki "wyciągnij tekst -> zbuduj dokument od nowa".
- **Kategoria bywa niejednoznaczna przy słowach istniejących w kilku
  słownikach naraz.** Przy tak dużych bazach (598k nazwisk, 68k imion,
  58k miejscowości) i lematyzacji zwiększającej ekspozycję na te kolizje,
  część słów istnieje jednocześnie w kilku słownikach — np. "Bytom" to
  zarówno realna miejscowość, jak i zarejestrowane nazwisko w PESEL.
  Dane i tak zostają poprawnie zamaskowane, ale trafiają pod etykietą
  kategorii o wyższym priorytecie (`imiona_nazwiska` przed `miastami` —
  patrz sekcja "Rozwiązywanie konfliktów" w notatce o mechanizmie
  wykrywania), nie zawsze tę najbardziej "intuicyjną". Świadomy skutek
  uboczny, nie błąd.
- **To nie jest gotowy "plug-and-play" produkt komercyjny** — architektura
  i pipeline end-to-end są solidne i przetestowane (49 testów jednostkowych),
  ale przed użyciem produkcyjnym z danymi rzeczywistymi
  klientów warto dostroić słowniki/progi na Waszych dokumentach.

## Struktura projektu

```
anonimizator/
├── anonimizator/
│   ├── __init__.py
│   ├── recognizers.py            regex + walidacja sum kontrolnych
│   ├── slowniki_recognizers.py   recognizery słownikowe, wielojęzyczne
│   ├── dane_slownikowe/          pliki imion/nazwisk/miast per język + ZRODLA.md
│   ├── ai_ner.py                 opcjonalny lokalny model NER (Tryb AI)
│   ├── extractors.py             TXT/DOCX/ODT/RTF/PDF/JPG/PNG + OCR (stary tryb zapisu)
│   ├── layout_docx.py            DOCX z zachowaniem formatowania/tabel/nagłówków
│   ├── layout_pdf.py             PDF z prawdziwą redakcją przez PyMuPDF
│   ├── layout_images.py          JPG/PNG + strony-skany PDF (redakcja OCR w miejscu)
│   ├── morfologia.py             lematyzacja (Morfeusz2) — klient IPC
│   ├── morfologia_worker.py      lematyzacja — proces roboczy (izolacja
│   │                              procesowa od PyMuPDF, patrz "Znane ograniczenia")
│   ├── crypto.py                 szyfrowanie mapowania (PBKDF2 + Fernet)
│   ├── anonimizator.py           silnik: style, tryb wsadowy, tryb BIP, prompt AI
│   ├── deanonimizator.py         przywracanie oryginału (usuwa dopisany prompt AI)
│   ├── raport.py                 raport PDF zabezpieczony hasłem
│   ├── czcionki_pdf.py           wspólna rejestracja czcionki DejaVu (PDF)
│   └── czcionki/                 czcionka DejaVu (polskie znaki w PDF)
├── app.py                        aplikacja webowa (GUI w stylu ciemnego "chrome",
│                                  wybór pliku z dysku, wszystkie funkcje)
├── cli.py                        interfejs linii poleceń
├── start_anonimizator.bat
├── requirements.txt
└── tests/                        70 testów jednostkowych
```

## Tryb AI — wyniki realnego testowania

Do tej sesji Tryb AI (spaCy `pl_core_news_lg`) miał gotową architekturę,
ale nigdy nie był realnie przetestowany — żaden test w projekcie nie
używał `tryb_ai=True`. Zainstalowano spaCy 3.8.13 + `pl_core_news_lg` i
przetestowano na realistycznym (syntetycznym, ale wiarygodnym) piśmie
procesowym — patrz `tests/test_tryb_ai.py`.

**Zainstalowane i działające** na Python 3.14 / Windows — koła binarne
(`blis`, `thinc`) dla cp314 są już dostępne na PyPI, instalacja
bezproblemowa (`pip install spacy && python -m spacy download pl_core_news_lg`,
model ok. 570 MB).

**Realna wartość dodana (potwierdzona testem):**
- Nazwiska/imiona spoza wszystkich załadowanych słowników językowych
  (np. obce imię i nazwisko niewystępujące w żadnym pakiecie pl/uk/fr/sk/cz)
  — całkowicie niewidoczne dla recognizerów słownikowych, wykrywane przez
  Tryb AI.
- Wieloczłonowe nazwy firm bywają poprawniej grupowane przez NER niż przez
  recognizer słownikowy nazwisk, który potrafi złapać tylko fragment nazwy
  jako fałszywe trafienie kategorii "osoba" (kolizja słownikowa — patrz
  niżej), zostawiając resztę nazwy odkrytą.

**Znane ograniczenie modelu:** `pl_core_news_lg` czasem błędnie segmentuje
skróty z kropkami na granicy nazwy, np. "Orlen S.A." bywa dzielone na
"Orlen S." (organizacja) i "A." (osoba). Recall zostaje zachowany (cała
wartość i tak znika z tekstu), ale kategoria bywa błędna. To ograniczenie
samego modelu, nie błąd projektu — udokumentowane testem, żeby ewentualna
zmiana przy aktualizacji modelu była widoczna.

**Efekt uboczny tego testowania — znaleziony i naprawiony bug (niezwiązany
z AI):** `_na_poczatku_zdania` w `slowniki_recognizers.py` traktowało
KAŻDY pojedynczy znak nowej linii jako początek zdania. W realnych
dokumentach (PDF, DOCX, tekst po OCR) zdania regularnie zawijają się na
kolejny wiersz w połowie — to blokowało wykrycie słowa zaraz po takim
zawinięciu, bezpośrednio przeciwko zasadzie recall > precyzja przyjętej
dla tego modułu. Naprawione: tylko pusty wiersz (prawdziwa granica
akapitu) liczy się teraz jako początek zdania, pojedyncze zawinięcie —
nie.

## Przetwarzanie równoległe — wyniki realnego testowania

Tryb wsadowy "niezależne" (każdy plik ma w pełni niezależny stan) wspiera
teraz `rownolegle=True/int` w `anonimizuj_wiele_plikow` — pliki są
przetwarzane w oddzielnych procesach (`ProcessPoolExecutor`, omija GIL).
Dostępne też z CLI (`--rownolegle [N]`) i w `app.py` (checkbox "Przetwarzaj
równolegle", aktywny tylko dla trybu "Niezależne dokumenty").

**Tryb "jedna sprawa" pozostaje zawsze sekwencyjny** — spójna numeracja
tokenów wymaga współdzielonego silnika przetwarzanego w deterministycznej
kolejności, co z definicji wyklucza równoległość. Flaga `rownolegle` jest
w tym trybie po cichu ignorowana (patrz `tests/test_rownolegle.py`).

**Realny wynik pomiaru** (8 rdzeni CPU, 16 plików ~kilkadziesiąt KB
każdy): **1,34x** przyspieszenia — solidne, ale dalekie od liniowego.
Powód: każdy proces roboczy musi od nowa wczytać ogromne słowniki GUS
(598k nazwisk + 68k imion + 58k miast) z dysku, a przy Trybie AI również
model spaCy — to koszt stały ponoszony raz na proces, niezależnie od
liczby plików, który amortyzuje się dopiero przy większych partiach. Dla
malutkich plików/małej liczby plików sekwencyjne przetwarzanie bywa
wręcz **szybsze** niż równoległe (potwierdzone pomiarem) — stąd
`rownolegle` domyślnie wyłączone.

**Pułapka Windows przy własnych skryptach:** jeśli wywołujecie
`anonimizuj_wiele_plikow(..., rownolegle=True)` z własnego skryptu (nie
przez `app.py` ani `cli.py`, które już mają odpowiedni guard), kod
uruchamiający musi być owinięty w `if __name__ == "__main__":` —
standardowy wymóg `multiprocessing` na Windowsie (tryb "spawn"). Bez tego
zabezpieczenia proces roboczy przy imporcie skryptu jako `__main__`
próbuje uruchomić go od nowa, co prowadzi do błędu bootstrapowania albo
rekurencyjnego odpalania całego skryptu — potwierdzone empirycznie przy
tej sesji.

## Dystrybucja jako samodzielny .exe (bez Pythona na docelowym komputerze)

```powershell
python -m PyInstaller --name AnonimizatorGUI --onefile --console --noupx `
  --add-data "anonimizator\dane_slownikowe;anonimizator\dane_slownikowe" `
  --add-data "anonimizator\czcionki;anonimizator\czcionki" `
  --collect-all morfeusz2 `
  --collect-all fitz `
  --hidden-import tkinter `
  --hidden-import tkinter.filedialog `
  app.py
```

Buduje `dist\AnonimizatorGUI.exe` (~130 MB, jeden plik) z całym silnikiem,
słownikami GUS i Morfeusz2 (jego słownik jest wbudowany w `morfeusz2.dll`,
nie trzeba dowozić osobnego pliku danych). `--noupx` jest ważne — kompresja
UPX potrafi zawiesić build na kilkanaście minut bez błędu (obserwowane
empirycznie na tej maszynie, prawdopodobnie w kombinacji z antywirusem
skanującym w locie każdy zapisywany plik). Pierwszy build trwa
kilka–kilkanaście minut (analiza pełnego drzewa zależności); kolejne
buildy z tym samym `AnonimizatorGUI.spec` w katalogu — sekundy, bo
PyInstaller cache'uje analizę.

**Ważne — jeśli w tym samym środowisku Python jest zainstalowane spaCy
(Tryb AI), build niepotrzebnie ściąga za sobą całą gałąź zależności
spaCy/pandas** (nawet gdy `app.py` importuje spaCy tylko leniwie wewnątrz
funkcji) — to wydłuża i tak już długi build. Rozważcie budowanie
w osobnym, czystym `venv` bez spaCy, jeśli to zacznie przeszkadzać.

### Krytyczna pułapka znaleziona przy pierwszym buildzie: lematyzacja cicho nie działała

Worker lematyzacji (`morfologia.py`) uruchamiał proces roboczy jako
`subprocess.Popen([sys.executable, "morfologia_worker.py"])`. W zwykłym
`python app.py` `sys.executable` to interpreter Pythona — działa. W
spakowanym `.exe` **`sys.executable` to sam ten `.exe`**, a
`morfologia_worker.py` nie istnieje jako osobny plik na dysku docelowej
maszyny (jest spakowany do archiwum) — worker w ogóle nie startował.
Ponieważ moduł ma wbudowaną bezpieczną degradację ("worker niedostępny ->
dopasowanie tylko dokładne"), **nic nie krzyczało błędem — po prostu
znikała cała lematyzacja**. Zmierzone bezpośrednio: dokument z formami
odmienionymi ("Krakowie", "Kowalskiego") dawał **zero wykryć** w
spakowanym `.exe`, mimo że te same dane w `python app.py` działały
poprawnie.

Naprawa (ten sam wzorzec co `multiprocessing.freeze_support()` na
Windows): gdy `sys.frozen` jest prawdą, `morfologia.py` uruchamia **sam
siebie** z flagą `--morfologia-worker-wewnetrzny`
(`ARGUMENT_TRYBU_WORKERA` w `morfologia.py`) zamiast wywoływać skrypt.
`app.py` i `cli.py` sprawdzają tę flagę jako dosłownie pierwszą rzecz —
przed importem Flask i czegokolwiek innego — i przekazują sterowanie
prosto do `morfologia_worker.main()`. Zweryfikowane end-to-end na
realnie zbudowanym `.exe`: przed poprawką 0 wykryć na tekście z odmianami,
po poprawce poprawne maskowanie obu form. Test regresyjny pilnujący
spójności literału flagi między trzema miejscami:
`test_flaga_workera_morfologii_spojna_w_app_i_cli`.

**Ogólna lekcja (przydatna przy każdym kolejnym `PyInstaller` build w tym
projekcie):** każdy mechanizm, który uruchamia `sys.executable` jako
podproces z myślą "to będzie Python", trzeba osobno przetestować w
spakowanej wersji — `sys.executable` w `.exe` PyInstallera to nie
interpreter, tylko ten sam plik wykonywalny.

### Co jest w środku, a co trzeba doinstalować na komputerze docelowym

| Zależność | W `.exe`? | Uwaga |
|---|---|---|
| Silnik anonimizacji, słowniki GUS, czcionki | ✅ wbudowane | |
| Morfeusz2 (lematyzacja) | ✅ wbudowane | słownik wbudowany w `morfeusz2.dll` |
| python-docx, PyMuPDF (fitz), reportlab, pypdf, PIL | ✅ wbudowane | |
| Tesseract OCR (skany PDF, JPG, PNG) | ❌ zewnętrzne | instalator z UB-Mannheim, pakiety `pol`+`eng` |
| Poppler | ❌ zewnętrzne | wspomaga OCR skanów PDF |
| Tryb AI (spaCy + `pl_core_news_lg`, ~570 MB) | ❌ zewnętrzne | wymaga Pythona na maszynie docelowej; zbyt duże, żeby sensownie pakować |

Bez Tesseract/Poppler: pliki JPG/PNG i strony PDF będące czystym skanem
nie zostaną przetworzone — aplikacja to **zgłasza** (widoczne w
interfejsie/CLI), nie robi tego po cichu. Bez Trybu AI: aplikacja działa
normalnie, po prostu bez dodatkowego wykrywania AI.

`app.py` automatycznie otwiera przeglądarkę pod `http://127.0.0.1:5000`
przy starcie (`threading.Timer` + `webbrowser.open`, 1,5 s opóźnienia) —
wygodne przy uruchamianiu przez podwójne kliknięcie `.exe`, kiedy nie ma
terminala z adresem pod ręką.

## Sugerowane następne kroki

1. ~~Zachowanie layoutu dla trybu wsadowego "jedna sprawa"~~ — zrobione
   (DOCX/PDF/JPG/PNG, spójna numeracja tokenów nawet w partiach
   mieszających formaty — patrz "Znane ograniczenia").
2. Rozszerzyć słowniki obcojęzyczne (UK/FR/SK/CZ) analogicznie do pakietu
   `pl` — o ile dokumenty realnie zawierają dane z tych krajów.
3. ~~Zainstalować i przetestować Tryb AI (`pl_core_news_lg`)~~ — zrobione.
   spaCy 3.8.13 + pl_core_news_lg zainstalowane i przetestowane na
   realistycznym piśmie procesowym (patrz `tests/test_tryb_ai.py` i sekcja
   "Tryb AI — wyniki realnego testowania" niżej). Przy okazji znaleziony
   i naprawiony niezwiązany bug w recognizerach słownikowych (zawijanie
   wiersza błędnie traktowane jako początek zdania).
4. Testy na realnych skanach (nie tylko syntetycznych obrazach) — jakość
   OCR na rzeczywistych dokumentach firmowych bywa różna.
5. ~~Rozważyć równoległe przetwarzanie dużych partii plików~~ — zrobione
   (tryb "niezalezne" — patrz "Przetwarzanie równoległe" wyżej). Tryb
   "jedna_sprawa" zostaje sekwencyjny z przyczyn architektonicznych.
6. Przed ewentualną dystrybucją poza organizację: rozstrzygnąć licencję
   PyMuPDF (AGPL v3 vs komercyjna Artifex) — patrz sekcja "Zachowanie
   layoutu oryginału" wyżej.
7. Wpiąć w `app.py` wyświetlanie `strony_bez_warstwy_tekstowej` dla
   trybu wsadowego "jedna sprawa" (dziś ta informacja jest zwracana
   przez `anonimizuj_wiele_plikow`, ale UI pokazuje ją tylko dla
   pojedynczego pliku — patrz `wynik["strony_bez_warstwy_tekstowej"]`,
   klucz per nazwa pliku).
8. ~~Przygotować dystrybucję jako samodzielny .exe~~ — zrobione (patrz
   "Dystrybucja jako samodzielny .exe" wyżej). Ewentualny kolejny krok:
   zbudować analogicznie `cli.py` jako osobny `.exe` (dziś tylko `app.py`
   jest spakowane), jeśli pojawi się potrzeba użycia z linii poleceń na
   maszynie bez Pythona.
