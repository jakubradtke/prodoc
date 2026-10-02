(function () {
  var input = document.getElementById("filter");
  var counter = document.getElementById("filter-count");
  var sections = document.querySelectorAll("section");
  // Count only the column lists, the "Recently updated" list repeats documents
  var total = document.querySelectorAll("main li").length;

  function applyTitles() {
    var q = input.value.trim().toLowerCase();
    var shownMain = 0;
    for (var i = 0; i < sections.length; i++) {
      var items = sections[i].querySelectorAll("li"), shown = 0;
      for (var j = 0; j < items.length; j++) {
        var match = items[j].querySelector("a").textContent.toLowerCase().indexOf(q) !== -1;
        items[j].hidden = !match;
        if (match) shown++;
      }
      sections[i].hidden = shown === 0;
      if (sections[i].id !== "recent") shownMain += shown;
    }
    counter.textContent = q ? shownMain + " of " + total : "";
  }

  // ---- Content search: section texts from <output>-search.js, loaded on first use ----
  var cinput = document.getElementById("content-search");
  var matchCase = document.getElementById("match-case");
  var box = document.getElementById("content-results");
  var src = cinput ? cinput.getAttribute("data-search") : null;
  var data = null, loading = false, timer = null;
  var MAX_RESULTS = 50, MIN_CHARS = 3;

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function show(title, html) {
    box.querySelector("h2").textContent = title;
    box.querySelector("ul").innerHTML = html;
    box.hidden = false;
  }

  function load(then) {
    if (data) return then();
    if (loading) return;
    loading = true;
    show("Loading content search…", "");
    var s = document.createElement("script");
    s.src = src;
    s.onload = function () {
      data = window.PRODOC_SEARCH;
      // Searchable strings prepared once: [4] heading+text, [5] heading (lower case),
      // [6] heading+text, [7] heading (original case, for "Match case")
      for (var i = 0; i < data.s.length; i++) {
        var e = data.s[i], all = e[2] + " " + e[3];
        e.push(all.toLowerCase(), e[2].toLowerCase(), all, e[2]);
      }
      // Search again with the current input, the user may have kept typing while loading
      searchContent();
    };
    s.onerror = function () { show("Content search unavailable", ""); };
    document.head.appendChild(s);
  }

  function snippet(text, words, cs) {
    var at = (cs ? text : text.toLowerCase()).indexOf(words[0]);
    var start = Math.max(0, at - 70), part = text.substr(start, 180);
    var html = (start > 0 ? "…" : "") + esc(part) + (start + 180 < text.length ? "…" : "");
    var re = new RegExp("(" + words.map(function (w) {
      return esc(w).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|") + ")", cs ? "g" : "gi");
    return html.replace(re, "<mark>$1</mark>");
  }

  function searchContent() {
    var cs = matchCase && matchCase.checked;
    var q = cinput.value.trim();
    if (!cs) q = q.toLowerCase();
    if (!src || q.length < MIN_CHARS) { box.hidden = true; return; }
    load(function () {
      var words = q.split(/\s+/), hits = [];
      var ALL = cs ? 6 : 4, HEAD = cs ? 7 : 5;
      for (var i = 0; i < data.s.length; i++) {
        var e = data.s[i], all = e[ALL], score = 0, ok = true;
        for (var w = 0; w < words.length; w++) {
          var n = all.split(words[w]).length - 1;
          if (!n) { ok = false; break; }
          score += Math.min(n, 20) + (e[HEAD].indexOf(words[w]) !== -1 ? 50 : 0);
        }
        if (ok) hits.push([score, e]);
      }
      hits.sort(function (a, b) { return b[0] - a[0]; });
      var html = "";
      for (var k = 0; k < Math.min(hits.length, MAX_RESULTS); k++) {
        var h = hits[k][1], doc = data.docs[h[0]];
        html += '<li><a href="' + esc(doc[1]) + "#" + esc(h[1]) + '" target="_blank" rel="noopener">' +
          esc(doc[0]) + (h[2] ? " › " + esc(h[2]) : "") + "</a>" +
          '<div class="snip">' + snippet(h[3] || h[2], words, cs) + "</div></li>";
      }
      var more = hits.length > MAX_RESULTS ? " — showing " + MAX_RESULTS : "";
      show("Matches in document content (" + hits.length + ")" + more, html);
    });
  }

  input.addEventListener("input", applyTitles);
  if (cinput) {
    cinput.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(searchContent, 200);
    });
  }
  if (matchCase) matchCase.addEventListener("change", searchContent);

  function clear(field) {
    if (!field || !field.value) return;
    field.value = "";
    if (field === input) applyTitles(); else box.hidden = true;
  }

  document.addEventListener("keydown", function (e) {
    var typing = document.activeElement === input || document.activeElement === cinput;
    // "/" focuses the title filter, "\" the content search, Esc clears the active field (or both)
    if (e.key === "/" && !typing) {
      e.preventDefault();
      input.focus();
    } else if (e.key === "\\" && cinput && !typing) {
      e.preventDefault();
      cinput.focus();
    } else if (e.key === "Escape") {
      if (typing) { clear(document.activeElement); document.activeElement.blur(); }
      else { clear(input); clear(cinput); }
    }
  });
})();
