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
    """Zapisuje wynik anonimizacji zawsze jako .txt (patrz uwaga w docstringu
    modułu — pełne odtworzenie oryginalnego formatu to osobne zadanie)."""
    sciezka.write_text(tresc, encoding="utf-8")


def zapisz_docx(sciezka: Path, tresc: str) -> None:
    """Wariant zachowujący format .docx: jeden akapit wyjściowy na jedną
    linię tekstu wejściowego (formatowanie znakowe oryginału nie jest
    odtwarzane — patrz ograniczenie w docstringu modułu)."""
    import docx
    dokument = docx.Document()
    for linia in tresc.split("\n"):
        dokument.add_paragraph(linia)
    dokument.save(str(sciezka))
