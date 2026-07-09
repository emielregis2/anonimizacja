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

# Znacznik kończący automatycznie dołączany prompt dla AI (patrz zbuduj_prompt_ai
# poniżej). Jest jednocześnie czytelny dla człowieka (wygląda jak naturalne
# zdanie zamykające instrukcję) i wystarczająco charakterystyczny, by
# deanonimizator.py mógł po nim rozpoznać i usunąć cały blok promptu przed
# przywróceniem oryginalnej treści — tak, by odtworzony dokument nie zawierał
# już tego dopisku.
GRANICA_PROMPTU_AI = "[--- KONIEC PROMPTU DLA AI — PONIŻEJ WŁAŚCIWA TREŚĆ DOKUMENTU ---]"


def zbuduj_prompt_ai(mapowanie: dict[str, str]) -> str:
    """Buduje prompt instruujący model AI, by zachował placeholdery dokładnie
    tak, jak występują w konkretnym dokumencie — niezależnie od wybranego
    stylu maskowania (pełny token, etykieta czy inicjały). Lista placeholderów
    pochodzi z faktycznego mapowania, więc zawsze pasuje do treści, zamiast
    zakładać jeden sztywny format (np. tylko nawiasy kwadratowe)."""
    if not mapowanie:
        return ""
    tokeny = sorted(mapowanie.keys())
    lista = ", ".join(tokeny)
    return (
        "Poniższy tekst został zanonimizowany. Pracując z nim, zachowaj dokładnie "
        "poniższe oznaczenia zastępcze — nie zmieniaj ich pisowni ani formy, nie "
        "zamieniaj ich na opisy typu „powódka”, „klient”, „strona” ani na inicjały, "
        "i nie wymyślaj nowych oznaczeń. Każde z poniższych oznaczeń w całym "
        "dokumencie odnosi się zawsze do tego samego, konkretnego podmiotu:\n\n"
        f"{lista}\n\n"
        f"{GRANICA_PROMPTU_AI}\n\n"
    )


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


@dataclass
class Zamiana:
    """Pojedyncza podmiana: pozycja w tekście źródłowym + oryginalna
    wartość + przypisany placeholder. Używane zarówno przez przetworz()
    (składanie zwykłego tekstu) jak i przez writery zachowujące layout
    (DOCX/PDF/obraz w extractors.py), które aplikują te same podmiany
    bezpośrednio na strukturze oryginalnego dokumentu zamiast budować
    go od nowa z gołego tekstu."""
    start: int
    end: int
    oryginal: str
    placeholder: str


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

    def wyznacz_zamiany(self, tekst: str, kategorie: list[str] | None = None,
                         tryb_ai: bool = False) -> list[Zamiana]:
        """Wykrywa PII i przypisuje placeholdery — dokładnie ta sama logika
        co przetworz(), ale zwraca listę Zamiana zamiast składać gotowy
        string. Dzięki temu writery zachowujące layout oryginału (DOCX/PDF/
        obraz) mogą aplikować te same, spójnie ponumerowane podmiany
        bezpośrednio na strukturze dokumentu (np. per akapit/run w DOCX,
        per strona w PDF), zamiast operować na jednym płaskim tekście
        całego dokumentu na raz — przetworz() nadal woła tę metodę wewnątrz,
        więc zachowanie dla zwykłego tekstu jest identyczne jak wcześniej."""
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

        zamiany: list[Zamiana] = []
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
            zamiany.append(Zamiana(m.start, m.end, m.text, placeholder))
        return zamiany

    def przetworz(self, tekst: str, kategorie: list[str] | None = None,
                   tryb_ai: bool = False) -> str:
        zamiany = self.wyznacz_zamiany(tekst, kategorie=kategorie, tryb_ai=tryb_ai)
        fragmenty = []
        ostatnia_pozycja = 0
        for z in zamiany:
            fragmenty.append(tekst[ostatnia_pozycja:z.start])
            fragmenty.append(z.placeholder)
            ostatnia_pozycja = z.end
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
    dolacz_prompt_ai: bool = True,
    zachowaj_layout: bool = True,
) -> dict[str, Path]:
    """Pełny przepływ dla pojedynczego pliku.

    dolacz_prompt_ai: gdy True (domyślnie) i mapowanie jest odwracalne
    (styl != "puste"), na początku zapisanego pliku doklejany jest prompt
    instruujący model AI, by zachował placeholdery bez zmian. Dzięki temu
    plik wynikowy jest od razu samowystarczalny — przydatne przy masowym,
    zautomatyzowanym przetwarzaniu całych serii dokumentów, bo każdy plik
    "niesie" swój własny prompt bez ręcznego dopisywania.

    zachowaj_layout: gdy True (domyślnie) i format wejściowy to DOCX lub
    PDF, dokument jest edytowany w miejscu (formatowanie, tabele, obrazy,
    nagłówki/stopki dla DOCX; kolumny, tabele, obrazy, czcionki dla PDF —
    prawdziwa redakcja przez PyMuPDF, nie tylko wizualne zasłonięcie)
    zamiast budowany od nowa z gołego tekstu. Ustaw False, by wymusić
    stary tryb "wyciągnij tekst -> zbuduj nowy dokument" (np. do
    porównania albo jeśli plik sprawia problemy). Dla PDF: strony bez
    warstwy tekstowej (czyste skany) nie są tą ścieżką redagowane —
    sprawdź pole "strony_bez_warstwy_tekstowej" w zwróconym słowniku."""
    katalog_wyjsciowy.mkdir(parents=True, exist_ok=True)
    nazwa_bazowa = sciezka_wejsciowa.stem
    rozszerzenie = sciezka_wejsciowa.suffix
    sciezka_tekst = katalog_wyjsciowy / f"{nazwa_bazowa}_anon{rozszerzenie}"
    sciezka_mapowanie = katalog_wyjsciowy / f"{nazwa_bazowa}_mapowanie.enc"

    if zachowaj_layout and rozszerzenie.lower() == ".docx":
        from . import layout_docx
        silnik = SilnikAnonimizacji(styl=styl)
        silnik._jezyki = tuple(jezyki or ["pl"])
        layout_docx.anonimizuj_docx_zachowaj_layout(
            sciezka_wejsciowa, sciezka_tekst, silnik,
            kategorie=kategorie, tryb_ai=tryb_ai,
            usun_numery_stron=usun_numery_stron,
        )
        prompt_dolaczony = ""
        if dolacz_prompt_ai and styl != "puste" and silnik.mapowanie:
            prompt_dolaczony = zbuduj_prompt_ai(silnik.mapowanie)
            layout_docx.wstaw_prompt_do_docx(sciezka_tekst, prompt_dolaczony)
        zaszyfrowane = crypto.zaszyfruj_mapowanie(silnik.mapowanie, haslo)
        sciezka_mapowanie.write_bytes(zaszyfrowane)
        return {
            "tekst": sciezka_tekst,
            "mapowanie": sciezka_mapowanie,
            "liczba_wykryc": silnik.liczba_wykryc,
            "mapowanie_jawne": silnik.mapowanie,
            # Płaski tekst wynikowy do podglądu/kopiowania w interfejsie —
            # sam plik DOCX ma zachowane formatowanie, to tylko pomocnicza
            # reprezentacja tekstowa tego, co w nim jest.
            "tekst_zanonimizowany": prompt_dolaczony + extractors.wczytaj_tekst(sciezka_tekst),
            "prompt_ai": prompt_dolaczony,
        }

    if zachowaj_layout and rozszerzenie.lower() == ".pdf":
        from . import layout_pdf
        silnik = SilnikAnonimizacji(styl=styl)
        silnik._jezyki = tuple(jezyki or ["pl"])
        strony_bez_tekstu = layout_pdf.anonimizuj_pdf_zachowaj_layout(
            sciezka_wejsciowa, sciezka_tekst, silnik,
            kategorie=kategorie, tryb_ai=tryb_ai,
            usun_numery_stron=usun_numery_stron,
        )
        prompt_dolaczony = ""
        if dolacz_prompt_ai and styl != "puste" and silnik.mapowanie:
            prompt_dolaczony = zbuduj_prompt_ai(silnik.mapowanie)
            layout_pdf.wstaw_prompt_do_pdf(sciezka_tekst, prompt_dolaczony)
        zaszyfrowane = crypto.zaszyfruj_mapowanie(silnik.mapowanie, haslo)
        sciezka_mapowanie.write_bytes(zaszyfrowane)
        wynik_slownik = {
            "tekst": sciezka_tekst,
            "mapowanie": sciezka_mapowanie,
            "liczba_wykryc": silnik.liczba_wykryc,
            "mapowanie_jawne": silnik.mapowanie,
            "tekst_zanonimizowany": prompt_dolaczony + extractors.wczytaj_tekst(sciezka_tekst),
            "prompt_ai": prompt_dolaczony,
        }
        if strony_bez_tekstu:
            # Strony bez warstwy tekstowej (skany) NIE zostały zredagowane
            # tą ścieżką — patrz ograniczenie w layout_pdf.py. Zwracamy tę
            # informację, żeby dało się ją pokazać użytkownikowi zamiast
            # milcząco zwrócić dokument z niezredagowanymi stronami.
            wynik_slownik["strony_bez_warstwy_tekstowej"] = strony_bez_tekstu
        return wynik_slownik

    tekst = extractors.wczytaj_tekst(sciezka_wejsciowa)

    wynik = anonimizuj_tekst(
        tekst, kategorie=kategorie, tryb_ai=tryb_ai,
        usun_numery_stron=usun_numery_stron, styl=styl, jezyki=jezyki,
    )

    prompt_dolaczony = ""
    if dolacz_prompt_ai and styl != "puste" and wynik.mapowanie:
        prompt_dolaczony = zbuduj_prompt_ai(wynik.mapowanie)
    tekst_do_zapisu = prompt_dolaczony + wynik.tekst_zanonimizowany

    extractors.zapisz_w_formacie(sciezka_tekst, tekst_do_zapisu)
    zaszyfrowane = crypto.zaszyfruj_mapowanie(wynik.mapowanie, haslo)
    sciezka_mapowanie.write_bytes(zaszyfrowane)

    return {
        "tekst": sciezka_tekst,
        "mapowanie": sciezka_mapowanie,
        "liczba_wykryc": wynik.liczba_wykryc,
        "mapowanie_jawne": wynik.mapowanie,
        "tekst_zanonimizowany": tekst_do_zapisu,
        "prompt_ai": prompt_dolaczony,
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
    dolacz_prompt_ai: bool = True,
    zachowaj_layout: bool = True,
) -> dict:
    """
    Przetwarza wiele plików naraz.

    tryb="jedna_sprawa": wspólna numeracja tokenów i jedno wspólne, zaszyfrowane
        mapowanie dla wszystkich plików — ten sam "Jan Kowalski" w trzech
        dokumentach tej samej sprawy dostaje ten sam token wszędzie.
        UWAGA: ten tryb NIE wspiera jeszcze zachowaj_layout — zawsze używa
        starej ścieżki "wyciągnij tekst -> zbuduj dokument od nowa", nawet
        dla DOCX/PDF. Wymagałoby to współdzielenia stanu silnika (spójna
        numeracja) razem z edycją w miejscu per plik — nie zaimplementowane.
    tryb="niezalezne": każdy plik ma własną, niezależną numerację i własny
        plik mapowania (dokładnie jak przy pojedynczym anonimizuj_plik) —
        w pełni wspiera zachowaj_layout, bo każdy plik przechodzi osobno
        przez anonimizuj_plik().

    dolacz_prompt_ai: patrz anonimizuj_plik. W trybie "jedna_sprawa" każdy
        plik dostaje prompt zawierający tylko te tokeny, które faktycznie
        w nim występują (nie całą, wspólną listę tokenów całej sprawy) —
        żeby prompt dołączony do konkretnego pisma miał sens w oderwaniu
        od pozostałych dokumentów sprawy.
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
                dolacz_prompt_ai=dolacz_prompt_ai, zachowaj_layout=zachowaj_layout,
            )
        return {"tryb": tryb, "pliki": wyniki_per_plik}


    # tryb == "jedna_sprawa": jeden wspólny silnik na wszystkie pliki
    silnik = SilnikAnonimizacji(styl=styl)
    silnik._jezyki = tuple(jezyki or ["pl"])
    sciezki_tekst = {}
    teksty_zanonimizowane = {}

    for sciezka in sciezki:
        tekst = extractors.wczytaj_tekst(sciezka)
        if usun_numery_stron:
            tekst = _usun_numery_stron(tekst)
        tekst_wynikowy = silnik.przetworz(tekst, kategorie=kategorie, tryb_ai=tryb_ai)

        tekst_do_zapisu = tekst_wynikowy
        if dolacz_prompt_ai and styl != "puste":
            tokeny_w_tym_pliku = {
                k: v for k, v in silnik.mapowanie.items() if k in tekst_wynikowy
            }
            if tokeny_w_tym_pliku:
                tekst_do_zapisu = zbuduj_prompt_ai(tokeny_w_tym_pliku) + tekst_wynikowy

        sciezka_tekst = katalog_wyjsciowy / f"{sciezka.stem}_anon{sciezka.suffix}"
        extractors.zapisz_w_formacie(sciezka_tekst, tekst_do_zapisu)
        sciezki_tekst[sciezka.name] = sciezka_tekst
        teksty_zanonimizowane[sciezka.name] = tekst_do_zapisu

    sciezka_mapowanie = katalog_wyjsciowy / "sprawa_mapowanie.enc"
    zaszyfrowane = crypto.zaszyfruj_mapowanie(silnik.mapowanie, haslo)
    sciezka_mapowanie.write_bytes(zaszyfrowane)

    return {
        "tryb": tryb,
        "pliki_tekst": sciezki_tekst,
        "mapowanie": sciezka_mapowanie,
        "mapowanie_jawne": silnik.mapowanie,
        "liczba_wykryc": silnik.liczba_wykryc,
        "teksty_zanonimizowane": teksty_zanonimizowane,
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
