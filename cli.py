#!/usr/bin/env python3
"""
Interfejs linii poleceń modułu anonimizacji.

Przykłady:
  # Pojedynczy plik, wszystkie kategorie, styl domyślny:
  python cli.py anonimizuj dokument.docx --haslo "MojeHaslo123!" --wszystko

  # Ze stylem "etykieta" i raportem PDF:
  python cli.py anonimizuj skan.pdf --haslo "MojeHaslo123!" --wszystko \\
      --styl etykieta --raport-pdf

  # Skan/obraz — OCR włączony domyślnie:
  python cli.py anonimizuj skan_faktury.jpg --haslo "MojeHaslo123!" --wszystko

  # Wiele plików tej samej sprawy, spójne tokeny:
  python cli.py anonimizuj-wsadowo pismo1.docx pismo2.pdf pismo3.txt \\
      --haslo "MojeHaslo123!" --wszystko --tryb jedna_sprawa

  # Tryb Archiwum/BIP — bezpowrotny, bez hasła:
  python cli.py anonimizuj-bip dokument.docx --wszystko

  # Z dodatkowymi językami (partner z Francji i Słowacji):
  python cli.py anonimizuj dokument.docx --haslo "..." --wszystko --jezyki pl,fr,sk

  # Przywrócenie oryginału:
  python cli.py deanonimizuj dokument_anon.pdf dokument_mapowanie.enc \\
      --haslo "MojeHaslo123!"
"""

from __future__ import annotations
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from anonimizator import (
    anonimizuj_plik, anonimizuj_wiele_plikow, anonimizuj_bip,
    deanonimizuj_plik, WSZYSTKIE_KATEGORIE, STYLE_MASKOWANIA,
    BladDeszyfrowania, generuj_raport_pdf,
)
from anonimizator.ai_ner import dostepny_tryb_ai


def _pobierz_haslo(args) -> str:
    if args.haslo:
        return args.haslo
    haslo = getpass.getpass("Podaj hasło szyfrujące mapowanie: ")
    potwierdzenie = getpass.getpass("Powtórz hasło: ")
    if haslo != potwierdzenie:
        print("Hasła się nie zgadzają.", file=sys.stderr)
        sys.exit(1)
    return haslo


def _ustal_kategorie(args) -> list[str]:
    if args.wszystko:
        return WSZYSTKIE_KATEGORIE
    if args.kategorie:
        kategorie = args.kategorie.split(",")
        nieznane = set(kategorie) - set(WSZYSTKIE_KATEGORIE)
        if nieznane:
            print(f"Nieznane kategorie: {nieznane}\nDostępne: {WSZYSTKIE_KATEGORIE}", file=sys.stderr)
            sys.exit(1)
        return kategorie
    print("Podaj --kategorie lub --wszystko", file=sys.stderr)
    sys.exit(1)


def _ostrzez_o_trybie_ai(args):
    if getattr(args, "tryb_ai", False) and not dostepny_tryb_ai():
        print("Uwaga: Tryb AI zażądany, ale model spaCy (pl_core_news_lg/sm) "
              "nie jest zainstalowany — kontynuuję bez Trybu AI.\n"
              "Instalacja: pip install spacy && python -m spacy download pl_core_news_lg",
              file=sys.stderr)


def _wypisz_wykrycia(liczba_wykryc: dict):
    print("\nLiczba wykrytych elementów wg kategorii:")
    for kategoria, liczba in sorted(liczba_wykryc.items()):
        print(f"  {kategoria}: {liczba}")
    if not liczba_wykryc:
        print("  (brak wykryć w wybranych kategoriach)")


def cmd_anonimizuj(args):
    sciezka = Path(args.plik)
    if not sciezka.exists():
        print(f"Nie znaleziono pliku: {sciezka}", file=sys.stderr)
        sys.exit(1)

    kategorie = _ustal_kategorie(args)
    _ostrzez_o_trybie_ai(args)
    jezyki = args.jezyki.split(",") if args.jezyki else ["pl"]

    haslo = _pobierz_haslo(args)
    wynik = anonimizuj_plik(
        sciezka, Path(args.katalog_wyjsciowy), haslo,
        kategorie=kategorie, tryb_ai=args.tryb_ai,
        usun_numery_stron=args.usun_numery_stron,
        styl=args.styl, jezyki=jezyki,
        dolacz_prompt_ai=not args.bez_promptu_ai,
        zachowaj_layout=not args.bez_zachowania_layoutu,
    )

    print(f"Zapisano: {wynik['tekst']}")
    print(f"Zapisano (zaszyfrowane): {wynik['mapowanie']}")
    _wypisz_wykrycia(wynik["liczba_wykryc"])
    if wynik.get("strony_bez_warstwy_tekstowej"):
        print(f"UWAGA: strony {wynik['strony_bez_warstwy_tekstowej']} (0-indeksowane) "
              "wyglądają na skan bez warstwy tekstowej — NIE zostały zredagowane.")

    if args.raport_pdf:
        sciezka_raportu = Path(args.katalog_wyjsciowy) / f"{sciezka.stem}_raport.pdf"
        generuj_raport_pdf(wynik["mapowanie_jawne"], haslo, sciezka_raportu, nazwa_dokumentu=sciezka.name)
        print(f"Zapisano raport PDF (zabezpieczony tym samym hasłem): {sciezka_raportu}")

    if args.styl != "puste":
        print("\nWAŻNE: zapamiętaj hasło. Bez niego mapowania NIE da się odszyfrować.")
    else:
        print("\nUwaga: styl 'puste' jest celowo NIEODWRACALNY — hasło chroni tu "
              "wyłącznie plik mapowania/raportu do celów audytu, nie umożliwia "
              "automatycznego przywrócenia tekstu.")


def cmd_anonimizuj_wsadowo(args):
    sciezki = [Path(p) for p in args.pliki]
    brakujace = [p for p in sciezki if not p.exists()]
    if brakujace:
        print(f"Nie znaleziono plików: {brakujace}", file=sys.stderr)
        sys.exit(1)

    kategorie = _ustal_kategorie(args)
    _ostrzez_o_trybie_ai(args)
    jezyki = args.jezyki.split(",") if args.jezyki else ["pl"]
    haslo = _pobierz_haslo(args)

    wynik = anonimizuj_wiele_plikow(
        sciezki, Path(args.katalog_wyjsciowy), haslo, tryb=args.tryb,
        kategorie=kategorie, tryb_ai=args.tryb_ai,
        usun_numery_stron=args.usun_numery_stron, styl=args.styl, jezyki=jezyki,
        dolacz_prompt_ai=not args.bez_promptu_ai,
        zachowaj_layout=not args.bez_zachowania_layoutu,
    )

    print(f"Tryb: {wynik['tryb']}")
    if wynik["tryb"] == "jedna_sprawa":
        for nazwa, sciezka in wynik["pliki_tekst"].items():
            print(f"  {nazwa} -> {sciezka}")
        print(f"Wspólne mapowanie (zaszyfrowane): {wynik['mapowanie']}")
        _wypisz_wykrycia(wynik["liczba_wykryc"])
        if args.raport_pdf:
            sciezka_raportu = Path(args.katalog_wyjsciowy) / "sprawa_raport.pdf"
            generuj_raport_pdf(wynik["mapowanie_jawne"], haslo, sciezka_raportu, nazwa_dokumentu="sprawa (wiele plików)")
            print(f"Raport PDF: {sciezka_raportu}")
    else:
        for nazwa, dane in wynik["pliki"].items():
            print(f"  {nazwa}: {dane['tekst']} + {dane['mapowanie']}")

    print("\nWAŻNE: zapamiętaj hasło. Bez niego mapowania NIE da się odszyfrować.")


def cmd_anonimizuj_bip(args):
    sciezka = Path(args.plik)
    if not sciezka.exists():
        print(f"Nie znaleziono pliku: {sciezka}", file=sys.stderr)
        sys.exit(1)

    kategorie = _ustal_kategorie(args)
    _ostrzez_o_trybie_ai(args)
    jezyki = args.jezyki.split(",") if args.jezyki else ["pl"]

    sciezka_wynikowa = anonimizuj_bip(
        sciezka, Path(args.katalog_wyjsciowy),
        kategorie=kategorie, tryb_ai=args.tryb_ai,
        usun_numery_stron=args.usun_numery_stron, jezyki=jezyki,
    )
    print(f"Zapisano (tryb Archiwum/BIP, bezpowrotnie): {sciezka_wynikowa}")
    print("Brak pliku hasła/mapowania — to zamierzone. Tego dokumentu nie da się odwrócić.")


def cmd_deanonimizuj(args):
    sciezka_tekst = Path(args.plik_tekst)
    sciezka_mapowanie = Path(args.plik_mapowanie)
    for p in (sciezka_tekst, sciezka_mapowanie):
        if not p.exists():
            print(f"Nie znaleziono pliku: {p}", file=sys.stderr)
            sys.exit(1)

    haslo = args.haslo or getpass.getpass("Podaj hasło szyfrujące mapowanie: ")
    if args.wyjscie:
        sciezka_wyjsciowa = Path(args.wyjscie)
    else:
        nazwa_bazowa = sciezka_tekst.stem.replace("_anon_BIP", "").replace("_anon", "")
        sciezka_wyjsciowa = sciezka_tekst.with_name(f"{nazwa_bazowa}_oryginal{sciezka_tekst.suffix}")

    try:
        deanonimizuj_plik(sciezka_tekst, sciezka_mapowanie, haslo, sciezka_wyjsciowa)
    except BladDeszyfrowania as e:
        print(f"Błąd: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Przywrócono oryginał: {sciezka_wyjsciowa}")


def _dodaj_wspolne_argumenty(parser):
    parser.add_argument("--katalog-wyjsciowy", default="./wynik")
    parser.add_argument("--haslo", default=None)
    parser.add_argument("--kategorie", default=None)
    parser.add_argument("--wszystko", action="store_true")
    parser.add_argument("--tryb-ai", action="store_true")
    parser.add_argument("--usun-numery-stron", action="store_true")
    parser.add_argument("--styl", default="pelny_token", choices=STYLE_MASKOWANIA)
    parser.add_argument("--jezyki", default=None, help="np. pl,fr,sk (domyślnie: pl)")
    parser.add_argument("--raport-pdf", action="store_true",
                         help="Dodatkowo wygeneruj czytelny raport PDF zabezpieczony tym samym hasłem")
    parser.add_argument("--bez-promptu-ai", action="store_true",
                         help="Nie dołączaj automatycznie promptu dla AI na początku pliku wynikowego "
                              "(domyślnie prompt jest dołączany, żeby plik był samowystarczalny)")
    parser.add_argument("--bez-zachowania-layoutu", action="store_true",
                         help="Dla DOCX/PDF: wymuś stary tryb 'wyciągnij tekst -> zbuduj dokument "
                              "od nowa' zamiast domyślnej edycji w miejscu z zachowaniem formatowania, "
                              "tabel, obrazów i (dla PDF) prawdziwą redakcją tekstu")


def main():
    parser = argparse.ArgumentParser(description="Moduł anonimizacji dokumentów")
    subparsers = parser.add_subparsers(required=True)

    p_anon = subparsers.add_parser("anonimizuj", help="Anonimizuje pojedynczy plik")
    p_anon.add_argument("plik")
    _dodaj_wspolne_argumenty(p_anon)
    p_anon.set_defaults(func=cmd_anonimizuj)

    p_wsad = subparsers.add_parser("anonimizuj-wsadowo", help="Anonimizuje wiele plików naraz")
    p_wsad.add_argument("pliki", nargs="+")
    p_wsad.add_argument("--tryb", default="niezalezne", choices=["jedna_sprawa", "niezalezne"])
    _dodaj_wspolne_argumenty(p_wsad)
    p_wsad.set_defaults(func=cmd_anonimizuj_wsadowo)

    p_bip = subparsers.add_parser("anonimizuj-bip", help="Tryb Archiwum/BIP — bezpowrotny, bez hasła")
    p_bip.add_argument("plik")
    p_bip.add_argument("--katalog-wyjsciowy", default="./wynik_bip")
    p_bip.add_argument("--kategorie", default=None)
    p_bip.add_argument("--wszystko", action="store_true")
    p_bip.add_argument("--tryb-ai", action="store_true")
    p_bip.add_argument("--usun-numery-stron", action="store_true")
    p_bip.add_argument("--jezyki", default=None)
    p_bip.set_defaults(func=cmd_anonimizuj_bip)

    p_deanon = subparsers.add_parser("deanonimizuj", help="Przywraca oryginał")
    p_deanon.add_argument("plik_tekst")
    p_deanon.add_argument("plik_mapowanie")
    p_deanon.add_argument("--haslo", default=None)
    p_deanon.add_argument("--wyjscie", default=None)
    p_deanon.set_defaults(func=cmd_deanonimizuj)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
