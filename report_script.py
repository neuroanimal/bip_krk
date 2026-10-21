#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrypt przeglądarkowy raportu: tracking klikania i filtrowanie.

Wydzielony z ``report_html.py``, gdy ten przekroczył 1000 linii — to
spójna, osobna odpowiedzialność: zachowanie raportu W PRZEGLĄDARCE,
podczas gdy ``report_html`` odpowiada za wygenerowanie dokumentu.

Dwie funkcje, obie działające BEZ serwera (raport to plik otwierany
lokalnie, często bez internetu):

* **tracking klikania** — kliknięta oferta zapisuje się w ``localStorage``
  pod kluczem ``BIP_KRK_CLICKED`` (mapa ``nab_id`` -> data ISO), karta
  zostaje wygaszona i przestaje być „NOWA”. Stan da się wyeksportować do
  ``clicks.json`` i wczytać z powrotem do datasetu, żeby przetrwał
  regenerację raportu;
* **filtrowanie** — po rodzaju umowy, dopasowaniu i źródle; ukrywa karty
  (``display:none``), bo wszystkie oferty są już w HTML.
"""

HTML_TRACKING_SCRIPT = """
<script>
(function () {
  "use strict";
  var STORE_KEY = "BIP_KRK_CLICKED";

  function loadClicked() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); }
    catch (e) { return {}; }
  }
  function saveClicked(map) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(map)); }
    catch (e) { /* brak localStorage (tryb prywatny) — tracking nieaktywny */ }
  }

  var clicked = loadClicked();

  function markCard(card, when) {
    if (card.classList.contains("clicked")) { return; }
    card.classList.add("clicked");
    var head = card.querySelector("h3");
    if (head && !head.querySelector(".seen-mark")) {
      var mark = document.createElement("span");
      mark.className = "seen-mark";
      mark.textContent = "oglądane" + (when ? " " + when.slice(0, 10) : "");
      head.appendChild(mark);
    }
  }

  function refreshCounter() {
    // Liczymy UNIKALNE oferty, nie karty w dokumencie. Oferta dopasowana
    // do profilu występuje w DOM dwukrotnie — raz w sekcji „Dopasowane do
    // profilu” na górze, raz w swojej kategorii. Zliczanie kart dawało
    // liczbę zawyżoną (w raporcie IT: 388 kart przy 229 ofertach), co
    // kłóciło się ze statystyką w pasku bocznym.
    // Pomijamy karty w sekcji „niedawno zamknięte oferty z profilu” —
    // tam terminy już minęły, więc nie są niczym „do przejrzenia”.
    // Bez tego licznik pokazywał 104 przy 98 ofertach w raporcie.
    // Liczymy wyłącznie oferty DOPASOWANE (sekcja profilu, łącznie
    // z podobnymi schowanymi pod „+ N podobnych”). Oferty spoza profilu są
    // zwinięte na dole — liczenie ich jako „do przejrzenia” dawało 211 przy
    // kilkudziesięciu ofertach, które naprawdę są do przejrzenia.
    var all = {}, clicked = {};
    document.querySelectorAll(
      ".profile-box .offer[data-nab]:not(.closed-matches .offer)"
    ).forEach(function (card) {
      var id = card.getAttribute("data-nab");
      all[id] = true;
      if (card.classList.contains("clicked")) { clicked[id] = true; }
    });
    var total = Object.keys(all).length;
    var seen = Object.keys(clicked).length;
    var el = document.getElementById("counter");
    if (el) {
      el.textContent = (total - seen) + " / " + total +
        " dopasowanych do przejrzenia";
    }
  }

  // Oznacz karty już klikniętych ofert (stan z poprzednich sesji).
  document.querySelectorAll(".offer[data-nab]").forEach(function (card) {
    var id = card.getAttribute("data-nab");
    if (clicked[id]) { markCard(card, clicked[id]); }
  });

  // Rejestruj kliknięcie w link szczegółów oferty.
  document.querySelectorAll(".offer[data-nab] a[href]").forEach(function (a) {
    a.addEventListener("click", function () {
      var card = a.closest(".offer[data-nab]");
      if (!card) { return; }
      var id = card.getAttribute("data-nab");
      if (!clicked[id]) {
        clicked[id] = new Date().toISOString();
        saveClicked(clicked);
      }
      markCard(card, clicked[id]);
      refreshCounter();
    });
  });

  // Przycisk: oznacz wszystkie jako przejrzane.
  var markAll = document.getElementById("mark-all");
  if (markAll) {
    markAll.addEventListener("click", function () {
      document.querySelectorAll(".offer[data-nab]").forEach(function (card) {
        var id = card.getAttribute("data-nab");
        if (!clicked[id]) { clicked[id] = new Date().toISOString(); }
        markCard(card, clicked[id]);
      });
      saveClicked(clicked);
      refreshCounter();
    });
  }

  // Przycisk: wyczyść historię klikania.
  var clearBtn = document.getElementById("clear-seen");
  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      if (!confirm("Wyczyścić historię oglądanych ofert?")) { return; }
      clicked = {};
      saveClicked(clicked);
      document.querySelectorAll(".offer.clicked").forEach(function (card) {
        card.classList.remove("clicked");
        var m = card.querySelector(".seen-mark");
        if (m) { m.remove(); }
      });
      refreshCounter();
    });
  }

  // Przycisk: eksport stanu do pliku clicks.json (do wczytania w datasecie).
  var exportBtn = document.getElementById("export-seen");
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      var payload = JSON.stringify({ clicked: clicked }, null, 2);
      var blob = new Blob([payload], { type: "application/json" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = "clicks.json";
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  refreshCounter();

  // ----- FILTROWANIE (rodzaj umowy / dopasowanie / źródło) -----
  //
  // Raport jest plikiem statycznym, więc nie ma serwera, który mógłby
  // przefiltrować dane. Wszystkie oferty są w HTML, a filtr ukrywa karty.
  //
  // Zasada: w obrębie JEDNEJ grupy (np. rodzaju umowy) działa suma —
  // wyłączenie B2B zostawia UoP i UZ. Między grupami działa iloczyn —
  // „UoP” i „DLA CIEBIE” pokazuje oferty spełniające oba warunki. To
  // zachowanie, którego ludzie oczekują od filtrów sklepowych.
  var OFF = { contract: {}, level: {}, source: {}, area: {} };

  // Język ogłoszeń brany pod uwagę. Domyślnie TYLKO polski — tak prosiła
  // adresatka; angielski włącza przycisk „EN”.
  var LANG_ON = { pl: true, en: false };

  // Geografia: dom (dzielnica) i promień dla ofert POZA Krakowem.
  // ``alwaysCity`` domyślnie FALSE — promień obowiązuje też w Krakowie.
  // Tak zdecydował użytkownik: oferta 18,5 km od domu jest za daleko,
  // a przełącznik zostaje na wypadek, gdy w pobliżu nic nie ma.
  var GEO = { home: null, radius: 10, alwaysCity: false };

  function haversine(aLat, aLon, bLat, bLon) {
    function rad(x) { return x * Math.PI / 180; }
    var dLat = rad(bLat - aLat), dLon = rad(bLon - aLon);
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(rad(aLat)) * Math.cos(rad(bLat)) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }

  function cardDistance(card) {
    // Zwraca odległość w km albo null, gdy nie da się policzyć.
    if (!GEO.home) { return null; }
    var lat = parseFloat(card.getAttribute("data-lat"));
    var lon = parseFloat(card.getAttribute("data-lon"));
    if (isNaN(lat) || isNaN(lon)) { return null; }
    return haversine(GEO.home[0], GEO.home[1], lat, lon);
  }

  function geoAllows(card) {
    // Oferta w Krakowie przechodzi bez względu na promień TYLKO wtedy,
    // gdy użytkownik zaznaczy „Kraków zawsze” (domyślnie wyłączone).
    if (GEO.alwaysCity && card.getAttribute("data-incity") === "1") {
      return true;
    }
    var dist = cardDistance(card);
    // Brak lokalizacji NIE ukrywa oferty — brak danych to nie „odrzuć”.
    if (dist === null) { return true; }
    return dist <= GEO.radius;
  }

  function cardMatches(card) {
    var kinds = (card.getAttribute("data-contract") || "nieznana").split(" ");
    // Karta przechodzi, gdy CHOĆ JEDEN jej rodzaj umowy jest włączony —
    // oferta „UoP albo B2B” ma pozostać widoczna przy filtrze „tylko UoP”.
    var anyContract = kinds.some(function (k) { return !OFF.contract[k]; });
    if (!anyContract) { return false; }
    // Język ogłoszenia.
    if (!LANG_ON[card.getAttribute("data-lang") || "pl"]) { return false; }
    // Obszary: karta przechodzi, gdy choć jeden jej obszar jest włączony.
    // Oferta bez obszarów (poza profilem) nie jest filtrowana tym kryterium.
    var areas = (card.getAttribute("data-areas") || "").split("|")
      .filter(function (x) { return x; });
    if (areas.length && !areas.some(function (a) { return !OFF.area[a]; })) {
      return false;
    }
    if (!geoAllows(card)) { return false; }
    if (OFF.level[card.getAttribute("data-level") || "none"]) { return false; }
    if (OFF.source[card.getAttribute("data-source") || "?"]) { return false; }
    return true;
  }

  function applyFilters() {
    var shown = {}, hidden = 0;
    document.querySelectorAll(
      ".offer[data-nab]:not(.closed-matches .offer)"
    ).forEach(function (card) {
      if (cardMatches(card)) {
        card.style.display = "";
        shown[card.getAttribute("data-nab")] = true;
      } else {
        card.style.display = "none";
        hidden++;
      }
    });
    // Nagłówek kategorii bez widocznych ofert tylko zaśmieca — ukrywamy
    // całą sekcję, gdy nic w niej nie zostało.
    document.querySelectorAll("section").forEach(function (sec) {
      var visible = sec.querySelectorAll(
        ".offer[data-nab]:not([style*='none'])").length;
      sec.style.display = visible ? "" : "none";
    });
    var el = document.getElementById("f-summary");
    if (el) {
      var total = Object.keys(shown).length;
      el.textContent = hidden
        ? ("widocznych ofert: " + total)
        : "bez filtrów — widoczne wszystkie";
    }
  }

  document.querySelectorAll(".fbtn[data-filter]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var group = btn.getAttribute("data-filter");
      var value = btn.getAttribute("data-value");
      OFF[group][value] = !OFF[group][value];
      btn.classList.toggle("on", !OFF[group][value]);
      applyFilters();
    });
  });

  // ----- GEOGRAFIA: dom i promień -----
  function refreshDistances() {
    // Odległość na karcie — liczona od aktualnie wybranej dzielnicy.
    document.querySelectorAll(".offer[data-nab]").forEach(function (card) {
      var el = card.querySelector(":scope > .meta > .dist");
      if (!el) { return; }
      var d = cardDistance(card);
      if (d === null) { el.textContent = ""; return; }
      var prec = card.getAttribute("data-geoprec") || "";
      var approx = (prec === "city" || prec === "district") ? "≈ " : "";
      el.textContent = approx + d.toFixed(1).replace(".", ",") + " km ·";
      el.title = approx
        ? "Odległość przybliżona: źródło podało tylko miasto lub dzielnicę"
        : "Odległość w linii prostej od wybranego miejsca wyjazdu";
    });
  }

  function refreshGeoLabel() {
    var el = document.getElementById("geo-radius-val");
    if (el) { el.textContent = GEO.radius + " km"; }
    var sum = document.getElementById("geo-summary");
    if (sum) {
      var hidden = 0, far = [];
      document.querySelectorAll(".offer[data-nab]:not(.closed-matches .offer)")
        .forEach(function (card) {
          if (!geoAllows(card)) {
            hidden++;
            var d = cardDistance(card);
            if (d !== null) { far.push(Math.round(d)); }
          }
        });
      sum.textContent = hidden
        ? ("odfiltrowanych odległością: " + hidden)
        : "wszystkie w zasięgu";
    }
    refreshDistances();
  }

  var homeSel = document.getElementById("geo-home");
  if (homeSel && window.KRK_DISTRICTS) {
    GEO.home = window.KRK_DISTRICTS[homeSel.value] || null;
    homeSel.addEventListener("change", function () {
      GEO.home = window.KRK_DISTRICTS[homeSel.value] || null;
      applyFilters();
      refreshGeoLabel();
    });
  }
  var radius = document.getElementById("geo-radius");
  if (radius) {
    GEO.radius = parseInt(radius.value, 10) || 10;
    radius.addEventListener("input", function () {
      GEO.radius = parseInt(radius.value, 10) || 0;
      applyFilters();
      refreshGeoLabel();
    });
  }
  var cityChk = document.getElementById("geo-city");
  if (cityChk) {
    cityChk.addEventListener("change", function () {
      GEO.alwaysCity = cityChk.checked;
      applyFilters();
      refreshGeoLabel();
    });
  }

  // ----- JĘZYK OGŁOSZEŃ -----
  document.querySelectorAll(".lbtn[data-offer-lang]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var code = btn.getAttribute("data-offer-lang");
      LANG_ON[code] = !LANG_ON[code];
      btn.classList.toggle("on", LANG_ON[code]);
      applyFilters();
    });
  });

  // ----- JĘZYK INTERFEJSU -----
  // Napisy trzymamy w jednej mapie zamiast duplikować cały HTML. Tłumaczymy
  // tylko etykiety sterowania — treść ogłoszeń zostaje w oryginale, bo to
  // dane, nie interfejs.
  var UI_TEXT = {
    pl: { home: "Miejsce wyjazdu:", radius: "Promień poza Krakowem:",
          always_city: "Kraków zawsze", areas: "Obszary:",
          match: "Dopasowanie:", contract: "Rodzaj umowy:",
          source: "Źródło:", sort: "Sortuj:", all: "Pokaż wszystkie" },
    en: { home: "Commute from:", radius: "Radius outside Kraków:",
          always_city: "Kraków always", areas: "Areas:",
          match: "Profile match:", contract: "Contract type:",
          source: "Source:", sort: "Sort by:", all: "Show all" }
  };

  function setUiLang(code) {
    var dict = UI_TEXT[code] || UI_TEXT.pl;
    document.querySelectorAll("[data-t]").forEach(function (el) {
      var key = el.getAttribute("data-t");
      if (dict[key]) { el.textContent = dict[key]; }
    });
    document.querySelectorAll(".flag[data-ui-lang]").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-ui-lang") === code);
    });
    document.documentElement.setAttribute("lang", code);
  }

  document.querySelectorAll(".flag[data-ui-lang]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      setUiLang(btn.getAttribute("data-ui-lang"));
    });
  });

  refreshGeoLabel();

  var allBtn = document.getElementById("f-all");
  if (allBtn) {
    allBtn.addEventListener("click", function () {
      OFF = { contract: {}, level: {}, source: {}, area: {} };
      document.querySelectorAll(".fbtn[data-filter]").forEach(function (b) {
        b.classList.add("on");
      });
      applyFilters();
    });
  }

  applyFilters();

  // ----- SORTOWANIE (pilność / wynagrodzenie / dopasowanie) -----
  //
  // Sortujemy karty W OBRĘBIE każdej sekcji, nie globalnie — grupowanie
  // po kategoriach (i sekcja „Dopasowane do profilu”) ma zostać, bo to
  // ona daje raportowi strukturę. Zmiana kolejności to przestawienie
  // węzłów DOM; przy kilkuset kartach jest to niezauważalne.
  //
  // Oferty bez podanej kwoty mają data-pay="-1" i lądują NA KOŃCU przy
  // sortowaniu po wynagrodzeniu — inaczej „brak danych” wyglądałby jak
  // „zarobki zerowe” i wypychałby realne oferty poza ekran.
  function sortCards(mode) {
    // Sekcja profilu ma śródtytuł „Może pasować” — przestawianie wszystkich
    // jej kart wymieszałoby obie grupy, więc tam sortujemy w obrębie
    // poziomu dopasowania (patrz porównanie poniżej).
    document.querySelectorAll("section, .profile-box").forEach(function (box) {
      var cards = Array.prototype.slice.call(
        box.querySelectorAll(":scope > .offer[data-nab]")
      );
      if (cards.length < 2) { return; }
      cards.sort(function (a, b) {
        var la = a.getAttribute("data-level") === "strong" ? 0 : 1;
        var lb = b.getAttribute("data-level") === "strong" ? 0 : 1;
        if (box.classList.contains("profile-box") && la !== lb) {
          return la - lb;
        }
        function num(card, attr, fallback) {
          var raw = parseInt(card.getAttribute(attr), 10);
          return isNaN(raw) ? fallback : raw;
        }
        if (mode === "pay") {
          var pa = num(a, "data-pay", -1), pb = num(b, "data-pay", -1);
          if (pa !== pb) {
            if (pa < 0) { return 1; }
            if (pb < 0) { return -1; }
            return pb - pa;  // malejąco
          }
        } else if (mode === "score") {
          var sa = num(a, "data-score", 0), sb = num(b, "data-score", 0);
          if (sa !== sb) { return sb - sa; }
        }
        // Domyślnie i jako rozstrzygnięcie remisu: po pilności terminu.
        return num(a, "data-days", 9999) - num(b, "data-days", 9999);
      });
      // Karty wstawiamy z powrotem PRZED śródtytułem / blokiem zamkniętych,
      // a nie na koniec pudełka — inaczej trafiłyby za nie.
      var head = box.querySelector(":scope > .weak-head");
      var closed = box.querySelector(":scope > details.closed-matches");
      cards.forEach(function (card) {
        var isWeak = card.getAttribute("data-level") !== "strong";
        var anchor = (!isWeak && head) ? head : closed;
        if (anchor) { box.insertBefore(card, anchor); }
        else { box.appendChild(card); }
      });
    });
  }

  document.querySelectorAll(".sbtn[data-sort]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".sbtn[data-sort]").forEach(function (b) {
        b.classList.remove("on");
      });
      btn.classList.add("on");
      sortCards(btn.getAttribute("data-sort"));
    });
  });
})();
</script>
"""
