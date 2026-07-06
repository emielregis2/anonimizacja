"""
Tryb AI — opcjonalne wzbogacenie detekcji o lokalny model NER (spaCy).

Ważne z punktu widzenia bezpieczeństwa: model NER działa WYŁĄCZNIE lokalnie
(na komputerze użytkownika), nie ma tu żadnego wywołania sieciowego ani API
zewnętrznego LLM. To celowa różnica względem podejścia "wyślij tekst do
chmury AI" — tutaj żadne dane nie opuszczają maszyny nawet w Trybie AI.

Wymaga: pip install spacy && python -m spacy download pl_core_news_lg
Jeśli model nie jest zainstalowany, Tryb AI jest po prostu pomijany
(reszta modułu działa normalnie na recognizerach regex/słownikowych).
"""

from __future__ import annotations
from .recognizers import Match

_NLP = None
_PROBOWANO_ZALADOWAC = False

_MAPA_ENCJI = {
    "persName": "imiona_nazwiska",
    "PERSON": "imiona_nazwiska",
    "orgName": "firmy_instytucje",
    "ORG": "firmy_instytucje",
    "placeName": "miasta",
    "GPE": "miasta",
    "LOC": "miasta",
}


def _zaladuj_model():
    global _NLP, _PROBOWANO_ZALADOWAC
    if _PROBOWANO_ZALADOWAC:
        return _NLP
    _PROBOWANO_ZALADOWAC = True
    try:
        import spacy
        _NLP = spacy.load("pl_core_news_lg")
    except Exception:
        try:
            import spacy
            _NLP = spacy.load("pl_core_news_sm")
        except Exception:
            _NLP = None
    return _NLP


def dostepny_tryb_ai() -> bool:
    return _zaladuj_model() is not None


def recognize_ai(text: str) -> list[Match]:
    """Zwraca dodatkowe dopasowania z lokalnego modelu NER (jeśli dostępny)."""
    nlp = _zaladuj_model()
    if nlp is None:
        return []
    wyniki = []
    doc = nlp(text)
    for ent in doc.ents:
        kategoria = _MAPA_ENCJI.get(ent.label_)
        if kategoria:
            wyniki.append(Match(ent.start_char, ent.end_char, ent.text, kategoria))
    return wyniki
