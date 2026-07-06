"""
Główny silnik anonimizacji.

Przepływ:
  1. Wczytaj tekst z pliku (extractors.py — obsługuje też OCR skanów/obrazów).
  2. Uruchom wybrane recognizery (recognizers.py, slowniki_recognizers.py,
     opcjonalnie ai_ner.py w Trybie AI).
  3. Rozwiąż nakładające się dopasowania (dłuższe/bardziej precyzyjne wygrywa).
  4. Podmień każde wystąpienie na placeholder w wybranym stylu (patrz
     STYLE_MASKOWANIA) — to samo wystąpienie tej samej wartości zawsze
     dostaje ten sam placeholder w obrębie jednej "sprawy".
  5. Zapisz zanonimizowany tekst (jawny) oraz zaszyfrowane mapowanie
     placeholder -> oryginalna wartość (crypto.py).

SilnikAnonimizacji pozwala przetwarzać wiele plików ze wspólną, spójną
numeracją tokenów (tryb "Jedna sprawa") albo z numeracją niezależną dla
każdego pliku (tryb "Niezależne dokumenty") — patrz anonimizuj_wiele_plikow.
"""

from __future__ import annotations
import re
import string
from dataclasses import dataclass, field
from pathlib import Path

from .recognizers import DETERMINISTIC_RECOGNIZERS, Match
from .slowniki_recognizers import SLOWNIKOWE_RECOGNIZERS
from .ai_ner import recognize_ai, dostepny_tryb_ai
from . import extractors, crypto

PREFIKSY_TOKENOW = {
    "imiona_nazwiska": "OSOBA",
    "telefony": "TELEFON",
    "paszporty": "PASZPORT",
    "nip": "NIP",
    "firmy_instytucje": "FIRMA",
    "miasta": "MIASTO",
    "kw": "KW",
    "tablice_rejestracyjne": "TABLICA_REJ",
    "adresy_www": "URL",
    "pesel": "PESEL",
    "email": "EMAIL",
    "prawo_jazdy": "PRAWO_JAZDY",
    "regon": "REGON",
    "iban": "IBAN",
    "kody_pocztowe": "KOD_POCZTOWY",
    "sygnatury_akt": "SYGNATURA_AKT",
    "identyfikatory_medyczne": "ID_MEDYCZNY",
    "konta_social": "KONTO_SOCIAL",
    "adresy_pocztowe": "ADRES",
    "numery_dokumentow": "DOKUMENT",
    "vin": "VIN",
    "krs": "KRS",
    "adresy_ip": "IP",
    "numery_dzialek": "DZIALKA",
    "sygnatury_adm": "SYGNATURA_ADM",
    "e_doreczenia": "E_DORECZENIE",
}

ETYKIETY_KATEGORII = {
    "imiona_nazwiska": "Osoba", "telefony": "Telefon", "paszporty": "Paszport",
    "nip": "NIP", "firmy_instytucje": "Firma", "miasta": "Miasto",
    "kw": "Księga wieczysta", "tablice_rejestracyjne": "Tablica rejestracyjna",
    "adresy_www": "Adres WWW", "pesel": "PESEL", "email": "E-mail",
    "prawo_jazdy": "Prawo jazdy", "regon": "REGON", "iban": "Konto bankowe",
    "kody_pocztowe": "Kod pocztowy", "sygnatury_akt": "Sygnatura akt",
    "identyfikatory_medyczne": "Identyfikator medyczny", "konta_social": "Konto social",
    "adresy_pocztowe": "Adres", "numery_dokumentow": "Dokument", "vin": "VIN",
    "krs": "KRS", "adresy_ip": "Adres IP", "numery_dzialek": "Działka",
    "sygnatury_adm": "Sygnatura adm.", "e_doreczenia": "E-doręczenie",
}

WSZYSTKIE_KATEGORIE = list(PREFIKSY_TOKENOW.keys())

PRIORYTET_KATEGORII = {
    "pesel": 0, "nip": 0, "regon": 0, "iban": 0, "e_doreczenia": 0, "vin": 0,
    "email": 1, "adresy_www": 1, "adresy_ip": 1, "kw": 1, "krs": 1,
    "sygnatury_akt": 2, "paszporty": 2, "numery_dokumentow": 2,
    "adresy_pocztowe": 3, "kody_pocztowe": 3, "tablice_rejestracyjne": 3,
    "telefony": 4, "prawo_jazdy": 4, "sygnatury_adm": 4, "numery_dzialek": 4,
    "identyfikatory_medyczne": 4, "konta_social": 4,
    "firmy_instytucje": 5, "imiona_nazwiska": 6, "miasta": 7,
}

# --- Style maskowania -------------------------------------------------------
# "pelny_token"  -> [OSOBA_1]                — w pełni odwracalny (domyślny)
# "etykieta"     -> Osoba A                    — w pełni odwracalny, czytelniejszy
# "inicjaly"     -> J. K. / częściowa maska    — odwracalny (mapowanie po wartości)
# "puste"        -> [USUNIĘTE]                 — NIEODWRACALNY (patrz deanonimizator.py)
STYLE_MASKOWANIA = ("pelny_token", "etykieta", "inicjaly", "puste")

WZORZEC_TOKENU = re.compile(r"\[[A-ZĄĆĘŁŃÓŚŹŻ_]+_\d+\]")


def _numer_do_liter(n: int) -> str:
    """1 -> A, 2 -> B, ..., 26 -> Z, 27 -> AA, ..."""
    litery = string.ascii_uppercase
    wynik = ""
    while n > 0:
        n, reszta = divmod(n - 1, 26)
        wynik = litery[reszta] + wynik
    return wynik


def _maskuj_czesciowo(wartosc: str) -> str:
    dlugosc = len(wartosc)
    if dlugosc <= 4:
        return "*" * dlugosc
    return wartosc[:2] + "*" * (dlugosc - 4) + wartosc[-2:]


def _inicjaly_osoby_lub_firmy(wartosc: str) -> str:
    slowa = [s for s in re.split(r"\s+", wartosc.strip()) if len(s) >= 2 and s[0].isupper()]
    if not slowa:
        return _maskuj_czesciowo(wartosc)
    return " ".join(f"{s[0]}." for s in slowa)


@dataclass
class WynikAnonimizacji:
    tekst_zanonimizowany: str
    mapowanie: dict[str, str]
    liczba_wykryc: dict[str, int] = field(default_factory=dict)


class SilnikAnonimizacji:
    """
    Silnik z zachowanym stanem (liczniki, mapowanie) — pozwala przetworzyć
    wiele tekstów/plików ze spójną numeracją tokenów w obrębie jednej
    "sprawy" (ten sam Jan Kowalski w trzech różnych pismach dostanie ten sam
    token we wszystkich trzech). Utwórz nową instancję, żeby zacząć od zera
    (np. dla trybu "Niezależne dokumenty").
    """

    _jezyki: tuple[str, ...] = ("pl",)

    def __init__(self, styl: str = "pelny_token"):
        if styl not in STYLE_MASKOWANIA:
            raise ValueError(f"Nieznany styl: {styl}. Dostępne: {STYLE_MASKOWANIA}")
        self.styl = styl
        self.mapowanie: dict[str, str] = {}
        self._wartosc_do_placeholdera: dict[tuple[str, str], str] = {}
        self._liczniki: dict[str, int] = {}
        self.liczba_wykryc: dict[str, int] = {}
        self._etykiety_w_uzyciu: dict[str, str] = {}
        self._licznik_usunietych = 0

    def _nastepny_placeholder(self, kategoria: str, wartosc: str) -> str:
        self._liczniki[kategoria] = self._liczniki.get(kategoria, 0) + 1
        n = self._liczniki[kategoria]

        if self.styl == "pelny_token":
            prefiks = PREFIKSY_TOKENOW.get(kategoria, kategoria.upper())
            return f"[{prefiks}_{n}]"
        if self.styl == "etykieta":
            etykieta = ETYKIETY_KATEGORII.get(kategoria, kategoria.capitalize())
            return f"{etykieta} {_numer_do_liter(n)}"
        if self.styl == "inicjaly":
            if kategoria in ("imiona_nazwiska", "firmy_instytucje"):
                return _inicjaly_osoby_lub_firmy(wartosc)
            return _maskuj_czesciowo(wartosc)
        if self.styl == "puste":
            return "[USUNIĘTE]"
        raise AssertionError("nieosiągalne")

    def przetworz(self, tekst: str, kategorie: list[str] | None = None,
                   tryb_ai: bool = False) -> str:
        kategorie = kategorie or WSZYSTKIE_KATEGORIE

        wszystkie_dopasowania: list[Match] = []
        for kategoria in kategorie:
            if kategoria in DETERMINISTIC_RECOGNIZERS:
                wszystkie_dopasowania += DETERMINISTIC_RECOGNIZERS[kategoria](tekst)
            elif kategoria in SLOWNIKOWE_RECOGNIZERS:
                wszystkie_dopasowania += SLOWNIKOWE_RECOGNIZERS[kategoria](tekst, self._jezyki)

        if tryb_ai and dostepny_tryb_ai():
            wszystkie_dopasowania += [m for m in recognize_ai(tekst) if m.category in kategorie]

        dopasowania = _rozwiaz_nakladania(wszystkie_dopasowania)

        fragmenty = []
        ostatnia_pozycja = 0

        for m in dopasowania:
            klucz_wartosci = (m.category, m.text.lower())

            if self.styl == "puste":
                # nieodwracalne z założenia — nie budujemy spójnego mapowania
                # 1:1 w tekście, ale zachowujemy wpis do raportu/audytu
                placeholder = "[USUNIĘTE]"
                self._licznik_usunietych += 1
                self.mapowanie[f"__usuniete_{self._licznik_usunietych}__ ({m.category})"] = m.text
            elif klucz_wartosci not in self._wartosc_do_placeholdera:
                placeholder = self._nastepny_placeholder(m.category, m.text)
                if placeholder in self._etykiety_w_uzyciu and \
                        self._etykiety_w_uzyciu[placeholder] != m.text:
                    placeholder = f"{placeholder} (2)"
                self._etykiety_w_uzyciu[placeholder] = m.text
                self._wartosc_do_placeholdera[klucz_wartosci] = placeholder
                self.mapowanie[placeholder] = m.text
            else:
                placeholder = self._wartosc_do_placeholdera[klucz_wartosci]

            self.liczba_wykryc[m.category] = self.liczba_wykryc.get(m.category, 0) + 1
            fragmenty.append(tekst[ostatnia_pozycja:m.start])
            fragmenty.append(placeholder)
            ostatnia_pozycja = m.end
        fragmenty.append(tekst[ostatnia_pozycja:])
        return "".join(fragmenty)


def _rozwiaz_nakladania(dopasowania: list[Match]) -> list[Match]:
    dopasowania = sorted(
        dopasowania,
        key=lambda m: (m.start, PRIORYTET_KATEGORII.get(m.category, 9), -(m.end - m.start)),
    )
    wynik: list[Match] = []
    ostatni_koniec = -1
    for m in dopasowania:
        if m.start >= ostatni_koniec:
            wynik.append(m)
            ostatni_koniec = m.end
    return wynik


def _usun_numery_stron(tekst: str) -> str:
    linie = tekst.split("\n")
    wynik = []
    for linia in linie:
        if re.fullmatch(r"\s*\d{1,4}\s*", linia):
            continue
        if re.fullmatch(r"\s*strona\s+\d+\s*(z|/)\s*\d+\s*", linia, re.IGNORECASE):
            continue
        wynik.append(linia)
    return "\n".join(wynik)


def anonimizuj_tekst(
    tekst: str,
    kategorie: list[str] | None = None,
    tryb_ai: bool = False,
    usun_numery_stron: bool = False,
    styl: str = "pelny_token",
    jezyki: list[str] | None = None,
) -> WynikAnonimizacji:
    if usun_numery_stron:
        tekst = _usun_numery_stron(tekst)

    silnik = SilnikAnonimizacji(styl=styl)
    silnik._jezyki = tuple(jezyki or ["pl"])
    tekst_wynikowy = silnik.przetworz(tekst, kategorie=kategorie, tryb_ai=tryb_ai)

    return WynikAnonimizacji(
        tekst_zanonimizowany=tekst_wynikowy,
        mapowanie=silnik.mapowanie,
        liczba_wykryc=silnik.liczba_wykryc,
    )


def anonimizuj_plik(
    sciezka_wejsciowa: Path,
    katalog_wyjsciowy: Path,
    haslo: str,
    kategorie: list[str] | None = None,
    tryb_ai: bool = False,
    usun_numery_stron: bool = False,
    styl: str = "pelny_token",
    jezyki: list[str] | None = None,
) -> dict[str, Path]:
    """Pełny przepływ dla pojedynczego pliku."""
    katalog_wyjsciowy.mkdir(parents=True, exist_ok=True)
    tekst = extractors.wczytaj_tekst(sciezka_wejsciowa)

    wynik = anonimizuj_tekst(
        tekst, kategorie=kategorie, tryb_ai=tryb_ai,
        usun_numery_stron=usun_numery_stron, styl=styl, jezyki=jezyki,
    )

    nazwa_bazowa = sciezka_wejsciowa.stem
    rozszerzenie = sciezka_wejsciowa.suffix
    sciezka_tekst = katalog_wyjsciowy / f"{nazwa_bazowa}_anon{rozszerzenie}"
    sciezka_mapowanie = katalog_wyjsciowy / f"{nazwa_bazowa}_mapowanie.enc"

    extractors.zapisz_w_formacie(sciezka_tekst, wynik.tekst_zanonimizowany)
    zaszyfrowane = crypto.zaszyfruj_mapowanie(wynik.mapowanie, haslo)
    sciezka_mapowanie.write_bytes(zaszyfrowane)

    return {
        "tekst": sciezka_tekst,
        "mapowanie": sciezka_mapowanie,
        "liczba_wykryc": wynik.liczba_wykryc,
        "mapowanie_jawne": wynik.mapowanie,
    }


def anonimizuj_wiele_plikow(
    sciezki: list[Path],
    katalog_wyjsciowy: Path,
    haslo: str,
    tryb: str = "niezalezne",
    kategorie: list[str] | None = None,
    tryb_ai: bool = False,
    usun_numery_stron: bool = False,
    styl: str = "pelny_token",
    jezyki: list[str] | None = None,
) -> dict:
    """
    Przetwarza wiele plików naraz.

    tryb="jedna_sprawa": wspólna numeracja tokenów i jedno wspólne, zaszyfrowane
        mapowanie dla wszystkich plików — ten sam "Jan Kowalski" w trzech
        dokumentach tej samej sprawy dostaje ten sam token wszędzie.
    tryb="niezalezne": każdy plik ma własną, niezależną numerację i własny
        plik mapowania (dokładnie jak przy pojedynczym anonimizuj_plik).
    """
    if tryb not in ("jedna_sprawa", "niezalezne"):
        raise ValueError('tryb musi być "jedna_sprawa" albo "niezalezne"')

    katalog_wyjsciowy.mkdir(parents=True, exist_ok=True)

    if tryb == "niezalezne":
        wyniki_per_plik = {}
        for sciezka in sciezki:
            wyniki_per_plik[sciezka.name] = anonimizuj_plik(
                sciezka, katalog_wyjsciowy, haslo,
                kategorie=kategorie, tryb_ai=tryb_ai,
                usun_numery_stron=usun_numery_stron, styl=styl, jezyki=jezyki,
            )
        return {"tryb": tryb, "pliki": wyniki_per_plik}

    # tryb == "jedna_sprawa": jeden wspólny silnik na wszystkie pliki
    silnik = SilnikAnonimizacji(styl=styl)
    silnik._jezyki = tuple(jezyki or ["pl"])
    sciezki_tekst = {}

    for sciezka in sciezki:
        tekst = extractors.wczytaj_tekst(sciezka)
        if usun_numery_stron:
            tekst = _usun_numery_stron(tekst)
        tekst_wynikowy = silnik.przetworz(tekst, kategorie=kategorie, tryb_ai=tryb_ai)

        sciezka_tekst = katalog_wyjsciowy / f"{sciezka.stem}_anon{sciezka.suffix}"
        extractors.zapisz_w_formacie(sciezka_tekst, tekst_wynikowy)
        sciezki_tekst[sciezka.name] = sciezka_tekst

    sciezka_mapowanie = katalog_wyjsciowy / "sprawa_mapowanie.enc"
    zaszyfrowane = crypto.zaszyfruj_mapowanie(silnik.mapowanie, haslo)
    sciezka_mapowanie.write_bytes(zaszyfrowane)

    return {
        "tryb": tryb,
        "pliki_tekst": sciezki_tekst,
        "mapowanie": sciezka_mapowanie,
        "mapowanie_jawne": silnik.mapowanie,
        "liczba_wykryc": silnik.liczba_wykryc,
    }


def anonimizuj_bip(
    sciezka_wejsciowa: Path,
    katalog_wyjsciowy: Path,
    kategorie: list[str] | None = None,
    tryb_ai: bool = False,
    usun_numery_stron: bool = False,
    jezyki: list[str] | None = None,
) -> Path:
    """
    Tryb Archiwum/BIP: anonimizacja BEZPOWROTNA, przeznaczona do publikacji
    (np. w Biuletynie Informacji Publicznej). W odróżnieniu od standardowego
    przepływu:
      - NIE generuje żadnego hasła ani pliku mapowania — mapowanie żyje
        wyłącznie w pamięci procesu i jest odrzucane po zakończeniu,
      - domyślnie używa stylu "etykieta" (czytelniejsze niż surowe tokeny
        dla odbiorcy publikacji, np. "Osoba A" zamiast "[OSOBA_1]"),
      - spójność w obrębie dokumentu jest zachowana (ta sama osoba = ta sama
        etykieta w całym pliku), ale nie da się jej NIGDZIE odwrócić.

    Zwraca tylko ścieżkę do zanonimizowanego tekstu.
    """
    katalog_wyjsciowy.mkdir(parents=True, exist_ok=True)
    tekst = extractors.wczytaj_tekst(sciezka_wejsciowa)

    wynik = anonimizuj_tekst(
        tekst, kategorie=kategorie, tryb_ai=tryb_ai,
        usun_numery_stron=usun_numery_stron, styl="etykieta", jezyki=jezyki,
    )
    # wynik.mapowanie świadomie NIE jest zapisywane na dysk — to jest cały
    # sens trybu Archiwum/BIP (bezpowrotność, brak klucza do odzyskania).

    sciezka_tekst = katalog_wyjsciowy / f"{sciezka_wejsciowa.stem}_anon_BIP{sciezka_wejsciowa.suffix}"
    extractors.zapisz_w_formacie(sciezka_tekst, wynik.tekst_zanonimizowany)
    return sciezka_tekst
