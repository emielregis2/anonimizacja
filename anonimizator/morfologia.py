"""
Lematyzacja — pozwala recognizerom słownikowym dopasowywać odmienione
formy słów ("Kowalskiego", "Krakowie", "Warszawy") do ich formy
podstawowej w słowniku ("Kowalski", "Kraków", "Warszawa") — bez trzymania
każdej możliwej odmiany w plikach dane_slownikowe/.

IZOLACJA PROCESOWA (ważne): silnik lematyzacji (Morfeusz2) działa
w OSOBNYM PROCESIE SYSTEMOWYM (morfologia_worker.py), komunikującym się
z resztą aplikacji przez potok stdin/stdout. To nie jest wybór
architektoniczny dla wygody — to konieczność. Pierwsza próba wdrożenia
(Morfeusz2 wywoływany bezpośrednio w tym samym procesie co reszta
aplikacji) ujawniła twardy, dwukierunkowy konflikt pamięciowy z PyMuPDF
(fitz): użycie obu bibliotek w jednym procesie, w dowolnej kolejności,
powoduje naruszenie dostępu do pamięci — crash całego procesu,
niemożliwy do złapania przez try/except, bo to nie jest wyjątek Pythona.
Uruchomienie Morfeusz2 w zupełnie osobnym procesie eliminuje ten problem
u źródła: dwie oddzielne przestrzenie adresowe fizycznie nie mogą sobie
nawzajem uszkodzić pamięci.

Konsekwencje tego podejścia:
  - Worker (morfologia_worker.py) jest uruchamiany raz, leniwie, przy
    pierwszym użyciu — nie nowy proces na każde słowo (za wolne).
  - Komunikacja to prosty protokół linia-JSON-na-linię-JSON przez potok.
  - Odrobinę wolniejsze niż wywołanie w procesie (narzut IPC per słowo),
    ale wciąż szybkie w praktyce (lokalny potok, nie sieć) i bezpieczne
    do cache'owania (@lru_cache) — powtórzone słowa nie pytają workera
    ponownie.
  - Jeśli worker nie wystartuje (np. brak pakietu morfeusz2) albo padnie
    w trakcie działania, lematyzacja cicho degraduje się do dopasowania
    tylko dokładnego — dokładnie tak samo jak Tryb AI degraduje się,
    gdy brakuje spaCy.

Wymaga: pip install morfeusz2
"""

from __future__ import annotations
import atexit
import contextlib
import json
import os
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path

WLACZ_LEMATYZACJE = True

# Flaga rozpoznawana przez app.py/cli.py na samym starcie (przed
# jakąkolwiek inną inicjalizacją) — pozwala spakowanemu .exe uruchomić
# sam siebie jako proces roboczy lematyzacji zamiast (nieistniejącego na
# docelowej maszynie) interpretera Pythona wywołującego osobny plik .py.
ARGUMENT_TRYBU_WORKERA = "--morfologia-worker-wewnetrzny"

_SCIEZKA_WORKERA = Path(__file__).parent / "morfologia_worker.py"
_STAN_LOCK = threading.Lock()
_PROCES: subprocess.Popen | None = None
_WORKER_DOSTEPNY: bool | None = None  # None = jeszcze nie sprawdzone
_WYLACZONA_TYMCZASOWO = False


@contextlib.contextmanager
def bez_lematyzacji():
    """Tymczasowo wyłącza lematyzację w obrębie bloku `with`. Zostawione
    jako ogólny mechanizm (np. do testów porównawczych/debugowania) —
    od czasu izolacji procesowej NIE jest już potrzebne jako obejście
    konfliktu z PyMuPDF (ten problem jest rozwiązany architektonicznie),
    więc layout_pdf.py go już nie używa."""
    global _WYLACZONA_TYMCZASOWO
    poprzednia = _WYLACZONA_TYMCZASOWO
    _WYLACZONA_TYMCZASOWO = True
    try:
        yield
    finally:
        _WYLACZONA_TYMCZASOWO = poprzednia


def _uruchom_worker_bez_locka() -> bool:
    """Zakłada, że wywołujący trzyma już _STAN_LOCK."""
    global _PROCES, _WORKER_DOSTEPNY
    if _PROCES is not None and _PROCES.poll() is None:
        return True
    if _WORKER_DOSTEPNY is False:
        return False
    try:
        srodowisko = dict(os.environ)
        srodowisko["PYTHONIOENCODING"] = "utf-8"
        if getattr(sys, "frozen", False):
            # W spakowanym .exe (PyInstaller) sys.executable to sam ten
            # .exe, nie interpreter Pythona — a morfologia_worker.py nie
            # istnieje jako osobny plik na dysku docelowej maszyny (jest
            # spakowany do archiwum). Zamiast uruchamiać skrypt, uruchamiamy
            # SAM SIEBIE ze specjalną flagą, którą app.py/cli.py rozpoznają
            # na starcie i przekazują sterowanie od razu do
            # morfologia_worker.main(), zanim cokolwiek innego się załaduje
            # (patrz odpowiedni fragment w app.py i cli.py). Ten sam wzorzec
            # co multiprocessing.freeze_support() na Windows.
            argumenty = [sys.executable, ARGUMENT_TRYBU_WORKERA]
        else:
            argumenty = [sys.executable, str(_SCIEZKA_WORKERA)]
        proces = subprocess.Popen(
            argumenty,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            env=srodowisko,
        )
        proces.stdin.write(json.dumps(["_test_startu_"]) + "\n")
        proces.stdin.flush()
        odpowiedz = proces.stdout.readline()
        if not odpowiedz:
            raise RuntimeError("worker morfologii nie odpowiedział przy starcie")
        wynik = json.loads(odpowiedz)
        if isinstance(wynik, dict) and "__blad_startu__" in wynik:
            raise RuntimeError(wynik["__blad_startu__"])
        _PROCES = proces
        _WORKER_DOSTEPNY = True
        return True
    except Exception:
        _WORKER_DOSTEPNY = False
        _PROCES = None
        return False


def dostepna_lematyzacja() -> bool:
    if not WLACZ_LEMATYZACJE or _WYLACZONA_TYMCZASOWO:
        return False
    with _STAN_LOCK:
        return _uruchom_worker_bez_locka()


def _zapytaj_worker(slowo: str) -> list[str] | None:
    """Zwraca listę lematów albo None, jeśli worker jest niedostępny
    (włącznie z sytuacją, w której padł w trakcie i restart się nie udał)."""
    global _PROCES, _WORKER_DOSTEPNY
    with _STAN_LOCK:
        if not _uruchom_worker_bez_locka():
            return None
        try:
            _PROCES.stdin.write(json.dumps([slowo], ensure_ascii=False) + "\n")
            _PROCES.stdin.flush()
            linia = _PROCES.stdout.readline()
            if not linia:
                raise RuntimeError("worker morfologii zakończył działanie")
            wynik = json.loads(linia)
            return wynik[0]
        except Exception:
            # Worker padł w trakcie dzialania - probujemy raz zrestartowac
            # PRZY NASTEPNYM wywolaniu (nie tutaj, zeby nie ryzykowac petli
            # awarii w jednym zapytaniu). Na razie: brak wyniku.
            try:
                _PROCES.kill()
            except Exception:
                pass
            _PROCES = None
            _WORKER_DOSTEPNY = None  # pozwól spróbować ponownie następnym razem
            return None


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
    w slowniki_recognizers.py."""
    if not dostepna_lematyzacja() or " " in slowo:
        return frozenset({slowo.lower()})
    return _lematy_z_cache(slowo)


@lru_cache(maxsize=16384)
def _lematy_z_cache(slowo: str) -> frozenset[str]:
    wynik = _zapytaj_worker(slowo)
    if wynik:
        return frozenset(wynik)
    return frozenset({slowo.lower()})


def pasuje_do_slownika(slowo: str, slowo_lower: str, slownik: frozenset[str]) -> bool:
    """Sprawdza, czy słowo (albo któryś z jego lematów) jest w słowniku.
    Dokładne dopasowanie sprawdzane jest jako pierwsze i najtańsze —
    lematyzacja (zapytanie do procesu roboczego) wywoływana tylko wtedy,
    gdy jest faktycznie potrzebna."""
    if slowo_lower in slownik:
        return True
    return any(lemat in slownik for lemat in lematy(slowo))


def zamknij_worker() -> None:
    """Kończy proces roboczy, jeśli działa — wołane przy zamykaniu
    aplikacji (atexit), żeby nie zostawiać osieroconych procesów."""
    global _PROCES
    with _STAN_LOCK:
        if _PROCES is not None:
            try:
                _PROCES.stdin.close()
            except Exception:
                pass
            try:
                _PROCES.terminate()
            except Exception:
                pass
            _PROCES = None


atexit.register(zamknij_worker)
