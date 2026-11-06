/* Play & coach page: talks to tools/play_server.py (local). */
(function () {
  const $ = (s, el) => (el || document).querySelector(s);
  fetch("data/cards.json").then(r => r.json()).then(j => RiftBoard.setCards(j)).catch(() => {});
  const api = async (path, body) => {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    return r.json();
  };
  let cur = null;
  function busy(on, msg) { document.body.classList.toggle("busy", on); $("#status").textContent = msg || ""; }

  async function loadDecks() {
    const j = await api("/api/decks");
    for (const id of ["deck0", "deck1"]) {
      $("#" + id).innerHTML = j.decks.map(d => `<option value="${d.path}">${d.name}</option>`).join("");
    }
    if (j.decks.length > 1) $("#deck1").selectedIndex = 1;
  }

  function gradeTag(g) { const cls = g === "only move" ? "only" : g; return `<span class="grade ${cls}">${g}</span>`; }

  function show(j) {
    cur = j;
    if (!j.started) return;
    RiftBoard.renderState(j.state);
    RiftBoard.bindTooltips();
    const d = j.decision;
    const opts = $("#options");
    if (j.over) {
      $("#decision").innerHTML = `<b>Game over.</b> ${j.winner == null ? "Draw" : (j.winner === j.human ? "You win!" : "The AI wins.")} (${j.reason})`;
      opts.innerHTML = "";
    } else if (d && d.player === j.human) {
      $("#decision").innerHTML = `<b>${d.kind}</b> · ${d.n} legal option${d.n === 1 ? "" : "s"}`;
      opts.innerHTML = d.labels.map((l, i) => `<button data-i="${i}">${l}</button>`).join("");
      opts.querySelectorAll("button").forEach(b => b.addEventListener("click", () => choose(+b.dataset.i)));
    } else {
      $("#decision").textContent = "AI is thinking…";
      opts.innerHTML = "";
    }
    $("#hint").innerHTML = "";
    if (j.review) {
      const r = j.review;
      let html = `${gradeTag(r.grade)} <b>${r.label}</b>`;
      if (r.win_pct != null) {
        html += `<div class="alt">Your line: <b>${r.win_pct}%</b> win chance · best line: <b>${r.best_win_pct}%</b> (${r.best_label}) · lost <b>${r.loss_pct}</b> points · rank ${r.rank}/${r.of}</div>`;
        html += `<div class="alt">Alternatives:<br>` + (r.alternatives || []).map(a => `${a.win_pct}% · ${a.label}`).join("<br>") + `</div>`;
      } else {
        html += `<div class="alt">Only one legal option, nothing to grade.</div>`;
      }
      $("#review").innerHTML = html;
    }
    const s = j.summary || {};
    if (s.moves) {
      const c = s.counts || {};
      $("#summary").innerHTML = `<b>${s.accuracy}% accuracy</b> over ${s.moves} graded moves · avg loss ${s.avg_loss} pts<br>` +
        ["best", "good", "inaccuracy", "mistake", "blunder"].filter(k => c[k]).map(k => `${gradeTag(k)} ${c[k]}`).join(" ");
    }
    $("#log").innerHTML = (j.log || []).slice().reverse().map(e =>
      `<div class="${e.player === j.human ? "me" : ""}">T${e.turn} <span class="p${e.player}c">P${e.player}</span> ${e.kind}: ${e.label}${e.grade ? " " + gradeTag(e.grade) : ""}</div>`).join("");
  }

  async function choose(i) {
    busy(true, "grading your move and letting the AI reply…");
    try { show(await api("/api/choose", { index: i })); }
    finally { busy(false); }
  }
  $("#btn-new").addEventListener("click", async () => {
    busy(true, "starting…");
    try {
      show(await api("/api/new", { deck0: $("#deck0").value, deck1: $("#deck1").value, human: +$("#human").value, ai: $("#ai").value,
                                   analysis: +$("#analysis").value, seed: +$("#seed").value }));
      $("#review").textContent = "Every move you make is rated against the engine's best line.";
      $("#summary").textContent = "–";
    } finally { busy(false); }
  });
  $("#btn-hint").addEventListener("click", async () => {
    busy(true, "thinking…");
    try {
      const j = await api("/api/hint");
      $("#hint").innerHTML = j.ok ? j.options.map(o => `${o.win_pct}% · ${o.label}`).join("<br>") : j.error;
    } finally { busy(false); }
  });
  loadDecks();
  api("/api/state").then(show).catch(() => {});
})();
