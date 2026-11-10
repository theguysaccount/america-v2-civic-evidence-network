/* AuditLine static edition: search over the published records. No dependencies, no tracking of its own. */
(function () {
  "use strict";
  var root = document.getElementById("search");
  if (!root) return;
  var base = (document.querySelector('meta[name="site-base"]') || {}).content || "";
  var els = { q: root.querySelector("[name=q]"), p: root.querySelector("[name=p]"), a: root.querySelector("[name=a]"), s: root.querySelector("[name=s]") };
  var out = document.getElementById("results"), count = document.getElementById("count"), more = document.getElementById("more");
  var PAGE = 60, shown = PAGE, data = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmt(d) {
    if (!d) return "";
    var x = new Date(d + "T00:00:00Z");
    return isNaN(x) ? "" : x.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
  }
  function row(r) {
    // r = [publisher index, slug, number, agency index, status index, issued, text]
    var pub = data.publishers[r[0]], status = data.statuses[r[4]];
    var state = /^open/i.test(status) ? "open" : /^closed/i.test(status) ? "closed" : "";
    return '<li><span><a href="' + base + "/rec/" + pub.id + "/" + esc(r[1]) + '/">' + esc(r[6]) + "</a><small>" + esc(pub.short) + " " + esc(r[2]) +
      " · " + esc(data.agencies[r[3]]) + (r[5] ? " · issued " + fmt(r[5]) : "") + '</small></span><span class="status ' + state + '">' + esc(status) + "</span></li>";
  }
  function render() {
    var words = els.q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    var p = els.p.value, a = els.a.value, s = els.s.value;
    var list = data.records.filter(function (r) {
      if (p !== "" && String(r[0]) !== p) return false;
      if (a !== "" && String(r[3]) !== a) return false;
      var status = data.statuses[r[4]];
      if (s === "open" && !/^open/i.test(status)) return false;
      if (s === "closed" && !/^closed/i.test(status)) return false;
      if (!words.length) return true;
      var hay = (r[2] + " " + r[6] + " " + data.agencies[r[3]]).toLowerCase();
      return words.every(function (w) { return hay.indexOf(w) >= 0; });
    });
    count.textContent = list.length.toLocaleString("en-US") + (list.length === 1 ? " recommendation" : " recommendations") +
      (list.length === data.records.length ? "" : " of " + data.records.length.toLocaleString("en-US"));
    out.innerHTML = list.slice(0, shown).map(row).join("") || "<li>Nothing matches. Try fewer words.</li>";
    more.hidden = list.length <= shown;
    var q = new URLSearchParams();
    Object.keys(els).forEach(function (k) { if (els[k].value) q.set(k, els[k].value); });
    var qs = q.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
  }
  fetch(base + "/assets/search.json").then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function (d) {
    data = d;
    d.publishers.forEach(function (p, i) { els.p.appendChild(new Option(p.short, String(i))); });
    d.agencies.map(function (n, i) { return [n, i]; }).sort(function (x, y) { return x[0].localeCompare(y[0]); })
      .forEach(function (x) { els.a.appendChild(new Option(x[0], String(x[1]))); });
    var params = new URLSearchParams(location.search);
    Object.keys(els).forEach(function (k) { if (params.get(k)) els[k].value = params.get(k); });
    var t;
    Object.keys(els).forEach(function (k) {
      els[k].addEventListener("input", function () { shown = PAGE; clearTimeout(t); t = setTimeout(render, 100); });
    });
    more.addEventListener("click", function () { shown += PAGE * 2; render(); });
    root.hidden = false;
    render();
  }).catch(function () {
    out.innerHTML = "<li>The search index could not be loaded. Browse by agency instead.</li>";
  });
})();
