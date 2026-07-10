# -*- coding: utf-8 -*-
"""
Testy równoległego przetwarzania partii plików (tryb "niezalezne") —
punkt 5 z listy "Sugerowane następne kroki" w README.

Tryb "jedna_sprawa" NIE jest równoległy (współdzielony silnik ze spójną
numeracją tokenów wymaga deterministycznej, sekwencyjnej kolejności) —
patrz test_rownolegle_ignorowane_w_trybie_jedna_sprawa niżej.
"""

from pathlib import Path
from anonimizator import anonimizuj_wiele_plikow


def _przygotuj_pliki(tmp_path, n=4):
    pliki = []
    for i in range(n):
        p = tmp_path / f"plik_{i}.txt"
        p.write_text(f"Dokument {i}: Jan Kowalski podpisal umowe.", encoding="utf-8")
        pliki.append(p)
    return pliki


def test_rownolegle_daje_identyczny_wynik_jak_sekwencyjnie(tmp_path):
    pliki = _przygotuj_pliki(tmp_path)

    wynik_seq = anonimizuj_wiele_plikow(
        pliki, tmp_path / "wynik_seq", "Haslo123!", tryb="niezalezne",
        kategorie=["imiona_nazwiska"], rownolegle=False,
    )
    wynik_par = anonimizuj_wiele_plikow(
        pliki, tmp_path / "wynik_par", "Haslo123!", tryb="niezalezne",
        kategorie=["imiona_nazwiska"], rownolegle=True,
    )

    assert set(wynik_seq["pliki"].keys()) == set(wynik_par["pliki"].keys())
    for nazwa in wynik_seq["pliki"]:
        t1 = wynik_seq["pliki"][nazwa]["tekst"].read_text(encoding="utf-8")
        t2 = wynik_par["pliki"][nazwa]["tekst"].read_text(encoding="utf-8")
        assert t1 == t2, f"rownolegle i sekwencyjne przetwarzanie dalo rozny wynik dla {nazwa}"


def test_rownolegle_z_jawna_liczba_procesow(tmp_path):
    pliki = _przygotuj_pliki(tmp_path)
    wynik = anonimizuj_wiele_plikow(
        pliki, tmp_path / "wynik", "Haslo123!", tryb="niezalezne",
        kategorie=["imiona_nazwiska"], rownolegle=2,
    )
    assert len(wynik["pliki"]) == len(pliki)
    for dane in wynik["pliki"].values():
        assert "[OSOBA_1]" in dane["tekst"].read_text(encoding="utf-8")


def test_rownolegle_dziala_dla_pojedynczego_pliku(tmp_path):
    """rownolegle=True z jednym plikiem nie powinno się wysypać — po
    prostu nie ma sensu tworzyć puli procesów dla jednego zadania, więc
    funkcja po cichu wraca do ścieżki sekwencyjnej (patrz warunek
    `len(sciezki) > 1` w anonimizuj_wiele_plikow)."""
    pliki = _przygotuj_pliki(tmp_path, n=1)
    wynik = anonimizuj_wiele_plikow(
        pliki, tmp_path / "wynik", "Haslo123!", tryb="niezalezne",
        kategorie=["imiona_nazwiska"], rownolegle=True,
    )
    assert len(wynik["pliki"]) == 1


def test_rownolegle_ignorowane_w_trybie_jedna_sprawa(tmp_path):
    """Tryb "jedna_sprawa" ma zostać poprawny (spójna numeracja tokenów)
    nawet jeśli ktoś przez pomyłkę poda rownolegle=True — flaga po prostu
    nie ma żadnego efektu w tej gałęzi, przetwarzanie zostaje sekwencyjne."""
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_text("Sprawa Jan Kowalski.", encoding="utf-8")
    p2.write_text("Ponownie: Jan Kowalski potwierdza odbior.", encoding="utf-8")

    wynik = anonimizuj_wiele_plikow(
        [p1, p2], tmp_path / "wynik", "Haslo123!", tryb="jedna_sprawa",
        kategorie=["imiona_nazwiska"], rownolegle=True,
    )
    t1 = wynik["pliki_tekst"]["a.txt"].read_text(encoding="utf-8")
    t2 = wynik["pliki_tekst"]["b.txt"].read_text(encoding="utf-8")
    assert "[OSOBA_1]" in t1 and "[OSOBA_1]" in t2, \
        "spojna numeracja tokenow (jedna_sprawa) musi dzialac tak samo, ignorujac rownolegle"
