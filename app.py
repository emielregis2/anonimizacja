#!/usr/bin/env python3
"""
Lokalna aplikacja webowa modułu anonimizacji — działa wyłącznie na
localhost (127.0.0.1), bez żadnej komunikacji z internetem.

Uruchomienie: python app.py  →  http://127.0.0.1:5000
"""

from __future__ import annotations
import io
import json
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
from anonimizator.anonimizator import ETYKIETY_KATEGORII, GRANICA_PROMPTU_AI
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
  :root {
    --bg-chrome: #0b0b0b;
    --bg-chrome-2: #1d1f21;
    --teal: #3fd7c4;
    --teal-dim: #2a9d8f;
    --ink: #101214;
    --ink-soft: #545c64;
    --paper: #ffffff;
    --paper-2: #f2f3f4;
    --line: #d7dbe0;
    --maroon: #7a3428;
    --warn-bg: #fff6e0;
    --warn-line: #e0a800;
    --err-bg: #ffe9e9;
    --err-line: #c0392b;
    --mono: Consolas, "SFMono-Regular", "Courier New", monospace;
    --sans: -apple-system, "Segoe UI", Arial, sans-serif;
  }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: var(--sans); color: var(--ink); background: var(--paper-2); font-size: 13px; }

  .chrome-top { background: var(--bg-chrome); color: #cfd3d6; padding: 10px 18px;
                display: flex; align-items: center; justify-content: space-between;
                flex-wrap: wrap; gap: 10px; }
  .brand { display:flex; align-items:center; gap:10px; }
  .brand .ikona { font-family: var(--mono); font-size: 18px; color: var(--teal); }
  .brand h1 { font-family: var(--mono); font-size: 16px; font-weight:700; margin:0;
              color:#f2f3f4; letter-spacing:.3px; }
  .brand small { display:block; font-family: var(--mono); font-size: 11px; color:#8a9096; margin-top:1px; }
  .nav-info { display:flex; gap:18px; }
  .nav-info button { background:none; border:none; color: var(--teal); font-family: var(--mono);
                      font-size: 11.5px; cursor:pointer; letter-spacing:.5px; padding:2px 0; }
  .nav-info button:hover { text-decoration: underline; }

  .tabs { display:flex; gap:2px; background: var(--bg-chrome); padding: 0 18px 10px; }
  .tab { font-family: var(--mono); font-size: 11.5px; letter-spacing:.4px; padding: 9px 16px;
         cursor:pointer; border: none; color: #b7bcc1; background: var(--bg-chrome-2); }
  .tab.aktywna { background: var(--paper); color: var(--ink); font-weight:700; }

  .info-panel { background:#141618; color:#cfd3d6; font-family: var(--mono); font-size:12px;
                padding:10px 18px; border-bottom:1px solid #2a2c2e; line-height:1.7; display:none; }
  .info-panel.widoczny { display:block; }

  .toolbar { background: var(--paper); padding: 12px 18px; border-bottom: 1px solid var(--line); }
  .wiersz { display:flex; align-items:center; gap:10px; margin-bottom:8px; flex-wrap:wrap; }
  .etykieta-wiersza { font-family: var(--mono); font-size: 11px; color: var(--ink-soft);
                       width: 150px; flex-shrink:0; letter-spacing:.3px; }
  .strefa { flex:1; min-width:260px; border: 1px dashed #aab2ba; border-radius: 3px;
            padding: 9px 12px; font-size:12.5px; color:#5a636b; cursor:pointer; background:#fafbfc; }
  .strefa.aktywna { background:#eaf7f4; border-color: var(--teal-dim); }

  .kategorie-blok { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line);
                     padding: 10px 0; margin: 10px 0; }
  .kategorie-tytul { font-family: var(--mono); font-size:10.5px; color: var(--ink-soft);
                      letter-spacing:.4px; margin-bottom:6px; }
  .kategorie { display:flex; flex-wrap:wrap; gap: 5px 20px; font-size:12.5px; }
  .kategorie label { white-space:nowrap; display:flex; align-items:center; gap:5px; }
  .kategorie input { accent-color: var(--maroon); }

  .opcje { display:flex; flex-wrap:wrap; gap: 9px 26px; align-items:center; margin: 9px 0; font-size: 12.5px; }
  select, input[type=password], input[type=text] { font-family: var(--sans); font-size:12.5px;
      padding: 5px 8px; border:1px solid var(--line); border-radius:3px; }

  .pasek-akcji { display:flex; align-items:center; gap:14px; margin-top: 10px; }
  .btn-start { font-family: var(--mono); background: var(--bg-chrome); color: var(--teal);
               border:none; padding: 10px 24px; font-size:12.5px; letter-spacing:.5px;
               cursor:pointer; border-radius:2px; }
  .btn-start:hover { background: var(--bg-chrome-2); }

  .body-3col { display:grid; grid-template-columns: 280px 1fr 1fr; gap:0;
               min-height: 320px; border-top:1px solid var(--line); }
  .panel { border-right: 1px solid var(--line); display:flex; flex-direction:column; background:#fff; }
  .panel:last-child { border-right:none; }
  .panel-head { background: var(--bg-chrome); color:#dfe2e5; font-family: var(--mono);
                font-size:11px; letter-spacing:.6px; padding: 7px 12px; }
  .panel-body { padding: 10px 12px; font-size:12.5px; flex:1; overflow:auto; }
  .stan-pusty { color:#9aa1a8; font-size:12px; font-style: italic; }

  table.wykryte { width:100%; border-collapse: collapse; font-size:12px; }
  table.wykryte th { text-align:left; font-family: var(--mono); font-size:10px; color: var(--ink-soft);
                      border-bottom:1px solid var(--line); padding: 4px 4px; letter-spacing:.3px; }
  table.wykryte td { padding: 4px 4px; border-bottom: 1px solid #eef0f2; }
  table.wykryte tr:hover td { background: #f7f9fa; }

  .plik-lista { font-size:12px; margin-top:8px; line-height:1.7; }

  .uwaga { background: var(--warn-bg); border-left: 3px solid var(--warn-line);
           padding: 7px 10px; font-size:12px; margin: 8px 0; }
  .uwaga.blad { background: var(--err-bg); border-left-color: var(--err-line); }

  textarea { width:100%; box-sizing:border-box; font-size:12.5px; padding:8px;
             border:1px solid var(--line); border-radius:3px; font-family: var(--sans); }

  .status-bar { background: var(--bg-chrome); color:#9aa0a6; font-family: var(--mono);
                font-size:11px; padding:7px 18px; display:flex; gap:20px; align-items:center; }
  .status-bar b { color:#dfe2e5; }
  .status-bar .prawo { margin-left:auto; color:#5f6569; }

  a { color: #185fa5; }
  .tab-panel { display:none; }
  .tab-panel.aktywny { display:block; }
</style>
</head>
<body>

<div class="chrome-top">
  <div class="brand">
    <span class="ikona">&#9776;</span>
    <div>
      <h1>Anonimizator dokumentów</h1>
      <small>Moduł anonimizacji — działa wyłącznie lokalnie (offline)</small>
    </div>
  </div>
  <div class="nav-info">
    <button type="button" onclick="pokazInfo('ustawienia')">USTAWIENIA</button>
    <button type="button" onclick="pokazInfo('pomoc')">POMOC</button>
    <button type="button" onclick="pokazInfo('nota')">NOTA PRAWNA</button>
  </div>
</div>

<div class="tabs">
  <button type="button" class="tab aktywna" id="tab-anon" onclick="pokazTab('anon')">ANONIMIZACJA</button>
  <button type="button" class="tab" id="tab-deanon" onclick="pokazTab('deanon')">DEANONIMIZACJA</button>
  <button type="button" class="tab" id="tab-bip" onclick="pokazTabBip()">ARCHIWUM / BIP</button>
</div>

<div class="info-panel" id="info-ustawienia">
Brak dodatkowych ustawień w tej wersji — wszystkie opcje przetwarzania znajdują się w panelu ANONIMIZACJA.
</div>
<div class="info-panel" id="info-pomoc">
1. Wybierz plik lub przeciągnij go do pola poniżej.&nbsp; 2. Zaznacz kategorie danych do wykrycia.&nbsp;
3. Podaj hasło szyfrujące mapowanie (albo włącz tryb Archiwum/BIP dla anonimizacji bezpowrotnej).&nbsp;
4. Kliknij Anonimizuj.&nbsp; 5. W zakładce DEANONIMIZACJA możesz wkleić odpowiedź AI, aby automatycznie
przywrócić prawdziwe dane (tylko style odwracalne, w ramach tej samej sesji).
</div>
<div class="info-panel" id="info-nota">
Aplikacja działa wyłącznie lokalnie (127.0.0.1) — żaden plik ani jego treść nie opuszcza tego
komputera i nie jest wysyłany do żadnego zewnętrznego serwera ani modelu AI. Mapowanie tokenów na
oryginalne dane jest szyfrowane hasłem podanym przez użytkownika i nie jest nigdzie zapisywane w
postaci jawnej.
</div>

<div class="tab-panel aktywny" id="panel-anon">

<div class="toolbar">

  <div class="wiersz">
    <span class="etykieta-wiersza">PLIK(I) WEJŚCIOWE:</span>
    <div id="strefa" class="strefa">Kliknij, aby wybrać plik(i), albo przeciągnij i upuść tutaj
      (można wybrać wiele naraz) — formaty: {{ formaty }} (skany PDF i obrazy: automatyczny OCR)
      <input type="file" id="plik" style="display:none" multiple></div>
    <button type="button" class="btn-start" id="btn_przegladaj_dysk" onclick="wybierzZDysku()"
      style="background:#2a2c2e;flex-shrink:0"
      title="Otwiera systemowe okno wyboru pliku — pozwala zapisać wynik obok źródła">PRZEGLĄDAJ (DYSK)</button>
  </div>
  <div class="wiersz" id="wiersz_sciezek_dysk" style="display:none">
    <span class="etykieta-wiersza"></span>
    <div class="plik-lista" id="lista_sciezek_dysk" style="font-size:12px;color:var(--ink-soft)"></div>
  </div>

  <div class="kategorie-blok">
    <div class="kategorie-tytul">KATEGORIE DANYCH</div>
    <div class="kategorie" id="kategorie">
    {% for kod, etykieta in kategorie.items() %}
      <label><input type="checkbox" name="kat" value="{{ kod }}" checked> {{ etykieta }}</label>
    {% endfor %}
    </div>
  </div>

  <div class="opcje">
    <label>Styl maskowania:
      <select id="styl">
      {% for kod, etykieta in style.items() %}
        <option value="{{ kod }}">{{ etykieta }}</option>
      {% endfor %}
      </select>
    </label>
    <label><input type="checkbox" id="tryb_ai"> Tryb AI (lokalny NER, dodatkowe wykrywanie)</label>
    <label><input type="checkbox" id="usun_strony"> Usuń numery stron</label>
    <label><input type="checkbox" id="dolacz_prompt" checked
      title="Dopisuje na początku pliku wynikowego instrukcję dla AI, by nie zmieniała placeholderów — przydatne przy masowym przetwarzaniu serii dokumentów.">
      Dołącz prompt dla AI do pliku wynikowego</label>
  </div>

  <div class="opcje">
    <span style="font-family:var(--mono);font-size:10.5px;color:var(--ink-soft);letter-spacing:.3px">JĘZYKI SŁOWNIKÓW:</span>
    {% for kod, etykieta in jezyki.items() %}
      <label><input type="checkbox" name="jezyk" value="{{ kod }}" {% if kod == 'pl' %}checked{% endif %}> {{ etykieta }}</label>
    {% endfor %}
  </div>

  <div class="opcje" id="pasek_wiele_plikow" style="display:none">
    <span style="font-family:var(--mono);font-size:10.5px;color:var(--ink-soft);letter-spacing:.3px">WIELE PLIKÓW:</span>
    <label><input type="radio" name="tryb_wsad" value="niezalezne" checked> Niezależne dokumenty</label>
    <label><input type="radio" name="tryb_wsad" value="jedna_sprawa"> Jedna sprawa (spójne tokeny)</label>
  </div>

  <div class="wiersz" style="margin-top:4px">
    <label><input type="checkbox" id="tryb_bip" onchange="przelaczBip()"> <strong>Tryb Archiwum/BIP</strong>
      — anonimizacja bezpowrotna, bez hasła, do publikacji</label>
  </div>
  <div class="uwaga" id="opis_bip" style="display:none">
    W tym trybie nie da się NIGDY odzyskać oryginalnych danych — nie ma pliku mapowania ani hasła.
  </div>

  <div class="opcje" id="pasek_haslo">
    <input type="password" id="haslo" placeholder="Hasło szyfrujące mapowanie" size="28">
    <label><input type="checkbox" id="raport_pdf"> Dołącz raport PDF (zabezpieczony tym hasłem)</label>
  </div>
  <div class="uwaga">Zapamiętaj hasło — nie jest nigdzie zapisywane. Bez niego mapowanie jest nieodwracalne.</div>

  <div class="pasek-akcji">
    <button class="btn-start" onclick="anonimizuj()">&#9654; ROZPOCZNIJ ANONIMIZACJĘ</button>
  </div>

</div>

<div class="body-3col">
  <div class="panel">
    <div class="panel-head">WYKRYTE DANE</div>
    <div class="panel-body" id="panel_wykryte">
      <span class="stan-pusty">Brak danych — uruchom anonimizację</span>
    </div>
  </div>
  <div class="panel">
    <div class="panel-head">PLIKI</div>
    <div class="panel-body">
      <span class="stan-pusty" id="stan_pusty_pliki">Wybierz lub przeciągnij plik(i) powyżej</span>
      <div class="plik-lista" id="lista_plikow"></div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-head">WYNIK</div>
    <div class="panel-body" id="wynik">
      <span class="stan-pusty">Zanonimizowany dokument pojawi się tutaj po przetworzeniu</span>
    </div>
  </div>
</div>

<div class="body-3col" id="blok_prompt_ai" style="display:none;grid-template-columns:1fr;border-top:none">
  <div class="panel">
    <div class="panel-head">PROMPT DOŁĄCZONY DO PLIKU WYNIKOWEGO</div>
    <div class="panel-body">
      <p id="prompt_ai_uwaga" style="font-size:12px;color:var(--ink-soft);margin:0 0 8px;display:none"></p>
      <pre id="tresc_prompt_ai" style="white-space:pre-wrap;font-family:var(--sans);font-size:12.5px;margin:0"></pre>
    </div>
  </div>
</div>

</div>

<div class="tab-panel" id="panel-deanon">
<div class="body-3col" style="grid-template-columns: 1fr 1fr">
  <div class="panel">
    <div class="panel-head">WKLEJ TEKST (ODPOWIEDŹ AI)</div>
    <div class="panel-body">
      <p style="font-size:12px;color:var(--ink-soft);margin-top:0">Po anonimizacji wklej tu
        odpowiedź modelu AI (zawierającą te same tokeny/etykiety) — automatycznie wrócą
        prawdziwe dane. Dostępne tylko dla stylów odwracalnych i tylko przez czas trwania tej
        sesji.</p>
      <textarea id="wklejka_ai" rows="12" placeholder="Wklej tu (Ctrl+V) odpowiedź AI..."
        oninput="autoDeanonimizuj()"></textarea>
      <div class="pasek-akcji">
        <button class="btn-start" onclick="zamknijSesje()">ZAMKNIJ SESJĘ</button>
      </div>
    </div>
  </div>
  <div class="panel">
    <div class="panel-head">WYNIK DEANONIMIZACJI</div>
    <div class="panel-body" id="wynik_deanon">
      <span class="stan-pusty">Wynik pojawi się tutaj po wklejeniu tekstu</span>
    </div>
  </div>
</div>
</div>

<div class="status-bar">
  <span>STAN: <b id="status_stan">GOTOWY</b></span>
  <span>TRYB: <b id="status_tryb">ANONIMIZACJA</b></span>
  <span>OFFLINE</span>
  <span>PLIKÓW: <b id="status_plikow">0</b></span>
  <span>CZAS: <b id="status_czas">-</b></span>
  <span class="prawo">Moduł anonimizacja — Dariusz Gąsior</span>
</div>

<script>
let PLIKI = [];
let SCIEZKI_DYSK = [];
let SESJA_ID = null;
let OSTATNI_TEKST_KOPIA = '';

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
  SCIEZKI_DYSK = [];
  document.getElementById('wiersz_sciezek_dysk').style.display = 'none';
  document.getElementById('lista_sciezek_dysk').innerHTML = '';
  document.getElementById('lista_plikow').innerHTML =
    PLIKI.map(f => `&bull; ${f.name}`).join('<br>');
  document.getElementById('stan_pusty_pliki').style.display = PLIKI.length ? 'none' : 'block';
  document.getElementById('pasek_wiele_plikow').style.display = PLIKI.length > 1 ? 'flex' : 'none';
  document.getElementById('status_plikow').textContent = PLIKI.length;
}

async function wybierzZDysku() {
  const btn = document.getElementById('btn_przegladaj_dysk');
  btn.disabled = true;
  btn.textContent = 'CZEKAM NA OKNO...';
  try {
    const odpowiedz = await fetch('/wybierz_pliki_dysk', { method: 'POST' });
    const json = await odpowiedz.json();
    if (json.sciezki && json.sciezki.length) {
      SCIEZKI_DYSK = json.sciezki;
      PLIKI = [];
      input.value = '';
      document.getElementById('lista_plikow').innerHTML = '';
      document.getElementById('stan_pusty_pliki').style.display = 'none';
      document.getElementById('wiersz_sciezek_dysk').style.display = 'flex';
      document.getElementById('lista_sciezek_dysk').innerHTML =
        SCIEZKI_DYSK.map(s => `&bull; ${s}`).join('<br>') +
        '<br><em>Wynik zostanie zapisany obok pliku(ów) źródłowego(ych).</em>';
      document.getElementById('pasek_wiele_plikow').style.display = SCIEZKI_DYSK.length > 1 ? 'flex' : 'none';
      document.getElementById('status_plikow').textContent = SCIEZKI_DYSK.length;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'PRZEGLĄDAJ (DYSK)';
  }
}

function przelaczBip() {
  const bip = document.getElementById('tryb_bip').checked;
  document.getElementById('pasek_haslo').style.display = bip ? 'none' : 'flex';
  document.getElementById('opis_bip').style.display = bip ? 'block' : 'none';
  document.getElementById('status_tryb').textContent = bip ? 'ARCHIWUM / BIP' : 'ANONIMIZACJA';
}

function pokazTab(nazwa) {
  document.getElementById('panel-anon').classList.toggle('aktywny', nazwa === 'anon');
  document.getElementById('panel-deanon').classList.toggle('aktywny', nazwa === 'deanon');
  document.getElementById('tab-anon').classList.toggle('aktywna', nazwa === 'anon');
  document.getElementById('tab-deanon').classList.toggle('aktywna', nazwa === 'deanon');
  document.getElementById('tab-bip').classList.remove('aktywna');
  if (nazwa === 'deanon') document.getElementById('status_tryb').textContent = 'DEANONIMIZACJA';
  else przelaczBip();
}

function pokazTabBip() {
  document.getElementById('tryb_bip').checked = true;
  przelaczBip();
  pokazTab('anon');
  document.getElementById('tab-bip').classList.add('aktywna');
  document.getElementById('tab-anon').classList.remove('aktywna');
}

function pokazInfo(nazwa) {
  ['ustawienia', 'pomoc', 'nota'].forEach(n => {
    const el = document.getElementById('info-' + n);
    if (n === nazwa) el.classList.toggle('widoczny');
    else el.classList.remove('widoczny');
  });
}

function wypelnijTabeleWykryte(liczbaWykryc) {
  const cel = document.getElementById('panel_wykryte');
  const wpisy = Object.entries(liczbaWykryc || {});
  if (!wpisy.length) {
    cel.innerHTML = '<span class="stan-pusty">Nie wykryto żadnych danych w wybranych kategoriach</span>';
    return;
  }
  let html = '<table class="wykryte"><tr><th>Kategoria</th><th style="text-align:right">Liczba</th></tr>';
  wpisy.forEach(([k, v]) => { html += `<tr><td>${k}</td><td style="text-align:right">${v}</td></tr>`; });
  html += '</table>';
  cel.innerHTML = html;
}

async function kopiujZPromptem() {
  const status = document.getElementById('kopiuj_status');
  try {
    await navigator.clipboard.writeText(OSTATNI_TEKST_KOPIA);
    if (status) status.textContent = 'Skopiowano do schowka.';
  } catch (e) {
    if (status) status.textContent = 'Nie udało się skopiować automatycznie — zaznacz i skopiuj ręcznie.';
  }
}

function wypelnijBlokPromptu(promptAi, wieluPlikow) {
  const blok = document.getElementById('blok_prompt_ai');
  const uwaga = document.getElementById('prompt_ai_uwaga');
  const tresc = document.getElementById('tresc_prompt_ai');
  if (!promptAi) {
    blok.style.display = 'none';
    return;
  }
  blok.style.display = 'grid';
  tresc.textContent = promptAi;
  if (wieluPlikow) {
    uwaga.style.display = 'block';
    uwaga.textContent = 'Przykład z pierwszego pliku — każdy plik w tej partii ma własny prompt, ' +
      'dopasowany do tokenów faktycznie w nim występujących (otwórz dany plik, aby go zobaczyć).';
  } else {
    uwaga.style.display = 'none';
  }
}

async function anonimizuj() {
  const wynikDiv = document.getElementById('wynik');
  const trybDysk = SCIEZKI_DYSK.length > 0;
  if (!trybDysk && !PLIKI.length) { wynikDiv.innerHTML = '<div class="uwaga blad">Najpierw wybierz plik(i).</div>'; return; }

  const trybBip = document.getElementById('tryb_bip').checked;
  const haslo = document.getElementById('haslo').value;
  if (!trybBip && !haslo) {
    wynikDiv.innerHTML = '<div class="uwaga blad">Podaj hasło szyfrujące (albo włącz Tryb Archiwum/BIP).</div>';
    return;
  }

  const dane = new FormData();
  if (trybDysk) {
    dane.append('sciezki_dysk', JSON.stringify(SCIEZKI_DYSK));
  } else {
    PLIKI.forEach(f => dane.append('pliki', f));
  }
  dane.append('haslo', haslo);
  dane.append('tryb_ai', document.getElementById('tryb_ai').checked);
  dane.append('usun_numery_stron', document.getElementById('usun_strony').checked);
  dane.append('dolacz_prompt_ai', document.getElementById('dolacz_prompt').checked);
  dane.append('styl', document.getElementById('styl').value);
  dane.append('tryb_bip', trybBip);
  dane.append('raport_pdf', document.getElementById('raport_pdf').checked);
  const trybWsadRadio = document.querySelector('input[name=tryb_wsad]:checked');
  dane.append('tryb_wsad', trybWsadRadio ? trybWsadRadio.value : 'niezalezne');
  document.querySelectorAll('input[name=kat]:checked').forEach(el => dane.append('kategorie', el.value));
  document.querySelectorAll('input[name=jezyk]:checked').forEach(el => dane.append('jezyki', el.value));

  const start = performance.now();
  document.getElementById('status_stan').textContent = 'PRZETWARZANIE...';
  wynikDiv.innerHTML = '<span class="stan-pusty">Przetwarzanie (OCR skanów może potrwać dłużej)...</span>';

  const odpowiedz = await fetch('/anonimizuj', { method: 'POST', body: dane });
  const json = await odpowiedz.json();
  const czas = ((performance.now() - start) / 1000).toFixed(1) + 's';
  document.getElementById('status_czas').textContent = czas;
  document.getElementById('status_stan').textContent = 'GOTOWY';

  if (json.blad) {
    wynikDiv.innerHTML = '<div class="uwaga blad">Błąd: ' + json.blad + '</div>';
    return;
  }

  SESJA_ID = json.sesja_id || null;
  OSTATNI_TEKST_KOPIA = json.tekst_do_kopiowania || '';
  wypelnijTabeleWykryte(json.liczba_wykryc);
  wypelnijBlokPromptu(json.prompt_ai, json.prompt_wielu_plikow);

  let html = '<strong>Gotowe.</strong> Wykryte kategorie:<br>';
  for (const [k, v] of Object.entries(json.liczba_wykryc || {})) html += `&nbsp;&nbsp;${k}: ${v}<br>`;
  if (json.strony_bez_warstwy_tekstowej && json.strony_bez_warstwy_tekstowej.length) {
    const numery = json.strony_bez_warstwy_tekstowej.map(n => n + 1).join(', ');
    html += `<div class="uwaga blad"><strong>Uwaga:</strong> strona(y) ${numery} PDF nie mają ` +
      'warstwy tekstowej (wyglądają na skan) i NIE zostały zredagowane tą ścieżką — sprawdź je ' +
      'ręcznie albo przetwórz plik ponownie.</div>';
  }
  if (trybDysk && json.zapisano && json.zapisano.length) {
    html += '<br><strong>Zapisano obok źródła:</strong><br>';
    json.zapisano.forEach(p => { html += `&nbsp;&nbsp;${p}<br>`; });
  }
  if (OSTATNI_TEKST_KOPIA) {
    html += '<br><button class="btn-start" style="padding:7px 14px;font-size:11.5px" ' +
      'onclick="kopiujZPromptem()">KOPIUJ TEKST (Z PROMPTEM)</button>' +
      '<span id="kopiuj_status" style="margin-left:8px;font-size:11.5px;color:var(--ink-soft)"></span><br>';
  }
  html += '<br>Pobierz pliki (kopia):<br>';
  (json.pliki || []).forEach(p => {
    html += `<a href="/pobierz/${p.id}" target="_blank">${p.nazwa}</a><br>`;
  });
  if (!json.pliki || !json.pliki.length) html = 'Brak plików do pobrania.';
  if (trybBip) {
    html += '<br><em>Tryb Archiwum/BIP — bez pliku mapowania, bez możliwości odzyskania danych.</em>';
  } else if (SESJA_ID) {
    html += '<br><small>Zakładka DEANONIMIZACJA jest teraz aktywna dla tej sesji.</small>';
  }
  wynikDiv.innerHTML = html;
}

let debounceTimer = null;
function autoDeanonimizuj() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(async () => {
    const tekst = document.getElementById('wklejka_ai').value;
    const wynikDiv = document.getElementById('wynik_deanon');
    if (!tekst.trim()) { wynikDiv.innerHTML = '<span class="stan-pusty">Wynik pojawi się tutaj po wklejeniu tekstu</span>'; return; }
    if (!SESJA_ID) {
      wynikDiv.innerHTML = '<div class="uwaga">Najpierw wykonaj anonimizację (styl odwracalny) w zakładce ANONIMIZACJA.</div>';
      return;
    }
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
  document.getElementById('wynik_deanon').innerHTML = '<span class="stan-pusty">Sesja zamknięta — dane usunięte z pamięci serwera.</span>';
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


@app.route("/wybierz_pliki_dysk", methods=["POST"])
def wybierz_pliki_dysk():
    """Otwiera natywne okno wyboru pliku Windows (proces Flask działa lokalnie,
    więc ma pełny dostęp do systemu plików tej samej maszyny). Zwraca pełne
    ścieżki — dzięki temu wynik można zapisać obok pliku źródłowego, czego
    zwykły upload w przeglądarce nie umożliwia (przeglądarka celowo ukrywa
    pełną ścieżkę wybranego pliku)."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    sciezki = filedialog.askopenfilenames(title="Wybierz plik(i) do anonimizacji")
    root.destroy()
    return jsonify({"sciezki": list(sciezki)})


@app.route("/anonimizuj", methods=["POST"])
def anonimizuj():
    _wyczysc_wygasle_sesje()
    try:
        sciezki_dysk_raw = request.form.get("sciezki_dysk", "")
        tryb_dysk = bool(sciezki_dysk_raw)

        if not tryb_dysk and not request.files.getlist("pliki"):
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
        dolacz_prompt_ai = request.form.get("dolacz_prompt_ai", "true") == "true"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zapisano_obok_zrodla = []

            if tryb_dysk:
                sciezki_wejsciowe = [Path(p) for p in json.loads(sciezki_dysk_raw)]
                brakujace = [str(p) for p in sciezki_wejsciowe if not p.exists()]
                if brakujace:
                    return jsonify({"blad": "Nie znaleziono pliku(ów): " + ", ".join(brakujace)}), 400
            else:
                sciezki_wejsciowe = []
                for plik in request.files.getlist("pliki"):
                    sciezka = tmp_path / plik.filename
                    plik.save(sciezka)
                    sciezki_wejsciowe.append(sciezka)

            # W trybie "z dysku" wynik ląduje w folderze pliku źródłowego;
            # przy uploadzie z przeglądarki (brak znanej ścieżki) — w katalogu tymczasowym.
            katalog_wyjsciowy = sciezki_wejsciowe[0].parent if tryb_dysk else (tmp_path / "wynik")

            pliki_do_pobrania = []
            sesja_id = None
            mapowanie_jawne = {}
            liczba_wykryc = {}
            tekst_zanon_pojedynczy = None
            strony_bez_tekstu = None
            prompt_pojedynczy = ""
            prompt_przyklad_wsad = ""

            if tryb_bip:
                for sciezka in sciezki_wejsciowe:
                    katalog_docelowy = sciezka.parent if tryb_dysk else katalog_wyjsciowy
                    sciezka_wyn = anonimizuj_bip(
                        sciezka, katalog_docelowy, kategorie=kategorie,
                        tryb_ai=tryb_ai, usun_numery_stron=usun_numery_stron, jezyki=jezyki,
                    )
                    pliki_do_pobrania.append(sciezka_wyn)

            elif len(sciezki_wejsciowe) > 1:
                wynik = anonimizuj_wiele_plikow(
                    sciezki_wejsciowe, katalog_wyjsciowy, haslo, tryb=tryb_wsad,
                    kategorie=kategorie, tryb_ai=tryb_ai,
                    usun_numery_stron=usun_numery_stron, styl=styl, jezyki=jezyki,
                    dolacz_prompt_ai=dolacz_prompt_ai,
                )
                liczba_wykryc = wynik.get("liczba_wykryc", {})
                mapowanie_jawne = wynik.get("mapowanie_jawne", {})
                if tryb_wsad == "jedna_sprawa":
                    pliki_do_pobrania += list(wynik["pliki_tekst"].values())
                    pliki_do_pobrania.append(wynik["mapowanie"])
                    teksty = wynik.get("teksty_zanonimizowane") or {}
                    if teksty:
                        pierwszy = next(iter(teksty.values()))
                        if GRANICA_PROMPTU_AI in pierwszy:
                            prompt_przyklad_wsad = pierwszy.split(GRANICA_PROMPTU_AI, 1)[0] + GRANICA_PROMPTU_AI
                else:
                    for dane in wynik["pliki"].values():
                        pliki_do_pobrania.append(dane["tekst"])
                        pliki_do_pobrania.append(dane["mapowanie"])
                        for k, v in dane["liczba_wykryc"].items():
                            liczba_wykryc[k] = liczba_wykryc.get(k, 0) + v
                        mapowanie_jawne.update(dane.get("mapowanie_jawne", {}))
                    pierwszy_dane = next(iter(wynik["pliki"].values()), None)
                    if pierwszy_dane:
                        prompt_przyklad_wsad = pierwszy_dane.get("prompt_ai", "")
            else:
                wynik = anonimizuj_plik(
                    sciezki_wejsciowe[0], katalog_wyjsciowy, haslo,
                    kategorie=kategorie, tryb_ai=tryb_ai,
                    usun_numery_stron=usun_numery_stron, styl=styl, jezyki=jezyki,
                    dolacz_prompt_ai=dolacz_prompt_ai,
                )
                liczba_wykryc = wynik["liczba_wykryc"]
                mapowanie_jawne = wynik["mapowanie_jawne"]
                pliki_do_pobrania += [wynik["tekst"], wynik["mapowanie"]]
                tekst_zanon_pojedynczy = wynik.get("tekst_zanonimizowany")
                prompt_pojedynczy = wynik.get("prompt_ai", "")
                strony_bez_tekstu = wynik.get("strony_bez_warstwy_tekstowej")

            if chce_raport and not tryb_bip and mapowanie_jawne:
                sciezka_raport = katalog_wyjsciowy / "raport.pdf"
                generuj_raport_pdf(mapowanie_jawne, haslo, sciezka_raport, nazwa_dokumentu="dokumenty")
                pliki_do_pobrania.append(sciezka_raport)

            if tryb_dysk:
                zapisano_obok_zrodla = [str(p) for p in pliki_do_pobrania]

            pliki_wynikowe = []
            for sciezka in pliki_do_pobrania:
                fid = str(uuid.uuid4())
                _PLIKI_DO_POBRANIA[fid] = {"dane": sciezka.read_bytes(), "nazwa": sciezka.name}
                pliki_wynikowe.append({"id": fid, "nazwa": sciezka.name})

            if not tryb_bip and styl != "puste" and mapowanie_jawne:
                sesja_id = str(uuid.uuid4())
                _SESJE[sesja_id] = {"mapowanie": mapowanie_jawne, "utworzono": time.time()}

            tekst_do_kopiowania = tekst_zanon_pojedynczy or ""
            prompt_ai = prompt_pojedynczy or prompt_przyklad_wsad
            prompt_wielu_plikow = bool(prompt_przyklad_wsad) and not tekst_zanon_pojedynczy

        return jsonify({
            "sesja_id": sesja_id,
            "liczba_wykryc": liczba_wykryc,
            "pliki": pliki_wynikowe,
            "zapisano": zapisano_obok_zrodla,
            "prompt_ai": prompt_ai,
            "prompt_wielu_plikow": prompt_wielu_plikow,
            "tekst_do_kopiowania": tekst_do_kopiowania,
            "strony_bez_warstwy_tekstowej": strony_bez_tekstu,
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
