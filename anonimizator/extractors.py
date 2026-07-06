"""
Odczyt tekstu z obsługiwanych formatów (TXT, DOCX, ODT, RTF, PDF, JPG, PNG)
oraz zapis wyniku anonimizacji.

OCR (rozpoznawanie tekstu ze skanów/obrazów) — działa lokalnie przez
Tesseract, bez wysyłania czegokolwiek na zewnątrz:
  - dla PDF: jeśli strona nie ma warstwy tekstowej (skan), automatycznie
    renderujemy ją jako obraz i uruchamiamy OCR na tej stronie,
  - dla JPG/PNG: całość obrazu przechodzi przez OCR.

Wymaga zainstalowanego Tesseract z polskim pakietem językowym:
  Linux:   sudo apt-get install tesseract-ocr tesseract-ocr-pol poppler-utils
  Windows: instalator z https://github.com/UB-Mannheim/tesseract/wiki
           (zaznaczyć język polski przy instalacji)

Ograniczenie świadomie przyjęte na tym etapie: dla DOCX odtwarzamy
strukturę akapitów (podmiana tekstu w miejscu). Dla PDF/RTF/ODT
ekstrahujemy czysty tekst — pełne odtworzenie oryginalnego layoutu
(kolumny, obrazy, tabele) to osobne, większe zadanie.
"""

from __future__ import annotations
from pathlib import Path

FORMATY_WSPIERANE = {".txt", ".docx", ".odt", ".rtf", ".pdf", ".jpg", ".jpeg", ".png"}

# Próg: jeśli strona PDF ma mniej niż tyle znaków tekstu, traktujemy ją
# jako prawdopodobny skan i próbujemy OCR zamiast/obok warstwy tekstowej.
PROG_PUSTEJ_STRONY = 20


def _tesseract_dostepny() -> bool:
    import shutil
    return shutil.which("tesseract") is not None


def wczytaj_tekst(sciezka: Path, uzyj_ocr: bool = True) -> str:
    rozszerzenie = sciezka.suffix.lower()
    if rozszerzenie == ".txt":
        return sciezka.read_text(encoding="utf-8", errors="replace")
    if rozszerzenie == ".docx":
        return _wczytaj_docx(sciezka)
    if rozszerzenie == ".odt":
        return _wczytaj_odt(sciezka)
    if rozszerzenie == ".rtf":
        return _wczytaj_rtf(sciezka)
    if rozszerzenie == ".pdf":
        return _wczytaj_pdf(sciezka, uzyj_ocr=uzyj_ocr)
    if rozszerzenie in (".jpg", ".jpeg", ".png"):
        return _wczytaj_obraz(sciezka, uzyj_ocr=uzyj_ocr)
    raise ValueError(
        f"Nieobsługiwany format: {rozszerzenie}. Obsługiwane: {sorted(FORMATY_WSPIERANE)}"
    )


def _wczytaj_docx(sciezka: Path) -> str:
    import docx
    dokument = docx.Document(str(sciezka))
    return "\n".join(akapit.text for akapit in dokument.paragraphs)


def _wczytaj_odt(sciezka: Path) -> str:
    from odf.opendocument import load
    from odf import text as odf_text
    from odf.element import Text as OdfTextNode

    dokument = load(str(sciezka))
    linie = []
    for akapit in dokument.getElementsByType(odf_text.P):
        fragmenty = []
        for node in akapit.childNodes:
            if isinstance(node, OdfTextNode):
                fragmenty.append(str(node))
            elif node.nodeType == node.ELEMENT_NODE:
                fragmenty.append("".join(
                    str(n) for n in node.childNodes if isinstance(n, OdfTextNode)
                ))
        linie.append("".join(fragmenty))
    return "\n".join(linie)


def _wczytaj_rtf(sciezka: Path) -> str:
    from striprtf.striprtf import rtf_to_text
    surowy = sciezka.read_text(encoding="utf-8", errors="replace")
    return rtf_to_text(surowy)


def _ocr_obraz_pil(obraz) -> str:
    import pytesseract
    return pytesseract.image_to_string(obraz, lang="pol+eng")


def _wczytaj_obraz(sciezka: Path, uzyj_ocr: bool = True) -> str:
    if not uzyj_ocr:
        return ""
    if not _tesseract_dostepny():
        raise RuntimeError(
            "Tesseract nie jest zainstalowany — OCR niedostępny. "
            "Zainstaluj: sudo apt-get install tesseract-ocr tesseract-ocr-pol "
            "(Linux) albo instalator Tesseract dla Windows z pakietem języka polskiego."
        )
    from PIL import Image
    obraz = Image.open(sciezka)
    return _ocr_obraz_pil(obraz)


def _wczytaj_pdf(sciezka: Path, uzyj_ocr: bool = True) -> str:
    import pdfplumber
    strony_tekst = []
    strony_do_ocr = []

    with pdfplumber.open(str(sciezka)) as pdf:
        for i, strona in enumerate(pdf.pages):
            tekst = strona.extract_text() or ""
            strony_tekst.append(tekst)
            if len(tekst.strip()) < PROG_PUSTEJ_STRONY:
                strony_do_ocr.append(i)

    if strony_do_ocr and uzyj_ocr and _tesseract_dostepny():
        from pdf2image import convert_from_path
        obrazy = convert_from_path(str(sciezka), dpi=300)
        for i in strony_do_ocr:
            if i < len(obrazy):
                strony_tekst[i] = _ocr_obraz_pil(obrazy[i])
    elif strony_do_ocr and uzyj_ocr and not _tesseract_dostepny():
        # Nie przerywamy całego przetwarzania — informujemy i kontynuujemy
        # z tym, co udało się wyciągnąć z warstwy tekstowej (może być puste).
        import warnings
        warnings.warn(
            f"{len(strony_do_ocr)} stron(y) wygląda na skan bez warstwy tekstowej, "
            "a Tesseract nie jest zainstalowany — te strony zostaną pominięte "
            "przy detekcji PII. Zainstaluj Tesseract, aby to naprawić."
        )

    return "\n".join(strony_tekst)


def zapisz_tekst(sciezka: Path, tresc: str) -> None:
    """Zapisuje treść jako zwykły plik .txt."""
    sciezka.write_text(tresc, encoding="utf-8")


def zapisz_docx(sciezka: Path, tresc: str) -> None:
    """Zapisuje treść jako .docx: jeden akapit wyjściowy na jedną linię
    tekstu wejściowego (formatowanie znakowe oryginału nie jest odtwarzane —
    patrz ograniczenie w docstringu modułu)."""
    import docx
    dokument = docx.Document()
    for linia in tresc.split("\n"):
        dokument.add_paragraph(linia)
    dokument.save(str(sciezka))


def _zapisz_odt(sciezka: Path, tresc: str) -> None:
    from odf.opendocument import OpenDocumentText
    from odf.text import P

    dokument = OpenDocumentText()
    for linia in tresc.split("\n"):
        dokument.text.addElement(P(text=linia))
    dokument.save(str(sciezka))


def _escape_rtf(tekst: str) -> str:
    """Ucieczka znaków specjalnych RTF; znaki spoza ASCII kodowane jako
    \\uNNNN z bezpiecznym znakiem zapasowym — działa niezależnie od strony
    kodowej czytnika, więc polskie znaki wyświetlą się poprawnie."""
    wynik = []
    for znak in tekst:
        if znak in ("\\", "{", "}"):
            wynik.append("\\" + znak)
        elif ord(znak) > 127:
            wynik.append(f"\\u{ord(znak)}?")
        else:
            wynik.append(znak)
    return "".join(wynik)


def _zapisz_rtf(sciezka: Path, tresc: str) -> None:
    linie = tresc.split("\n")
    tresc_rtf = "\\par\n".join(_escape_rtf(linia) for linia in linie)
    dokument = (
        "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Arial;}}\\f0\\fs22 "
        + tresc_rtf + "}"
    )
    sciezka.write_text(dokument, encoding="utf-8")


def _zapisz_pdf(sciezka: Path, tresc: str) -> None:
    import html
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from .czcionki_pdf import zarejestruj_czcionki_pl

    zarejestruj_czcionki_pl()
    dokument = SimpleDocTemplate(
        str(sciezka), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm,
    )
    styl = getSampleStyleSheet()["Normal"]
    styl.fontName = "DejaVuSans"
    styl.fontSize = 11
    styl.leading = 15

    elementy = []
    for linia in tresc.split("\n"):
        if linia.strip():
            elementy.append(Paragraph(html.escape(linia), styl))
        else:
            elementy.append(Spacer(1, 8))
    dokument.build(elementy or [Paragraph("", styl)])


def _zapisz_obraz(sciezka: Path, tresc: str) -> None:
    """Renderuje zanonimizowaną treść jako nowy obraz — dla plików wejściowych
    JPG/PNG (skanów przetworzonych przez OCR), zamiast zwracać sam plik .txt.
    Layout oryginalnego obrazu nie jest odtwarzany, tylko czysty tekst na
    białym tle — patrz ograniczenie w docstringu modułu."""
    from PIL import Image, ImageDraw, ImageFont

    czcionka_sciezka = Path(__file__).parent / "czcionki" / "DejaVuSans.ttf"
    rozmiar_czcionki = 22
    try:
        font = ImageFont.truetype(str(czcionka_sciezka), rozmiar_czcionki)
    except Exception:
        font = ImageFont.load_default()

    linie = tresc.split("\n") or [""]
    tymczasowy = Image.new("RGB", (10, 10))
    rysownik_tymczasowy = ImageDraw.Draw(tymczasowy)
    szerokosci = [rysownik_tymczasowy.textlength(l, font=font) for l in linie] or [0]

    szerokosc_linii_tekstu = int(max(szerokosci, default=0))
    wysokosc_linii = rozmiar_czcionki + 10
    szerokosc = max(szerokosc_linii_tekstu + 40, 400)
    wysokosc = max(wysokosc_linii * len(linie) + 40, 100)

    obraz = Image.new("RGB", (szerokosc, wysokosc), color="white")
    rysownik = ImageDraw.Draw(obraz)
    y = 20
    for linia in linie:
        rysownik.text((20, y), linia, fill="black", font=font)
        y += wysokosc_linii

    format_obrazu = "JPEG" if sciezka.suffix.lower() in (".jpg", ".jpeg") else "PNG"
    obraz.save(str(sciezka), format=format_obrazu)


def zapisz_w_formacie(sciezka_wyjsciowa: Path, tresc: str) -> None:
    """Zapisuje treść w formacie zgodnym z rozszerzeniem sciezka_wyjsciowa —
    czyli w tym samym formacie co plik źródłowy (patrz anonimizator.py, które
    dobiera rozszerzenie pliku wyjściowego na podstawie pliku wejściowego)."""
    rozszerzenie = sciezka_wyjsciowa.suffix.lower()
    if rozszerzenie == ".txt":
        zapisz_tekst(sciezka_wyjsciowa, tresc)
    elif rozszerzenie == ".docx":
        zapisz_docx(sciezka_wyjsciowa, tresc)
    elif rozszerzenie == ".odt":
        _zapisz_odt(sciezka_wyjsciowa, tresc)
    elif rozszerzenie == ".rtf":
        _zapisz_rtf(sciezka_wyjsciowa, tresc)
    elif rozszerzenie == ".pdf":
        _zapisz_pdf(sciezka_wyjsciowa, tresc)
    elif rozszerzenie in (".jpg", ".jpeg", ".png"):
        _zapisz_obraz(sciezka_wyjsciowa, tresc)
    else:
        raise ValueError(
            f"Nieobsługiwany format zapisu: {rozszerzenie}. "
            f"Obsługiwane: {sorted(FORMATY_WSPIERANE)}"
        )
