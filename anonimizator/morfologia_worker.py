#!/usr/bin/env python3
"""
Proces roboczy dla lematyzacji (Morfeusz2), uruchamiany jako osobny
podproces przez morfologia.py.

Celowo NIGDY nie importuje fitz/pymupdf ani żadnych innych modułów
projektu — to jedyny sens tego pliku: fizyczne odizolowanie Morfeusz2
od PyMuPDF w oddzielnych przestrzeniach adresowych procesu, bo oba w tym
samym procesie powodują twardy crash (naruszenie dostępu do pamięci,
zweryfikowane eksperymentalnie, patrz morfologia.py).

Protokół: jedna linia JSON na wejściu (stdin) = lista słów do
zanalizowania, jedna linia JSON na wyjściu (stdout) = lista list lematów,
równoległa do listy wejściowej (dla i-tego słowa wejściowego,
wynik[i] to posortowana lista jego możliwych lematów, małymi literami).
Działa w pętli aż do zamknięcia stdin (EOF) — jeden długożyjący proces
obsługuje wiele zapytań, nie nowy proces na każde słowo (zbyt wolne).

Uruchomienie ręczne do testów:
    echo ["Kowalskiego"] | python morfologia_worker.py
"""
import sys
import json

# Wymuszenie UTF-8 na stdin/stdout tego procesu — bez tego, na Windows,
# domyślne kodowanie konsoli (np. cp1250) psuje polskie znaki w locie,
# mimo że proces rodzica prosi o UTF-8 po swojej stronie potoku (Popen
# encoding="utf-8" kontroluje tylko interpretację po stronie rodzica,
# nie to, czym dziecko faktycznie koduje bajty, które wysyła).
sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")


def main():
    try:
        import morfeusz2
        morf = morfeusz2.Morfeusz()
    except Exception as e:
        # Sygnalizujemy blad startowy jedna linia, zeby proces rodzica
        # nie czekal w nieskonczonosc na odpowiedz, ktora nigdy nie przyjdzie.
        print(json.dumps({"__blad_startu__": str(e)}), flush=True)
        return

    for linia in sys.stdin:
        linia = linia.strip()
        if not linia:
            continue
        try:
            slowa = json.loads(linia)
        except Exception:
            print(json.dumps([]), flush=True)
            continue

        wynik = []
        for slowo in slowa:
            lematy_slowa = set()
            try:
                for _start, _koniec, interpretacja in morf.analyse(slowo):
                    lemat = interpretacja[1].split(":")[0]
                    lematy_slowa.add(lemat.lower())
            except Exception:
                pass
            if not lematy_slowa:
                lematy_slowa.add(slowo.lower())
            wynik.append(sorted(lematy_slowa))

        print(json.dumps(wynik, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
