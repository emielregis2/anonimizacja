"""
Testy nowych funkcji: style maskowania, tryb wsadowy, tryb Archiwum/BIP,
OCR, raport PDF, wielojęzyczność.

Uruchomienie: pytest tests/ -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from anonimizator import (
    anonimizuj_tekst, anonimizuj_plik, anonimizuj_wiele_plikow, anonimizuj_bip,
    deanonimizuj_tekst, deanonimizuj_plik, STYLE_MASKOWANIA,
    NieodwracalnyStylMaskowania,
)


def test_wszystkie_style_generuja_tekst():
    tekst = "Jan Kowalski, kontakt: jan@firma.pl"
    for styl in STYLE_MASKOWANIA:
        wynik = anonimizuj_tekst(tekst, kategorie=["imiona_nazwiska", "email"], styl=styl)
        assert "Jan Kowalski" not in wynik.tekst_zanonimizowany
        assert "jan@firma.pl" not in wynik.tekst_zanonimizowany


def test_style_odwracalne_przywracaja_oryginal():
    tekst = "Jan Kowalski, kontakt: jan@firma.pl"
    for styl in ("pelny_token", "etykieta", "inicjaly"):
        wynik = anonimizuj_tekst(tekst, kategorie=["imiona_nazwiska", "email"], styl=styl)
        przywrocony = deanonimizuj_tekst(wynik.tekst_zanonimizowany, wynik.mapowanie)
        assert przywrocony == tekst, f"styl {styl} nie odtworzył oryginału"


def test_styl_puste_jest_nieodwracalny():
    tekst = "Jan Kowalski, kontakt: jan@firma.pl"
    wynik = anonimizuj_tekst(tekst, kategorie=["imiona_nazwiska", "email"], styl="puste")
    assert "[USUNIĘTE]" in wynik.tekst_zanonimizowany
    try:
        deanonimizuj_tekst(wynik.tekst_zanonimizowany, wynik.mapowanie)
        assert False, "powinien zostać zgłoszony wyjątek NieodwracalnyStylMaskowania"
    except NieodwracalnyStylMaskowania:
        pass


def test_etykieta_numeruje_literami():
    tekst = "Anna, Piotr, Karolina, Marek rozmawiali."
    wynik = anonimizuj_tekst(tekst, kategorie=["imiona_nazwiska"], styl="etykieta")
    assert "Osoba A" in wynik.tekst_zanonimizowany
    assert "Osoba B" in wynik.tekst_zanonimizowany


def test_tryb_wsadowy_jedna_sprawa_spojne_tokeny(tmp_path):
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_text("Sprawa Jan Kowalski, tel. 501 234 567.")
    p2.write_text("Ponownie: Jan Kowalski potwierdza odbiór.")

    wynik = anonimizuj_wiele_plikow(
        [p1, p2], tmp_path / "wynik", "Haslo123!",
        tryb="jedna_sprawa", kategorie=["imiona_nazwiska"],
    )
    t1 = wynik["pliki_tekst"]["a.txt"].read_text()
    t2 = wynik["pliki_tekst"]["b.txt"].read_text()
    # ten sam token dla tej samej osoby w obu plikach
    assert "[OSOBA_1]" in t1 and "[OSOBA_1]" in t2


def test_tryb_wsadowy_niezalezne_osobne_mapowania(tmp_path):
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_text("Jan Kowalski.")
    p2.write_text("Anna Nowak.")

    wynik = anonimizuj_wiele_plikow(
        [p1, p2], tmp_path / "wynik", "Haslo123!",
        tryb="niezalezne", kategorie=["imiona_nazwiska"],
    )
    assert (tmp_path / "wynik" / "a_mapowanie.enc").exists()
    assert (tmp_path / "wynik" / "b_mapowanie.enc").exists()


def test_tryb_bip_nie_zapisuje_zadnego_mapowania(tmp_path):
    p1 = tmp_path / "a.txt"
    p1.write_text("Jan Kowalski, PESEL 44051401359.")

    sciezka_wyn = anonimizuj_bip(p1, tmp_path / "wynik_bip", kategorie=["imiona_nazwiska", "pesel"])
    assert sciezka_wyn.exists()
    assert "Jan Kowalski" not in sciezka_wyn.read_text()

    pliki_w_katalogu = list((tmp_path / "wynik_bip").iterdir())
    nazwy = [p.name for p in pliki_w_katalogu]
    assert not any(n.endswith(".enc") for n in nazwy), \
        "Tryb BIP nie powinien zapisywać żadnego pliku mapowania"


def test_ocr_obrazu_wykrywa_dane(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1200, 120), color="white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except Exception:
        font = ImageFont.load_default()
    d.text((20, 30), "Kontakt: test@przyklad.pl", fill="black", font=font)
    sciezka_obrazu = tmp_path / "skan.png"
    img.save(sciezka_obrazu)

    wynik = anonimizuj_plik(
        sciezka_obrazu, tmp_path / "wynik", "Haslo123!", kategorie=["email"]
    )
    tekst_wynikowy = wynik["tekst"].read_text()
    assert "[EMAIL_1]" in tekst_wynikowy
    assert "test@przyklad.pl" not in tekst_wynikowy


def test_raport_pdf_zabezpieczony_haslem(tmp_path):
    from anonimizator import generuj_raport_pdf
    from pypdf import PdfReader

    mapowanie = {"[OSOBA_1]": "Jan Kowalski"}
    sciezka_pdf = tmp_path / "raport.pdf"
    generuj_raport_pdf(mapowanie, "Haslo123!", sciezka_pdf, nazwa_dokumentu="test")

    czytnik = PdfReader(str(sciezka_pdf))
    assert czytnik.is_encrypted
    assert czytnik.decrypt("ZleHaslo") == 0
    czytnik2 = PdfReader(str(sciezka_pdf))
    assert czytnik2.decrypt("Haslo123!") > 0
    assert "Jan Kowalski" in czytnik2.pages[0].extract_text()


def test_wielojezyczne_slowniki_wykrywaja_obce_imiona():
    tekst = "Spotkanie z James Smith z Londynu oraz Jean Dupont z Paryża."
    wynik = anonimizuj_tekst(
        tekst, kategorie=["imiona_nazwiska"], jezyki=["pl", "uk", "fr"]
    )
    assert "James" not in wynik.tekst_zanonimizowany
    assert "Jean" not in wynik.tekst_zanonimizowany


def test_bez_pakietu_jezykowego_obce_imiona_niewykryte():
    tekst = "Spotkanie z James Smith."
    wynik = anonimizuj_tekst(tekst, kategorie=["imiona_nazwiska"], jezyki=["pl"])
    assert "James" in wynik.tekst_zanonimizowany  # brak pakietu UK -> nie wykryto
