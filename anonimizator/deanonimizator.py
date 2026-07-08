"""Przywracanie oryginalnej treści na podstawie placeholderów i zaszyfrowanego
mapowania. Wymaga hasła użytego przy anonimizacji — bez niego mapowanie
jest bezużyteczne (patrz crypto.py).

Uwaga: styl maskowania "puste" (patrz anonimizator.py) jest CELOWO
nieodwracalny — wszystkie wystąpienia zamieniane są na identyczny placeholder
"[USUNIĘTE]", więc w tekście nie ma już informacji pozwalającej ustalić,
który fragment odpowiada której wartości z mapowania. Mapowanie z tego trybu
służy wyłącznie do raportu/audytu, nie do automatycznego przywracania.
"""

from __future__ import annotations
from pathlib import Path
from . import crypto, extractors
from .anonimizator import GRANICA_PROMPTU_AI


class NieodwracalnyStylMaskowania(Exception):
    """Zgłaszane, gdy próbuje się deanonimizować tekst zanonimizowany
    w stylu 'puste' — z założenia nie da się tego odwrócić."""


def deanonimizuj_tekst(tekst_zanonimizowany: str, mapowanie: dict[str, str]) -> str:
    klucze_realne = [k for k in mapowanie if not k.startswith("__usuniete_")]
    klucze_usuniete = len(mapowanie) - len(klucze_realne)

    if klucze_usuniete and not klucze_realne:
        raise NieodwracalnyStylMaskowania(
            "Ten dokument został zanonimizowany w stylu 'puste' (dane trwale "
            "usunięte, bez możliwości odtworzenia). Mapowanie zawiera dane "
            "wyłącznie do celów raportu/audytu."
        )

    # Jeśli plik ma automatycznie dołączony prompt dla AI (patrz
    # anonimizator.zbuduj_prompt_ai), usuwamy go przed przywróceniem —
    # inaczej odtworzony "oryginał" zawierałby dopisek, którego w prawdziwym
    # oryginale nigdy nie było.
    if GRANICA_PROMPTU_AI in tekst_zanonimizowany:
        tekst_zanonimizowany = tekst_zanonimizowany.split(GRANICA_PROMPTU_AI, 1)[1].lstrip("\n")

    # Podmiana najdłuższych placeholderów najpierw — zapobiega częściowym
    # kolizjom (np. "Osoba A" vs "Osoba AA").
    wynik = tekst_zanonimizowany
    for placeholder in sorted(klucze_realne, key=len, reverse=True):
        wynik = wynik.replace(placeholder, mapowanie[placeholder])
    return wynik


def deanonimizuj_plik(
    sciezka_tekst: Path,
    sciezka_mapowanie: Path,
    haslo: str,
    sciezka_wyjsciowa: Path,
) -> Path:
    """Odczytuje zanonimizowany plik NIEZALEŻNIE OD JEGO FORMATU (od wersji
    z zapisem w oryginalnym formacie, zanonimizowany plik może być np. .pdf
    albo .docx, nie tylko .txt) i zapisuje przywrócony oryginał w formacie
    zgodnym z rozszerzeniem sciezka_wyjsciowa."""
    tekst = extractors.wczytaj_tekst(sciezka_tekst)
    zaszyfrowane = sciezka_mapowanie.read_bytes()
    mapowanie = crypto.odszyfruj_mapowanie(zaszyfrowane, haslo)
    oryginal = deanonimizuj_tekst(tekst, mapowanie)
    extractors.zapisz_w_formacie(sciezka_wyjsciowa, oryginal)
    return sciezka_wyjsciowa
