"""
Anonimizacja DOCX z zachowaniem layoutu oryginału (formatowanie, tabele,
obrazy, nagłówki/stopki) — w przeciwieństwie do extractors.zapisz_docx(),
która buduje zupełnie nowy dokument z gołego tekstu.

Podejście: zamiast "wyciągnij cały tekst -> zbuduj nowy dokument", edytujemy
oryginalny dokument w miejscu. Każdy akapit ma listę "runów" (fragmentów
tekstu ze wspólnym formatowaniem) — budujemy płaski tekst akapitu, wykrywamy
w nim PII przez SilnikAnonimizacji.wyznacz_zamiany(), po czym aplikujemy
podmiany z powrotem na runy, modyfikując tylko ich tekst (formatowanie runu
jako obiektu zostaje nietknięte — pogrubienia, kolory, style, czcionka).
Obrazy, tabele (poza samym tekstem w komórkach), nagłówki/stopki i podział
na strony nie są w ogóle ruszane, więc zostają dokładnie takie jak
w oryginale.

Podmiana rozciągająca się na kilka runów o różnym formatowaniu ląduje
w całości w pierwszym z nich — pozostałe runy tracą tylko nachodzącą
część tekstu, zachowując swoje formatowanie dla części nienachodzącej.

Znane ograniczenie: python-docx nie zawsze eksponuje runy wewnątrz
hiperłączy (element w:hyperlink) przez paragraph.runs — PII w samym
tekście hiperłącza może nie zostać wykryte. Rzadki przypadek w praktyce
dokumentów prawniczych.
"""

from __future__ import annotations
import re
from pathlib import Path

WZORZEC_NUMERU_STRONY = re.compile(r"^\s*\d{1,4}\s*$")
WZORZEC_STRONA_Z = re.compile(r"^\s*strona\s+\d+\s*(z|/)\s*\d+\s*$", re.IGNORECASE)


def _jest_numerem_strony(tekst: str) -> bool:
    return bool(WZORZEC_NUMERU_STRONY.match(tekst) or WZORZEC_STRONA_Z.match(tekst))


def _zastosuj_zamiany_na_runach(runy, zamiany: list) -> None:
    """Aplikuje listę Zamiana na runach akapitu, modyfikując run.text
    w miejscu (formatowanie runu jako obiektu zostaje niezmienione).
    Podmiana nachodząca na kilka runów ląduje w pierwszym z nich, z
    pozostałych runów usuwana jest tylko nachodząca część tekstu.
    Przetwarzanie od końca akapitu — wcześniejsze (dalsze) podmiany nie
    przesuwają pozycji tych, które jeszcze czekają na aplikację."""
    granice = []
    pozycja = 0
    for r in runy:
        dlugosc = len(r.text)
        granice.append((pozycja, pozycja + dlugosc, r))
        pozycja += dlugosc

    for z in sorted(zamiany, key=lambda z: z.start, reverse=True):
        pierwszy = True
        for start_r, end_r, run in granice:
            if end_r <= z.start or start_r >= z.end:
                continue
            lokalny_start = max(z.start, start_r) - start_r
            lokalny_end = min(z.end, end_r) - start_r
            if pierwszy:
                run.text = run.text[:lokalny_start] + z.placeholder + run.text[lokalny_end:]
                pierwszy = False
            else:
                run.text = run.text[:lokalny_start] + run.text[lokalny_end:]


def _anonimizuj_akapit(akapit, silnik, kategorie, tryb_ai, usun_numery_stron) -> None:
    runy = akapit.runs
    if not runy:
        return
    pelny_tekst = "".join(r.text for r in runy)
    if not pelny_tekst.strip():
        return

    if usun_numery_stron and _jest_numerem_strony(pelny_tekst):
        for r in runy:
            r.text = ""
        return

    zamiany = silnik.wyznacz_zamiany(pelny_tekst, kategorie=kategorie, tryb_ai=tryb_ai)
    if zamiany:
        _zastosuj_zamiany_na_runach(runy, zamiany)


def _anonimizuj_tabele(tabela, silnik, kategorie, tryb_ai, usun_numery_stron) -> None:
    for wiersz in tabela.rows:
        for komorka in wiersz.cells:
            for akapit in komorka.paragraphs:
                _anonimizuj_akapit(akapit, silnik, kategorie, tryb_ai, usun_numery_stron)
            for zagniezdzona in komorka.tables:
                _anonimizuj_tabele(zagniezdzona, silnik, kategorie, tryb_ai, usun_numery_stron)


def anonimizuj_docx_zachowaj_layout(
    sciezka_wejsciowa: Path, sciezka_wyjsciowa: Path, silnik,
    kategorie: list[str] | None = None, tryb_ai: bool = False,
    usun_numery_stron: bool = False,
) -> None:
    """Anonimizuje DOCX w miejscu, zachowując formatowanie, tabele, obrazy,
    nagłówki i stopki. Wymaga instancji SilnikAnonimizacji (współdzieli
    mapowanie/liczniki tokenów z resztą przetwarzania, np. w trybie
    wsadowym "jedna sprawa" — ta sama instancja przekazywana kolejno dla
    wielu plików)."""
    import docx
    dokument = docx.Document(str(sciezka_wejsciowa))

    for akapit in dokument.paragraphs:
        _anonimizuj_akapit(akapit, silnik, kategorie, tryb_ai, usun_numery_stron)

    for tabela in dokument.tables:
        _anonimizuj_tabele(tabela, silnik, kategorie, tryb_ai, usun_numery_stron)

    for sekcja in dokument.sections:
        for akapit in sekcja.header.paragraphs:
            _anonimizuj_akapit(akapit, silnik, kategorie, tryb_ai, usun_numery_stron)
        for akapit in sekcja.footer.paragraphs:
            _anonimizuj_akapit(akapit, silnik, kategorie, tryb_ai, usun_numery_stron)

    dokument.save(str(sciezka_wyjsciowa))


def wstaw_prompt_do_docx(sciezka: Path, prompt_tekst: str) -> None:
    """Dopisuje prompt dla AI jako nowe akapity na początku istniejącego
    pliku DOCX (już zapisanego przez anonimizuj_docx_zachowaj_layout).
    Osobny krok, bo pełne mapowanie (potrzebne do zbudowania promptu)
    jest znane dopiero po przetworzeniu całego dokumentu."""
    if not prompt_tekst:
        return
    import docx
    dokument = docx.Document(str(sciezka))
    linie = prompt_tekst.split("\n")
    if dokument.paragraphs:
        pierwszy = dokument.paragraphs[0]
        for linia in linie:
            pierwszy.insert_paragraph_before(linia)
    else:
        for linia in linie:
            dokument.add_paragraph(linia)
    dokument.save(str(sciezka))
