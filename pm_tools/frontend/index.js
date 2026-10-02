(function () {
  var input = document.getElementById("filter");
  var counter = document.getElementById("filter-count");
  var sections = document.querySelectorAll("section");
  // Count only the column lists, the "Recently updated" list repeats documents
  var total = document.querySelectorAll("main li").length;

  function apply() {
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

  input.addEventListener("input", apply);
  document.addEventListener("keydown", function (e) {
    // "/" focuses the filter box, Esc clears it
    if (e.key === "/" && document.activeElement !== input) {
      e.preventDefault();
      input.focus();
    } else if (e.key === "Escape" && input.value) {
      input.value = "";
      apply();
      input.blur();
    }
  });
})();
