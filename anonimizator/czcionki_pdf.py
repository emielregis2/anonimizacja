"""
Wspólna rejestracja czcionek DejaVu Sans dla reportlab.

Domyślne czcionki bazowe reportlab (Helvetica) nie mają polskich znaków
diakrytycznych. DejaVu Sans jest dołączona do projektu (katalog czcionki/),
więc działa niezależnie od czcionek zainstalowanych w systemie użytkownika.

Wydzielone do osobnego modułu, żeby raport.py i extractors.py (generowanie
PDF z zanonimizowaną treścią) nie duplikowały tej samej logiki rejestracji.
"""

from __future__ import annotations
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

KATALOG_CZCIONEK = Path(__file__).parent / "czcionki"
_ZAREJESTROWANE = False

NAZWA_REGULARNA = "DejaVuSans"
NAZWA_POGRUBIONA = "DejaVuSans-Bold"


def zarejestruj_czcionki_pl() -> None:
    global _ZAREJESTROWANE
    if _ZAREJESTROWANE:
        return
    pdfmetrics.registerFont(TTFont(NAZWA_REGULARNA, str(KATALOG_CZCIONEK / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(NAZWA_POGRUBIONA, str(KATALOG_CZCIONEK / "DejaVuSans-Bold.ttf")))
    _ZAREJESTROWANE = True
