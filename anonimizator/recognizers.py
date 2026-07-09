"""
Rozpoznawacze (recognizery) poszczególnych kategorii danych wrażliwych.

Każdy recognizer to funkcja o sygnaturze: (text: str) -> list[Match]
gdzie Match = (start, end, dopasowany_tekst).

Architektura wzorowana na Microsoft Presidio: każda kategoria to osobny,
niezależnie testowalny recognizer, który można włączać/wyłączać pojedynczo
(dokładnie jak checkboxy w interfejsie, który miałeś na screenie).
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class Match:
    start: int
    end: int
    text: str
    category: str

    @property
    def end_exclusive(self) -> int:
        return self.end


# ---------------------------------------------------------------------------
# Funkcje walidujące sumy kontrolne (ograniczają liczbę false positives)
# ---------------------------------------------------------------------------

def _valid_pesel(pesel: str) -> bool:
    if not re.fullmatch(r"\d{11}", pesel):
        return False
    wagi = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    suma = sum(int(pesel[i]) * wagi[i] for i in range(10))
    kontrolna = (10 - (suma % 10)) % 10
    return kontrolna == int(pesel[10])


def _valid_nip(nip: str) -> bool:
    cyfry = re.sub(r"[\s-]", "", nip)
    if not re.fullmatch(r"\d{10}", cyfry):
        return False
    wagi = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    suma = sum(int(cyfry[i]) * wagi[i] for i in range(9))
    return suma % 11 == int(cyfry[9])


def _valid_regon(regon: str) -> bool:
    cyfry = re.sub(r"[\s-]", "", regon)
    if len(cyfry) == 9:
        wagi = [8, 9, 2, 3, 4, 5, 6, 7]
        suma = sum(int(cyfry[i]) * wagi[i] for i in range(8))
        kontrolna = suma % 11
        kontrolna = 0 if kontrolna == 10 else kontrolna
        return kontrolna == int(cyfry[8])
    if len(cyfry) == 14:
        wagi = [2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8]
        suma = sum(int(cyfry[i]) * wagi[i] for i in range(13))
        kontrolna = suma % 11
        kontrolna = 0 if kontrolna == 10 else kontrolna
        return kontrolna == int(cyfry[13])
    return False


def _valid_iban(iban: str) -> bool:
    iban = re.sub(r"[\s-]", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    przestawiony = iban[4:] + iban[:4]
    liczba = "".join(str(int(ch, 36)) for ch in przestawiony)
    return int(liczba) % 97 == 1


def _valid_dowod_osobisty(numer: str) -> bool:
    """Norma ICAO 9303 — obowiązkowa dla dowodów wydawanych w Polsce od
    2001 r. Format: 3 litery (seria) + 6 cyfr, gdzie pierwsza cyfra to
    cyfra kontrolna. Litery -> wartości 10-35 (A=10 ... Z=35), wagi cykliczne
    7-3-1 nakładane na 3 litery + pozostałe 5 cyfr (cyfra kontrolna sama w
    sobie jest pomijana w sumowaniu, bo to ją właśnie weryfikujemy).
    Zweryfikowano na 3 niezależnych przykładach z różnych źródeł."""
    numer = re.sub(r"\s", "", numer).upper()
    if not re.fullmatch(r"[A-Z]{3}\d{6}", numer):
        return False
    wartosci = [ord(znak) - ord("A") + 10 for znak in numer[:3]] + [int(c) for c in numer[3:]]
    cyfra_kontrolna = wartosci[3]
    pozostale = wartosci[:3] + wartosci[4:]
    wagi = [7, 3, 1, 7, 3, 1, 7, 3]
    suma = sum(w * v for w, v in zip(wagi, pozostale))
    return suma % 10 == cyfra_kontrolna


# ---------------------------------------------------------------------------
# Generyczny builder recognizera regex + opcjonalna walidacja
# ---------------------------------------------------------------------------

def _make_regex_recognizer(pattern: str, category: str,
                            validate: Callable[[str], bool] | None = None,
                            flags=re.IGNORECASE):
    compiled = re.compile(pattern, flags)

    def recognizer(text: str) -> list[Match]:
        wyniki = []
        for m in compiled.finditer(text):
            fragment = m.group(0)
            if validate is None or validate(fragment):
                wyniki.append(Match(m.start(), m.end(), fragment, category))
        return wyniki

    return recognizer


# ---------------------------------------------------------------------------
# Recognizery deterministyczne (regex + suma kontrolna) — wysoka precyzja
# ---------------------------------------------------------------------------

recognize_pesel = _make_regex_recognizer(r"\b\d{11}\b", "pesel", _valid_pesel)

recognize_nip = _make_regex_recognizer(
    r"\b\d{3}[-\s]?\d{2,3}[-\s]?\d{2}[-\s]?\d{2,3}\b", "nip", _valid_nip
)

recognize_regon = _make_regex_recognizer(
    r"\b\d{9}(\d{5})?\b", "regon", _valid_regon
)

recognize_iban = _make_regex_recognizer(
    r"\b(PL\s?)?\d{2}(\s?\d{4}){6}\b", "iban", _valid_iban
)

recognize_email = _make_regex_recognizer(
    r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", "email"
)

recognize_www = _make_regex_recognizer(
    r"\b(https?://|www\.)[^\s,)]+", "adresy_www"
)

recognize_ip = _make_regex_recognizer(
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:[a-f0-9]{1,4}:){7}[a-f0-9]{1,4}\b", "adresy_ip"
)

recognize_kod_pocztowy = _make_regex_recognizer(
    r"\b\d{2}-\d{3}\b", "kody_pocztowe"
)

recognize_telefon = _make_regex_recognizer(
    r"(?<!\d)(\+48[\s-]?)?(\d{3}[\s-]\d{3}[\s-]\d{3}|\d{9})(?!\d)", "telefony"
)

recognize_vin = _make_regex_recognizer(
    r"\b(?=[A-HJ-NPR-Z0-9]{17}\b)(?=.*[A-HJ-NPR-Z])(?=.*\d)[A-HJ-NPR-Z0-9]{17}\b",
    "vin", flags=0
)

recognize_tablica_rej = _make_regex_recognizer(
    r"\b[A-Z]{2,3}\s?[A-Z0-9]{4,5}\b", "tablice_rejestracyjne", flags=0
)

recognize_paszport = _make_regex_recognizer(
    r"\b[A-Z]{2}\d{7}\b", "paszporty", flags=0
)

recognize_dowod_osobisty = _make_regex_recognizer(
    r"\b[A-Z]{3}\d{6}\b", "numery_dokumentow", _valid_dowod_osobisty, flags=0
)

recognize_krs = _make_regex_recognizer(
    r"\bKRS[\s:]?\d{10}\b|\b0{3}\d{7}\b", "krs"
)

recognize_kw = _make_regex_recognizer(
    r"\b[A-Z]{2}\d[A-Z]/\d{8}/\d\b", "kw", flags=0
)

recognize_sygnatura_akt = _make_regex_recognizer(
    r"\b[IVX]{1,4}\s?[A-Z]{1,3}\s?\d{1,5}/\d{2,4}\b", "sygnatury_akt", flags=0
)

recognize_dzialka = _make_regex_recognizer(
    r"\b(dzia[łl]k[a-zęó]*\s+(nr\.?|numer)?\s*)(\d{1,5}(/\d{1,4})?)\b",
    "numery_dzialek"
)

recognize_e_doreczenia = _make_regex_recognizer(
    r"\bAE:PL-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{2}\b", "e_doreczenia", flags=0
)

recognize_pwz = _make_regex_recognizer(
    r"\bPWZ[\s:]?\d{7}\b", "identyfikatory_medyczne"
)

recognize_konto_social = _make_regex_recognizer(
    r"(?<!\w)@[A-Za-z0-9_.]{3,30}\b|\b(facebook|instagram|twitter|x|linkedin|tiktok)\.com/[A-Za-z0-9_.\-/]+",
    "konta_social"
)

recognize_prawo_jazdy = _make_regex_recognizer(
    r"\bprawo jazdy\s+(nr\.?|numer)?\s*[:\-]?\s*([A-Z0-9]{5,15})\b", "prawo_jazdy"
)

recognize_sygnatura_adm = _make_regex_recognizer(
    r"\b(sygn\.?\s?akt|nr\s?sprawy|znak\s?sprawy)[\s:]+([A-Za-z0-9./\-]{4,20})\b",
    "sygnatury_adm"
)

recognize_adres_pocztowy = _make_regex_recognizer(
    r"\b(ul\.|al\.|pl\.|os\.)\s?[A-ZŁŚŻŹĆŃÓĄĘ][\wąćęłńóśźż.\-]*(\s[A-ZŁŚŻŹĆŃÓĄĘ0-9][\wąćęłńóśźż.\-]*)*\s+\d{1,4}[A-Za-z]?(/\d+)?\b",
    "adresy_pocztowe"
)

# ---------------------------------------------------------------------------
# Recognizery słownikowe / heurystyczne — wymagają danych referencyjnych
# (patrz slowniki.py); niższa precyzja bez modelu NER (spaCy)
# ---------------------------------------------------------------------------

DETERMINISTIC_RECOGNIZERS: dict[str, Callable[[str], list[Match]]] = {
    "pesel": recognize_pesel,
    "nip": recognize_nip,
    "regon": recognize_regon,
    "iban": recognize_iban,
    "email": recognize_email,
    "adresy_www": recognize_www,
    "adresy_ip": recognize_ip,
    "kody_pocztowe": recognize_kod_pocztowy,
    "telefony": recognize_telefon,
    "vin": recognize_vin,
    "tablice_rejestracyjne": recognize_tablica_rej,
    "paszporty": recognize_paszport,
    "numery_dokumentow": recognize_dowod_osobisty,
    "krs": recognize_krs,
    "kw": recognize_kw,
    "sygnatury_akt": recognize_sygnatura_akt,
    "numery_dzialek": recognize_dzialka,
    "e_doreczenia": recognize_e_doreczenia,
    "identyfikatory_medyczne": recognize_pwz,
    "konta_social": recognize_konto_social,
    "prawo_jazdy": recognize_prawo_jazdy,
    "sygnatury_adm": recognize_sygnatura_adm,
    "adresy_pocztowe": recognize_adres_pocztowy,
}
