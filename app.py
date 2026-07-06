#!/usr/bin/env python3
"""
Lokalna aplikacja webowa modułu anonimizacji — działa wyłącznie na
localhost (127.0.0.1), bez żadnej komunikacji z internetem.

Uruchomienie: python app.py  →  http://127.0.0.1:5000
"""

from __future__ import annotations
import io
import tempfile
import time
import traceback
import uuid
from pathlib import Path

from flask import Flask, request, render_template_string, send_file, jsonify

from anonimizator import (
    anonimizuj_plik, anonimizuj_wiele_plikow, anonimizuj_bip,
    deanonimizuj_tekst, WSZYSTKIE_KATEGORIE, STYLE_MASKOWANIA,
    NieodwracalnyStylMaskowania, generuj_raport_pdf,
)
from anonimizator.anonimizator import ETYKIETY_KATEGORII
from anonimizator.extractors import FORMATY_WSPIERANE

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB (wiele plików naraz)

JEZYKI_ETYKIETY = {
    "pl": "Polski", "uk": "Wielka Brytania", "fr": "Francja",
    "sk": "Słowacja", "cz": "Czechy",
}

STYLE_ETYKIETY = {
    "pelny_token": "Pełny token — [OSOBA_1]  (w pełni odwracalny)",
    "etykieta": "Neutralna etykieta — Osoba A  (w pełni odwracalny, czytelniejszy)",
    "inicjaly": "Inicjały / częściowa maska — J. K.  (odwracalny)",
    "puste": "Puste miejsce — [USUNIĘTE]  (NIEODWRACALNY, maksymalna ochrona)",
}

# Sesje w pamięci — trzymają odszyfrowane mapowanie tylko na czas potrzebny
# do wygodnego auto-wklejania (funkcja "Wklej odpowiedź AI"). Wygasają same
# po 30 minutach albo po ręcznym kliknięciu "Zamknij sesję".
_SESJE: dict[str, dict] = {}
CZAS_ZYCIA_SESJI_S = 30 * 60


def _wyczysc_wygasle_sesje():
    teraz = time.time()
    wygasle = [sid for sid, s in _SESJE.items() if teraz - s["utworzono"] > CZAS_ZYCIA_SESJI_S]
    for sid in wygasle:
        _SESJE.pop(sid, None)


SZABLON = """
<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<title>Anonimizator dokumentów</title>
<style>
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 1100px;
         margin: 30px auto; color: #1a1a1a; padding: 0 16px; }
  h1 { font-size: 22px; font-weight: 600; margin-bottom: 4px; }
  h2 { font-size: 16px; font-weight: 600; margin: 22px 0 8px; }
  .layout { display: flex; gap: 28px; align-items: flex-start; }
  .kolumna { flex: 1; min-width: 0; }
  .strefa { border: 2px dashed #9aa; border-radius: 10px; padding: 30px;
            text-align: center; color: #556; cursor: pointer; margin-bottom: 14px; }
  .strefa.aktywna { background: #eef4ff; border-color: #3878e0; }
  .kategorie { display: flex; flex-wrap: wrap; gap: 5px 16px; margin: 10px 0; font-size: 13px; }
  .kategorie label { white-space: nowrap; }
  .sekcja { border: 1px solid #ddd; border-radius: 8px; padding: 12px 14px; margin: 10px 0; }
  .pasek { display: flex; gap: 10px; align-items: center; margin: 10px 0; flex-wrap: wrap; }
  input[type=password], input[type=text], select { padding: 6px 10px; font-size: 13px; }
  button { padding: 8px 16px; font-size: 14px; cursor: pointer; }
  textarea { width: 100%; box-sizing: border-box; font-size: 13px; padding: 8px; }
  #wynik, #wynik_deanon { white-space: pre-wrap; background: #f6f6f6; padding: 12px;
           border-radius: 6px; font-size: 13px; margin-top: 10px; }
  .uwaga { background: #fff6e0; border-left: 4px solid #e0a800; padding: 8px 12px;
           font-size: 12.5px; margin: 10px 0; }
  .uwaga.blad { background: #ffe9e9; border-left-color: #c0392b; }
  small { color: #667; }
  .plik-lista { font-size: 12.5px; margin: 6px 0; }
</style>
</head>
<body>
<h1>Anonimizator dokumentów (wersja lokalna)</h1>
<p style="font-size:13px;color:#667">Działa wyłącznie lokalnie — żaden plik ani jego treść nie
opuszcza tego komputera. Formaty: {{ formaty }} (skany PDF i obrazy — automatyczny OCR).</p>

<div class="layout">
<div class="kolumna">

<h2>1. Anonimizacja</h2>
<div id="strefa" class="strefa">Kliknij, aby wybrać plik(i), albo przeciągnij i upuść tutaj
(można wybrać wiele naraz)
<br><input type="file" id="plik" style="display:none" multiple></div>
<div class="plik-lista" id="lista_plikow"></div>

<div class="sekcja">
  <strong>Kategorie danych</strong>
  <div class="kategorie" id="kategorie">
  {% for kod, etykieta in kategorie.items() %}
    <label><input type="checkbox" name="kat" value="{{ kod }}" checked> {{ etykieta }}</label>
  {% endfor %}
  </div>
</div>

<div class="sekcja">
  <div class="pasek">
    <label>Styl maskowania:
      <select id="styl">
      {% for kod, etykieta in style.items() %}
        <option value="{{ kod }}">{{ etykieta }}</option>
      {% endfor %}
      </select>
    </label>
  </div>
  <div class="pasek">
    <label><input type="checkbox" id="tryb_ai"> Tryb AI (lokalny NER, dodatkowe wykrywanie)</label>
    <label><input type="checkbox" id="usun_strony"> Usuń numery stron</label>
  </div>
  <div class="pasek">
    <span>Języki słowników (imiona/miasta):</span>
    {% for kod, etykieta in jezyki.items() %}
      <label><input type="checkbox" name="jezyk" value="{{ kod }}" {% if kod == 'pl' %}checked{% endif %}> {{ etykieta }}</label>
    {% endfor %}
  </div>
  <div class="pasek" id="pasek_wiele_plikow" style="display:none">
    <span>Wiele plików:</span>
    <label><input type="radio" name="tryb_wsad" value="niezalezne" checked> Niezależne dokumenty</label>
    <label><input type="radio" name="tryb_wsad" value="jedna_sprawa"> Jedna sprawa (spójne tokeny)</label>
  </div>
</div>

<div class="sekcja">
  <label><input type="checkbox" id="tryb_bip" onchange="przelaczBip()"> <strong>Tryb Archiwum/BIP</strong>
  — anonimizacja bezpowrotna, bez hasła, do publikacji</label>
  <div class="uwaga" id="opis_bip" style="display:none">
    W tym trybie nie da się NIGDY odzyskać oryginalnych danych — nie ma pliku mapowania ani hasła.
  </div>
</div>

<div class="pasek" id="pasek_haslo">
  <input type="password" id="haslo" placeholder="Hasło szyfrujące mapowanie" size="28">
  <label><input type="checkbox" id="raport_pdf"> Dołącz raport PDF (zabezpieczony tym hasłem)</label>
</div>

<div class="uwaga">Zapamiętaj hasło — nie jest nigdzie zapisywane. Bez niego mapowanie jest nieodwracalne.</div>

<button onclick="anonimizuj()">Anonimizuj</button>
<div id="wynik"></div>

</div>

<div class="kolumna" style="max-width:380px">
<h2>2. Wklej odpowiedź AI (auto-deanonimizacja)</h2>
<p style="font-size:12.5px;color:#667">Po anonimizacji wklej tu odpowiedź modelu AI (zawierającą
te same tokeny/etykiety) — automatycznie wrócą prawdziwe dane. Dostępne tylko dla stylów
odwracalnych i tylko przez czas trwania tej sesji przeglądarki.</p>
<textarea id="wklejka_ai" rows="10" placeholder="Wklej tu (Ctrl+V) odpowiedź AI..."
  oninput="autoDeanonimizuj()"></textarea>
<div id="wynik_deanon"></div>
<button onclick="zamknijSesje()" style="margin-top:8px">Zamknij sesję (wyczyść dane z pamięci)</button>
</div>

</div>

<script>
let PLIKI = [];
let SESJA_ID = null;

const strefa = document.getElementById('strefa');
const input = document.getElementById('plik');
strefa.addEventListener('click', () => input.click());
strefa.addEventListener('dragover', e => { e.preventDefault(); strefa.classList.add('aktywna'); });
strefa.addEventListener('dragleave', () => strefa.classList.remove('aktywna'));
strefa.addEventListener('drop', e => {
  e.preventDefault(); strefa.classList.remove('aktywna');
  ustawPliki(e.dataTransfer.files);
});
input.addEventListener('change', () => ustawPliki(input.files));

function ustawPliki(files) {
  PLIKI = Array.from(files);
  document.getElementById('lista_plikow').innerHTML =
    PLIKI.map(f => `• ${f.name}`).join('<br>');
  document.getElementById('pasek_wiele_plikow').style.display = PLIKI.length > 1 ? 'flex' : 'none';
}

function przelaczBip() {
  const bip = document.getElementById('tryb_bip').checked;
  document.getElementById('pasek_haslo').style.display = bip ? 'none' : 'flex';
  document.getElementById('opis_bip').style.display = bip ? 'block' : 'none';
}

async function anonimizuj() {
  const wynikDiv = document.getElementById('wynik');
  if (!PLIKI.length) { wynikDiv.textContent = 'Najpierw wybierz plik(i).'; return; }

  const trybBip = document.getElementById('tryb_bip').checked;
  const haslo = document.getElementById('haslo').value;
  if (!trybBip && !haslo) { wynikDiv.textContent = 'Podaj hasło szyfrujące (albo włącz Tryb Archiwum/BIP).'; return; }

  const dane = new FormData();
  PLIKI.forEach(f => dane.append('pliki', f));
  dane.append('haslo', haslo);
  dane.append('tryb_ai', document.getElementById('tryb_ai').checked);
  dane.append('usun_numery_stron', document.getElementById('usun_strony').checked);
  dane.append('styl', document.getElementById('styl').value);
  dane.append('tryb_bip', trybBip);
  dane.append('raport_pdf', document.getElementById('raport_pdf').checked);
  const trybWsadRadio = document.querySelector('input[name=tryb_wsad]:checked');
  dane.append('tryb_wsad', trybWsadRadio ? trybWsadRadio.value : 'niezalezne');
  document.querySelectorAll('input[name=kat]:checked').forEach(el => dane.append('kategorie', el.value));
  document.querySelectorAll('input[name=jezyk]:checked').forEach(el => dane.append('jezyki', el.value));

  wynikDiv.textContent = 'Przetwarzanie (OCR skanów może potrwać dłużej)...';
  const odpowiedz = await fetch('/anonimizuj', { method: 'POST', body: dane });
  const json = await odpowiedz.json();
  if (json.blad) { wynikDiv.innerHTML = '<div class="uwaga blad">Błąd: ' + json.blad + '</div>'; return; }

  SESJA_ID = json.sesja_id || null;

  let html = '<strong>Gotowe.</strong> Wykryte kategorie:<br>';
  for (const [k, v] of Object.entries(json.liczba_wykryc || {})) html += `&nbsp;&nbsp;${k}: ${v}<br>`;
  html += '<br>Pobierz pliki:<br>';
  (json.pliki || []).forEach(p => {
    html += `<a href="/pobierz/${p.id}" target="_blank">${p.nazwa}</a><br>`;
  });
  if (!json.pliki || !json.pliki.length) html = 'Brak plików do pobrania.';
  if (trybBip) {
    html += '<br><em>Tryb Archiwum/BIP — bez pliku mapowania, bez możliwości odzyskania danych.</em>';
  } else if (SESJA_ID) {
    html += '<br><small>Panel po prawej ("Wklej odpowiedź AI") jest teraz aktywny dla tej sesji.</small>';
  }
  wynikDiv.innerHTML = html;
}

let debounceTimer = null;
function autoDeanonimizuj() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const tekst = document.getElementById('wklejka_ai').value;
    const wynikDiv = document.getElementById('wynik_deanon');
    if (!tekst.trim()) { wynikDiv.textContent = ''; return; }
    if (!SESJA_ID) { wynikDiv.innerHTML = '<div class="uwaga">Najpierw wykonaj anonimizację (styl odwracalny) w tej samej sesji.</div>'; return; }

    const odpowiedz = await fetch('/deanonimizuj_fragment', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ sesja_id: SESJA_ID, tekst: tekst }),
    });
    const json = await odpowiedz.json();
    if (json.blad) { wynikDiv.innerHTML = '<div class="uwaga blad">' + json.blad + '</div>'; return; }
    wynikDiv.textContent = json.tekst;
  }, 250);
}

async function zamknijSesje() {
  if (SESJA_ID) {
    await fetch('/zamknij_sesje/' + SESJA_ID, { method: 'POST' });
    SESJA_ID = null;
  }
  document.getElementById('wklejka_ai').value = '';
  document.getElementById('wynik_deanon').textContent = 'Sesja zamknięta — dane usunięte z pamięci serwera.';
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        SZABLON,
        kategorie={k: ETYKIETY_KATEGORII.get(k, k) for k in WSZYSTKIE_KATEGORIE},
        style=STYLE_ETYKIETY,
        jezyki=JEZYKI_ETYKIETY,
        formaty=", ".join(sorted(FORMATY_WSPIERANE)),
    )


@app.route("/anonimizuj", methods=["POST"])
def anonimizuj():
    _wyczysc_wygasle_sesje()
    try:
        pliki = request.files.getlist("pliki")
        if not pliki:
            return jsonify({"blad": "Nie przesłano żadnego pliku."}), 400

        kategorie = request.form.getlist("kategorie") or WSZYSTKIE_KATEGORIE
        jezyki = request.form.getlist("jezyki") or ["pl"]
        tryb_ai = request.form.get("tryb_ai") == "true"
        usun_numery_stron = request.form.get("usun_numery_stron") == "true"
        styl = request.form.get("styl", "pelny_token")
        tryb_bip = request.form.get("tryb_bip") == "true"
        chce_raport = request.form.get("raport_pdf") == "true"
        tryb_wsad = request.form.get("tryb_wsad", "niezalezne")
        haslo = request.form.get("haslo", "")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sciezki_wejsciowe = []
            for plik in pliki:
                sciezka = tmp_path / plik.filename
                plik.save(sciezka)
                sciezki_wejsciowe.append(sciezka)

            katalog_wyjsciowy = tmp_path / "wynik"
            pliki_do_pobrania = []
            sesja_id = None
            mapowanie_jawne = {}
            liczba_wykryc = {}

            if tryb_bip:
                for sciezka in sciezki_wejsciowe:
                    sciezka_wyn = anonimizuj_bip(
                        sciezka, katalog_wyjsciowy, kategorie=kategorie,
                        tryb_ai=tryb_ai, usun_numery_stron=usun_numery_stron, jezyki=jezyki,
                    )
                    pliki_do_pobrania.append(sciezka_wyn)

            elif len(sciezki_wejsciowe) > 1:
                wynik = anonimizuj_wiele_plikow(
                    sciezki_wejsciowe, katalog_wyjsciowy, haslo, tryb=tryb_wsad,
                    kategorie=kategorie, tryb_ai=tryb_ai,
                    usun_numery_stron=usun_numery_stron, styl=styl, jezyki=jezyki,
                )
                liczba_wykryc = wynik.get("liczba_wykryc", {})
                mapowanie_jawne = wynik.get("mapowanie_jawne", {})
                if tryb_wsad == "jedna_sprawa":
                    pliki_do_pobrania += list(wynik["pliki_tekst"].values())
                    pliki_do_pobrania.append(wynik["mapowanie"])
                else:
                    for dane in wynik["pliki"].values():
                        pliki_do_pobrania.append(dane["tekst"])
                        pliki_do_pobrania.append(dane["mapowanie"])
                        for k, v in dane["liczba_wykryc"].items():
                            liczba_wykryc[k] = liczba_wykryc.get(k, 0) + v
                        mapowanie_jawne.update(dane.get("mapowanie_jawne", {}))
            else:
                wynik = anonimizuj_plik(
                    sciezki_wejsciowe[0], katalog_wyjsciowy, haslo,
                    kategorie=kategorie, tryb_ai=tryb_ai,
                    usun_numery_stron=usun_numery_stron, styl=styl, jezyki=jezyki,
                )
                liczba_wykryc = wynik["liczba_wykryc"]
                mapowanie_jawne = wynik["mapowanie_jawne"]
                pliki_do_pobrania += [wynik["tekst"], wynik["mapowanie"]]

            if chce_raport and not tryb_bip and mapowanie_jawne:
                sciezka_raport = katalog_wyjsciowy / "raport.pdf"
                generuj_raport_pdf(mapowanie_jawne, haslo, sciezka_raport, nazwa_dokumentu="dokumenty")
                pliki_do_pobrania.append(sciezka_raport)

            pliki_wynikowe = []
            for sciezka in pliki_do_pobrania:
                fid = str(uuid.uuid4())
                _PLIKI_DO_POBRANIA[fid] = {"dane": sciezka.read_bytes(), "nazwa": sciezka.name}
                pliki_wynikowe.append({"id": fid, "nazwa": sciezka.name})

            if not tryb_bip and styl != "puste" and mapowanie_jawne:
                sesja_id = str(uuid.uuid4())
                _SESJE[sesja_id] = {"mapowanie": mapowanie_jawne, "utworzono": time.time()}

        return jsonify({
            "sesja_id": sesja_id,
            "liczba_wykryc": liczba_wykryc,
            "pliki": pliki_wynikowe,
        })
    except NieodwracalnyStylMaskowania as e:
        return jsonify({"blad": str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"blad": str(e)}), 400


_PLIKI_DO_POBRANIA: dict[str, dict] = {}


@app.route("/pobierz/<plik_id>")
def pobierz(plik_id):
    wpis = _PLIKI_DO_POBRANIA.get(plik_id)
    if not wpis:
        return "Plik wygasł — uruchom anonimizację ponownie.", 404
    return send_file(io.BytesIO(wpis["dane"]), as_attachment=True, download_name=wpis["nazwa"])


@app.route("/deanonimizuj_fragment", methods=["POST"])
def deanonimizuj_fragment():
    _wyczysc_wygasle_sesje()
    dane = request.get_json(force=True)
    sesja = _SESJE.get(dane.get("sesja_id", ""))
    if not sesja:
        return jsonify({"blad": "Sesja wygasła albo nie istnieje — wykonaj anonimizację ponownie."}), 404
    try:
        przywrocony = deanonimizuj_tekst(dane.get("tekst", ""), sesja["mapowanie"])
        return jsonify({"tekst": przywrocony})
    except NieodwracalnyStylMaskowania as e:
        return jsonify({"blad": str(e)}), 400


@app.route("/zamknij_sesje/<sesja_id>", methods=["POST"])
def zamknij_sesje(sesja_id):
    _SESJE.pop(sesja_id, None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("Uruchamiam lokalnie: http://127.0.0.1:5000  (Ctrl+C aby zatrzymać)")
    app.run(host="127.0.0.1", port=5000, debug=False)
