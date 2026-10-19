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
    var all = {}, clicked = {};
    document.querySelectorAll(
      ".offer[data-nab]:not(.closed-matches .offer)"
    ).forEach(function (card) {
      var id = card.getAttribute("data-nab");
      all[id] = true;
      if (card.classList.contains("clicked")) { clicked[id] = true; }
    });
    var total = Object.keys(all).length;
    var seen = Object.keys(clicked).length;
    var el = document.getElementById("counter");
    if (el) {
      el.textContent = (total - seen) + " / " + total + " nieprzejrzanych";
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
  var OFF = { contract: {}, level: {}, source: {} };

  function cardMatches(card) {
    var kinds = (card.getAttribute("data-contract") || "nieznana").split(" ");
    // Karta przechodzi, gdy CHOĆ JEDEN jej rodzaj umowy jest włączony —
    // oferta „UoP albo B2B” ma pozostać widoczna przy filtrze „tylko UoP”.
    var anyContract = kinds.some(function (k) { return !OFF.contract[k]; });
    if (!anyContract) { return false; }
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

  var allBtn = document.getElementById("f-all");
  if (allBtn) {
    allBtn.addEventListener("click", function () {
      OFF = { contract: {}, level: {}, source: {} };
      document.querySelectorAll(".fbtn[data-filter]").forEach(function (b) {
        b.classList.add("on");
      });
      applyFilters();
    });
  }

  applyFilters();
})();
</script>
"""
