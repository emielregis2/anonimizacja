# Źródła danych słownikowych

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
  dane osób zmarłych nie zostały uwzględnione w zestawieniu źródłowym.

Pobrane bezpośrednio z dane.gov.pl (nie skopiowane z żadnego produktu
trzeciego), przetworzone lokalnym skryptem do postaci jednej nazwy na
linię (deduplikacja, bez licznika wystąpień).

## imiona_pl.txt

Wersja podstawowa (157 imion) — bez formalnej dokumentacji źródła w chwili
utworzenia tego pliku. Do rozważenia: rozszerzenie o dataset
https://dane.gov.pl/pl/dataset/1667 ("Lista imion występujących w rejestrze
PESEL — osoby żyjące", CC0 1.0) — imiona żeńskie (~26 811) i męskie
(~44 676) pobrane, ale jeszcze niezintegrowane (stan: [uzupełnić przy
integracji]).

## miasta_pl.txt

Bez formalnej dokumentacji źródła w chwili utworzenia tego pliku.
