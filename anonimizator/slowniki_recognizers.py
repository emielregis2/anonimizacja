"""
Recognizery wymagające danych referencyjnych (słowników) zamiast czystego
regexu: imiona i nazwiska, miasta, firmy/instytucje.

Obsługa wielu języków — jeśli macie umowę z partnerem zagranicznym i
dokumenty zawierają obce imiona/miasta, dobierzcie odpowiednie pakiety
językowe parametrem `jezyki` (domyślnie tylko polski):

    anonimizuj_tekst(tekst, jezyki=["pl", "uk", "fr"])

Dostępne pakiety: pl (polski), uk (Wielka Brytania), fr (Francja),
sk (Słowacja), cz (Czechy). Dane wczytywane są z plików tekstowych w
katalogu dane_slownikowe/ — łatwo dodać kolejny język, wystarczy dorzucić
imiona_XX.txt i miasta_XX.txt.

Bez modelu NER (spaCy, patrz ai_ner.py) te recognizery mają niższą
precyzję i recall niż deterministyczne regexy z recognizers.py — nie
stosują lematyzacji (odmiana przez przypadki nie jest rozpoznawana).
Tryb AI pozwala to istotnie poprawić bez wysyłania danych na zewnątrz.
"""

from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path
from .recognizers import Match

KATALOG_DANYCH = Path(__file__).parent / "dane_slownikowe"
JEZYKI_DOSTEPNE = ("pl", "uk", "fr", "sk", "cz")
JEZYK_DOMYSLNY = ["pl"]


@lru_cache(maxsize=None)
def _wczytaj_liste(nazwa_pliku: str) -> frozenset[str]:
    sciezka = KATALOG_DANYCH / nazwa_pliku
    if not sciezka.exists():
        return frozenset()
    with open(sciezka, encoding="utf-8") as f:
        return frozenset(linia.strip().lower() for linia in f if linia.strip())


@lru_cache(maxsize=None)
def _imiona_dla_jezykow(jezyki: tuple[str, ...]) -> frozenset[str]:
    wynik: set[str] = set()
    for jezyk in jezyki:
        wynik |= _wczytaj_liste(f"imiona_{jezyk}.txt")
    return frozenset(wynik)


@lru_cache(maxsize=None)
def _miasta_dla_jezykow(jezyki: tuple[str, ...]) -> frozenset[str]:
    wynik: set[str] = set()
    for jezyk in jezyki:
        wynik |= _wczytaj_liste(f"miasta_{jezyk}.txt")
    return frozenset(wynik)


SUFIKSY_FIRM = re.compile(
    r"\b(sp\.\s?z\s?o\.?o\.?|s\.a\.|sp\.\s?k\.|sp\.\s?j\.|spółka\s?akcyjna|"
    r"spółka\s?z\s?ograniczoną\s?odpowiedzialnością|ltd\.?|llc|gmbh|s\.r\.o\.?)\b",
    re.IGNORECASE,
)

PREFIKSY_INSTYTUCJI = re.compile(
    r"\b(urząd\s\w+|sąd\s(rejonowy|okręgowy|apelacyjny)|ministerstwo\s\w+|"
    r"prokuratura\s\w+|starostwo\s\w+|urząd\s?gminy|urząd\s?miasta)\b",
    re.IGNORECASE,
)


def recognize_miasta(text: str, jezyki: tuple[str, ...] = ("pl",)) -> list[Match]:
    miasta = _miasta_dla_jezykow(jezyki)
    wyniki = []
    # miasta bywają wielowyrazowe (np. "Nowy Sącz", "Bielsko-Biała") —
    # sprawdzamy sekwencje do 3 słów zaczynających się wielką literą
    for m in re.finditer(
        r"\b[A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż\-]+"
        r"(\s[A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż\-]+){0,2}\b",
        text,
    ):
        if m.group(0).lower() in miasta:
            wyniki.append(Match(m.start(), m.end(), m.group(0), "miasta"))
    return wyniki


def recognize_imiona_nazwiska(text: str, jezyki: tuple[str, ...] = ("pl",)) -> list[Match]:
    """
    Heurystyka: szukamy wystąpień znanych imion (jako zakotwiczenie), a nie
    dowolnego wielkiego słowa na początku dopasowania — inaczej słowo
    rozpoczynające zdanie (też pisane wielką literą) błędnie "zjadałoby"
    kolejne słowo jako parę imię+nazwisko, np. "Sprawa Jan Kowalski"
    dopasowałoby się jako ("Sprawa", "Jan"), pomijając "Kowalski".
    Jeśli po imieniu następuje kolejne słowo pisane wielką literą, traktujemy
    je jako potencjalne nazwisko i dołączamy do dopasowania.

    Bez modelu NER to nadal przybliżenie — część nazwisk pisanych
    samodzielnie (bez imienia w sąsiedztwie) NIE zostanie wykryta.
    Zalecane uzupełnienie: Tryb AI (spaCy NER).
    """
    imiona = _imiona_dla_jezykow(jezyki)
    wyniki = []
    for m in re.finditer(r"\b[A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż]+\b", text):
        if m.group(0).lower() not in imiona:
            continue
        start, end = m.start(), m.end()
        dopasowanie_nazwiska = re.match(
            r"\s+([A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż]+)", text[end:end + 40]
        )
        if dopasowanie_nazwiska:
            end += dopasowanie_nazwiska.end()
        wyniki.append(Match(start, end, text[start:end], "imiona_nazwiska"))
    return wyniki


def recognize_firmy_instytucje(text: str, jezyki: tuple[str, ...] = ("pl",)) -> list[Match]:
    wyniki = []
    for m in re.finditer(
        r"\b([A-ZŁŚŻŹĆŃÓĄĘ][\w\-]+(\s[A-Z][\w\-]+)?)\s+" + SUFIKSY_FIRM.pattern,
        text, re.IGNORECASE,
    ):
        wyniki.append(Match(m.start(), m.end(), m.group(0), "firmy_instytucje"))
    for m in PREFIKSY_INSTYTUCJI.finditer(text):
        wyniki.append(Match(m.start(), m.end(), m.group(0), "firmy_instytucje"))
    return wyniki


# Rejestr recognizerów słownikowych — każdy przyjmuje (text, jezyki)
SLOWNIKOWE_RECOGNIZERS = {
    "miasta": recognize_miasta,
    "imiona_nazwiska": recognize_imiona_nazwiska,
    "firmy_instytucje": recognize_firmy_instytucje,
}
