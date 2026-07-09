"""
Podstawowe testy jednostkowe recognizerów.

Uruchomienie: pytest tests/ -v
(dobry punkt startowy do rozbudowy o kolejne przypadki brzegowe)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from anonimizator.recognizers import (
    recognize_pesel, recognize_nip, recognize_email, recognize_iban,
    recognize_dowod_osobisty,
)
from anonimizator.anonimizator import anonimizuj_tekst


def test_pesel_poprawny_wykryty():
    wyniki = recognize_pesel("Numer PESEL: 44051401359 do weryfikacji.")
    assert len(wyniki) == 1
    assert wyniki[0].text == "44051401359"


def test_pesel_niepoprawna_suma_kontrolna_odrzucony():
    # 11 cyfr, ale zła suma kontrolna — nie powinno zostać wykryte jako PESEL
    wyniki = recognize_pesel("Numer: 11111111111")
    assert len(wyniki) == 0


def test_nip_z_myslnikami():
    wyniki = recognize_nip("NIP: 526-000-12-46")
    assert len(wyniki) == 1


def test_email_wykryty():
    wyniki = recognize_email("Kontakt: jan.kowalski@przyklad.pl")
    assert len(wyniki) == 1
    assert wyniki[0].text == "jan.kowalski@przyklad.pl"


def test_iban_poprawny():
    wyniki = recognize_iban("PL61109010140000071219812874")
    assert len(wyniki) == 1


def test_dowod_osobisty_poprawna_suma_kontrolna_wykryty():
    # Przykłady zweryfikowane niezależnie w 3 źródłach (Wikipedia PL,
    # romek.info, generatorliczb.pl) — dały ten sam wynik.
    wyniki = recognize_dowod_osobisty("Dowód nr ABS123456 okazany do wglądu.")
    assert len(wyniki) == 1
    assert wyniki[0].text == "ABS123456"

    wyniki = recognize_dowod_osobisty("Numer dokumentu: ABA300000")
    assert len(wyniki) == 1


def test_dowod_osobisty_niepoprawna_suma_kontrolna_odrzucony():
    # Ten sam kształt (3 litery + 6 cyfr), ale zmieniona cyfra kontrolna
    # (2 zamiast 1) — nie powinno przejść walidacji.
    wyniki = recognize_dowod_osobisty("Numer dokumentu: ABS223456")
    assert len(wyniki) == 0


def test_anonimizacja_pelnego_tekstu_spojnosc_tokenow():
    """Ta sama wartość powinna zawsze dostać ten sam token w całym dokumencie."""
    tekst = "Kontakt: jan@firma.pl. Proszę pisać na jan@firma.pl w tej sprawie."
    wynik = anonimizuj_tekst(tekst, kategorie=["email"])
    assert wynik.tekst_zanonimizowany.count("[EMAIL_1]") == 2
    assert wynik.mapowanie["[EMAIL_1]"] == "jan@firma.pl"


def test_deanonimizacja_przywraca_oryginal():
    from anonimizator.deanonimizator import deanonimizuj_tekst
    tekst = "Kontakt: jan@firma.pl"
    wynik = anonimizuj_tekst(tekst, kategorie=["email"])
    przywrocony = deanonimizuj_tekst(wynik.tekst_zanonimizowany, wynik.mapowanie)
    assert przywrocony == tekst
