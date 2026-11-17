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
    $("#analysis").value = 100;     // deeper than 60 so fewer moves fall inside the margin of error; about 1.6x the time per move
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
        if (e.dkind === "action" && e.choice === "pass") {   // passing Focus / priority is what moves a showdown or chain along
          const st = cur && cur.state, sd = st && st.showdown;
          logLines.push({ cls: (e.player === human ? "me" : "op") + " pass",
                          html: `${e.player === human ? "You pass" : "Opponent passes"}${chainOpen.size ? " (chain)" : sd ? " Focus" : ""}.` });
          continue;
        }
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

  /* ---- drag and drop, clickable runes (the decision's meta says what each option does to which card and where) */
  let picked = {};        // uid -> true: units chosen to move together
  let paySel = {};        // uid -> "ex" | "rc": runes you tapped for the current payment
  let payKey = null;      // which pay decision paySel belongs to
  const myTurnDecision = j => j && j.decision && j.decision.player === j.human && !j.over && !inFlight;
  function dragInfo(d) {
    const drag = {}, runes = {};
    if (!d) return { drag, runes };
    if (d.kind === "action" && d.meta) {
      d.meta.forEach(m => {
        if (m.k === "play" || m.k === "move" || m.k === "hide") m.uids.forEach(u => { drag[u] = true; });
        if (m.k === "rune") runes[m.uids[0]] = "tap";
      });
    }
    if (d.kind === "pay" && d.plans) {
      const grp = payGroups(cur);
      d.plans.forEach(pl => pl.runes.forEach(r => { (grp.members[grp.of[r.uid]] || [r.uid]).forEach(u => { if (!runes[u]) runes[u] = "pick"; }); }));
      Object.entries(paySel).forEach(([u, h]) => { runes[u] = h; });
    }
    return { drag, runes };
  }
  function drawBoard(j, opts) {
    if (!j || !j.started) return;
    const mine = myTurnDecision(j);
    const d = mine ? j.decision : null;
    if (d && d.kind === "pay") { const k = d.labels.join("|"); if (k !== payKey) { payKey = k; paySel = {}; } } else { paySel = {}; payKey = null; }
    if (!d || d.kind !== "action") picked = {};
    const di = dragInfo(d);
    B.render($("#board"), j.state, Object.assign({
      me: j.human, victory: j.victory || 8, thinking: inFlight && !(j.decision && j.decision.player === j.human),
      playable: mine ? playableMap(j.decision) : {}, decisionKind: mine ? j.decision.kind : null, banner,
      drag: di.drag, runes: di.runes, selected: picked,
    }, opts || {}));
    // a big button on the mat for ending the turn / passing, like a digital TCG client
    if (d && d.kind === "action") {
      const i = d.labels.findIndex(l => l === "end turn"), k = i >= 0 ? i : d.labels.findIndex(l => l === "pass");
      const mat = $("#board .mat");
      if (k >= 0 && mat) {
        mat.insertAdjacentHTML("beforeend", `<button class="end-btn ${i >= 0 ? "end" : "pass"}" data-i="${k}">${i >= 0 ? "End<br>turn" : "Pass"}</button>`);
        mat.querySelector(".end-btn").addEventListener("click", ev => { ev.stopPropagation(); choose(k); });
      }
    }
  }

  // which options a drop of `uids` on zone `zone` (data-zone key, or null = anywhere on the mat) would take
  const sortKey = a => a.slice().sort((x, y) => x - y).join(",");
  function dropOptions(d, uids, zone) {
    if (!d || !d.meta) return [];
    const set = sortKey(uids), out = [];
    d.meta.forEach((m, i) => {
      if (m.k === "play" || m.k === "hide") {
        if (uids.length === 1 && m.uids[0] === uids[0] && (m.to === zone || (zone == null && m.to == null && m.k === "play"))) out.push(i);
      } else if (m.k === "move" && zone && m.to === zone && sortKey(m.uids) === set) out.push(i);
    });
    if (!out.length && zone) d.meta.forEach((m, i) => { if (m.k === "move_select" && m.to === zone) out.push(i); });
    return out;
  }
  function zonesFor(d, uids) {
    const z = new Set(); let anywhere = false;
    if (!d || !d.meta) return { z, anywhere };
    const set = sortKey(uids);
    d.meta.forEach(m => {
      if ((m.k === "play" || m.k === "hide") && uids.length === 1 && m.uids[0] === uids[0]) { if (m.to) z.add(m.to); else if (m.k === "play") anywhere = true; }
      if (m.k === "move" && sortKey(m.uids) === set) z.add(m.to);
    });
    if (!z.size && uids.length > 1) d.meta.forEach(m => { if (m.k === "move_select") z.add(m.to); });  // choose which on drop
    return { z, anywhere };
  }
  /* A small menu at the pointer when a drop (or a rune click) could mean more than one thing. */
  function popMenu(x, y, items) {
    closePop();
    const el = document.createElement("div");
    el.id = "pop-menu";
    el.innerHTML = items.map((it, k) => `<button data-k="${k}">${it.html}</button>`).join("") + `<button class="cancel" data-k="-1">Cancel</button>`;
    document.body.appendChild(el);
    const w = el.offsetWidth, h = el.offsetHeight;
    el.style.left = Math.max(6, Math.min(window.innerWidth - w - 6, x - w / 2)) + "px";
    el.style.top = Math.max(6, Math.min(window.innerHeight - h - 6, y + 10)) + "px";
    el.addEventListener("click", ev => { const b = ev.target.closest("button"); if (!b) return; ev.stopPropagation(); const k = +b.dataset.k; closePop(); if (k >= 0) items[k].go(); });
    setTimeout(() => document.addEventListener("pointerdown", outsidePop, true), 0);
  }
  function outsidePop(ev) { if (!ev.target.closest("#pop-menu")) closePop(); }
  function closePop() { const e = $("#pop-menu"); if (e) e.remove(); document.removeEventListener("pointerdown", outsidePop, true); }
  function chooseAmong(ix, x, y) {
    const d = cur.decision;
    if (ix.length === 1) choose(ix[0]);
    else if (ix.length > 1) popMenu(x, y, ix.map(i => ({ html: B.say(d.labels[i]), go: () => choose(i) })));
  }

  let drag = null, suppressClick = false;
  const boardEl = $("#board");
  boardEl.addEventListener("dragstart", ev => ev.preventDefault());   // no native image drag: it would cancel ours
  boardEl.addEventListener("pointerdown", ev => {
    if (ev.button !== 0 || !myTurnDecision(cur)) return;
    const c = ev.target.closest(".card[data-drag]");
    if (!c) return;
    drag = { el: c, uid: +c.dataset.uid, x0: ev.clientX, y0: ev.clientY, on: false, pid: ev.pointerId };
  });
  window.addEventListener("pointermove", ev => {
    if (!drag || ev.pointerId !== drag.pid) return;
    if (!drag.on) {
      if (Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 7) return;
      startDrag(ev);
    }
    ev.preventDefault();
    const g = drag.ghost;
    g.style.left = (ev.clientX - drag.dx) + "px"; g.style.top = (ev.clientY - drag.dy) + "px";
    const under = document.elementFromPoint(ev.clientX, ev.clientY);
    const zEl = under && under.closest("[data-zone]");
    const zone = zEl && drag.zones.z.has(zEl.dataset.zone) ? zEl.dataset.zone : null;
    boardEl.querySelectorAll(".drop-hover").forEach(e => e.classList.remove("drop-hover"));
    const overMat = !!(under && under.closest(".mat") && !under.closest(".my-hand"));
    if (zone) zEl.classList.add("drop-hover");
    else if (drag.zones.anywhere && overMat) boardEl.querySelector(".mat").classList.add("drop-hover");
    drag.zone = zone; drag.overMat = overMat;
  });
  function startDrag(ev) {
    drag.on = true;
    const d = cur.decision;
    const group = picked[drag.uid] ? Object.keys(picked).map(Number) : [drag.uid];
    if (!picked[drag.uid]) picked = {};
    drag.uids = group;
    drag.zones = zonesFor(d, group);
    const r = drag.el.getBoundingClientRect();
    drag.dx = ev.clientX - r.left; drag.dy = ev.clientY - r.top;
    const g = drag.el.cloneNode(true);
    g.classList.add("drag-ghost"); g.classList.remove("exhausted");
    g.style.width = drag.el.offsetWidth + "px"; g.style.left = r.left + "px"; g.style.top = r.top + "px";
    if (group.length > 1) g.insertAdjacentHTML("beforeend", `<i class="ghost-n">×${group.length}</i>`);
    document.body.appendChild(g);
    drag.ghost = g;
    group.forEach(u => { const e = boardEl.querySelector(`.card[data-uid="${u}"]`); if (e) e.classList.add("dragging"); });
    drag.zones.z.forEach(k => { const e = boardEl.querySelector(`[data-zone="${k}"]`); if (e) e.classList.add("drop-ok"); });
    if (drag.zones.anywhere) boardEl.querySelector(".mat").classList.add("drop-any");
    document.body.classList.add("is-dragging");
    $("#tooltip").hidden = true;
  }
  function endDragVisuals() {
    document.body.classList.remove("is-dragging");
    boardEl.querySelectorAll(".drop-ok,.drop-hover,.drop-any,.dragging").forEach(e => e.classList.remove("drop-ok", "drop-hover", "drop-any", "dragging"));
  }
  window.addEventListener("pointerup", ev => {
    if (!drag || ev.pointerId !== drag.pid) return;
    const dg = drag; drag = null;
    if (!dg.on) return;                     // a plain click: the click listener handles it
    suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);
    endDragVisuals();
    const d = cur && cur.decision;
    let ix = [];
    if (dg.zone) ix = dropOptions(d, dg.uids, dg.zone);
    else if (dg.zones.anywhere && dg.overMat) ix = dropOptions(d, dg.uids, null);
    if (ix.length) { dg.ghost.remove(); picked = {}; status(""); chooseAmong(ix, ev.clientX, ev.clientY); return; }
    // dropped somewhere it can't go: fly back
    const r = dg.el.getBoundingClientRect();
    const a = dg.ghost.animate([{ left: dg.ghost.style.left, top: dg.ghost.style.top }, { left: r.left + "px", top: r.top + "px" }], { duration: 220, easing: "ease-out" });
    a.onfinish = () => dg.ghost.remove();
  });
  window.addEventListener("pointercancel", () => { if (drag && drag.ghost) drag.ghost.remove(); drag = null; endDragVisuals(); });

  boardEl.addEventListener("click", ev => {
    if (suppressClick || !myTurnDecision(cur)) return;
    const d = cur.decision;
    const rn = ev.target.closest("[data-rune]");
    if (rn) { runeClick(+rn.dataset.rune, ev); return; }
    const c = ev.target.closest(".card[data-uid]");
    if (!c) return;
    const uid = +c.dataset.uid;
    if (c.dataset.opts) {                       // a playable card in hand / champion zone
      const ix = c.dataset.opts.split(",").map(Number);
      if (ix.length === 1) choose(ix[0]);
      else { filterUid = uid; drawDecision(cur); }
      return;
    }
    if (c.dataset.drag && d.kind === "action") {  // a unit on the board: pick it to move together with others
      if (picked[uid]) delete picked[uid]; else picked[uid] = true;
      drawBoard(cur);
      const n = Object.keys(picked).length;
      status(n ? `${n} unit${n === 1 ? "" : "s"} picked: drag one of them to a battlefield or your base to move them together` : "");
    }
  });

  /* Runes that the engine treats as the same (same domain, same ready state). */
  function payGroups(j) {
    const of = {}, members = {};
    if (!j || !j.state) return { of, members };
    const me = j.state.players.find(p => p.idx === j.human);
    me.runes.forEach(r => { const g = `${(r.name || "").split(" ")[0]}|${r.exhausted ? 1 : 0}`; of[r.uid] = g; (members[g] = members[g] || []).push(r.uid); });
    return { of, members };
  }
  /* Runes: on your turn a click offers Exhaust / Recycle; while paying, a click cycles untouched -> tap -> recycle -> untouched. */
  function runeClick(uid, ev) {
    const d = cur.decision;
    if (d.kind === "action" && d.meta) {
      const ix = d.meta.map((m, i) => m.k === "rune" && m.uids[0] === uid ? i : -1).filter(i => i >= 0);
      if (ix.length) popMenu(ev.clientX, ev.clientY, ix.map(i => ({ html: B.say(d.labels[i]) + ' <span class="muted">(adds to your pool)</span>', go: () => choose(i) })));
      return;
    }
    if (d.kind === "pay" && d.plans) {
      const grp = payGroups(cur), g = grp.of[uid];
      const hows = new Set();
      d.plans.forEach(pl => pl.runes.forEach(r => { if (grp.of[r.uid] === g) hows.add(r.how); }));
      if (!hows.size) return;
      const order = [undefined, "ex", "rc"].filter(h => h === undefined || hows.has(h));
      const nx = order[(order.indexOf(paySel[uid]) + 1) % order.length];
      if (nx) paySel[uid] = nx; else delete paySel[uid];
      drawBoard(cur); drawDecision(cur);
    }
  }
  /* The payment plan that matches the runes you tapped (by group and tap/recycle; runes of a group are interchangeable). */
  function matchPlan(j, d) {
    const grp = payGroups(j);
    const sig = list => list.map(x => `${grp.of[x.uid]}|${x.how}`).sort().join(",");
    const want = sig(Object.entries(paySel).map(([u, h]) => ({ uid: +u, how: h })));
    let best = -1;
    d.plans.forEach((pl, i) => { if (!pl.decline && sig(pl.runes) === want && (best < 0 || pl.abilities.length < d.plans[best].abilities.length)) best = i; });
    return best;
  }
  function drawPay(j, d) {
    const n = Object.keys(paySel).length;
    const m = matchPlan(j, d);
    const pw = (d.cost && d.cost.power) || [];
    const cost = d.cost ? `${d.cost.energy || 0} energy${pw.length ? " + " + pw.length + " " + esc(pw.map(x => x.split("|").join(" or ")).join(", ")) + " power" : ""}` : "";
    let html = `<div class="pay-tap"><b>Tap your runes</b> on the board to pay${cost ? " <b>" + cost + "</b>" : ""}. Click a glowing rune once to exhaust it (1 energy), again to recycle it (1 power of its domain), and again to undo.
      <div class="pay-now">${n ? `${n} rune${n === 1 ? "" : "s"} chosen` : "No runes chosen yet"}${m >= 0 ? `: <span class="ok">${B.say(d.labels[m])}</span>` : n ? ' <span class="muted">(not a complete payment yet)</span>' : ""}</div>
      <button class="opt primary" id="pay-go" ${m >= 0 ? "" : "disabled"}>Pay</button></div>`;
    const dec = d.plans.findIndex(p => p.decline);
    html += `<details class="og runes"><summary class="ogt">Or pick a payment from the list (${d.plans.filter(p => !p.decline).length})</summary>` +
      d.labels.map((_, i) => i === dec ? "" : optionButton(d, i)).join("") + `</details>`;
    if (dec >= 0) html += `<div class="og end">${optionButton(d, dec)}</div>`;
    $("#options").innerHTML = html;
    $("#options").querySelectorAll("button.opt[data-i]").forEach(b => b.addEventListener("click", () => choose(+b.dataset.i)));
    $("#pay-go").addEventListener("click", () => { const k = matchPlan(cur, cur.decision); if (k >= 0) choose(k); });
    $("#btn-hint").disabled = d.n < 2;
  }

  function optionButton(d, i) {
    const h = hints && hints[i] != null ? `<span class="hintpct">${hints[i]}%</span>` : "";
    if (d.kind === "assign_damage") {
      const plan = B.damagePlan(d.labels[i]);
      if (plan) return `<button class="opt dmg" data-i="${i}">${plan}${h}</button>`;
    }
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
    if (d.kind === "pay" && d.plans && !hints) { drawPay(j, d); return; }
    let html = "";
    if (filterUid != null) html += `<button class="link" id="clear-filter">← show all options</button>`;
    if (d.kind === "action") {
      const groups = [[/^play /, "Play a card"], [/^move /, "Move units"], [/^activate /, "Use an ability"], [/^hide /, "Hide a card"],
                      [/^(exhaust|recycle) an? \w+ rune/, "Use runes now (adds to your pool)"]];
      const used = new Set();
      for (const [k, t] of groups) {
        const g = idx.filter(i => k.test(d.labels[i]));
        g.forEach(i => used.add(i));
        if (!g.length) continue;
        if (/rune/.test(t)) {
          // optional: legal at any time, only useful right before paying (the payment step offers runes too)
          html += `<details class="og runes"><summary class="ogt">Optional: use runes early (${g.length})</summary>` +
                  `${g.map(i => optionButton(d, i)).join("")}</details>`;
        } else {
          html += `<div class="og"><div class="ogt">${t}</div>${g.map(i => optionButton(d, i)).join("")}</div>`;
        }
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
    // coach recommendations: best options first, click one to select those cards
    let coach = "";
    if (hints && Object.keys(hints).length) {
      const ranked = Object.keys(hints).map(Number).filter(i => hints[i] != null).sort((x, y) => hints[y] - hints[x]).slice(0, 6);
      coach = `<div class="og"><div class="ogt">Coach: best mulligans (win chance)</div>` +
        ranked.map(i => `<button class="opt mull-hint" data-i="${i}"><span class="ol">${B.say(d.labels[i])}</span>` +
          `<span class="hintpct">${hints[i]}%</span></button>`).join("") + `</div>`;
    }
    $("#options").innerHTML = `<div class="mull">${cards}</div>
      <button class="opt primary" id="mull-go">${n ? `Mulligan ${n} card${n === 1 ? "" : "s"} (draw ${n} new)` : "Keep this hand"}</button>${coach}`;
    $("#options").querySelectorAll(".mull-hint").forEach(b => b.addEventListener("click", () => {
      mullSel = (d.option_uids[+b.dataset.i] || []).slice();
      drawMulligan(cur, cur.decision);
    }));
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

  /* One request at a time: a click while the coach is still grading waits for that grade, then plays. */
  let gradeP = null;
  async function runGrade() {
    status("coach is grading your move…");
    try {
      const g = await api("/api/grade", {});
      drawReview(g.review); drawSummary(g.summary);
      status("");
    } catch (e) { status("error: " + e.message); }
    finally { gradeP = null; }
  }
  async function choose(i) {
    if (inFlight || !cur || !cur.decision) return;
    const d = cur.decision, label = d.labels[i];
    inFlight = true; filterUid = null; hints = null;
    banner = { me: true, html: `<span class="who-me">You</span> ${B.say(label)}` };
    drawBoard(cur); drawDecision(cur);
    try {
      if (gradeP) await gradeP;
      $("#review").innerHTML = `${B.say(label)}<div class="alt"><span class="dots"><span></span><span></span><span></span></span> the coach will grade this once the opponent has moved…</div>`;
      const r = await api("/api/apply", { index: i });
      show(r);
      const last = await playOut(r);
      inFlight = false; banner = null;
      show(last);
      if (r.grading || last.grading) gradeP = runGrade();
      else drawReview({ grade: "only move", label, win_pct: null });
    } catch (e) {
      status("error: " + e.message);
    } finally {
      inFlight = false; banner = null;
      if (cur) { drawBoard(cur); drawDecision(cur); }
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
    if (gradeP) await gradeP;
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
