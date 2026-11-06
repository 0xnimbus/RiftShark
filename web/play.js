/* Play & coach page. Talks to tools/play_server.py when it is running, else runs the engine in a web worker (Pyodide).
   Your move is shown at once (apply), then each opponent decision arrives one by one (ai_step) and is shown from a
   display queue while the next one is being computed; the coach's grade (grade) comes last. The page never greys out. */
(function () {
  const $ = (s, el) => (el || document).querySelector(s);
  const B = RiftBoard, esc = B.esc;
  fetch("data/cards.json").then(r => r.json()).then(j => B.setCards(j)).catch(() => {});
  B.bindTooltips();

  // ------------------------------------------------------------------ backend
  let worker = null, nextId = 1; const pending = {};
  function workerApi(path, body) {
    if (!worker) {
      worker = new Worker("engine_worker.js");
      worker.onmessage = e => {
        if (e.data.progress !== undefined) { status(e.data.progress); return; }
        const p = pending[e.data.id]; delete pending[e.data.id];
        if (!p) return;
        e.data.error ? p.reject(new Error(e.data.error)) : p.resolve(e.data.result);
      };
      worker.onerror = e => { for (const k in pending) { pending[k].reject(new Error(e.message)); delete pending[k]; } };
    }
    const cmd = path.replace("/api/", "");
    return new Promise((resolve, reject) => { const id = nextId++; pending[id] = { resolve, reject }; worker.postMessage({ id, cmd, args: body || {} }); });
  }
  const serverApi = async (path, body) => {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    return r.json();
  };
  let backend = null;  // "server" | "browser"
  async function detectBackend() {
    try {
      const j = await serverApi("/api/decks");
      if (j && j.server) { backend = "server"; return j; }
    } catch (e) { /* static host */ }
    backend = "browser";
    $("#mode").textContent = "The engine runs in your browser: the first start downloads it (a few seconds), and the AI thinks a little slower than the local server.";
    $("#analysis").value = 60;
    return workerApi("/api/decks");
  }
  const api = async (path, body) => {
    const r = await (backend === "server" ? serverApi(path, body) : workerApi(path, body));
    if (r && r.ok === false && r.error) throw new Error(r.error);
    return r;
  };
  function status(msg) { $("#status").textContent = msg || ""; $("#status").classList.toggle("on", !!msg); }

  // ------------------------------------------------------------------ view state
  let cur = null;          // latest payload shown
  let inFlight = false;    // a move is being processed (you can't act, the page stays live)
  let banner = null;       // {html, me}
  let hints = null;        // index -> win%
  let filterUid = null;    // show only options for this card (clicked in hand)
  const logLines = [];     // {turn, html, cls}
  let lastTurnLogged = null;
  const chainOpen = new Set();  // chain items currently waiting to resolve (for the log's indentation)

  function gradeTag(g) { if (!g) return ""; const cls = (g === "only move" || g === "resource") ? "only" : g; return `<span class="grade ${cls}">${g}</span>`; }

  function addEvents(evs, human) {
    for (const e of evs || []) {
      if (e.turn !== lastTurnLogged && e.turn != null) {
        lastTurnLogged = e.turn;
        logLines.push({ cls: "turn", html: e.turn ? `Turn ${e.turn}` : "Before the game" });
      }
      if (e.kind === "decision") {
        if (e.dkind === "action" || (e.dkind === "mulligan" && e.player !== human)) continue;  // shown by their own entries
        logLines.push({ cls: e.player === human ? "me" : "op", html: `${e.player === human ? "You choose" : "Opponent chooses"}: ${B.say(e.choice)}` });
        continue;
      }
      const cs = B.chainStep(e, chainOpen);
      const h = B.describe(e);
      if (h) logLines.push({ cls: (e.player === human ? "me" : (e.player == null ? "" : "op")) + (chainOpen.size || cs.depth ? " chain" : ""),
                             html: h + cs.note, depth: cs.depth });
    }
    if (logLines.length > 600) logLines.splice(0, logLines.length - 600);
  }
  function renderLog() {
    const el = $("#log");
    el.innerHTML = logLines.map(l => `<div class="ln ${l.cls}"${l.depth ? ` style="margin-left:${Math.min(4, l.depth) * 14}px"` : ""}>${l.html}</div>`).join("");
    el.scrollTop = el.scrollHeight;
  }

  /* uid -> option indexes, for clicking a card in hand / champion zone to play it */
  function playableMap(d) {
    const m = {};
    if (!d || d.kind !== "action") return m;
    d.labels.forEach((l, i) => { if (l.startsWith("play ")) { const u = B.uidsIn(l)[0]; if (u != null) (m[u] = m[u] || []).push(i); } });
    return m;
  }

  function drawBoard(j, opts) {
    if (!j || !j.started) return;
    const mine = j.decision && j.decision.player === j.human && !j.over && !inFlight;
    B.render($("#board"), j.state, Object.assign({
      me: j.human, victory: j.victory || 8, thinking: inFlight && !(j.decision && j.decision.player === j.human),
      playable: mine ? playableMap(j.decision) : {}, decisionKind: mine ? j.decision.kind : null, banner,
    }, opts || {}));
    $("#board").querySelectorAll(".card[data-opts]").forEach(el => el.addEventListener("click", () => {
      const ix = el.dataset.opts.split(",").map(Number);
      if (ix.length === 1) choose(ix[0]);
      else { filterUid = +el.dataset.uid; drawDecision(cur); }
    }));
  }

  function optionButton(d, i) {
    const h = hints && hints[i] != null ? `<span class="hintpct">${hints[i]}%</span>` : "";
    return `<button class="opt" data-i="${i}">${B.thumbs(d.labels[i])}<span class="ol">${B.say(d.labels[i])}</span>${h}</button>`;
  }
  function drawDecision(j) {
    const d = j && j.decision;
    const opts = $("#options");
    $("#btn-hint").disabled = true;
    if (!j || !j.started) return;
    if (j.over) {
      const res = j.winner == null ? "Draw" : (j.winner === j.human ? "You win!" : "The AI wins.");
      $("#decision").innerHTML = `<h3>Game over</h3><p class="big">${res}</p><p class="muted">${esc(j.reason || "")}</p>`;
      opts.innerHTML = "";
      return;
    }
    if (inFlight || !d || d.player !== j.human) {
      $("#decision").innerHTML = `<h3>Opponent's move</h3><p class="muted"><span class="dots"><span></span><span></span><span></span></span> The opponent is thinking. Their moves appear on the board as they make them.</p>`;
      opts.innerHTML = "";
      return;
    }
    const [title, text] = B.explain(d, j.state);
    const src = d.source ? `<div class="src" data-uid="${d.source.uid}">${d.source.image ? `<img src="${esc(d.source.image)}" alt="">` : ""}<span>${esc(d.source.name)}</span></div>` : "";
    $("#decision").innerHTML = `<h3>${title}</h3>${src}<p>${text}</p>`;
    let idx = d.labels.map((_, i) => i);
    if (filterUid != null) {
      const f = idx.filter(i => B.uidsIn(d.labels[i])[0] === filterUid);
      if (f.length) idx = f; else filterUid = null;
    }
    if (d.kind === "mulligan" && d.option_uids) { drawMulligan(j, d); return; }
    let html = "";
    if (filterUid != null) html += `<button class="link" id="clear-filter">← show all options</button>`;
    if (d.kind === "action") {
      const groups = [[/^play /, "Play a card"], [/^move /, "Move units"], [/^activate /, "Use an ability"], [/^hide /, "Hide a card"],
                      [/^(exhaust|recycle) an? \w+ rune/, "Use runes now (adds to your pool)"]];
      const used = new Set();
      for (const [k, t] of groups) {
        const g = idx.filter(i => k.test(d.labels[i]));
        g.forEach(i => used.add(i));
        if (g.length) html += `<div class="og"><div class="ogt">${t}</div>${g.map(i => optionButton(d, i)).join("")}</div>`;
      }
      const rest = idx.filter(i => !used.has(i));
      if (rest.length) html += `<div class="og end">${rest.map(i => optionButton(d, i)).join("")}</div>`;
    } else {
      html += idx.map(i => optionButton(d, i)).join("");
    }
    opts.innerHTML = html;
    opts.querySelectorAll("button.opt").forEach(b => b.addEventListener("click", () => choose(+b.dataset.i)));
    const cf = $("#clear-filter");
    if (cf) cf.addEventListener("click", () => { filterUid = null; drawDecision(cur); });
    $("#btn-hint").disabled = d.n < 2;
  }

  /* Mulligan: your hand as big cards; click up to two to set aside, then confirm (the matching engine option is chosen). */
  let mullSel = [];
  function drawMulligan(j, d) {
    const me = j.state.players.find(p => p.idx === j.human);
    const key = a => a.slice().sort((x, y) => x - y).join(",");
    const idxOf = sel => d.option_uids.findIndex(o => key(o) === key(sel));
    mullSel = mullSel.filter(u => me.hand.some(c => c.uid === u));
    const cards = me.hand.map(c => `<button class="mull-card${mullSel.includes(c.uid) ? " sel" : ""}" data-uid="${c.uid}">
        <img src="${esc(c.image || "")}" alt=""><span>${esc(c.name)}</span>${mullSel.includes(c.uid) ? '<i class="mull-tag">SET ASIDE</i>' : ""}</button>`).join("");
    const n = mullSel.length;
    $("#options").innerHTML = `<div class="mull">${cards}</div>
      <button class="opt primary" id="mull-go">${n ? `Mulligan ${n} card${n === 1 ? "" : "s"} (draw ${n} new)` : "Keep this hand"}</button>`;
    $("#options").querySelectorAll(".mull-card").forEach(b => b.addEventListener("click", () => {
      const u = +b.dataset.uid;
      if (mullSel.includes(u)) mullSel = mullSel.filter(x => x !== u);
      else if (mullSel.length < 2) mullSel.push(u);
      drawMulligan(cur, cur.decision);
    }));
    $("#mull-go").addEventListener("click", () => {
      const i = idxOf(mullSel);
      if (i >= 0) { mullSel = []; choose(i); }
    });
    $("#btn-hint").disabled = d.n < 2;
  }

  function drawReview(r) {
    if (!r) return;
    let html = `${gradeTag(r.grade)} ${B.say(r.label)}`;
    if (r.win_pct != null) {
      html += `<div class="alt">Your line: <b>${r.win_pct}%</b> to win. Best line: <b>${r.best_win_pct}%</b> (${B.say(r.best_label)}). ` +
        (r.loss_pct > 0 ? `You gave up <b>${r.loss_pct}</b> points of win chance.` :
          (r.raw_loss_pct > 0 ? `The gap (${r.raw_loss_pct} points) is within the search's margin of error (±${r.noise_pct}), so it isn't counted.` : "That was the engine's top choice.")) +
        ` Rank ${r.rank} of ${r.of}.</div>`;
      html += `<div class="alt alts">${(r.alternatives || []).filter(a => a.win_pct != null).map(a => `<div><span class="pct">${a.win_pct}%</span> ${B.say(a.label)}</div>`).join("")}</div>`;
    } else if (r.grade === "resource") html += `<div class="alt">${r.note || "Floating resources isn't graded on its own."}</div>`;
    else html += `<div class="alt">Only one legal option, nothing to grade.</div>`;
    $("#review").innerHTML = html;
  }
  function drawSummary(s) {
    if (!s || !s.moves) return;
    const c = s.counts || {};
    $("#summary").innerHTML = `<b>${s.accuracy}% accuracy</b> over ${s.moves} graded moves (average loss ${s.avg_loss} points)<br>` +
      ["best", "good", "inaccuracy", "mistake", "blunder"].filter(k => c[k]).map(k => `${gradeTag(k)} ${c[k]}`).join(" ");
  }

  function show(j) {
    cur = j;
    if (!j.started) return;
    if (!j.__logged) { j.__logged = true; addEvents(j.events, j.human); }  // a payload can be drawn twice; log it once
    renderLog();
    drawBoard(j);
    drawDecision(j);
    if (j.summary) drawSummary(j.summary);
  }

  // ------------------------------------------------------------------ display queue
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const DWELL = 900;  // ms each opponent move stays on screen before the next one is drawn
  async function playOut(first) {
    /* producer: ask the engine for opponent moves one at a time; consumer: draw them with a minimum dwell time */
    const queue = [];
    let done = first.over || !(first.decision && first.decision.player !== first.human);
    let wake = null, err = null;
    const producer = (async () => {
      try {
        while (!done) {
          const r = await api("/api/ai_step", {});
          queue.push(r);
          if (r.ai_done || r.over) done = true;
          if (wake) { wake(); wake = null; }
        }
      } catch (e) { err = e; done = true; if (wake) { wake(); wake = null; } }
    })();
    let last = cur;
    while (true) {
      if (!queue.length) {
        if (done) break;
        await new Promise(r => { wake = r; });
        continue;
      }
      const r = queue.shift();
      const mv = r.ai_move;
      banner = mv ? { me: false, html: `<span class="who-op">Opponent</span> ${B.say(mv.label)}` } : null;
      show(r);
      last = r;
      await sleep(queue.length ? DWELL * 0.6 : DWELL);
    }
    await producer;
    if (err) throw err;
    return last;
  }

  async function choose(i) {
    if (inFlight || !cur || !cur.decision) return;
    const d = cur.decision, label = d.labels[i];
    inFlight = true; filterUid = null; hints = null;
    banner = { me: true, html: `<span class="who-me">You</span> ${B.say(label)}` };
    drawBoard(cur); drawDecision(cur);
    $("#review").innerHTML = `${B.say(label)}<div class="alt"><span class="dots"><span></span><span></span><span></span></span> the coach will grade this once the opponent has moved…</div>`;
    let graded = false;
    try {
      const r = await api("/api/apply", { index: i });
      show(r);
      const last = await playOut(r);
      inFlight = false; banner = null;
      show(last);
      if (r.grading || last.grading) {
        status("coach is grading your move…");
        const g = await api("/api/grade", {});
        graded = true;
        drawReview(g.review); drawSummary(g.summary);
      } else {
        drawReview({ grade: "only move", label, win_pct: null });
      }
    } catch (e) {
      status("error: " + e.message);
    } finally {
      inFlight = false; banner = null;
      if (cur) { drawBoard(cur); drawDecision(cur); }
      if (graded || !$("#status").textContent.startsWith("error")) status("");
    }
  }

  // ------------------------------------------------------------------ controls
  async function loadDecks() {
    const j = await detectBackend();
    for (const id of ["deck0", "deck1"]) $("#" + id).innerHTML = j.decks.map(d => `<option value="${esc(d.path)}">${esc(d.name)}</option>`).join("");
    if (j.decks.length > 1) $("#deck1").selectedIndex = 1;
    if (!j.decks.length) $("#mode").textContent = "No deck can run exactly as printed yet, so there is nothing to play. The engine refuses decks with unscripted cards.";
  }
  $("#btn-new").addEventListener("click", async () => {
    if (inFlight) return;
    inFlight = true; logLines.length = 0; lastTurnLogged = null; chainOpen.clear(); hints = null; filterUid = null;
    $("#board").innerHTML = `<div class="empty-board"><span class="dots"><span></span><span></span><span></span></span> Shuffling and dealing…</div>`;
    status("starting…");
    try {
      // a fresh shuffle every game unless a seed was typed in to replay one
      const seed = $("#seed").value.trim() === "" ? Math.floor(Math.random() * 2147483647) : +$("#seed").value;
      const j = await api("/api/new", { deck0: $("#deck0").value, deck1: $("#deck1").value, human: +$("#human").value, ai: $("#ai").value,
                                        analysis: +$("#analysis").value, seed });
      inFlight = false;
      $("#review").textContent = "Every move you make is rated against the engine's best line, like a chess engine.";
      $("#summary").textContent = "";
      $("#setup").open = false;
      $("#seed-used").textContent = `Game seed ${j.seed != null ? j.seed : seed} (type it under "New game" to replay this exact shuffle).`;
      show(j);
      status("");
    } catch (e) { inFlight = false; status("error: " + e.message); }
  });
  $("#btn-hint").addEventListener("click", async () => {
    if (inFlight) return;
    $("#btn-hint").disabled = true;
    status("the coach is looking at every option…");
    try {
      const j = await api("/api/hint");
      hints = {};
      (j.options || []).forEach(o => { hints[o.index] = o.win_pct; });
      drawDecision(cur);
      status("");
    } catch (e) { status("error: " + e.message); }
  });
  loadDecks().then(() => { if (backend === "server") api("/api/state").then(j => { if (j.started) { $("#setup").open = false; show(j); } }).catch(() => {}); })
    .catch(e => status("could not load the engine: " + e.message));
})();
