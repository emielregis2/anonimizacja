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
| 1 | 25+ kategorii polskich danych | 26 kategorii, regex + suma kontrolna gdzie możliwe |
| 2 | PDF, DOCX, ODT, RTF, TXT + OCR skanów/obrazów | `extractors.py` — automatyczny OCR (Tesseract, lokalnie) dla stron PDF bez warstwy tekstowej oraz dla JPG/PNG |
| 3 | Wiele plików naraz (2 tryby) | `anonimizuj_wiele_plikow(..., tryb="jedna_sprawa"/"niezalezne")` |
| 4 | Tryb Archiwum/BIP | `anonimizuj_bip(...)` — bez hasła, bez pliku mapowania, bezpowrotne |
| 5 | Raport anonimizacji (PDF z hasłem) | `generuj_raport_pdf(...)` — tabela placeholder→wartość, AES-256 w samym PDF |
| 6 | Auto-deanonimizacja (wklej odpowiedź AI) | Panel w interfejsie webowym — wklejasz tekst, tokeny wracają na żywo |
| 7 | Dowolny model AI | Naturalna właściwość — wynik to zwykły tekst |
| 8 | Wybór stylu anonimizacji | 4 style: `pelny_token`, `etykieta`, `inicjaly`, `puste` |
| 9 | Słowniki imion/miast, języki obce | PL (rozszerzone), + UK, FR, SK, CZ — dobierane parametrem `jezyki` |

Uczciwie o granicach tej realizacji — patrz sekcja "Znane ograniczenia" niżej.

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

## Wielojęzyczne słowniki (funkcja 9)

```python
anonimizuj_tekst(tekst, jezyki=["pl", "fr", "sk"])
```

Dostępne pakiety: `pl`, `uk`, `fr`, `sk`, `cz` (pliki w
`anonimizator/dane_slownikowe/`). Dorzucenie kolejnego języka to dodanie
dwóch plików tekstowych (`imiona_XX.txt`, `miasta_XX.txt`) — zero zmian
w kodzie.

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
  (dopełniacz) nie dopasuje się do wpisu "warszawa". Tryb AI (spaCy)
  istotnie to poprawia, jeśli zainstalowany.
- **OCR jakości zależnej od skanu.** Niska rozdzielczość, pochylone
  strony czy odręczne pismo obniżają skuteczność. 300 DPI (domyślne w
  module) to rozsądny punkt startowy.
- **DOCX**: podmiana zachowuje podział na akapity, nie formatowanie
  znak-po-znaku. PDF/RTF/ODT: tylko ekstrakcja treści, bez odtwarzania
  layoutu.
- **Styl `puste` jest odwracalny wyłącznie do celów raportu/audytu** —
  nie da się z niego automatycznie przywrócić tekstu (to zamierzone).
- **Auto-deanonimizacja trzyma mapowanie w pamięci serwera** przez czas
  trwania sesji — patrz kompromis opisany wyżej.
- **Słowniki obcojęzyczne (UK/FR/SK/CZ) są umiarkowanej wielkości**
  (kilkadziesiąt–150 pozycji) — solidny szkielet architektury
  wielojęzycznej, nie kompletna baza danych. Łatwo rozszerzyć,
  podmieniając pliki w `dane_slownikowe/`.
- **To nie jest gotowy "plug-and-play" produkt komercyjny** — architektura
  i pipeline end-to-end są solidne i przetestowane (18 testów
  jednostkowych), ale przed użyciem produkcyjnym z danymi rzeczywistymi
  klientów warto dostroić słowniki/progi na Waszych dokumentach.

## Struktura projektu

```
anonimizator/
├── anonimizator/
│   ├── __init__.py
│   ├── recognizers.py            regex + walidacja sum kontrolnych
│   ├── slowniki_recognizers.py   recognizery słownikowe, wielojęzyczne
│   ├── dane_slownikowe/          pliki imion/miast per język
│   ├── ai_ner.py                 opcjonalny lokalny model NER (Tryb AI)
│   ├── extractors.py             TXT/DOCX/ODT/RTF/PDF/JPG/PNG + OCR
│   ├── crypto.py                 szyfrowanie mapowania (PBKDF2 + Fernet)
│   ├── anonimizator.py           silnik: style, tryb wsadowy, tryb BIP
│   ├── deanonimizator.py         przywracanie oryginału
│   ├── raport.py                 raport PDF zabezpieczony hasłem
│   └── czcionki/                 czcionka DejaVu (polskie znaki w PDF)
├── app.py                        aplikacja webowa (drag&drop, wszystkie funkcje)
├── cli.py                        interfejs linii poleceń
├── start_anonimizator.bat
├── requirements.txt
└── tests/                        18 testów jednostkowych
```

## Sugerowane następne kroki

1. Rozszerzyć słowniki (miasta, imiona, w tym obcojęzyczne) o pełniejsze
   listy referencyjne zamiast plików w repozytorium.
2. Zainstalować i przetestować Tryb AI (`pl_core_news_lg`) na Waszych
   realnych, ale niewrażliwych dokumentach testowych.
3. Testy na realnych skanach (nie tylko syntetycznych obrazach) — jakość
   OCR na rzeczywistych dokumentach firmowych bywa różna.
4. Rozważyć równoległe przetwarzanie dużych partii plików (obecnie
   sekwencyjne) — łatwe do dodania, jeśli batch okaże się wolny.
