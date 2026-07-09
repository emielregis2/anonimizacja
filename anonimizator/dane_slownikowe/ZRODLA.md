# Źródła danych słownikowych

Wszystkie poniższe dane pobrane bezpośrednio z dane.gov.pl (nie skopiowane
z żadnego produktu trzeciego), przetworzone lokalnymi skryptami do postaci
jednej pozycji na linię (deduplikacja, bez metadanych typu licznik
wystąpień czy przynależność administracyjna).

## nazwiska_pl.txt

- **Źródło:** Główny Urząd Statystyczny (GUS) / Ministerstwo Cyfryzacji
- **Dataset:** "Nazwiska osób żyjących występujące w rejestrze PESEL"
- **Adres:** https://dane.gov.pl/pl/dataset/1681
- **Stan na:** 2026-01-20 (zasoby: nazwiska żeńskie — resource 1148811,
  nazwiska męskie — resource 1148808)
- **Licencja:** CC0 1.0 (domena publiczna)
- **Liczba wpisów:** 598 476 unikalnych form (żeńskie + męskie łącznie,
  np. Kowalski/Kowalska liczone osobno)
- **Podstawa prawna udostępnienia:** ustawa z dnia 11 sierpnia 2021 r.
  o otwartych danych i ponownym wykorzystywaniu informacji sektora
  publicznego (Dz.U. 2021 poz. 1641)
- **Uwaga producenta danych:** nazwiska z pojedynczą liczbą wystąpień oraz
  dane osób zmarłych nie zostały uwzględnione w zestawieniu źródłowym —
  zbiór obejmuje też nazwiska obcego pochodzenia osób zameldowanych
  w Polsce (np. "Smith", "James" są realnie zarejestrowanymi nazwiskami).

## imiona_pl.txt

- **Źródło:** Główny Urząd Statystyczny (GUS) / Ministerstwo Cyfryzacji
- **Dataset:** "Lista imion występujących w rejestrze PESEL — osoby żyjące"
- **Adres:** https://dane.gov.pl/pl/dataset/1667
- **Licencja:** CC0 1.0 (domena publiczna)
- **Liczba wpisów:** 68 183 unikalnych imion (żeńskie + męskie, po
  deduplikacji — część imion unisex występuje w obu listach źródłowych)

## miasta_pl.txt

- **Źródło:** Ministerstwo Spraw Wewnętrznych i Administracji / GUS
  (rejestr TERYT, system SIMC)
- **Dataset:** "Wykaz urzędowych nazw miejscowości i ich części"
  (obwieszczenie MSWiA z 17 października 2019 r., poz. 2360, z późniejszymi
  aktualizacjami)
- **Adres:** https://dane.gov.pl/pl/dataset/188
- **Licencja:** dane publiczne (akt normatywny — obwieszczenie ministra)
- **Liczba wpisów:** 58 025 unikalnych nazw miejscowości i ich części
  (uwzględnia też przysiółki, kolonie, osady — nie tylko miasta i wsie
  jako całość)

## Uwaga dotycząca jakości wykrywania

Żaden z powyższych słowników nie obsługuje odmiany przez przypadki —
dopasowanie odbywa się po dokładnym dopasowaniu formy mianownikowej (lub
takiej, w jakiej dana wartość występuje w rejestrze źródłowym). Odmienione
formy ("Kowalskiego", "Krakowie") nie zostaną wykryte bez Trybu AI
(lokalny model spaCy, patrz ai_ner.py).

Dwa zabezpieczenia przed fałszywymi trafieniami (oba w
`slowniki_recognizers.py`), stosowane do samodzielnych nazwisk i do
miejscowości:

- `_na_poczatku_zdania` — pomija dopasowanie na samym początku zdania
  (każde zdanie zaczyna się wielką literą, niezależnie od tego, czy to
  akurat nazwisko/miejscowość, czy zwykłe słowo).
- `_tylko_to_slowo` — wyjątek od powyższego: jeśli cały przekazany
  fragment (np. cała komórka tabeli, całe pole formularza) to dokładnie
  to jedno dopasowanie, to nie jest to "zdanie" w sensie tego zabezpieczenia
  i dopasowanie jest przyjmowane mimo pozycji 0 — typowy przypadek to
  komórka tabeli zawierająca wyłącznie nazwisko.

Przy tak dużych bazach (598k nazwisk, 68k imion) trzeba liczyć się z tym,
że część zwykłych polskich słów jest jednocześnie realnie zarejestrowanym
imieniem lub nazwiskiem w PESEL — np. "Strona" i "Dane" to sprawdzone,
prawdziwe przykłady (odpowiednio nazwisko i imię). To świadomie
zaakceptowany kompromis recall/precyzja, nie błąd.
