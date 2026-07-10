# -*- coding: utf-8 -*-
"""
Testy Trybu AI (lokalny NER, spaCy `pl_core_news_lg`) — punkt 3 z listy
"Sugerowane następne kroki" w README: architektura była gotowa od dawna,
ale model nigdy nie był realnie przetestowany (żaden test w projekcie nie
używał tryb_ai=True przed tą sesją).

Testy poniżej opierają się na realistycznym (syntetycznym, ale
wiarygodnym) fragmencie pisma procesowego — zgodnie z zasadą, że nic nie
pokazuje rzeczywistego zachowania lepiej niż realistyczny przykład.
Wszystkie pomijane (skip), jeśli spaCy + pl_core_news_lg nie są
zainstalowane w środowisku (dokładnie ten sam wzorzec co przy testach
lematyzacji/Morfeusz2).

Instalacja: pip install spacy && python -m spacy download pl_core_news_lg
"""

import pytest
from anonimizator import anonimizuj_tekst
from anonimizator.ai_ner import dostepny_tryb_ai

pytestmark = pytest.mark.skipif(
    not dostepny_tryb_ai(), reason="spacy / pl_core_news_lg niezainstalowane"
)

PISMO_PROCESOWE = """Powód: Jan Kowalski, zamieszkały w Warszawie, wnosi pozew przeciwko
pozwanej spółce Nowak i Wspólnicy Sp. z o.o. z siedzibą w Poznaniu.

Sprawa dotyczy umowy zawartej z Xhavitem Berishą, obywatelem Albanii,
który działał w imieniu firmy Alpha Consulting Group.

Świadkiem w sprawie jest również Hans Mueller, który przebywał w
Krakowie w dniu zdarzenia. Kontakt do niego: hans.mueller@example.de.
"""


def test_tryb_ai_wykrywa_obce_nazwisko_spoza_slownikow():
    """Główna wartość Trybu AI: nazwisko, którego nie ma w żadnym
    załadowanym słowniku (tu: obywatel Albanii, pakiet językowy uk/fr/sk/cz
    ani tak nie pomógłby — to imię i nazwisko nie występują w żadnym z
    obecnych pakietów), jest kompletnie niewidoczne dla samych
    recognizerów słownikowych, ale zostaje wykryte przez lokalny NER."""
    bez_ai = anonimizuj_tekst(PISMO_PROCESOWE, kategorie=["imiona_nazwiska"], tryb_ai=False)
    assert "Berish" in bez_ai.tekst_zanonimizowany, \
        "test zakłada, że BEZ trybu AI to nazwisko faktycznie umyka -- " \
        "jeśli to się zmieni (np. rozszerzone słowniki), test trzeba zaktualizować"

    z_ai = anonimizuj_tekst(PISMO_PROCESOWE, kategorie=["imiona_nazwiska"], tryb_ai=True)
    assert "Berish" not in z_ai.tekst_zanonimizowany
    assert "Xhavitem Berishą" in z_ai.mapowanie.values()


def test_tryb_ai_grupuje_wieloczlonowa_nazwe_firmy_lepiej_niz_slownik():
    """Realny przykład z tej sesji: recognizer słownikowy nazwisk (598k
    pozycji z PESEL) błędnie łapie "Alpha Consulting" jako osobę (kolizja
    kategorii, patrz README "Znane ograniczenia"), zostawiając "Group" poza
    dopasowaniem. Tryb AI poprawnie grupuje całą nazwę "Alpha Consulting
    Group" jako jedną, spójną encję organizacji."""
    z_ai = anonimizuj_tekst(
        PISMO_PROCESOWE, kategorie=["imiona_nazwiska", "firmy_instytucje"], tryb_ai=True
    )
    assert "Alpha Consulting Group" not in z_ai.tekst_zanonimizowany
    assert "Group" not in z_ai.tekst_zanonimizowany, \
        "cala nazwa firmy powinna zniknac, nie tylko jej pierwsza czesc"


def test_tryb_ai_nie_psuje_zwyklej_detekcji_znanych_nazwisk():
    """Tryb AI ma być czystym uzupełnieniem — nazwiska już wykrywane przez
    recognizery słownikowe (Jan Kowalski, Hans Mueller) nadal muszą zniknąć
    z tekstu, niezależnie od tego, czy AI też je oznaczy (nakładanie się
    rozstrzyga _rozwiaz_nakladania w anonimizator.py)."""
    z_ai = anonimizuj_tekst(PISMO_PROCESOWE, kategorie=["imiona_nazwiska"], tryb_ai=True)
    assert "Jan Kowalski" not in z_ai.tekst_zanonimizowany
    assert "Hans Mueller" not in z_ai.tekst_zanonimizowany


def test_tryb_ai_email_nadal_wykrywany_przez_zwykly_recognizer():
    """Tryb AI dokłada tylko kategorie z _MAPA_ENCJI (osoby/firmy/miejsca)
    — e-mail nadal musi zostać złapany przez zwykły recognizer regex,
    niezależnie od tryb_ai."""
    z_ai = anonimizuj_tekst(PISMO_PROCESOWE, kategorie=["email"], tryb_ai=True)
    assert "hans.mueller@example.de" not in z_ai.tekst_zanonimizowany


def test_tryb_ai_znane_ograniczenie_skrot_spolki_akcyjnej():
    """UDOKUMENTOWANE OGRANICZENIE odkryte przy tym testowaniu: model NER
    (pl_core_news_lg) błędnie segmentuje skrót "S.A." na granicy zdania/
    nazwy, np. "Orlen S.A." bywa dzielone na organizację "Orlen S." i
    "osobę" "A.". Recall pozostaje wysoki (wartość i tak znika z tekstu),
    ale kategoria bywa błędna. Nie jest to błąd projektu — to ograniczenie
    samego modelu spaCy na skrótach z kropkami. Test dokumentuje aktualny
    stan, żeby ewentualna zmiana zachowania (np. przy aktualizacji modelu)
    była widoczna, a nie cicha."""
    tekst = "Pozwana spółka Orlen S.A. z siedzibą w Płocku odmówiła wypowiedzi."
    wynik = anonimizuj_tekst(
        tekst, kategorie=["firmy_instytucje", "imiona_nazwiska"], tryb_ai=True
    )
    # Cała wartość "Orlen S.A." znika z tekstu (recall zachowany) -- to
    # jest właściwa gwarancja, nie dokładność kategoryzacji.
    assert "Orlen S.A." not in wynik.tekst_zanonimizowany
    assert "Orlen" not in wynik.tekst_zanonimizowany


def test_tryb_ai_dziala_w_pelnym_przeplywie_pliku(tmp_path):
    """Test end-to-end z prawdziwym plikiem (nie tylko anonimizuj_tekst),
    żeby upewnić się, że tryb_ai przechodzi poprawnie przez cały
    anonimizuj_plik (w tym zapis/odczyt) bez wyjątków na realistycznym,
    wieloakapitowym dokumencie."""
    from anonimizator import anonimizuj_plik
    p = tmp_path / "pismo.txt"
    p.write_text(PISMO_PROCESOWE, encoding="utf-8")

    wynik = anonimizuj_plik(
        p, tmp_path / "wynik", "Haslo123!",
        kategorie=["imiona_nazwiska", "firmy_instytucje", "miasta", "email"],
        tryb_ai=True,
    )
    tresc = wynik["tekst"].read_text(encoding="utf-8")
    assert "Berish" not in tresc
    assert "hans.mueller@example.de" not in tresc


# --- Regresja: bug z zawijaniem wiersza znaleziony przy tym testowaniu ----
# Nie jest specyficzny dla Trybu AI, ale wyszedł na jaw właśnie przy
# testowaniu na realistycznym, wieloliniowym dokumencie (patrz notatka
# sesji) -- _na_poczatku_zdania traktowało KAŻDY pojedynczy znak nowej
# linii jako początek zdania, co w praktyce blokowało wykrycie słowa
# zaraz po zawinięciu wiersza w środku zdania.

def test_miasto_po_zawinieciu_wiersza_w_srodku_zdania_jest_wykrywane():
    from anonimizator.slowniki_recognizers import recognize_miasta
    tekst = "Świadkiem był również ktoś, kto przebywał w\nKrakowie w dniu zdarzenia."
    wyniki = recognize_miasta(tekst, jezyki=("pl",))
    assert len(wyniki) == 1
    assert wyniki[0].text == "Krakowie"


def test_nazwisko_po_zawinieciu_wiersza_w_srodku_zdania_jest_wykrywane():
    from anonimizator.slowniki_recognizers import recognize_imiona_nazwiska
    tekst = "Rozmawiałem wczoraj z panem, którego nazwisko to\nKowalski."
    wyniki = recognize_imiona_nazwiska(tekst, jezyki=("pl",))
    assert len(wyniki) == 1
    assert wyniki[0].text == "Kowalski"


def test_granica_akapitu_podwojny_enter_nadal_jest_poczatkiem_zdania():
    """Prawdziwa granica akapitu (pusty wiersz) nadal ma działać jako
    zabezpieczenie -- to nie jest to samo co zwykłe zawinięcie wiersza.
    Uwaga: celowo unikamy tu słowa "Polski" na końcu (dopełniacz "Polska"
    to znana kolizja słownikowa opisana w innych testach — chodzi wyłącznie
    o sprawdzenie zabezpieczenia "początek akapitu", nie o tę kolizję)."""
    from anonimizator.slowniki_recognizers import recognize_miasta
    tekst = "Pierwszy akapit kończy się tutaj bez żadnych nazw własnych.\n\nWarszawa ma wielu mieszkańców."
    wyniki = recognize_miasta(tekst, jezyki=("pl",))
    assert len(wyniki) == 0, \
        "Warszawa jest pierwszym slowem nowego akapitu -- zabezpieczenie powinno zadzialac"
