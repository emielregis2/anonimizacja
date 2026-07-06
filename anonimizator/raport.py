"""
Raport anonimizacji — czytelna tabela (placeholder -> kategoria -> wartość
oryginalna) w formie pliku PDF zabezpieczonego hasłem. Przeznaczona do akt
sprawy (dowód, co dokładnie zostało zanonimizowane) albo do wglądu klienta,
bez konieczności programistycznego odszyfrowywania pliku .enc.

Hasło do PDF-a jest tym samym hasłem, którego użyto do zaszyfrowania
mapowania .enc (crypto.py) — jedno hasło chroni oba artefakty tej samej
operacji anonimizacji.
"""

from __future__ import annotations
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from pypdf import PdfReader, PdfWriter

_KATALOG_CZCIONEK = Path(__file__).parent / "czcionki"
_CZCIONKI_ZAREJESTROWANE = False


def _zarejestruj_czcionki_pl():
    """Domyślne czcionki bazowe reportlab (Helvetica) nie mają polskich
    znaków diakrytycznych — rejestrujemy DejaVu Sans (dołączoną do projektu,
    więc działa niezależnie od systemu i czcionek zainstalowanych u klienta)."""
    global _CZCIONKI_ZAREJESTROWANE
    if _CZCIONKI_ZAREJESTROWANE:
        return
    pdfmetrics.registerFont(TTFont("DejaVuSans", str(_KATALOG_CZCIONEK / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(_KATALOG_CZCIONEK / "DejaVuSans-Bold.ttf")))
    _CZCIONKI_ZAREJESTROWANE = True


def _zbuduj_pdf_niezaszyfrowany(mapowanie: dict[str, str], nazwa_dokumentu: str) -> bytes:
    _zarejestruj_czcionki_pl()
    bufor = BytesIO()
    dokument = SimpleDocTemplate(
        bufor, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    style = getSampleStyleSheet()
    style["Title"].fontName = "DejaVuSans-Bold"
    style["Normal"].fontName = "DejaVuSans"
    elementy = [
        Paragraph(f"Raport anonimizacji — {nazwa_dokumentu}", style["Title"]),
        Spacer(1, 8),
        Paragraph(
            "Ten dokument jest zabezpieczony hasłem. Zawiera pełne zestawienie "
            "danych oryginalnych podmienionych podczas anonimizacji — traktuj go "
            "z taką samą starannością jak dokument źródłowy.",
            style["Normal"],
        ),
        Spacer(1, 14),
    ]

    dane_tabeli = [["Placeholder w tekście", "Kategoria", "Wartość oryginalna"]]
    for placeholder, wartosc in sorted(mapowanie.items()):
        if placeholder.startswith("__usuniete_"):
            # wyciągnij nazwę kategorii z klucza wewnętrznego "__usuniete_N__ (kategoria)"
            kategoria = placeholder.split("(")[-1].rstrip(")") if "(" in placeholder else "?"
            dane_tabeli.append(["[USUNIĘTE]", kategoria, wartosc])
        else:
            dane_tabeli.append([placeholder, "-", wartosc])

    tabela = Table(dane_tabeli, colWidths=[55 * mm, 40 * mm, 75 * mm], repeatRows=1)
    tabela.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVuSans-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1EFE8")]),
    ]))
    elementy.append(tabela)
    dokument.build(elementy)
    return bufor.getvalue()


def generuj_raport_pdf(
    mapowanie: dict[str, str],
    haslo: str,
    sciezka_wyjsciowa: Path,
    nazwa_dokumentu: str = "dokument",
) -> Path:
    surowy_pdf = _zbuduj_pdf_niezaszyfrowany(mapowanie, nazwa_dokumentu)

    czytnik = PdfReader(BytesIO(surowy_pdf))
    zapis = PdfWriter()
    for strona in czytnik.pages:
        zapis.add_page(strona)
    zapis.encrypt(haslo, algorithm="AES-256")

    with open(sciezka_wyjsciowa, "wb") as f:
        zapis.write(f)
    return sciezka_wyjsciowa
