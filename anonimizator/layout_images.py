"""
Anonimizacja obrazów (JPG/PNG) z zachowaniem layoutu oryginału — zamiast
generowania zupełnie nowego obrazu z czystym tekstem na białym tle
(extractors._zapisz_obraz), zamalowujemy wykryte dane bezpośrednio na
kopii oryginalnego zdjęcia, dokładnie tam, gdzie faktycznie się znajdują.

Podejście: pytesseract.image_to_data() (zamiast image_to_string()) daje
nie tylko rozpoznany tekst, ale też współrzędne (bounding box) każdego
rozpoznanego słowa. Składamy z tych słów płaski tekst (z odstępami/
nowymi liniami odtwarzającymi układ linii OCR), wykrywamy w nim PII przez
SilnikAnonimizacji.wyznacz_zamiany(), a następnie dla każdego dopasowania
zamalowujemy bounding-boxy nachodzących słów bezpośrednio na kopii
oryginalnego obrazu i wpisujemy placeholder w miejscu pierwszego z nich.

Ta sama technika (OCR ze współrzędnymi + zamalowanie w miejscu) domyka
przy okazji ograniczenie z redakcji PDF: strony-skany bez warstwy
tekstowej — patrz anonimizuj_strone_skanowana_pdf() niżej, która renderuje
taką stronę jako obraz przez PyMuPDF (bez dodatkowej zależności od
poppler/pdf2image — fitz ma rasteryzację wbudowaną) i stosuje tę samą
funkcję redakcji, wstawiając zredagowany obraz z powrotem jako treść
strony.

Ograniczenie: jakość redakcji zależy od jakości OCR (patrz README —
niska rozdzielczość, pochylone strony, odręczne pismo obniżają
skuteczność) — dokładnie tak samo jak przy dotychczasowej ekstrakcji
tekstu ze skanów gdzie indziej w projekcie.
"""

from __future__ import annotations
from pathlib import Path

SCIEZKA_CZCIONKI = Path(__file__).parent / "czcionki" / "DejaVuSans.ttf"


def _wczytaj_czcionke(rozmiar: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(SCIEZKA_CZCIONKI), rozmiar)
    except Exception:
        return ImageFont.load_default()


def _szerokosc_tekstu(czcionka, tekst: str) -> float:
    if hasattr(czcionka, "getlength"):
        return czcionka.getlength(tekst)
    return czcionka.getsize(tekst)[0]


def _zawin_tekst(tekst: str, czcionka, max_szerokosc: int) -> list[str]:
    """Prosty word-wrap dla PIL — dzieli tekst na linie mieszczące się
    w max_szerokosc pikseli, zachowując istniejące podziały linii."""
    linie_wynikowe = []
    for oryginalna_linia in tekst.split("\n"):
        if not oryginalna_linia.strip():
            linie_wynikowe.append("")
            continue
        slowa = oryginalna_linia.split(" ")
        biezaca = ""
        for slowo in slowa:
            proba = (biezaca + " " + slowo).strip()
            if _szerokosc_tekstu(czcionka, proba) <= max_szerokosc or not biezaca:
                biezaca = proba
            else:
                linie_wynikowe.append(biezaca)
                biezaca = slowo
        if biezaca:
            linie_wynikowe.append(biezaca)
    return linie_wynikowe


def _zbuduj_plaski_tekst_i_mape_slow(dane_ocr: dict) -> tuple[str, list[tuple]]:
    """dane_ocr: wynik pytesseract.image_to_data(..., output_type=Output.DICT).
    Zwraca (plaski_tekst, lista_slow), gdzie lista_slow to
    [(start, end, left, top, width, height), ...] dla każdego niepustego
    rozpoznanego słowa, w tej samej kolejności co w plaski_tekst."""
    czesci = []
    slowa = []
    pozycja = 0
    poprzedni_klucz_linii = None
    n = len(dane_ocr["text"])
    for i in range(n):
        tekst_slowa = dane_ocr["text"][i].strip()
        if not tekst_slowa:
            continue
        klucz_linii = (dane_ocr["block_num"][i], dane_ocr["par_num"][i], dane_ocr["line_num"][i])
        if poprzedni_klucz_linii is not None:
            if klucz_linii != poprzedni_klucz_linii:
                czesci.append("\n")
                pozycja += 1
            else:
                czesci.append(" ")
                pozycja += 1
        start = pozycja
        czesci.append(tekst_slowa)
        pozycja += len(tekst_slowa)
        slowa.append((start, pozycja, dane_ocr["left"][i], dane_ocr["top"][i],
                       dane_ocr["width"][i], dane_ocr["height"][i]))
        poprzedni_klucz_linii = klucz_linii
    return "".join(czesci), slowa


def _redaguj_obraz(obraz, silnik, kategorie=None, tryb_ai: bool = False) -> list:
    """Zamalowuje wykryte PII bezpośrednio na przekazanym obrazie PIL
    (modyfikacja w miejscu — przekaż kopię, jeśli oryginał ma zostać
    nietknięty). Zwraca listę zastosowanych Zamiana."""
    import pytesseract
    from PIL import ImageDraw

    dane_ocr = pytesseract.image_to_data(obraz, lang="pol+eng",
                                          output_type=pytesseract.Output.DICT)
    plaski_tekst, slowa = _zbuduj_plaski_tekst_i_mape_slow(dane_ocr)
    if not plaski_tekst.strip():
        return []

    zamiany = silnik.wyznacz_zamiany(plaski_tekst, kategorie=kategorie, tryb_ai=tryb_ai)
    if not zamiany:
        return []

    rysownik = ImageDraw.Draw(obraz)
    for z in zamiany:
        pierwsze_pole = None
        for (s_start, s_end, left, top, width, height) in slowa:
            if s_end <= z.start or s_start >= z.end:
                continue
            rysownik.rectangle([left, top, left + width, top + height], fill=(255, 255, 255))
            if pierwsze_pole is None:
                pierwsze_pole = (left, top, width, height)
        if pierwsze_pole:
            left, top, width, height = pierwsze_pole
            czcionka = _wczytaj_czcionke(max(10, int(height * 0.85)))
            rysownik.text((left, top), z.placeholder, fill=(0, 0, 0), font=czcionka)
    return zamiany


def anonimizuj_obraz_zachowaj_layout(
    sciezka_wejsciowa: Path, sciezka_wyjsciowa: Path, silnik,
    kategorie: list[str] | None = None, tryb_ai: bool = False,
) -> None:
    """Anonimizuje JPG/PNG w miejscu — zamalowuje wykryte dane
    bezpośrednio na kopii oryginalnego obrazu, zachowując resztę zdjęcia
    (tło, inne elementy, jakość, rozdzielczość) nietkniętą."""
    from PIL import Image
    obraz = Image.open(sciezka_wejsciowa).convert("RGB")
    _redaguj_obraz(obraz, silnik, kategorie=kategorie, tryb_ai=tryb_ai)
    obraz.save(sciezka_wyjsciowa)


def wstaw_prompt_do_obrazu(sciezka: Path, prompt_tekst: str) -> None:
    """Dopisuje prompt dla AI jako pas tekstu u góry obrazu (rozszerza
    canvas, nie nadpisuje treści zdjęcia) — przydatne, jeśli obraz trafi
    bezpośrednio do modelu AI z obsługą obrazów, który "przeczyta" prompt
    tak samo jak resztę tekstu na obrazie."""
    if not prompt_tekst:
        return
    from PIL import Image, ImageDraw
    obraz = Image.open(sciezka)
    szerokosc, wysokosc = obraz.size
    rozmiar_czcionki = 16
    czcionka = _wczytaj_czcionke(rozmiar_czcionki)

    linie = _zawin_tekst(prompt_tekst, czcionka, szerokosc - 40)
    wysokosc_pasa = len(linie) * (rozmiar_czcionki + 6) + 20

    nowy_obraz = Image.new("RGB", (szerokosc, wysokosc + wysokosc_pasa), (255, 255, 255))
    nowy_obraz.paste(obraz, (0, wysokosc_pasa))
    rysownik = ImageDraw.Draw(nowy_obraz)
    y = 10
    for linia in linie:
        rysownik.text((20, y), linia, fill=(0, 0, 0), font=czcionka)
        y += rozmiar_czcionki + 6
    nowy_obraz.save(sciezka)


def anonimizuj_strone_skanowana_pdf(strona, silnik, kategorie=None, tryb_ai: bool = False,
                                     dpi: int = 300) -> bool:
    """Domyka ograniczenie z layout_pdf.py: strona PDF bez warstwy
    tekstowej (czysty skan) nie ma czego zredagować przez search_for.
    Zamiast tego: renderujemy stronę jako obraz (fitz — bez dodatkowej
    zależności od poppler), stosujemy tę samą redakcję OCR co dla JPG/PNG,
    usuwamy oryginalny, niezredagowany obraz strony (nie tylko zasłaniamy
    go wizualnie — inaczej pierwotny skan nadal siedziałby osadzony
    w pliku PDF pod spodem) i wklejamy zredagowany obraz w jego miejsce.

    Zwraca True, jeśli cokolwiek wykryto i strona została zredagowana."""
    import fitz
    from PIL import Image
    import io

    mnoznik = dpi / 72
    pixmap = strona.get_pixmap(matrix=fitz.Matrix(mnoznik, mnoznik))
    obraz = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")

    zamiany = _redaguj_obraz(obraz, silnik, kategorie=kategorie, tryb_ai=tryb_ai)
    if not zamiany:
        return False

    bufor = io.BytesIO()
    obraz.save(bufor, format="PNG")

    # Usuwamy oryginalne obrazy strony (prawdziwe usunięcie z pliku, nie
    # tylko wizualne zasłonięcie) przed wklejeniem zredagowanej wersji.
    for info_obrazu in strona.get_images(full=True):
        xref = info_obrazu[0]
        try:
            strona.delete_image(xref)
        except Exception:
            pass

    strona.insert_image(strona.rect, stream=bufor.getvalue())
    return True
