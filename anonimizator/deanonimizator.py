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
from . import crypto


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
    tekst = sciezka_tekst.read_text(encoding="utf-8")
    zaszyfrowane = sciezka_mapowanie.read_bytes()
    mapowanie = crypto.odszyfruj_mapowanie(zaszyfrowane, haslo)
    oryginal = deanonimizuj_tekst(tekst, mapowanie)
    sciezka_wyjsciowa.write_text(oryginal, encoding="utf-8")
    return sciezka_wyjsciowa
