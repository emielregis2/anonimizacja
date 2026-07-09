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

Odmienione formy pojedynczych słów ("Kowalskiego", "Krakowie") są
rozpoznawane przez lematyzację (Morfeusz2, patrz morfologia.py) — zawsze
aktywna, jeśli pakiet jest zainstalowany, degraduje się bezpiecznie do
samego dopasowania dokładnego, jeśli nie. Dopasowania wielowyrazowe
(np. "Nowy Sącz") nie są lematyzowane — patrz ograniczenie przy
recognize_miasta. Tryb AI (spaCy, patrz ai_ner.py) pozostaje dodatkowym
uzupełnieniem dla przypadków spoza słownika w ogóle.
"""

from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path
from . import morfologia
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


@lru_cache(maxsize=None)
def _nazwiska_dla_jezykow(jezyki: tuple[str, ...]) -> frozenset[str]:
    wynik: set[str] = set()
    for jezyk in jezyki:
        wynik |= _wczytaj_liste(f"nazwiska_{jezyk}.txt")
    return frozenset(wynik)


def _na_poczatku_zdania(text: str, pozycja: int) -> bool:
    """Sprawdza, czy dane miejsce w tekście zaczyna nowe zdanie/linię —
    używane jako zabezpieczenie przed fałszywym trafieniem samodzielnego
    nazwiska na pierwszym słowie zdania (ten sam problem, który wcześniej
    rozwiązano dla pary imię+nazwisko: pierwsze słowo zdania też jest pisane
    wielką literą, niezależnie od tego, czy jest nazwiskiem, czy nie)."""
    przed = text[:pozycja].rstrip(" \t")
    if not przed:
        return True
    if przed.endswith("\n"):
        return True
    return przed[-1] in ".!?"


def _tylko_to_slowo(text: str, dopasowanie: str) -> bool:
    """True, gdy przekazany fragment tekstu (np. cały akapit / komórka
    tabeli) w praktyce składa się wyłącznie z tego jednego dopasowania —
    typowe dla izolowanych wartości (komórka tabeli z samym nazwiskiem,
    pole formularza, nagłówek), gdzie zabezpieczenie "początek zdania"
    nie ma sensu, bo to w ogóle nie jest zdanie."""
    return text.strip() == dopasowanie


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
    """Miejscowości bywają wielowyrazowe (np. "Nowy Sącz", "Bielsko-Biała") —
    sprawdzamy sekwencje do 3 słów zaczynających się wielką literą.

    Tak jak przy samodzielnych nazwiskach: dopasowanie na samym początku
    zdania jest pomijane (zabezpieczenie przed częstymi fałszywymi
    trafieniami — pierwsze słowo zdania zawsze jest pisane wielką literą,
    niezależnie od tego, czy przypadkiem pokrywa się z nazwą miejscowości).

    Lematyzacja (morfologia.pasuje_do_slownika) obejmuje tylko dopasowania
    jednowyrazowe — "Krakowie" → "Kraków" zadziała, "Nowym Sączu" → "Nowy
    Sącz" nie (lematyzacja fraz wielowyrazowych wymagałaby analizy każdego
    słowa z osobna i rekonstrukcji lematu całej frazy — nie zaimplementowane,
    niska wartość względem nakładu, bo większość miejscowości to jedno
    słowo)."""
    miasta = _miasta_dla_jezykow(jezyki)
    wyniki = []
    for m in re.finditer(
        r"\b[A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż\-]+"
        r"(\s[A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż\-]+){0,2}\b",
        text,
    ):
        dopasowanie = m.group(0)
        pasuje = morfologia.pasuje_do_slownika(dopasowanie, dopasowanie.lower(), miasta)
        if pasuje and (
            not _na_poczatku_zdania(text, m.start()) or _tylko_to_slowo(text, dopasowanie)
        ):
            wyniki.append(Match(m.start(), m.end(), dopasowanie, "miasta"))
    return wyniki


def recognize_imiona_nazwiska(text: str, jezyki: tuple[str, ...] = ("pl",)) -> list[Match]:
    """
    Dwa niezależne mechanizmy, oba scalane w jedną kategorię "imiona_nazwiska":

    1. Kotwiczenie po imieniu: szukamy wystąpień znanych imion (jako
       zakotwiczenie), a nie dowolnego wielkiego słowa na początku
       dopasowania — inaczej słowo rozpoczynające zdanie (też pisane
       wielką literą) błędnie "zjadałoby" kolejne słowo jako parę
       imię+nazwisko, np. "Sprawa Jan Kowalski" dopasowałoby się jako
       ("Sprawa", "Jan"), pomijając "Kowalski". Jeśli po imieniu następuje
       kolejne słowo pisane wielką literą, traktujemy je jako potencjalne
       nazwisko i dołączamy do dopasowania.

    2. Samodzielne nazwisko (bez poprzedzającego imienia): sprawdzane
       względem osobnego słownika nazwisk (nazwiska_XX.txt, dane GUS —
       patrz dane_slownikowe/ZRODLA.md), ale TYLKO gdy słowo nie jest
       pierwszym słowem zdania — to samo zabezpieczenie co wyżej, bo
       inaczej każde zdanie zaczynające się od słowa, które przypadkiem
       jest też czyimś nazwiskiem (np. "Kowal" jako zawód), dawałoby
       fałszywe trafienie.

    Nakładające się dopasowania (np. "Kowalski" z pary "Jan Kowalski"
    ORAZ jako osobne, samodzielne dopasowanie na tej samej pozycji) są
    poprawnie rozwiązywane przez _rozwiaz_nakladania w anonimizator.py
    (dłuższe/wcześniejsze dopasowanie wygrywa) — nie trzeba tego obsługiwać
    tutaj.

    Lematyzacja (morfologia.pasuje_do_slownika, patrz morfologia.py):
    odmienione formy imion i samodzielnych nazwisk ("Kowalskiego",
    "Kowalskim") są rozpoznawane, jeśli pakiet morfeusz2 jest zainstalowany
    — bez niego zachowanie jest identyczne jak dopasowanie tylko dokładne.
    Nazwisko doklejane po rozpoznanym imieniu (druga część pary) NIE jest
    osobno sprawdzane względem słownika nazwisk — przyjmowane jest każde
    kolejne słowo z wielkiej litery, tak jak wcześniej.
    """
    imiona = _imiona_dla_jezykow(jezyki)
    nazwiska = _nazwiska_dla_jezykow(jezyki)
    wyniki = []
    for m in re.finditer(r"\b[A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż]+\b", text):
        slowo = m.group(0)
        slowo_lower = slowo.lower()
        start, end = m.start(), m.end()

        if morfologia.pasuje_do_slownika(slowo, slowo_lower, imiona):
            dopasowanie_nazwiska = re.match(
                r"\s+([A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż]+)", text[end:end + 40]
            )
            if dopasowanie_nazwiska:
                end += dopasowanie_nazwiska.end()
            wyniki.append(Match(start, end, text[start:end], "imiona_nazwiska"))
        elif morfologia.pasuje_do_slownika(slowo, slowo_lower, nazwiska) and (
            not _na_poczatku_zdania(text, start) or _tylko_to_slowo(text, slowo)
        ):
            wyniki.append(Match(start, end, slowo, "imiona_nazwiska"))
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
