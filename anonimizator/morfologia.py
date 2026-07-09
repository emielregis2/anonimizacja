"""
Lematyzacja — cienka warstwa nad Morfeusz2 (analizator morfologiczny dla
języka polskiego), pozwalająca recognizerom słownikowym dopasowywać
odmienione formy słów ("Kowalskiego", "Krakowie", "Warszawy") do ich formy
podstawowej w słowniku ("Kowalski", "Kraków", "Warszawa") — bez trzymania
każdej możliwej odmiany w plikach dane_slownikowe/.

Działa lokalnie (biblioteka Python z gotowym wheel dla Windows/Linux, zero
komunikacji sieciowej) i — tak jak Tryb AI — degraduje się bezpiecznie do
braku lematyzacji (tylko dokładne dopasowanie), jeśli pakiet `morfeusz2`
nie jest zainstalowany.

W przeciwieństwie do Trybu AI: to nie jest opcjonalny dodatek do włączenia
w interfejsie, tylko zawsze aktywny, tani krok podstawowy — analiza
morfologiczna jest deterministyczna i szybka (skompilowana biblioteka C++,
nie model ML), więc nie ma powodu, żeby chować ją za checkboxem.

Wymaga: pip install morfeusz2

ZNANY, POWAŻNY PROBLEM ODKRYTY PRZY WDROŻENIU — LEMATYZACJA DOMYŚLNIE
WYŁĄCZONA: interakcja Morfeusz2 z PyMuPDF (fitz) w tym samym procesie
powoduje odtworzony eksperymentalnie, dwukierunkowy crash (naruszenie
dostępu do pamięci, niemożliwe do złapania przez try/except — to nie jest
wyjątek Pythona). Potwierdzone:
  - fitz użyty w procesie, potem Morfeusz2 (nawet w innym, niepowiązanym
    pliku) -> crash
  - Morfeusz2 najpierw, potem fitz -> również crash
  - TXT/DOCX/obrazy (JPG/PNG) + Morfeusz2, BEZ fitz w ogóle -> bezpieczne
To oznacza ryzyko dla każdego długo działającego procesu (np. app.py),
który choć raz przetworzy PDF — nie tylko dla samego przetwarzania PDF.
Dlatego lematyzacja jest domyślnie WYŁĄCZONA (WLACZ_LEMATYZACJE = False
poniżej) — świadome włączenie tylko jeśli wiesz, że Twój proces nigdy
nie dotknie fitz/PDF, albo po znalezieniu bezpiecznej izolacji (np.
osobny podproces dla Morfeusz2).
"""

from __future__ import annotations
import contextlib
from functools import lru_cache

# Patrz ostrzeżenie w docstringu modułu wyżej — zmień świadomie, rozumiejąc
# ryzyko crashu całego procesu przy jakimkolwiek użyciu PDF (fitz) w tym
# samym procesie, w dowolnej kolejności.
WLACZ_LEMATYZACJE = False

_MORF = None
_PROBOWANO_ZALADOWAC = False
_WYLACZONA_TYMCZASOWO = False


@contextlib.contextmanager
def bez_lematyzacji():
    """Tymczasowo wyłącza lematyzację w obrębie bloku `with` — używane
    przez layout_pdf.py jako dodatkowe zabezpieczenie, na wypadek gdyby
    WLACZ_LEMATYZACJE zostało kiedyś świadomie ustawione na True mimo
    ostrzeżenia. Zagnieżdżalne."""
    global _WYLACZONA_TYMCZASOWO
    poprzednia = _WYLACZONA_TYMCZASOWO
    _WYLACZONA_TYMCZASOWO = True
    try:
        yield
    finally:
        _WYLACZONA_TYMCZASOWO = poprzednia


def dostepna_lematyzacja() -> bool:
    global _MORF, _PROBOWANO_ZALADOWAC
    if not WLACZ_LEMATYZACJE or _WYLACZONA_TYMCZASOWO:
        return False
    if not _PROBOWANO_ZALADOWAC:
        _PROBOWANO_ZALADOWAC = True
        try:
            import morfeusz2
            _MORF = morfeusz2.Morfeusz()
        except Exception:
            _MORF = None
    return _MORF is not None


def lematy(slowo: str) -> frozenset[str]:
    """Zwraca zbiór możliwych lematów (form podstawowych) danego słowa,
    małymi literami. Słowo bywa niejednoznaczne morfologicznie (np.
    "Kowalskim" pasuje jednocześnie do "Kowalski", "Kowalska", "Kowalskie")
    — zwracamy wszystkie kandydatury, dopasowanie do słownika sprawdza
    każdą z nich. Jeśli lematyzacja jest niedostępna albo słowo nie zostało
    rozpoznane, zbiór zawiera wyłącznie samo słowo (bez zmian) — czyli
    zachowanie identyczne jak przed wdrożeniem lematyzacji.

    Działa tylko na pojedynczych słowach (bez spacji) — dopasowania
    wielowyrazowe (np. "Nowy Sącz") pomijają ten krok, patrz ograniczenie
    w slowniki_recognizers.py.

    Sprawdzenie dostępności celowo NIE jest częścią cache'owanej funkcji
    (_lematy_z_cache) — bez_lematyzacji() jest stanem tymczasowym, więc
    scache'owanie wyniku "brak lematyzacji" dla danego słowa zatrułoby
    późniejsze, prawidłowe wywołania poza blokiem `with`."""
    if not dostepna_lematyzacja() or " " in slowo:
        return frozenset({slowo.lower()})
    return _lematy_z_cache(slowo)


@lru_cache(maxsize=16384)
def _lematy_z_cache(slowo: str) -> frozenset[str]:
    wyniki = set()
    for _start, _end, interpretacja in _MORF.analyse(slowo):
        lemat = interpretacja[1]
        # Lemat czasem ma dopisek gramatyczny po dwukropku, np.
        # "Kowalski:Sm1" (S = nazwisko, m1 = rodzaj męskoosobowy) —
        # interesuje nas tylko czysta forma podstawowa.
        lemat_czysty = lemat.split(":")[0]
        wyniki.add(lemat_czysty.lower())

    if not wyniki:
        wyniki.add(slowo.lower())
    return frozenset(wyniki)


def pasuje_do_slownika(slowo: str, slowo_lower: str, slownik: frozenset[str]) -> bool:
    """Sprawdza, czy słowo (albo któryś z jego lematów) jest w słowniku.
    Dokładne dopasowanie sprawdzane jest jako pierwsze i najtańsze —
    lematyzacja wywoływana tylko wtedy, gdy jest faktycznie potrzebna."""
    if slowo_lower in slownik:
        return True
    return any(lemat in slownik for lemat in lematy(slowo))
