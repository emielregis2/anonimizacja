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

- **Recognizery słownikowe nie stosują lematyzacji.** "Warszawy"
  (dopełniacz) nie dopasuje się do wpisu "Warszawa". Tryb AI (spaCy)
  istotnie to poprawia, jeśli zainstalowany. Rozważana alternatywa bez
  pełnego modelu NER: analizator morfologiczny (Morfeusz2) sprowadzający
  słowo do formy podstawowej przed porównaniem ze słownikiem — nie
  zaimplementowane.
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
- **Tryb wsadowy "jedna sprawa" nie wspiera jeszcze zachowania layoutu** —
  zawsze używa starego trybu, nawet dla DOCX/PDF (wymagałoby współdzielenia
  stanu silnika ze ścieżką edycji w miejscu per plik — nie zaimplementowane).
  Tryb "niezależne" pliki wspiera to w pełni, bo każdy plik przechodzi
  osobno przez zwykły `anonimizuj_plik()`.
- **To nie jest gotowy "plug-and-play" produkt komercyjny** — architektura
  i pipeline end-to-end są solidne i przetestowane (47 testów jednostkowych),
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
└── tests/                        47 testów jednostkowych
```

## Sugerowane następne kroki

1. Lematyzacja (np. Morfeusz2) dla nazwisk/miejscowości — najskuteczniejsze
   rozwiązanie problemu odmiany przez przypadki bez pełnego Trybu AI.
2. Zachowanie layoutu dla trybu wsadowego "jedna sprawa" (dziś tylko
   pojedyncze pliki i tryb "niezależne" — patrz "Znane ograniczenia").
3. Rozszerzyć słowniki obcojęzyczne (UK/FR/SK/CZ) analogicznie do pakietu
   `pl` — o ile dokumenty realnie zawierają dane z tych krajów.
4. Zainstalować i przetestować Tryb AI (`pl_core_news_lg`) na Waszych
   realnych, ale niewrażliwych dokumentach testowych.
5. Testy na realnych skanach (nie tylko syntetycznych obrazach) — jakość
   OCR na rzeczywistych dokumentach firmowych bywa różna.
6. Rozważyć równoległe przetwarzanie dużych partii plików (obecnie
   sekwencyjne) — łatwe do dodania, jeśli batch okaże się wolny.
7. Przed ewentualną dystrybucją poza organizację: rozstrzygnąć licencję
   PyMuPDF (AGPL v3 vs komercyjna Artifex) — patrz sekcja "Zachowanie
   layoutu oryginału" wyżej.
