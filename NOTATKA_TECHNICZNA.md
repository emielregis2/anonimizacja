# Jak działa Anonimizator — notatka techniczna

Ten dokument tłumaczy **wewnętrzny przepływ danych** i najważniejsze
decyzje projektowe modułu `anonimizacja` — nie "co zrobić", tylko "co
się dzieje w środku i dlaczego akurat tak". README.md odpowiada na
pytanie "jak tego użyć"; ten dokument odpowiada na pytanie "jak to jest
zbudowane".

## 1. Przegląd: od pliku do pliku, w jednym zdaniu

Plik wejściowy → wyciągnięcie tekstu (+ OCR jeśli trzeba) → wykrycie PII
przez zestaw niezależnych "recognizerów" → nadanie każdemu wykryciu
placeholdera → zapisanie wyniku (albo w miejscu, z zachowaniem
formatowania, albo od nowa jako czysty tekst) → osobno: zaszyfrowanie
mapowania placeholder→oryginał.

Cztery warstwy, każda w osobnym pliku, każda testowalna niezależnie:

```
extractors.py          -- "przynieś mi płaski tekst z tego pliku"
recognizers*.py         -- "znajdź w tym tekście dane osobowe"
anonimizator.py          -- "zamień znalezione dane na tokeny, pilnuj spójności"
layout_*.py / extractors -- "zapisz wynik z powrotem do pliku"
```

## 2. Warstwa 1 — ekstrakcja tekstu (`extractors.py`)

Dla każdego wspieranego formatu (TXT/DOCX/ODT/RTF/PDF/JPG/PNG) jest
funkcja, która zwraca płaski string. Dla PDF: jeśli strona ma warstwę
tekstową, tekst wyciągany jest wprost; jeśli nie (czysty skan), strona
jest renderowana jako obraz i przepuszczana przez Tesseract (OCR). To
samo dla JPG/PNG — zawsze przez OCR.

Ta warstwa jest używana w **dwóch różnych celach**, co czasem myli przy
pierwszym kontakcie z kodem:
1. Do wykrycia PII (zawsze — potrzebujemy płaskiego tekstu, żeby na nim
   uruchomić regexy/słowniki).
2. Do zapisu wyniku w "starym trybie" (`zachowaj_layout=False`) —
   budowanie zupełnie nowego pliku z gołego tekstu. Dla DOCX/PDF/obrazów
   ten tryb jest dziś domyślnie **wyłączony** na rzecz warstwy 4 (edycja
   w miejscu) — patrz sekcja 5.

## 3. Warstwa 2 — wykrywanie PII (recognizery)

### 3.1. Dwa rodzaje recognizerów

**Deterministyczne** (`recognizers.py`) — czysty regex + walidacja sumy
kontrolnej tam, gdzie się da (PESEL, NIP, REGON, IBAN, numer dowodu wg
normy ICAO 9303). Szybkie, precyzyjne, zero fałszywych trafień przy
poprawnej sumie kontrolnej.

**Słownikowe** (`slowniki_recognizers.py`) — dla kategorii bez
sztywnego formatu (imiona, nazwiska, miejscowości, firmy). Sprawdzają,
czy dane słowo jest w załadowanym słowniku (frozenset — sprawdzenie
przynależności to O(1), nawet przy 598 476 nazwiskach). Tu jest
najwięcej niuansów:

- **Kotwiczenie po imieniu**: "Jan Kowalski" — "Jan" jest w słowniku
  imion, więc kolejne słowo z wielkiej litery ("Kowalski") jest
  przyjmowane jako nazwisko **bez sprawdzania go w słowniku nazwisk**.
- **Samodzielne nazwisko**: "Kowalski przyszedł..." — bez poprzedzającego
  imienia, sprawdzane wprost względem słownika nazwisk. Tu włącza się
  zabezpieczenie `_na_poczatku_zdania` (patrz 3.3).
- **Miejscowości**: do 3 słów pod rząd zaczynających się wielką literą
  ("Nowy Sącz"), sprawdzane jako fraza względem słownika miast.

### 3.2. Lematyzacja — dlaczego jest w osobnym procesie systemowym

Żeby "Kowalskiego" (dopełniacz) dopasować do wpisu "Kowalski" w
słowniku, trzeba znać *formę podstawową* słowa. Do tego służy
Morfeusz2 — ale **nie jest wywoływany bezpośrednio w tym samym procesie
co reszta programu**. Jest uruchamiany jako osobny proces systemowy
(`morfologia_worker.py`), z którym `morfologia.py` rozmawia przez potok
stdin/stdout (jedna linia JSON = zapytanie, jedna linia JSON = odpowiedź).

To nie jest ozdobnik architektoniczny — to obejście prawdziwego,
eksperymentalnie potwierdzonego problemu: Morfeusz2 i PyMuPDF (biblioteka
do PDF) w tym samym procesie, w dowolnej kolejności użycia, powodują
twardy crash (naruszenie dostępu do pamięci — nie wyjątek Pythona, więc
nie da się go złapać przez `try/except`). Dwie oddzielne przestrzenie
adresowe procesów fizycznie nie mogą sobie nawzajem uszkodzić pamięci —
stąd izolacja.

Konsekwencje tego wyboru:
- Worker startuje **leniwie**, przy pierwszym słowie wymagającym
  lematyzacji, i **żyje przez cały czas działania programu** (nie nowy
  proces na każde słowo — za wolne).
- Jeśli worker nie wystartuje (brak `morfeusz2`) albo padnie w trakcie,
  cały mechanizm **cicho degraduje się** do dopasowania tylko dokładnego
  — program dalej działa, tylko trochę mniej trafnie. To świadomy wybór
  (fail-soft), ale ma cień: w spakowanym `.exe` ta cicha degradacja
  ukryła prawdziwy bug na dłużej niż powinna — patrz sekcja 8.
- Wyniki lematyzacji są cache'owane (`@lru_cache`) — to samo słowo
  pytane drugi raz nie generuje kolejnego zapytania do workera.

### 3.3. Zabezpieczenie przed fałszywymi trafieniami na początku zdania

Każde zdanie zaczyna się wielką literą — więc samo "wielka litera" nie
odróżnia nazwiska od zwykłego pierwszego słowa zdania, które przypadkiem
pokrywa się z czyimś nazwiskiem (np. "Nowak" jako pospolite słowo w
innym kontekście). `_na_poczatku_zdania(text, pozycja)` sprawdza, co
poprzedza dane miejsce w tekście:

- początek stringa → tak, to początek zdania
- **podwójny** znak nowej linii (`\n\n`, granica akapitu) → tak
- kropka/wykrzyknik/pytajnik → tak
- **pojedynczy** znak nowej linii → **nie** (to zawinięcie wiersza
  w środku zdania, nie nowe zdanie)

Ten ostatni punkt to poprawka z tej sesji — pierwotna wersja traktowała
*każdy* `\n` jako początek zdania, co w prawdziwych, wieloliniowych
dokumentach (PDF, DOCX, tekst po OCR) blokowało wykrycie słowa zaraz po
zawinięciu wiersza w połowie zdania. Osobny wyjątek: `_tylko_to_slowo`
— jeśli cały przekazany fragment to dokładnie to jedno słowo (typowe dla
komórki tabeli, pola formularza), zabezpieczenie się nie stosuje, bo to
w ogóle nie jest "zdanie" w sensie gramatycznym.

### 3.4. Tryb AI — uzupełnienie, nie zamiennik

`ai_ner.py` ładuje lokalny model spaCy (`pl_core_news_lg`) **wyłącznie
lokalnie** — zero komunikacji sieciowej, żaden tekst nigdzie nie
wychodzi. Włączany opcjonalnie (`tryb_ai=True`), dokłada swoje
wykrycia do tej samej listy co recognizery deterministyczne/słownikowe.
Jego realna wartość: łapie nazwiska/nazwy firm, których nie ma w żadnym
załadowanym słowniku językowym — np. obce imię i nazwisko spoza
wszystkich pakietów pl/uk/fr/sk/cz. Model bywa niedokładny na
szczegółach (np. źle segmentuje skróty typu "S.A."), ale to nie problem
projektu, tylko ograniczenie modelu — i tak zwykle *coś* wykrywa tam,
gdzie recognizery słownikowe widzą pustkę.

### 3.5. Rozwiązywanie nakładających się dopasowań

Różne recognizery mogą trafić w ten sam fragment tekstu (np. "Kowalski"
wykryty i jako część pary "Jan Kowalski", i jako samodzielne nazwisko).
`_rozwiaz_nakladania` w `anonimizator.py` sortuje wszystkie dopasowania
po: pozycji startu → priorytecie kategorii (PESEL/NIP/IBAN wygrywają z
imieniem/nazwiskiem, bo są bardziej precyzyjne) → długości dopasowania
(dłuższe wygrywa). Pierwsze dopasowanie "zajmuje" swój zakres, kolejne
nakładające się są odrzucane.

## 4. Warstwa 3 — silnik i stan (`SilnikAnonimizacji`)

Klasa `SilnikAnonimizacji` trzyma cały stan potrzebny do spójnego
maskowania: licznik per kategoria (do numerowania `[OSOBA_1]`,
`[OSOBA_2]`...), mapowanie wartość→placeholder (żeby ten sam "Jan
Kowalski" zawsze dostawał ten sam token w obrębie jednej instancji
silnika) i finalne mapowanie placeholder→oryginał (do zaszyfrowania).

Kluczowa właściwość: **jedna instancja silnika = jedna spójna
numeracja**. To, czy przetwarzasz jeden plik, czy dziesięć, sprowadza
się do pytania "czy używam jednej instancji silnika dla wszystkich, czy
osobnej dla każdego" — stąd dwa tryby wsadowe (`jedna_sprawa` vs
`niezalezne`, sekcja 6).

## 5. Warstwa 4 — zapis wyniku: w miejscu vs od nowa

**Stary tryb** (`zachowaj_layout=False`): wyciągnij cały tekst, podmień
placeholdery, zbuduj zupełnie nowy plik od zera. Proste, ale gubi
formatowanie, tabele, obrazy.

**Tryb domyślny** (`zachowaj_layout=True`, DOCX/PDF/JPG/PNG): edycja
w miejscu.
- **DOCX** (`layout_docx.py`): dokument ma strukturę akapit → runy
  (fragmenty tekstu ze wspólnym formatowaniem). Budujemy płaski tekst
  jednego akapitu, wykrywamy w nim PII, po czym podmieniamy **tylko
  tekst** trafionych runów — obiekt runu (a więc jego pogrubienie,
  kolor, czcionka) zostaje nietknięty. Podmiana rozciągająca się na
  dwa runy o różnym formatowaniu ląduje w całości w pierwszym z nich.
- **PDF** (`layout_pdf.py`): prawdziwa redakcja przez PyMuPDF
  (`add_redact_annot` + `apply_redactions`) — tekst jest **fizycznie
  usuwany** z warstwy tekstowej, nie tylko zasłonięty wizualnie. Strony
  bez warstwy tekstowej (czyste skany) idą osobną ścieżką OCR
  (`layout_images.anonimizuj_strone_skanowana_pdf`).
- **Obrazy** (`layout_images.py`): `pytesseract.image_to_data` daje nie
  tylko tekst, ale współrzędne każdego słowa — zamalowujemy dokładnie
  bounding-box trafionego fragmentu, resztę zdjęcia zostawiamy bez zmian.

Wspólny mianownik wszystkich trzech: przyjmują **gotową instancję**
`SilnikAnonimizacji` z zewnątrz (nie tworzą własnej) — dzięki temu ta
sama instancja może być przekazywana kolejno przez wiele plików w trybie
`jedna_sprawa`, zachowując spójną numerację niezależnie od formatu pliku.

## 6. Tryb wsadowy — dwa modele współdzielenia stanu

`anonimizuj_wiele_plikow(tryb=...)`:

- **`niezalezne`**: każdy plik dostaje własną, świeżą instancję silnika
  (przez zwykłe `anonimizuj_plik()`) — zero zależności między plikami,
  każdy ma osobny plik mapowania. To sprawia, że pliki można przetwarzać
  **w dowolnej kolejności, nawet równolegle** (sekcja 7).
- **`jedna_sprawa`**: jedna instancja silnika przechodzi sekwencyjnie
  przez wszystkie pliki. Ten sam "Jan Kowalski" w trzech dokumentach tej
  samej sprawy dostaje ten sam token wszędzie, bo to dosłownie ten sam
  słownik `wartosc→placeholder` w pamięci. To z definicji **wymaga
  kolejności** — stąd ten tryb nigdy nie jest równoległy.

## 7. Przetwarzanie równoległe — dlaczego procesy, nie wątki

`rownolegle=True/int` (tylko `niezalezne`) używa `ProcessPoolExecutor`,
nie `ThreadPoolExecutor`. Powód: Python ma GIL (Global Interpreter Lock)
— w danym momencie tylko jeden wątek wykonuje kod Pythona, więc wątki
nie przyspieszają pracy zdominowanej przez regex/porównania w słowniku
(czysty CPU-bound Python). Osobne procesy mają osobne interpretery, więc
faktycznie działają równolegle na wielu rdzeniach.

Cena: każdy proces roboczy musi **od nowa** wczytać do pamięci ogromne
słowniki (598k nazwisk) i — jeśli trzeba — uruchomić własny worker
lematyzacji. To koszt stały, ponoszony raz na proces, niezależnie od
liczby plików, który dominuje przy małych partiach (dla nich sekwencyjne
bywa szybsze — zmierzone wprost) i amortyzuje się dopiero przy większych.

## 8. Dystrybucja jako `.exe` — freezing i jego pułapki

PyInstaller pakuje interpreter Pythona + wszystkie zależności + kod
projektu w jeden plik wykonywalny. Z punktu widzenia programu zmienia to
jedną fundamentalną rzecz: **`sys.executable` przestaje wskazywać na
interpreter Pythona — wskazuje na sam ten `.exe`**.

To ma znaczenie wszędzie tam, gdzie kod uruchamia `subprocess.Popen([sys.executable, ...])`
z założeniem "to uruchomi Pythona z jakimś skryptem". Dokładnie to
robił `morfologia.py` przy starcie workera lematyzacji — w wersji
spakowanej próba uruchomienia `[AnonimizatorGUI.exe, "morfologia_worker.py"]`
nie ma sensu (plik `.py` nie istnieje osobno na dysku, a `.exe` nie wie,
co zrobić z argumentem-ścieżką-do-skryptu). Standardowe rozwiązanie
(ten sam wzorzec, którego używa `multiprocessing.freeze_support()`):
program uruchamia **sam siebie** z rozpoznawalną flagą wiersza poleceń,
a punkt wejścia (`app.py`/`cli.py`) sprawdza tę flagę jako pierwszą
rzecz — zanim załaduje cokolwiek innego — i jeśli jest obecna,
przekazuje sterowanie prosto do funkcji workera zamiast normalnie
startować.

Ogólna zasada do zapamiętania przy każdym kolejnym module używającym
podprocesów w tym projekcie: **jeśli kod zakłada, że `sys.executable`
to Python, przetestuj to osobno w wersji spakowanej** — w trybie
deweloperskim błąd się nie ujawni.

## 9. Bezpieczeństwo i szyfrowanie

- **Offline z założenia**: żadna z bibliotek w ścieżce przetwarzania
  (regex, słowniki, Morfeusz2, Tesseract, spaCy) nie wykonuje żadnego
  wywołania sieciowego. Serwer webowy (`app.py`) nasłuchuje wyłącznie na
  `127.0.0.1` — nieosiągalny spoza tej samej maszyny.
- **Szyfrowanie mapowania** (`crypto.py`): hasło podane przez
  użytkownika → PBKDF2-HMAC-SHA256 (600 000 iteracji) → klucz dla
  Fernet (AES-128-CBC + HMAC, z biblioteki `cryptography`). To
  świadoma poprawka względem konkurencyjnego narzędzia Beznazwisk.pl,
  które przy audycie okazało się używać samego Base64 (kodowanie, nie
  szyfrowanie) tam, gdzie deklarowało AES-256-GCM.
- **Deanonimizacja** wymaga tego samego hasła — bez niego mapowanie
  jest matematycznie nieodzyskiwalne (nie ma "backdoora", nie ma
  "zapomniałem hasła, odzyskaj mi dane").

## 10. Gdzie szukać czego (skrót)

| Pytanie | Plik |
|---|---|
| Jak wygląda konkretny wzorzec regex dla PESEL/NIP/IBAN? | `recognizers.py` |
| Dlaczego "Kowalski" nie zostało wykryte na początku zdania? | `slowniki_recognizers.py`, `_na_poczatku_zdania` |
| Jak działa lematyzacja / dlaczego jest wolna przy pierwszym słowie? | `morfologia.py` (start workera jest leniwy) |
| Dlaczego DOCX zachował pogrubienie po anonimizacji? | `layout_docx.py`, `_zastosuj_zamiany_na_runach` |
| Skąd bierze się numer `[OSOBA_2]` a nie `[OSOBA_1]`? | `anonimizator.py`, `SilnikAnonimizacji._nastepny_placeholder` |
| Dlaczego w trybie "jedna sprawa" nie da się przetwarzać równolegle? | sekcja 6 wyżej / docstring `anonimizuj_wiele_plikow` |
| Dlaczego .exe nie wykrywał odmienionych form przed poprawką? | sekcja 8 wyżej / `ARGUMENT_TRYBU_WORKERA` w `morfologia.py` |
