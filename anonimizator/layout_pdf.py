"""
Anonimizacja PDF z zachowaniem layoutu oryginału (kolumny, tabele, obrazy,
czcionki) — używa mechanizmu redakcji PyMuPDF (fitz), który NAPRAWDĘ usuwa
tekst z warstwy tekstowej PDF (nie tylko wizualnie go zasłania jak
zamalowanie), a w tym samym miejscu może wstawić tekst zastępczy.

Podejście: dla każdej strony wykrywamy PII na jej tekście (przez
SilnikAnonimizacji.wyznacz_zamiany), a następnie dla każdej unikalnej
wykrytej wartości na tej stronie znajdujemy jej współrzędne
(page.search_for) i redagujemy wszystkie jej wystąpienia jednym
przebiegiem (add_redact_annot + apply_redactions per strona).

WAŻNE OGRANICZENIE (świadomie przyjęte na tym etapie): działa tylko dla
stron z realną warstwą tekstową (dokumenty "born-digital" albo już
przepuszczone przez OCR z osadzeniem tekstu). Strony będące czystym
skanem (obraz bez warstwy tekstowej) korzystają z uzupełniającej ścieżki
w layout_images.anonimizuj_strone_skanowana_pdf() — OCR strony renderowanej
jako obraz + redakcja na współrzędnych OCR, ta sama technika co dla
JPG/PNG. Jeśli Tesseract nie jest zainstalowany, taka strona pozostaje
niezredagowana i trafia na listę strony_bez_warstwy_tekstowej.

Ograniczenie techniczne: page.search_for dopasowuje dokładny, literalny
tekst — jeśli PDF ma nietypowe odstępy wewnętrzne (np. z kerningu przy
eksporcie z niektórych programów), dopasowanie pojedynczego fragmentu
może się nie udać. To ten sam mechanizm, na którym opiera się większość
narzędzi do redakcji PDF.
"""

from __future__ import annotations
import re
from pathlib import Path

WZORZEC_NUMERU_STRONY = re.compile(r"^\s*\d{1,4}\s*$")
WZORZEC_STRONA_Z = re.compile(r"^\s*strona\s+\d+\s*(z|/)\s*\d+\s*$", re.IGNORECASE)

SCIEZKA_CZCIONKI = Path(__file__).parent / "czcionki" / "DejaVuSans.ttf"
PROG_PUSTEJ_STRONY = 20  # ten sam prog co w extractors.py


def _jest_numerem_strony(tekst: str) -> bool:
    return bool(WZORZEC_NUMERU_STRONY.match(tekst) or WZORZEC_STRONA_Z.match(tekst))


def anonimizuj_pdf_zachowaj_layout(
    sciezka_wejsciowa: Path, sciezka_wyjsciowa: Path, silnik,
    kategorie: list[str] | None = None, tryb_ai: bool = False,
    usun_numery_stron: bool = False,
) -> list[int]:
    """Anonimizuje PDF w miejscu, zachowując kolumny, obrazy, tabele
    i czcionki — redaguje (usuwa z warstwy tekstowej) wykryte dane
    osobowe bezpośrednio na oryginalnych stronach.

    Zwraca listę numerów stron (0-indeksowanych), które wyglądają na
    skan bez warstwy tekstowej I nie udało się ich zredagować (Tesseract
    niedostępny albo błąd OCR) — te strony wymagają ręcznej weryfikacji."""
    import fitz
    dokument = fitz.open(str(sciezka_wejsciowa))
    strony_bez_warstwy_tekstowej = []

    for numer_strony, strona in enumerate(dokument):
        tekst_strony = strona.get_text()
        if len(tekst_strony.strip()) < PROG_PUSTEJ_STRONY:
            zredagowano = False
            try:
                from . import extractors
                if extractors._tesseract_dostepny():
                    from . import layout_images
                    zredagowano = layout_images.anonimizuj_strone_skanowana_pdf(
                        strona, silnik, kategorie=kategorie, tryb_ai=tryb_ai,
                    )
            except Exception:
                zredagowano = False
            if not zredagowano:
                strony_bez_warstwy_tekstowej.append(numer_strony)
            continue

        cokolwiek_do_redakcji = False

        if usun_numery_stron:
            for linia in tekst_strony.split("\n"):
                if linia.strip() and _jest_numerem_strony(linia):
                    for prostokat in strona.search_for(linia.strip()):
                        strona.add_redact_annot(prostokat, text="", fill=(1, 1, 1))
                        cokolwiek_do_redakcji = True

        zamiany = silnik.wyznacz_zamiany(tekst_strony, kategorie=kategorie, tryb_ai=tryb_ai)
        wartosci_zredagowane = set()
        for z in zamiany:
            if z.oryginal in wartosci_zredagowane:
                continue
            wartosci_zredagowane.add(z.oryginal)
            for prostokat in strona.search_for(z.oryginal):
                strona.add_redact_annot(prostokat, text=z.placeholder, fill=(1, 1, 1))
                cokolwiek_do_redakcji = True

        if cokolwiek_do_redakcji:
            strona.apply_redactions()

    dokument.save(str(sciezka_wyjsciowa))
    dokument.close()
    return strony_bez_warstwy_tekstowej


def wstaw_prompt_do_pdf(sciezka: Path, prompt_tekst: str) -> None:
    """Dopisuje prompt dla AI jako nową, pierwszą stronę istniejącego
    pliku PDF (już zapisanego przez anonimizuj_pdf_zachowaj_layout).
    Osadza DejaVu Sans (ta sama czcionka co w raport.py/extractors.py),
    bo domyślne czcionki bazowe PDF nie mają polskich znaków."""
    if not prompt_tekst:
        return
    import fitz
    dokument = fitz.open(str(sciezka))
    strona = dokument.new_page(pno=0, width=595, height=842)  # A4 w punktach
    strona.insert_font(fontname="DejaVu", fontfile=str(SCIEZKA_CZCIONKI))
    strona.insert_textbox(
        fitz.Rect(56, 56, 595 - 56, 842 - 56),
        prompt_tekst,
        fontsize=10.5, fontname="DejaVu",
    )
    tymczasowa = sciezka.with_suffix(".tmp.pdf")
    dokument.save(str(tymczasowa))
    dokument.close()
    tymczasowa.replace(sciezka)
