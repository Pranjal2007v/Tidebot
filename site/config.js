// Build .tide.yml live from the config builder's switches and reviewers box.
(function () {
  // Same output as to_yaml in tidebot/config.py, so the page and the bot agree.
  function tideYaml(switches, reviewersText) {
    var lines = switches.map(function (s) { return s.name + ": " + (s.on ? "true" : "false"); });
    var rules = parseReviewers(reviewersText || "");
    if (rules.length) {
      lines.push("reviewers:");
      rules.forEach(function (r) {
        var people = r.owners.map(function (o) { return JSON.stringify(o); }).join(", ");
        lines.push("  " + JSON.stringify(r.pattern) + ": [" + people + "]");
      });
    }
    return lines.join("\n") + "\n";
  }

  // One rule per line: "docs/: alice, @org/docs". Lines without a pattern or
  // without anyone after the colon are skipped, as the bot skips them.
  function parseReviewers(text) {
    var rules = [];
    text.split("\n").forEach(function (line) {
      var at = line.lastIndexOf(":");
      if (at === -1) return;
      var pattern = line.slice(0, at).trim();
      var owners = line.slice(at + 1).split(/[\s,]+/).map(function (p) {
        return p.replace(/^@+/, "");
      }).filter(Boolean).map(function (p) { return "@" + p; });
      if (pattern && owners.length) rules.push({ pattern: pattern, owners: owners });
    });
    return rules;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { tideYaml: tideYaml, parseReviewers: parseReviewers };
    return;
  }

  var form = document.getElementById("options");
  var reviewers = document.getElementById("reviewers");
  var out = document.getElementById("yaml");
  var copy = document.getElementById("copy");
  if (!form || !out) return;
  var boxes = Array.prototype.slice.call(form.querySelectorAll("input[type=checkbox]"));

  function update() {
    out.textContent = tideYaml(boxes.map(function (b) {
      return { name: b.name, on: b.checked };
    }), reviewers ? reviewers.value : "");
  }

  form.addEventListener("change", update);
  if (reviewers) reviewers.addEventListener("input", update);
  if (copy) {
    copy.addEventListener("click", function () {
      var done = function () { copy.textContent = "Copied"; };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(out.textContent).then(done, function () {
          copy.textContent = "Select the text to copy";
        });
      } else {
        copy.textContent = "Select the text to copy";
      }
      setTimeout(function () { copy.textContent = "Copy .tide.yml"; }, 2000);
    });
  }
  update();
})();
