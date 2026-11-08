// Filter the command reference by search words and by access tier.
(function () {
  var search = document.getElementById("search");
  var tier = document.getElementById("tier");
  var empty = document.getElementById("no-results");
  if (!search || !tier) return;
  var commands = Array.prototype.slice.call(document.querySelectorAll(".command"));
  var groups = Array.prototype.slice.call(document.querySelectorAll(".group"));

  function matches(el, words, level) {
    if (level !== "" && Number(el.dataset.level) > Number(level)) return false;
    var text = el.dataset.search;
    return words.every(function (w) { return text.indexOf(w) !== -1; });
  }

  function update() {
    var words = search.value.toLowerCase().replace(/^:tide\s+/, "").replace(/\//g, " ")
      .split(/\s+/).filter(Boolean);
    var shown = 0;
    commands.forEach(function (el) {
      var ok = matches(el, words, tier.value);
      el.hidden = !ok;
      if (ok) shown++;
    });
    groups.forEach(function (g) {
      g.hidden = !g.querySelector(".command:not([hidden])");
    });
    empty.hidden = shown !== 0;
  }

  search.addEventListener("input", update);
  tier.addEventListener("change", update);
  update();
})();
