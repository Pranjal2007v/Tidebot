// Read one repo's numbers from a Tidebot server and show them as four cards.
(function () {
  function seconds(value) {
    if (value === null || value === undefined) return "none yet";
    if (value < 60) return value.toFixed(1) + "s";
    var m = Math.floor(value / 60);
    return m + "m " + Math.round(value - m * 60) + "s";
  }

  function plural(n, word) {
    return n + " " + word + (n === 1 ? "" : "s");
  }

  // The top few entries of a {name: count} map as "/name 3, /other 1".
  function top(counts, limit) {
    return Object.keys(counts || {}).slice(0, limit).map(function (name) {
      return "/" + name + " " + counts[name];
    }).join(", ");
  }

  // The four cards for a report from GET /api/stats/<owner>/<repo>.
  function cards(report) {
    var commands = report.commands || { total: 0, by_command: {} };
    var queue = report.queue || { jobs: 0 };
    var reviews = report.reviews || { total: 0, by_command: {} };
    return [
      { label: "Commands run", value: String(commands.total),
        detail: top(commands.by_command, 3) || "No commands yet" },
      { label: "Median queue wait", value: seconds(queue.median_wait),
        detail: plural(queue.jobs, "AI job") + ", longest " + seconds(queue.max_wait) },
      { label: "Reviews posted", value: String(reviews.total),
        detail: top(reviews.by_command, 5) || "No reviews yet" },
      { label: "Duplicates caught", value: String(report.duplicates_caught || 0),
        detail: "Issues that got a duplicates comment" },
    ];
  }

  // What to tell the reader when the server doesn't answer with numbers.
  function problem(status) {
    if (status === 401) return "The server refused the token.";
    if (status === 404) return "Stats are turned off on that server (TIDEBOT_STATS_TOKEN is not set).";
    return "The server answered " + status + ".";
  }

  function statsUrl(server, repo) {
    return server.replace(/\/+$/, "") + "/api/stats/" + repo.split("/").map(encodeURIComponent).join("/");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { cards: cards, problem: problem, seconds: seconds, statsUrl: statsUrl };
    return;
  }

  var form = document.getElementById("lookup");
  var status = document.getElementById("status");
  var numbers = document.getElementById("numbers");
  if (!form) return;

  // Remember the server and repo, never the token.
  try {
    var saved = JSON.parse(localStorage.getItem("tidebot-dashboard") || "{}");
    if (saved.server) form.server.value = saved.server;
    if (saved.repo) form.repo.value = saved.repo;
  } catch (e) { /* storage is optional */ }

  function show(report) {
    numbers.textContent = "";
    cards(report).forEach(function (c) {
      var card = document.createElement("div");
      card.className = "feature";
      var label = document.createElement("h3");
      label.textContent = c.label;
      var value = document.createElement("p");
      value.className = "stat";
      value.textContent = c.value;
      var detail = document.createElement("p");
      detail.textContent = c.detail;
      card.append(label, value, detail);
      numbers.append(card);
    });
    numbers.hidden = false;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var server = form.server.value.trim();
    var repo = form.repo.value.trim();
    try {
      localStorage.setItem("tidebot-dashboard", JSON.stringify({ server: server, repo: repo }));
    } catch (e) { /* storage is optional */ }
    status.textContent = "Loading " + repo + "...";
    numbers.hidden = true;
    fetch(statsUrl(server, repo), { headers: { Authorization: "Bearer " + form.token.value } })
      .then(function (res) {
        if (!res.ok) throw new Error(problem(res.status));
        return res.json();
      })
      .then(function (report) {
        status.textContent = "Numbers for " + report.repo + ".";
        show(report);
      })
      .catch(function (err) {
        // fetch rejects with a TypeError when the request never gets an answer.
        status.textContent = err instanceof TypeError
          ? "Couldn't reach the server. Check the address, and that it allows this page's origin."
          : err.message;
      });
  });
})();
