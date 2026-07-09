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
from anonimizator.anonimizator import GRANICA_PROMPTU_AI, zbuduj_prompt_ai


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
    p1.write_text("Sprawa Jan Kowalski, tel. 501 234 567.", encoding="utf-8")
    p2.write_text("Ponownie: Jan Kowalski potwierdza odbiór.", encoding="utf-8")

    wynik = anonimizuj_wiele_plikow(
        [p1, p2], tmp_path / "wynik", "Haslo123!",
        tryb="jedna_sprawa", kategorie=["imiona_nazwiska"],
    )
    t1 = wynik["pliki_tekst"]["a.txt"].read_text(encoding="utf-8")
    t2 = wynik["pliki_tekst"]["b.txt"].read_text(encoding="utf-8")
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
    assert "Jan Kowalski" not in sciezka_wyn.read_text(encoding="utf-8")

    pliki_w_katalogu = list((tmp_path / "wynik_bip").iterdir())
    nazwy = [p.name for p in pliki_w_katalogu]
    assert not any(n.endswith(".enc") for n in nazwy), \
        "Tryb BIP nie powinien zapisywać żadnego pliku mapowania"


def test_ocr_obrazu_wykrywa_dane(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    # Czcionka dolaczona do projektu (nie sciezka systemowa) - dzieki temu
    # test dziala identycznie na Linuksie i Windows.
    czcionka_projektu = Path(__file__).parent.parent / "anonimizator" / "czcionki" / "DejaVuSans-Bold.ttf"
    img = Image.new("RGB", (1200, 120), color="white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(czcionka_projektu), 48)
    except Exception:
        font = ImageFont.load_default()
    d.text((20, 30), "Kontakt: test@przyklad.pl", fill="black", font=font)
    sciezka_obrazu = tmp_path / "skan.png"
    img.save(sciezka_obrazu)

    wynik = anonimizuj_plik(
        sciezka_obrazu, tmp_path / "wynik", "Haslo123!", kategorie=["email"]
    )
    # Wynik dla pliku wejściowego .png jest zapisywany w tym samym formacie
    # (nowy obraz z narysowanym zanonimizowanym tekstem), więc odczytujemy go
    # z powrotem przez OCR, zamiast czytać jako zwykły plik tekstowy.
    assert wynik["tekst"].suffix == ".png"
    from anonimizator.extractors import wczytaj_tekst
    tekst_wynikowy = wczytaj_tekst(wynik["tekst"])
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


def test_bez_pakietu_jezykowego_obcy_imie_nie_kotwiczy_pary():
    """Bez załadowanego pakietu językowego danego kraju, obce imię nie
    działa jako kotwica dla pary imię+nazwisko (nie ma go w żadnym
    załadowanym słowniku imion). Używamy celowo nieistniejących słów,
    żeby test nie zależał od tego, czy akurat są/nie są zarejestrowanym
    nazwiskiem w PESEL (patrz test niżej — to się może zdarzyć)."""
    from anonimizator.slowniki_recognizers import recognize_imiona_nazwiska
    wyniki = recognize_imiona_nazwiska("Spotkanie z Xhavitem Zzqprothem.", jezyki=("pl",))
    assert len(wyniki) == 0


def test_nazwiska_pesel_obejmuja_tez_nazwiska_obcego_pochodzenia():
    """WAŻNE ODKRYCIE przy integracji danych GUS: nazwiska_pl.txt to pełny
    rejestr PESEL, nie "polski pakiet językowy" w tym samym sensie co
    imiona_XX.txt — obejmuje wszystkie osoby zarejestrowane w Polsce,
    w tym z nazwiskami obcego pochodzenia. 'Smith' i 'James' są realnie
    zarejestrowanymi nazwiskami w PESEL, więc zostają wykryte jako
    samodzielne nazwiska niezależnie od wybranych pakietów językowych
    imion. To oczekiwane, poprawne działanie (recall > precyzja), nie błąd."""
    tekst = "Kontrahentem jest firma reprezentowana przez pana Smith."
    wynik = anonimizuj_tekst(tekst, kategorie=["imiona_nazwiska"], jezyki=["pl"])
    assert "[OSOBA_1]" in wynik.tekst_zanonimizowany
    assert wynik.mapowanie["[OSOBA_1]"] == "Smith"


def test_samodzielne_nazwisko_wykrywane_bez_poprzedzajacego_imienia():
    """Główna nowa zdolność: nazwisko bez poprzedzającego, rozpoznanego
    imienia jest teraz wykrywane (wcześniej — udokumentowane ograniczenie
    w notatce o mechanizmie wykrywania — było to niemożliwe bez Trybu AI)."""
    from anonimizator.slowniki_recognizers import recognize_imiona_nazwiska
    wyniki = recognize_imiona_nazwiska("Rozmawiałem wczoraj z Kowalski.", jezyki=("pl",))
    assert len(wyniki) == 1
    assert wyniki[0].text == "Kowalski"


def test_samodzielne_nazwisko_na_poczatku_zdania_nie_jest_wykrywane():
    """Zabezpieczenie przed fałszywym trafieniem: słowo na samym początku
    zdania nie jest sprawdzane jako samodzielne nazwisko, nawet jeśli jest
    w słowniku — każde zdanie zaczyna się wielką literą, więc bez tego
    zabezpieczenia zwykłe słowa pokrywające się z nazwiskami dawałyby
    fałszywe trafienia."""
    from anonimizator.slowniki_recognizers import recognize_imiona_nazwiska
    tekst = "Kowalski przyszedł na spotkanie. Rozmawiałem wczoraj z Kowalski."
    wyniki = recognize_imiona_nazwiska(tekst, jezyki=("pl",))
    # tylko drugie wystąpienie (nie na początku zdania) powinno zostać wykryte
    assert len(wyniki) == 1
    assert wyniki[0].start == tekst.rindex("Kowalski")  # to drugie, nie pierwsze wystąpienie


def test_miasto_na_poczatku_zdania_nie_jest_wykrywane():
    """To samo zabezpieczenie co przy nazwiskach, zastosowane do
    rozszerzonego (58 025 pozycji) słownika miejscowości. Uwaga: "Polski"
    celowo unikane w tym zdaniu — po wdrożeniu lematyzacji (Morfeusz2)
    "Polski" ma wśród kandydatów na lemat "Polska", a to naprawdę
    istnieje jako osobna miejscowość w TERYT (ten sam efekt co "Strona"/
    "Dane" — świadomy kompromis recall/precyzja, nie błąd)."""
    from anonimizator.slowniki_recognizers import recognize_miasta
    tekst = "Warszawa to duże miasto. Mieszkam w Warszawa od lat."
    wyniki = recognize_miasta(tekst, jezyki=("pl",))
    assert len(wyniki) == 1
    assert wyniki[0].start == tekst.rindex("Warszawa")


def test_miasto_srodku_zdania_wykrywane():
    from anonimizator.slowniki_recognizers import recognize_miasta
    wyniki = recognize_miasta("Sprawa toczy się przed sądem w mieście Kraków.", jezyki=("pl",))
    assert len(wyniki) == 1
    assert wyniki[0].text == "Kraków"


def test_lematyzacja_odmieniona_forma_nazwiska_wykrywana(tmp_path):
    """Główny cel wdrożenia Morfeusz2: forma odmieniona ("Kowalskiego",
    dopełniacz) jest teraz wykrywana, mimo że w słowniku jest tylko
    mianownik ("Kowalski"). Test pomijany bez zainstalowanego morfeusz2."""
    from anonimizator import morfologia
    if not morfologia.dostepna_lematyzacja():
        import pytest
        pytest.skip("morfeusz2 niezainstalowany")
    from anonimizator.slowniki_recognizers import recognize_imiona_nazwiska
    wyniki = recognize_imiona_nazwiska("Rozmawiałem wczoraj z Kowalskiego.", jezyki=("pl",))
    assert len(wyniki) == 1
    assert wyniki[0].text == "Kowalskiego"


def test_lematyzacja_odmieniona_forma_miasta_wykrywana():
    """To samo dla miejscowości: "Krakowie" (miejscownik) wykrywane mimo
    że w słowniku jest tylko "Kraków"."""
    from anonimizator import morfologia
    if not morfologia.dostepna_lematyzacja():
        import pytest
        pytest.skip("morfeusz2 niezainstalowany")
    from anonimizator.slowniki_recognizers import recognize_miasta
    wyniki = recognize_miasta("Sprawa toczy się przed sądem w Krakowie.", jezyki=("pl",))
    assert len(wyniki) == 1
    assert wyniki[0].text == "Krakowie"


def test_izolowane_nazwisko_bez_reszty_zdania_wykrywane():
    """Komórka tabeli / pole formularza zawierające WYŁĄCZNIE nazwisko
    (bez żadnego innego tekstu) to nie jest "zdanie" w sensie zabezpieczenia
    _na_poczatku_zdania — powinno zostać wykryte mimo pozycji 0."""
    from anonimizator.slowniki_recognizers import recognize_imiona_nazwiska, recognize_miasta
    assert len(recognize_imiona_nazwiska("Nowak", jezyki=("pl",))) == 1
    assert len(recognize_miasta("Warszawa", jezyki=("pl",))) == 1
    # ale prawdziwe zdanie zaczynające się od tego samego słowa nadal pomijane
    assert len(recognize_imiona_nazwiska("Nowak i Kowalski złożyli pozew.", jezyki=("pl",))) == 1
    wyniki = recognize_imiona_nazwiska("Nowak i Kowalski złożyli pozew.", jezyki=("pl",))
    assert wyniki[0].text == "Kowalski"  # tylko drugie nazwisko, nie pierwsze (start zdania)


def test_nazwa_pliku_wynikowego_ma_przyrostek_anon_i_oryginalne_rozszerzenie(tmp_path):
    p = tmp_path / "umowa.txt"
    p.write_text("Jan Kowalski podpisal umowe.")
    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    assert wynik["tekst"].name == "umowa_anon.txt"


def test_wynik_docx_zachowuje_format_docx(tmp_path):
    import docx
    sciezka_docx = tmp_path / "pismo.docx"
    dokument = docx.Document()
    dokument.add_paragraph("Sprawa dotyczy Jan Kowalski.")
    dokument.save(str(sciezka_docx))

    wynik = anonimizuj_plik(sciezka_docx, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    assert wynik["tekst"].name == "pismo_anon.docx"
    assert wynik["tekst"].suffix == ".docx"

    from anonimizator.extractors import wczytaj_tekst
    tresc = wczytaj_tekst(wynik["tekst"])
    assert "[OSOBA_1]" in tresc
    assert "Jan Kowalski" not in tresc


def test_wynik_pdf_zachowuje_format_pdf(tmp_path):
    from reportlab.pdfgen import canvas
    sciezka_pdf = tmp_path / "faktura.pdf"
    c = canvas.Canvas(str(sciezka_pdf))
    c.drawString(50, 750, "Odbiorca: Jan Kowalski")
    c.save()

    wynik = anonimizuj_plik(sciezka_pdf, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    assert wynik["tekst"].name == "faktura_anon.pdf"

    from anonimizator.extractors import wczytaj_tekst
    tresc = wczytaj_tekst(wynik["tekst"])
    assert "[OSOBA_1]" in tresc
    assert "Jan Kowalski" not in tresc


def test_deanonimizacja_plikow_roznych_formatow_dziala(tmp_path):
    from anonimizator import deanonimizuj_plik
    p = tmp_path / "notatka.rtf"
    # Minimalny poprawny plik RTF
    p.write_text(r"{\rtf1\ansi Sprawa Jan Kowalski.}", encoding="utf-8")

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    assert wynik["tekst"].suffix == ".rtf"

    sciezka_wyjsciowa = tmp_path / "przywrocony.txt"
    deanonimizuj_plik(wynik["tekst"], wynik["mapowanie"], "Haslo123!", sciezka_wyjsciowa)
    tresc = sciezka_wyjsciowa.read_text(encoding="utf-8")
    assert "Jan Kowalski" in tresc


def test_prompt_ai_domyslnie_dolaczony_i_zawiera_tokeny(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Jan Kowalski, NIP: 526-000-12-46.", encoding="utf-8")

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!",
                             kategorie=["imiona_nazwiska", "nip"])
    tresc_pliku = wynik["tekst"].read_text(encoding="utf-8")

    assert GRANICA_PROMPTU_AI in tresc_pliku
    assert "[OSOBA_1]" in wynik["prompt_ai"]
    assert "[NIP_1]" in wynik["prompt_ai"]
    # prompt musi poprzedzać właściwą treść w zapisanym pliku
    assert tresc_pliku.index(GRANICA_PROMPTU_AI) < tresc_pliku.index("[OSOBA_1]", tresc_pliku.index(GRANICA_PROMPTU_AI) + 1)


def test_prompt_ai_mozna_wylaczyc(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Jan Kowalski.", encoding="utf-8")

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!",
                             kategorie=["imiona_nazwiska"], dolacz_prompt_ai=False)
    tresc_pliku = wynik["tekst"].read_text(encoding="utf-8")
    assert GRANICA_PROMPTU_AI not in tresc_pliku
    assert wynik["prompt_ai"] == ""


def test_prompt_ai_nieobecny_w_trybie_bip(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("Jan Kowalski.", encoding="utf-8")

    sciezka_wyn = anonimizuj_bip(p, tmp_path / "wynik_bip", kategorie=["imiona_nazwiska"])
    assert GRANICA_PROMPTU_AI not in sciezka_wyn.read_text(encoding="utf-8")


def test_prompt_ai_usuwany_przy_deanonimizacji(tmp_path):
    p = tmp_path / "a.txt"
    tekst_oryginalny = "Jan Kowalski dzwonił w sprawie umowy."
    p.write_text(tekst_oryginalny, encoding="utf-8")

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    assert GRANICA_PROMPTU_AI in wynik["tekst"].read_text(encoding="utf-8")

    sciezka_wyjsciowa = tmp_path / "przywrocony.txt"
    deanonimizuj_plik(wynik["tekst"], wynik["mapowanie"], "Haslo123!", sciezka_wyjsciowa)
    tresc = sciezka_wyjsciowa.read_text(encoding="utf-8")

    assert GRANICA_PROMPTU_AI not in tresc
    assert tresc == tekst_oryginalny


def test_prompt_ai_w_trybie_jedna_sprawa_zawiera_tylko_tokeny_z_danego_pliku(tmp_path):
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_text("Jan Kowalski.", encoding="utf-8")
    # Celowo ta sama, nieodmieniona forma "Jan Kowalski" — silnik dopasowuje
    # po dokładnym tekście, bez analizy fleksyjnej języka polskiego.
    p2.write_text("Anna Nowak i Jan Kowalski byli na spotkaniu.", encoding="utf-8")

    wynik = anonimizuj_wiele_plikow(
        [p1, p2], tmp_path / "wynik", "Haslo123!",
        tryb="jedna_sprawa", kategorie=["imiona_nazwiska"],
    )
    t1 = wynik["pliki_tekst"]["a.txt"].read_text(encoding="utf-8")
    t2 = wynik["pliki_tekst"]["b.txt"].read_text(encoding="utf-8")

    # plik a.txt wspomina tylko Jana Kowalskiego -> tylko OSOBA_1 w jego promptcie
    assert "[OSOBA_1]" in t1
    # plik b.txt wspomina obie osoby -> oba tokeny w jego promptcie
    assert "[OSOBA_1]" in t2 and "[OSOBA_2]" in t2


def test_docx_zachowuje_formatowanie_pogrubienia(tmp_path):
    """Kluczowy test nowej funkcjonalności: format wyjściowy DOCX zachowuje
    layout (formatowanie) oryginału, zamiast budować dokument od nowa."""
    import docx
    p = tmp_path / "pismo.docx"
    dokument = docx.Document()
    akapit = dokument.add_paragraph()
    akapit.add_run("Powód: ")
    run_pogrubiony = akapit.add_run("Jan Kowalski")
    run_pogrubiony.bold = True
    akapit.add_run(" wnosi o zapłatę.")
    dokument.save(p)

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"],
                             dolacz_prompt_ai=False)
    assert wynik["tekst"].suffix == ".docx"

    sprawdz = docx.Document(wynik["tekst"])
    runy_z_tokenem = [r for r in sprawdz.paragraphs[0].runs if "[OSOBA_1]" in r.text]
    assert len(runy_z_tokenem) == 1
    assert runy_z_tokenem[0].bold is True


def test_docx_podmiana_na_granicy_dwoch_runow(tmp_path):
    """PII rozciągające się na dwa runy o różnym formatowaniu — powinno
    zostać poprawnie wykryte i podmienione (cały placeholder w pierwszym
    runie, nachodząca część wyczyszczona z drugiego)."""
    import docx
    p = tmp_path / "pismo2.docx"
    dokument = docx.Document()
    akapit = dokument.add_paragraph()
    akapit.add_run("Jan").bold = True
    akapit.add_run(" Kowalski").bold = False
    dokument.save(p)

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"],
                             dolacz_prompt_ai=False)
    sprawdz = docx.Document(wynik["tekst"])
    pelny_tekst = "".join(r.text for r in sprawdz.paragraphs[0].runs)
    assert pelny_tekst == "[OSOBA_1]"


def test_docx_tabela_jest_anonimizowana(tmp_path):
    import docx
    p = tmp_path / "umowa.docx"
    dokument = docx.Document()
    tabela = dokument.add_table(rows=1, cols=2)
    # Pierwsza komórka celowo pusta — przy bazie 68k imion + 598k nazwisk
    # z PESEL każde "bezpieczne" słowo-etykieta ryzykuje przypadkowym
    # trafieniem (już złapaliśmy "Strona" jako nazwisko i "Dane" jako
    # imię przy pisaniu tego testu) — najpewniejszy test eliminuje
    # tę zmienną zamiast szukać kolejnego "bezpiecznego" słowa.
    tabela.cell(0, 1).text = "Nowak"
    dokument.save(p)

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    sprawdz = docx.Document(wynik["tekst"])
    tekst_komorki = sprawdz.tables[0].cell(0, 1).text
    assert "Nowak" not in tekst_komorki
    assert "[OSOBA_1]" in tekst_komorki


def test_docx_naglowek_jest_anonimizowany(tmp_path):
    import docx
    p = tmp_path / "pismo3.docx"
    dokument = docx.Document()
    dokument.sections[0].header.paragraphs[0].text = "Sprawa: Jan Kowalski"
    dokument.add_paragraph("Treść bez danych osobowych.")
    dokument.save(p)

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    sprawdz = docx.Document(wynik["tekst"])
    assert "Kowalski" not in sprawdz.sections[0].header.paragraphs[0].text


def test_docx_layout_deanonimizacja_przywraca_oryginal(tmp_path):
    """Pełny przepływ end-to-end: zapis z zachowaniem layoutu + automatyczny
    prompt AI + deanonimizacja (usuwająca prompt, przywracająca oryginał)."""
    import docx
    from anonimizator import deanonimizuj_plik
    from anonimizator.anonimizator import GRANICA_PROMPTU_AI
    p = tmp_path / "pismo4.docx"
    dokument = docx.Document()
    dokument.add_paragraph("Klientem jest Kowalski, mieszkający w Warszawa.")
    dokument.save(p)

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!",
                             kategorie=["imiona_nazwiska", "miasta"])
    assert GRANICA_PROMPTU_AI in wynik["tekst_zanonimizowany"]

    sciezka_wyjsciowa = tmp_path / "przywrocony.txt"
    deanonimizuj_plik(wynik["tekst"], wynik["mapowanie"], "Haslo123!", sciezka_wyjsciowa)
    przywrocony = sciezka_wyjsciowa.read_text(encoding="utf-8")
    assert "Kowalski" in przywrocony
    assert "Warszawa" in przywrocony
    assert GRANICA_PROMPTU_AI not in przywrocony


def test_docx_zachowaj_layout_false_uzywa_starej_sciezki(tmp_path):
    """Jawne wyłączenie zachowaj_layout wraca do starego trybu
    (wyciągnij tekst -> zbuduj dokument od nowa) — dla porównania/awaryjnie."""
    import docx
    p = tmp_path / "pismo5.docx"
    dokument = docx.Document()
    akapit = dokument.add_paragraph()
    akapit.add_run("Jan Kowalski").bold = True
    dokument.save(p)

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!",
                             kategorie=["imiona_nazwiska"], zachowaj_layout=False)
    sprawdz = docx.Document(wynik["tekst"])
    # w starym trybie kazdy akapit budowany od nowa, wiec formatowanie
    # (pogrubienie) nie jest zachowane
    assert sprawdz.paragraphs[0].runs[0].bold is not True


def test_pdf_redakcja_naprawde_usuwa_tekst_nie_tylko_zaslania(tmp_path):
    """Kluczowa różnica względem zwykłego "zamalowania": PyMuPDF usuwa
    tekst z warstwy tekstowej PDF, więc oryginalnej wartości nie da się
    odzyskać przez zaznaczenie/kopiowanie ani przez ponowną ekstrakcję —
    sprawdzamy to bezpośrednio przez fitz, nie przez wysokopoziomowy
    wczytaj_tekst()."""
    import fitz
    from reportlab.pdfgen import canvas
    p = tmp_path / "pismo.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(50, 750, "Klient: Kowalski, ulica testowa 5.")
    c.save()

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"],
                             dolacz_prompt_ai=False)

    dokument = fitz.open(str(wynik["tekst"]))
    tekst_strony = dokument[0].get_text()
    dokument.close()
    assert "Kowalski" not in tekst_strony
    assert "[OSOBA_1]" in tekst_strony
    # reszta tekstu na stronie (poza redagowaną wartością) zostaje
    assert "Klient:" in tekst_strony
    assert "ulica testowa 5" in tekst_strony


def test_pdf_layout_deanonimizacja_przywraca_oryginal(tmp_path):
    from reportlab.pdfgen import canvas
    from anonimizator import deanonimizuj_plik
    from anonimizator.anonimizator import GRANICA_PROMPTU_AI
    p = tmp_path / "pismo2.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(50, 750, "Sprawa dotyczy Nowak, mieszkajacego w Bytom.")
    c.save()

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!",
                             kategorie=["imiona_nazwiska", "miasta"])
    assert GRANICA_PROMPTU_AI in wynik["tekst_zanonimizowany"]

    sciezka_wyjsciowa = tmp_path / "przywrocony.txt"
    deanonimizuj_plik(wynik["tekst"], wynik["mapowanie"], "Haslo123!", sciezka_wyjsciowa)
    przywrocony = sciezka_wyjsciowa.read_text(encoding="utf-8")
    assert "Nowak" in przywrocony
    assert "Bytom" in przywrocony
    assert GRANICA_PROMPTU_AI not in przywrocony


def test_pdf_strona_bez_warstwy_tekstowej_zgloszona(tmp_path):
    """Strona będąca czystym obrazem (bez warstwy tekstowej) nie jest
    redagowana tą ścieżką — powinna zostać zgłoszona w wyniku, żeby nie
    zwrócić milcząco dokumentu z niezredagowaną stroną."""
    import fitz
    p = tmp_path / "skan.pdf"
    dokument = fitz.open()
    strona = dokument.new_page()
    # pusty obraz (bialy prostokat) zamiast tekstu - strona "bez warstwy
    # tekstowej", tak jak prawdziwy skan bez OCR
    strona.draw_rect(fitz.Rect(0, 0, 100, 100), color=(1, 1, 1), fill=(1, 1, 1))
    dokument.save(str(p))
    dokument.close()

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])
    assert wynik.get("strony_bez_warstwy_tekstowej") == [0]


def _obraz_testowy(tmp_path, nazwa, tekst, rozmiar=(1400, 160), pozycja=(20, 40)):
    from PIL import Image, ImageDraw, ImageFont
    czcionka_projektu = Path(__file__).parent.parent / "anonimizator" / "czcionki" / "DejaVuSans-Bold.ttf"
    img = Image.new("RGB", rozmiar, color="white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(str(czcionka_projektu), 40)
    except Exception:
        font = ImageFont.load_default()
    # Spacja koncowa daje OCR margines - bez niej tekst tuz przy krawedzi
    # bywa ucinany (np. koncowka ".pl" e-maila), niezalezne od redakcji.
    d.text(pozycja, tekst + "  ", fill="black", font=font)
    sciezka = tmp_path / nazwa
    img.save(sciezka)
    return sciezka, img.size


def test_obraz_zachowuje_reszte_tresci_i_wymiary(tmp_path):
    """Kluczowa różnica względem starego trybu (nowy, pusty obraz z całym
    tekstem od nowa): reszta treści na obrazie i jego wymiary zostają
    nietknięte — tylko wykryty fragment jest zamalowany."""
    sciezka, rozmiar_oryg = _obraz_testowy(
        tmp_path, "notatka.png",
        "Numer akt: 123/24  Kontakt: jan.kowalski@przyklad.pl",
    )
    wynik = anonimizuj_plik(sciezka, tmp_path / "wynik", "Haslo123!", kategorie=["email"],
                             dolacz_prompt_ai=False)

    from PIL import Image
    obraz_wyn = Image.open(wynik["tekst"])
    assert obraz_wyn.size == rozmiar_oryg  # canvas nietknięty, nie zbudowany od nowa

    from anonimizator.extractors import wczytaj_tekst
    tekst_wynikowy = wczytaj_tekst(wynik["tekst"])
    assert "jan.kowalski@przyklad.pl" not in tekst_wynikowy
    assert "[EMAIL_1]" in tekst_wynikowy
    assert "Numer akt: 123/24" in tekst_wynikowy  # reszta treści zachowana


def test_obraz_prompt_ai_dopisany_jako_pas_u_gory(tmp_path):
    sciezka, rozmiar_oryg = _obraz_testowy(tmp_path, "pismo.png", "Kontakt: test@firma.pl")
    wynik = anonimizuj_plik(sciezka, tmp_path / "wynik", "Haslo123!", kategorie=["email"])

    from PIL import Image
    obraz_wyn = Image.open(wynik["tekst"])
    # prompt dopisany jako dodatkowy pas u gory -> obraz wynikowy wyzszy
    # niz oryginal, ta sama szerokosc
    assert obraz_wyn.size[0] == rozmiar_oryg[0]
    assert obraz_wyn.size[1] > rozmiar_oryg[1]
    assert wynik["prompt_ai"] != ""


def test_pdf_strona_skanowana_redagowana_przez_ocr(tmp_path):
    """Bonus tej sesji: strona-skan (obraz bez warstwy tekstowej) w PDF
    jest teraz redagowana przez tę samą technikę OCR co JPG/PNG, zamiast
    być tylko zgłaszaną jako niezredagowana."""
    import fitz
    sciezka_obrazu, _ = _obraz_testowy(
        tmp_path, "skan_wejsciowy.png", "Klient: Kowalski", rozmiar=(800, 150),
    )

    p = tmp_path / "skan.pdf"
    dokument = fitz.open()
    strona = dokument.new_page(width=800, height=150)
    strona.insert_image(strona.rect, filename=str(sciezka_obrazu))
    dokument.save(str(p))
    dokument.close()
    # potwierdzenie, ze to faktycznie strona bez warstwy tekstowej (czysty obraz)
    sprawdz = fitz.open(str(p))
    assert sprawdz[0].get_text().strip() == ""
    sprawdz.close()

    wynik = anonimizuj_plik(p, tmp_path / "wynik", "Haslo123!", kategorie=["imiona_nazwiska"])

    # strona zostala zredagowana przez fallback OCR, wiec NIE powinna
    # trafic na liste niezredagowanych
    assert not wynik.get("strony_bez_warstwy_tekstowej")

    import pytesseract
    sprawdz = fitz.open(str(wynik["tekst"]))
    pixmap = sprawdz[0].get_pixmap()
    from PIL import Image
    import io
    obraz_wyn = Image.open(io.BytesIO(pixmap.tobytes("png")))
    tekst_po_ocr = pytesseract.image_to_string(obraz_wyn, lang="pol+eng")
    sprawdz.close()
    assert "Kowalski" not in tekst_po_ocr
    # Nie sprawdzamy dokladnej tresci placeholdera przez re-OCR — male,
    # stylizowane tokeny jak "[OSOBA_1]" bywaja odczytywane niedokladnie
    # (np. nawiasy jako "()", "O" jako "0") niezaleznie od poprawnosci
    # samej redakcji. Istotne jest, ze oryginalna wartosc znikla.
