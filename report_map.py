#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mapa ofert w raporcie — offline, w SVG, bez bibliotek i kafelków.

DLACZEGO TAK, A NIE LEAFLET/OPENSTREETMAP
-----------------------------------------
Raport jest pojedynczym plikiem otwieranym lokalnie, często bez internetu.
Zwykła mapa internetowa (Leaflet + kafelki OSM) pokazałaby wtedy szary
prostokąt. Dlatego podkład to **granice 18 dzielnic Krakowa** wbudowane
w raport jako SVG (plik ``krakow_districts.json``, ~20 kB, zbudowany raz
narzędziem ``tools/build_district_map.py``). Działa offline, drukuje się
i nie zależy od żadnego serwera.

PODZIAŁ PRACY
-------------
* **Python** (ten moduł) rzutuje i rysuje dzielnice — są stałe.
* **Przeglądarka** (``MAP_SCRIPT``) rysuje kropki ofert, dom i okrąg
  promienia — bo zależą od filtrów, wybranej dzielnicy i suwaka, a mają
  reagować natychmiast. Rzut jest w obu miejscach ten sam (stałe
  :data:`LAT0`, :data:`LON0`, :data:`SCALE` przekazane do JS).

CO POKAZUJE KROPKA
------------------
* **pozycja** — punkt oferty (adres, siedziba instytucji albo współrzędne
  ze źródła),
* **wielkość** — liczba ofert w tym miejscu,
* **kolor** — najlepsze dopasowanie w tym miejscu (zielony = DLA CIEBIE,
  bursztynowy = może pasować, szary = spoza profilu); wypełnienie pełne
  albo puste dodatkowo odróżnia punkt dokładny od przybliżonego (sama
  dzielnica), żeby informacja nie zależała wyłącznie od koloru,
* **pulsowanie** — w tym miejscu jest oferta NOWA od ostatniego raportu
  (wyłączane przy ``prefers-reduced-motion``),
* **kliknięcie** — lista ofert zawęża się do tego miejsca.

UCZCIWOŚĆ DANYCH
----------------
Oferty, dla których źródło podało tylko „Kraków”, **nie dostają kropki na
Rynku** — przy pomiarze było ich 69 w jednym punkcie, co dawało jedną
wielką, nic nieznaczącą kropkę. Zamiast tego liczy je osobny opis „miejsce
w Krakowie nieznane: N”. Podobnie oferty poza obszarem mapy (Olkusz,
Wieliczka…) są wymienione z odległością pod mapą.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

# Plik granic — obok modułu, także wewnątrz .exe (PyInstaller rozpakowuje
# dane do tego samego katalogu co moduły, ``sys._MEIPASS``).
DISTRICTS_FILE = Path(__file__).resolve().parent / "krakow_districts.json"

# Rzut: prosty równoodległościowy wokół środka Krakowa. Na obszarze ~30 km
# zniekształcenie jest pomijalne, a wzór da się powtórzyć w JS jedną linijką.
LAT0 = 50.06
LON0 = 20.00
SCALE = 30.0        # pikseli SVG na kilometr
KM_PER_DEG_LAT = 111.32

# Margines wokół granic miasta (km) — żeby okrąg promienia i bliskie
# miejscowości tuż za granicą (Zabierzów, Wieliczka) mieściły się na mapie.
MARGIN_KM = 4.0


def project(lat: float, lon: float) -> Tuple[float, float]:
    """Rzutuje współrzędne geograficzne na płaszczyznę SVG.

    Args:
        lat: szerokość geograficzna.
        lon: długość geograficzna.

    Returns:
        Para (x, y) w pikselach SVG (y rośnie w dół).
    """
    km_x = (lon - LON0) * KM_PER_DEG_LAT * math.cos(math.radians(LAT0))
    km_y = (LAT0 - lat) * KM_PER_DEG_LAT
    return km_x * SCALE, km_y * SCALE


def load_districts() -> Dict[str, object]:
    """Wczytuje granice dzielnic.

    Returns:
        Słownik z ``districts`` i ``attribution``; pusty, gdy pliku brak
        (wtedy mapa się nie pojawia, a raport działa dalej).
    """
    if not DISTRICTS_FILE.exists():
        return {}
    try:
        return json.loads(DISTRICTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_map() -> str:
    """Buduje blok mapy (SVG z dzielnicami + kontenery na dane z JS).

    Returns:
        Fragment HTML albo pusty łańcuch, gdy brak pliku granic.
    """
    data = load_districts()
    districts = data.get("districts") or []
    if not districts:
        return ""

    paths: List[str] = []
    xs: List[float] = []
    ys: List[float] = []
    labels: List[str] = []
    for district in districts:
        for ring in district.get("rings") or []:
            pts = [project(lat, lon) for lon, lat in ring]
            xs.extend(p[0] for p in pts)
            ys.extend(p[1] for p in pts)
            d_attr = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
            paths.append(f"<path class='mdist' d='{d_attr}'>"
                         f"<title>{district['name']}</title></path>")
        # Etykieta w środku ciężkości wierzchołków największego pierścienia.
        ring = max(district.get("rings") or [[]], key=len)
        if ring:
            cx = sum(project(lat, lon)[0] for lon, lat in ring) / len(ring)
            cy = sum(project(lat, lon)[1] for lon, lat in ring) / len(ring)
            labels.append(f"<text class='mlabel' x='{cx:.0f}' y='{cy:.0f}'>"
                          f"{district['name']}</text>")

    margin = MARGIN_KM * SCALE
    min_x, max_x = min(xs) - margin, max(xs) + margin
    min_y, max_y = min(ys) - margin, max(ys) + margin
    view = f"{min_x:.0f} {min_y:.0f} {max_x - min_x:.0f} {max_y - min_y:.0f}"

    config = json.dumps({"lat0": LAT0, "lon0": LON0, "scale": SCALE,
                         "kmPerDeg": KM_PER_DEG_LAT,
                         "box": [min_x, min_y, max_x, max_y]})
    return (
        "<details class='mapbox' open><summary>Mapa ofert "
        "<span class='mhint'>— kliknij kropkę, żeby pokazać oferty z tego "
        "miejsca</span></summary>"
        f"<svg id='offer-map' viewBox='{view}' role='img' "
        "aria-label='Mapa ofert pracy na tle dzielnic Krakowa'>"
        f"<g class='mdistricts'>{''.join(paths)}</g>"
        f"<g class='mlabels'>{''.join(labels)}</g>"
        "<g id='map-radius'></g><g id='map-dots'></g><g id='map-home'></g>"
        "</svg>"
        "<div class='mlegend'>"
        "<span><i class='lg s'></i>DLA CIEBIE</span>"
        "<span><i class='lg w'></i>może pasować</span>"
        "<span><i class='lg n'></i>spoza profilu</span>"
        "<span><i class='lg o'></i>punkt przybliżony (dzielnica)</span>"
        "<span><i class='lg p'></i>pulsuje = NOWE</span>"
        "<span>wielkość = liczba ofert</span>"
        "</div>"
        "<div class='mnotes' id='map-notes'></div>"
        "<div class='mfilter' id='map-filter' hidden></div>"
        f"<div class='mattr'>{data.get('attribution', '')}</div>"
        f"<script>window.KRK_MAP = {config};</script>"
        "</details>"
    )


MAP_STYLE = """
/* Mapa ofert (moduł report_map). */
details.mapbox { background: #fff; border: 1px solid #d0d7de;
                 border-radius: 6px; padding: 0.5em 0.8em; margin: 0 0 1em; }
details.mapbox > summary { cursor: pointer; font-weight: 600; color: #24292f; }
.mhint { font-weight: 400; color: #6e7781; font-size: 0.85em; }
#offer-map { width: 100%; height: auto; max-height: 460px; display: block;
             margin-top: 0.4em; }
.mdist { fill: #f6f8fa; stroke: #afb8c1; stroke-width: 1.2; }
.mdist:hover { fill: #eef2f6; }
.mlabel { font-size: 15px; fill: #8c959f; text-anchor: middle;
          pointer-events: none; }
.mdot { cursor: pointer; stroke: #fff; stroke-width: 2; }
.mdot.s { fill: #1a7f37; } .mdot.w { fill: #bf8700; } .mdot.n { fill: #8c959f; }
.mdot.approx { fill: #fff; stroke-width: 3; }
.mdot.approx.s { stroke: #1a7f37; } .mdot.approx.w { stroke: #bf8700; }
.mdot.approx.n { stroke: #8c959f; }
.mdot.sel { stroke: #0969da; stroke-width: 4; }
.mpulse { fill: none; stroke-width: 3; pointer-events: none;
          transform-box: fill-box; transform-origin: center;
          animation: mpulse 1.8s ease-out infinite; }
.mpulse.s { stroke: #1a7f37; } .mpulse.w { stroke: #bf8700; }
.mpulse.n { stroke: #8c959f; }
@keyframes mpulse { from { transform: scale(1); opacity: 0.9; }
                    to { transform: scale(2.6); opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .mpulse { animation: none; } }
.mradius { fill: #0969da14; stroke: #0969da; stroke-width: 2;
           stroke-dasharray: 8 6; pointer-events: none; }
.mhome { fill: #0969da; stroke: #fff; stroke-width: 2; }
.mcount { font-size: 13px; font-weight: 700; fill: #fff; text-anchor: middle;
          dominant-baseline: central; pointer-events: none; }
.mlegend { display: flex; flex-wrap: wrap; gap: 0.9em; font-size: 0.78em;
           color: #57606a; margin-top: 0.3em; }
.lg { display: inline-block; width: 0.8em; height: 0.8em; border-radius: 50%;
      margin-right: 0.3em; vertical-align: -0.05em; }
.lg.s { background: #1a7f37; } .lg.w { background: #bf8700; }
.lg.n { background: #8c959f; } .lg.o { border: 2px solid #57606a; }
.lg.p { border: 2px solid #1a7f37; box-shadow: 0 0 0 3px #1a7f3733; }
.mnotes { font-size: 0.8em; color: #57606a; margin-top: 0.4em; }
.mfilter { font-size: 0.85em; margin-top: 0.4em; }
.mfilter button { font: inherit; cursor: pointer; margin-left: 0.4em;
                  border: 1px solid #d0d7de; border-radius: 6px;
                  background: #f6f8fa; padding: 0.1em 0.5em; }
.mattr { font-size: 0.7em; color: #8c959f; text-align: right; }
@media print { .mpulse { display: none; } }
"""

MAP_SCRIPT = """
<script>
(function () {
  // Mapa ofert: kropki, dom i okrąg promienia. Dane czytamy z atrybutów
  // kart (data-lat, data-lon, data-level, data-geoprec), czyli z tego, co
  // właśnie jest w raporcie — mapa pokazuje to samo co lista, z filtrami.
  var cfg = window.KRK_MAP;
  var svg = document.getElementById("offer-map");
  if (!cfg || !svg) { return; }
  var NS = "http://www.w3.org/2000/svg";
  var RANK = { strong: 0, weak: 1, none: 2 };
  var CLS = ["s", "w", "n"];

  function proj(lat, lon) {
    var kx = (lon - cfg.lon0) * cfg.kmPerDeg * Math.cos(cfg.lat0 * Math.PI / 180);
    var ky = (cfg.lat0 - lat) * cfg.kmPerDeg;
    return [kx * cfg.scale, ky * cfg.scale];
  }
  function inBox(p) {
    return p[0] >= cfg.box[0] && p[0] <= cfg.box[2] &&
           p[1] >= cfg.box[1] && p[1] <= cfg.box[3];
  }
  function el(name, attrs) {
    var node = document.createElementNS(NS, name);
    for (var k in attrs) { node.setAttribute(k, attrs[k]); }
    return node;
  }
  function visible(card) {
    // Karta przeszła filtry (nie ma display:none na sobie ani na przodkach,
    // z wyjątkiem zwiniętych <details> — te nie ukrywają ofert z mapy).
    for (var e = card; e && e !== document.body; e = e.parentElement) {
      if (e.style && e.style.display === "none") { return false; }
    }
    return true;
  }

  window.KRK_MAP_POINT = null;  // wybrane miejsce (klucz "lat,lon")

  function render() {
    var dots = document.getElementById("map-dots");
    var home = document.getElementById("map-home");
    var ring = document.getElementById("map-radius");
    dots.innerHTML = ""; home.innerHTML = ""; ring.innerHTML = "";

    var groups = {}, unknownCity = 0, outside = {};
    var seen = {};
    document.querySelectorAll(
      ".offer[data-nab]:not(.closed-matches .offer)"
    ).forEach(function (card) {
      var id = card.getAttribute("data-nab");
      if (seen[id] || !visible(card) || card.getAttribute("data-mapskip")) {
        return;
      }
      seen[id] = true;
      var prec = card.getAttribute("data-geoprec") || "";
      var lat = parseFloat(card.getAttribute("data-lat"));
      var lon = parseFloat(card.getAttribute("data-lon"));
      if (isNaN(lat) || isNaN(lon)) { return; }
      if (prec === "city") {
        if (card.getAttribute("data-incity") === "1") { unknownCity++; }
        else {
          var name = card.getAttribute("data-city") || "?";
          outside[name] = (outside[name] || 0) + 1;
        }
        return;
      }
      var p = proj(lat, lon);
      if (!inBox(p)) {
        var nm = card.getAttribute("data-city") || "?";
        outside[nm] = (outside[nm] || 0) + 1;
        return;
      }
      var key = lat.toFixed(3) + "," + lon.toFixed(3);
      var g = groups[key] || (groups[key] = { p: p, n: 0, best: 2,
                                              isNew: false, approx: true,
                                              titles: [] });
      g.n++;
      // Jawne sprawdzenie zamiast „|| 2”: RANK.strong to 0, a „0 || 2”
      // daje 2 — w pierwszej wersji wszystkie mocne trafienia rysowały się
      // przez to jako szare kropki „spoza profilu”.
      var rank = RANK[card.getAttribute("data-level")];
      g.best = Math.min(g.best, rank === undefined ? 2 : rank);
      if (card.classList.contains("is-new")) { g.isNew = true; }
      if (prec !== "district") { g.approx = false; }
      // Tytuł = pierwszy niepusty węzeł tekstowy nagłówka (dalej są
      // odznaki). ``firstChild`` bywał samym znakiem nowej linii, przez co
      // podpowiedzi pokazywały liczbę ofert bez ich tytułów.
      var h3 = card.querySelector("h3");
      if (h3 && g.titles.length < 6) {
        var txt = "";
        for (var i = 0; i < h3.childNodes.length && !txt; i++) {
          if (h3.childNodes[i].nodeType === 3) {
            txt = h3.childNodes[i].textContent.trim();
          }
        }
        g.titles.push(txt);
      }
    });

    // Duże kropki pod spodem, małe na wierzchu — żeby nic się nie chowało.
    Object.keys(groups).sort(function (a, b) {
      return groups[b].n - groups[a].n;
    }).forEach(function (key) {
      var g = groups[key];
      var r = 7 + 4 * Math.sqrt(g.n);
      var cls = CLS[g.best];
      if (g.isNew) {
        dots.appendChild(el("circle", { cx: g.p[0], cy: g.p[1], r: r,
                                        "class": "mpulse " + cls }));
      }
      var dot = el("circle", { cx: g.p[0], cy: g.p[1], r: r,
        "class": "mdot " + cls + (g.approx ? " approx" : "") +
                 (window.KRK_MAP_POINT === key ? " sel" : ""),
        "data-key": key, tabindex: "0", role: "button" });
      var tip = el("title", {});
      tip.textContent = g.n + (g.n === 1 ? " oferta" : " ofert") + ":\\n" +
        g.titles.join("\\n") + (g.n > g.titles.length ? "\\n…" : "");
      dot.appendChild(tip);
      dot.addEventListener("click", function () { pick(key); });
      dot.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(key); }
      });
      dots.appendChild(dot);
      if (g.n > 1) {
        var t = el("text", { x: g.p[0], y: g.p[1], "class": "mcount" });
        t.textContent = g.n;
        dots.appendChild(t);
      }
    });

    // Dom i okrąg promienia.
    var sel = document.getElementById("geo-home");
    var rad = document.getElementById("geo-radius");
    if (sel && window.KRK_DISTRICTS && window.KRK_DISTRICTS[sel.value]) {
      var hp = window.KRK_DISTRICTS[sel.value];
      var hc = proj(hp[0], hp[1]);
      var km = rad ? parseInt(rad.value, 10) || 0 : 0;
      if (km > 0) {
        ring.appendChild(el("circle", { cx: hc[0], cy: hc[1],
                                        r: km * cfg.scale, "class": "mradius" }));
      }
      var s = 9;
      home.appendChild(el("path", { "class": "mhome", d:
        "M" + hc[0] + "," + (hc[1] - s * 1.4) +
        " L" + (hc[0] + s) + "," + (hc[1] - s * 0.3) +
        " L" + (hc[0] + s) + "," + (hc[1] + s) +
        " L" + (hc[0] - s) + "," + (hc[1] + s) +
        " L" + (hc[0] - s) + "," + (hc[1] - s * 0.3) + " Z" }));
    }

    // Uwagi pod mapą — to, czego uczciwie nie da się postawić na mapie.
    var notes = [];
    if (unknownCity) {
      notes.push("miejsce w Krakowie nieznane (źródło podało tylko miasto): " +
                 unknownCity);
    }
    var out = Object.keys(outside).sort().map(function (k) {
      return k + (outside[k] > 1 ? " (" + outside[k] + ")" : "");
    });
    if (out.length) { notes.push("poza mapą: " + out.join(", ")); }
    document.getElementById("map-notes").textContent = notes.join(" · ");
  }

  function pick(key) {
    window.KRK_MAP_POINT = (window.KRK_MAP_POINT === key) ? null : key;
    var box = document.getElementById("map-filter");
    document.querySelectorAll(".offer[data-nab]").forEach(function (card) {
      var lat = parseFloat(card.getAttribute("data-lat"));
      var lon = parseFloat(card.getAttribute("data-lon"));
      var k = isNaN(lat) ? "" : lat.toFixed(3) + "," + lon.toFixed(3);
      var hit = !window.KRK_MAP_POINT || k === window.KRK_MAP_POINT;
      card.classList.toggle("map-out", !hit);
    });
    if (window.KRK_MAP_POINT) {
      box.hidden = false;
      box.innerHTML = "Pokazuję oferty tylko z wybranego miejsca.";
      var b = document.createElement("button");
      b.type = "button"; b.textContent = "pokaż wszystkie";
      b.addEventListener("click", function () { pick(window.KRK_MAP_POINT); });
      box.appendChild(b);
      // Otwieramy sekcję „pozostałe”, jeśli wybrane miejsce ma tylko takie.
      var rest = document.querySelector("details.rest");
      if (rest) { rest.open = true; }
    } else {
      box.hidden = true;
    }
    render();
  }

  window.KRK_MAP_RENDER = render;
  render();
})();
</script>
"""
