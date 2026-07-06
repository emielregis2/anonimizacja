"""
Szyfrowanie pliku mapowania token -> dane rzeczywiste.

W przeciwieństwie do rozwiązań, w których plik mapowania jest jedynie
zakodowany (np. Base64 — to NIE jest szyfrowanie, tylko kodowanie
odwracalne bez klucza), tutaj:

  1. Klucz szyfrujący jest pochodną hasła użytkownika (PBKDF2-HMAC-SHA256,
     600 000 iteracji, losowa sól zapisana razem z plikiem — sól nie jest
     tajemnicą, ale spowalnia ataki słownikowe/bruteforce).
  2. Samo szyfrowanie to Fernet (AES-128-CBC + HMAC-SHA256 do integralności),
     zaimplementowane w bibliotece `cryptography`.
  3. Hasło NIGDY nie jest zapisywane na dysku — trzeba je znać, żeby
     odszyfrować mapowanie. Sama anonimizowana treść pozostaje czytelna
     i użyteczna bez hasła; tylko oryginalne dane są niedostępne bez klucza.

Konsekwencja bezpieczeństwa: jeśli ktoś przejmie sam plik .enc, bez hasła
nie odzyska danych osobowych (w przeciwieństwie do kodowania Base64,
które każdy odwróci w 2 sekundy).
"""

from __future__ import annotations
import base64
import json
import os
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERACJE_KDF = 600_000
DLUGOSC_SOLI = 16


class BladDeszyfrowania(Exception):
    """Błędne hasło lub uszkodzony/naruszony plik mapowania."""


def _wyprowadz_klucz(haslo: str, sol: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=sol,
        iterations=ITERACJE_KDF,
    )
    return base64.urlsafe_b64encode(kdf.derive(haslo.encode("utf-8")))


def zaszyfruj_mapowanie(mapowanie: dict[str, str], haslo: str) -> bytes:
    """Zwraca zawartość pliku .enc: [16 bajtów soli][token Fernet]."""
    sol = os.urandom(DLUGOSC_SOLI)
    klucz = _wyprowadz_klucz(haslo, sol)
    fernet = Fernet(klucz)
    dane = json.dumps(mapowanie, ensure_ascii=False).encode("utf-8")
    token = fernet.encrypt(dane)
    return sol + token


def odszyfruj_mapowanie(zawartosc: bytes, haslo: str) -> dict[str, str]:
    sol, token = zawartosc[:DLUGOSC_SOLI], zawartosc[DLUGOSC_SOLI:]
    klucz = _wyprowadz_klucz(haslo, sol)
    fernet = Fernet(klucz)
    try:
        dane = fernet.decrypt(token)
    except InvalidToken as e:
        raise BladDeszyfrowania(
            "Nieprawidłowe hasło albo plik mapowania został zmodyfikowany/uszkodzony."
        ) from e
    return json.loads(dane.decode("utf-8"))
