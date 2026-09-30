(function () {
  var input = document.getElementById("filter");
  var sections = document.querySelectorAll("main section");
  input.addEventListener("input", function () {
    var q = input.value.trim().toLowerCase();
    for (var i = 0; i < sections.length; i++) {
      var items = sections[i].querySelectorAll("li"), shown = 0;
      for (var j = 0; j < items.length; j++) {
        var match = items[j].querySelector("a").textContent.toLowerCase().indexOf(q) !== -1;
        items[j].hidden = !match;
        if (match) shown++;
      }
      sections[i].hidden = shown === 0;
    }
  });
  // Press "/" anywhere to focus the filter box
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== input) {
      e.preventDefault();
      input.focus();
    }
  });
})();
