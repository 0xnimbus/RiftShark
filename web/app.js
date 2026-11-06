/* RiftShark frontend: dashboard + replay viewer. Plain JS, no build step. Data lives in ./data/. */
(function () {
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const DATA = "data/";
  // Optional online store (Supabase, read-only publishable key). Falls back to the static files in ./data/.
  const CFG = window.RIFTSHARK_CONFIG || {};
  async function sb(path) {
    if (!CFG.supabaseUrl || !CFG.supabaseKey) throw new Error("no supabase config");
    const r = await fetch(CFG.supabaseUrl + "/rest/v1/" + path, { headers: { apikey: CFG.supabaseKey, Authorization: "Bearer " + CFG.supabaseKey } });
    if (!r.ok) throw new Error("supabase " + r.status);
    return r.json();
  }
  let SB_BATCH = null;
  async function loadFromSupabase() {
    const b = (await sb("batches?select=*&order=created_at.desc&limit=1"))[0];
    if (!b) throw new Error("no batches");
    const cards = await sb(`card_stats?select=deck,card,games,played,win_rate_when_played&batch_id=eq.${b.id}&order=games.desc&limit=2000`);
    const decks = await sb(`deck_stats?select=*&batch_id=eq.${b.id}`);
    const summary = Object.assign({}, b.summary || {}, { games: b.games, draws: b.draws, avg_turns: b.avg_turns, avg_secs: b.avg_secs, cards,
      decks: Object.fromEntries(decks.map(d => [d.deck, d])) });
    SB_BATCH = b;
    return { summary, batch: b };
  }

  // ------------------------------------------------------------ tabs
  $$("nav button").forEach(b => b.addEventListener("click", () => {
    $$("nav button").forEach(x => x.classList.toggle("active", x === b));
    $$(".tab").forEach(t => t.classList.toggle("active", t.id === b.dataset.tab));
    location.hash = b.dataset.tab;
  }));
  if (location.hash) { const b = $(`nav button[data-tab="${location.hash.slice(1)}"]`); if (b) b.click(); }

  // ------------------------------------------------------------ dashboard
  async function loadDashboard() {
    let res, source = "static files";
    try { res = await loadFromSupabase(); source = `Supabase batch #${res.batch.id} (${res.batch.policy_a} vs ${res.batch.policy_b}, ${new Date(res.batch.created_at).toLocaleString()})`; }
    catch (e) {
      try { res = await (await fetch(DATA + "results.json")).json(); }
      catch (e2) { $("#summary").innerHTML = `<div class="stat"><div class="v">No data</div><div class="l">run a batch and export to web/data</div></div>`; return; }
    }
    const s = res.summary;
    $("#source").textContent = "source: " + source;
    const stats = [
      ["Games", s.games], ["Avg turns", s.avg_turns], ["Draws / limits", s.draws], ["Avg time / game", s.avg_secs + " s"],
    ];
    $("#summary").innerHTML = stats.map(([l, v]) => `<div class="stat"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");
    const rows = Object.entries(s.decks).map(([name, d]) => ({ name, ...d }));
    $("#deck-table").innerHTML = table(rows, [
      ["Deck", r => r.name], ["Games", r => r.games], ["Wins", r => r.wins],
      ["Win rate", r => bar(r.win_rate)], ["Win rate going first", r => bar(r.first_win_rate)], ["Avg points", r => r.avg_points],
    ]);
    const cards = s.cards;
    const render = () => {
      const f = $("#card-filter").value.toLowerCase();
      const min = $("#min-games").checked ? 5 : 0;
      const rs = cards.filter(c => c.games >= min && (!f || c.card.toLowerCase().includes(f) || c.deck.toLowerCase().includes(f)));
      $("#card-table").innerHTML = table(rs.slice(0, 300), [
        ["Deck", r => r.deck], ["Card", r => r.card], ["Games played in", r => r.games], ["Times played", r => r.played],
        ["Win rate when played", r => bar(r.win_rate_when_played)],
      ]);
    };
    $("#card-filter").addEventListener("input", render);
    $("#min-games").addEventListener("change", render);
    render();
  }
  function bar(v) { const p = Math.round((v || 0) * 100); return `<div style="display:flex;gap:8px;align-items:center"><div class="bar"><i style="width:${p}%"></i></div><span>${p}%</span></div>`; }
  function table(rows, cols) {
    return `<table><thead><tr>${cols.map(c => `<th>${c[0]}</th>`).join("")}</tr></thead><tbody>` +
      rows.map(r => `<tr>${cols.map(c => `<td>${c[1](r)}</td>`).join("")}</tr>`).join("") + `</tbody></table>`;
  }

  // ------------------------------------------------------------ replays
  let rep = null, frame = 0, timer = null, CARDS = {};
  fetch(DATA + "cards.json").then(r => r.json()).then(j => { CARDS = j; }).catch(() => {});
  const imgOf = o => (CARDS[o.card] || {}).image || "";
  async function loadReplayList() {
    let idx;
    try {
      const rows = await sb("replays?select=id,seed,decks,winner,turns,frames,batch_id&order=batch_id.desc,seed.asc&limit=40");
      if (!rows.length) throw new Error("none");
      idx = { replays: rows.map(r => ({ name: "sb:" + r.id, seed: r.seed, decks: r.decks, frames: r.frames, result: { winner: r.winner, turns: r.turns, points: [] } })) };
    } catch (e) {
      try { idx = await (await fetch(DATA + "replays/index.json")).json(); }
      catch (e2) { $("#replay-list").innerHTML = `<div class="muted">No replays exported yet.</div>`; return; }
    }
    $("#replay-list").innerHTML = idx.replays.map((r, i) => `<div class="item" data-i="${i}" data-name="${r.name}">
        <div><span class="p0c">${r.decks[0]}</span> vs <span class="p1c">${r.decks[1]}</span></div>
        <div class="r">seed ${r.seed} · winner P${r.result.winner} · ${r.result.turns} turns · ${r.result.points.length ? r.result.points.join("–") + " · " : ""}${r.frames} decisions</div>
      </div>`).join("");
    $$("#replay-list .item").forEach(el => el.addEventListener("click", () => openReplay(el.dataset.name, el)));
  }
  async function openReplay(name, el) {
    $$("#replay-list .item").forEach(x => x.classList.toggle("active", x === el));
    rep = name.startsWith("sb:") ? (await sb(`replays?select=data&id=eq.${name.slice(3)}`))[0].data
                                 : await (await fetch(DATA + "replays/" + name + ".json")).json();
    frame = 0;
    $("#viewer-empty").hidden = true;
    $("#board").hidden = false;
    $("#frame-slider").max = Math.max(0, rep.frames.length - 1);
    render();
  }
  function card(o, cls) {
    const im = imgOf(o);
    const img = im ? `background-image:url('${im}')` : "";
    const ex = o.exhausted ? " exhausted" : "", st = o.stunned ? " stunned" : "";
    const m = o.might != null ? `<span class="m">${o.might}</span>` : "";
    const d = o.damage ? `<span class="d">-${o.damage}</span>` : "";
    const b = (o.buffs || o.empowered) ? `<span class="b">${o.buffs ? "+1" : ""}${o.empowered ? "E" : ""}</span>` : "";
    return `<div class="card p${o.controller}${ex}${st} ${cls || ""}" style="${img}" data-img="${im}" title="${o.name}">${m}${d}${b}<span class="n">${o.name}</span></div>`;
  }
  function render() {
    if (!rep) return;
    const f = rep.frames[frame];
    const st = f.state;
    const players = st.players;
    for (const p of players) {
      const strip = $(`#p${p.idx}-strip`);
      const runes = p.runes.map(r => `<span class="rune ${(r.name || "").split(" ")[0].toLowerCase()}${r.exhausted ? " ex" : ""}"></span>`).join("");
      const hand = p.hand.map(c => card(c, "small")).join("") || `<span class="muted">empty hand</span>`;
      const champ = p.champion ? card(p.champion, "small") : "";
      const legend = p.legend_obj ? card(p.legend_obj, "small") : "";
      strip.innerHTML = `<span class="name p${p.idx}c">P${p.idx} · ${p.deck}</span>
        <span class="pts">${p.points} pts</span>
        <span class="muted">deck ${p.deck_size} · trash ${p.trash.length} · XP ${p.xp}</span>
        <span class="runes">${runes}</span>
        <span class="muted">pool ${p.energy}⚡ ${p.power.join(",")}</span>
        <span class="muted">legend</span>${legend}<span class="muted">champion</span>${champ}
        <span class="muted">hand</span><span class="hand">${hand}</span>`;
      const base = $(`#base-${p.idx}`);
      base.innerHTML = `<h4>P${p.idx} base</h4>` + p.base.map(c => card(c)).join("");
    }
    $("#bfs").innerHTML = st.battlefields.map(b => {
      const u0 = b.units.filter(u => u.controller === 0), u1 = b.units.filter(u => u.controller === 1);
      const ctrl = b.controller == null ? "uncontrolled" : `controlled by P${b.controller}`;
      const con = b.contested_by != null ? ` · contested by P${b.contested_by}` : "";
      const fd = Object.keys(b.facedown).length ? ` · hidden: ${Object.keys(b.facedown).map(k => "P" + k).join(",")}` : "";
      return `<div class="bf ${b.controller != null ? "c" + b.controller : ""}">
        <h4><span data-img="${(CARDS[b.card] || {}).image || ""}">${b.name}</span> · ${ctrl}${con}${fd}</h4>
        <div class="row p1">${u1.map(c => card(c)).join("")}</div>
        <div class="row p0">${u0.map(c => card(c)).join("")}</div></div>`;
    }).join("");
    const chain = st.chain.map(it => `<span class="item">${it.label} (P${it.controller}${it.finalized ? "" : ", pending"})</span>`).join("");
    const phase = st.showdown ? (st.combat ? `combat at BF${st.combat.bf}` : `showdown at BF${st.showdown.bf}`) : st.phase;
    $("#chain").innerHTML = `turn ${st.turn} · P${st.turn_player}'s turn · ${phase} · chain: ${chain || "empty"}`;
    const d = f.decision;
    $("#decision").innerHTML = `<b class="p${d.player}c">P${d.player}</b> ${d.kind}: <b>${d.label}</b>
      <div class="opts">${d.n_options} options: ${d.options.slice(0, 12).join(" · ")}${d.n_options > 12 ? " …" : ""}</div>`;
    $("#frame-label").textContent = `${frame + 1} / ${rep.frames.length}`;
    $("#frame-slider").value = frame;
    // events between this decision and the next
    const next = rep.frames[frame + 1] ? rep.frames[frame + 1].event_index : rep.events.length;
    const evs = rep.events.slice(f.event_index, next).filter(e => !e.kind.startsWith("event:") && e.kind !== "pay");
    $("#events").innerHTML = evs.map(e => `<div class="ev ${e.kind === "decision" ? "hl" : ""}">${fmtEvent(e)}</div>`).join("");
    $$("[data-img]").forEach(el => {
      el.addEventListener("mouseenter", ev => { const img = el.dataset.img; if (!img) return; const t = $("#tooltip"); t.innerHTML = `<img src="${img}">`; t.hidden = false; move(ev); });
      el.addEventListener("mousemove", move);
      el.addEventListener("mouseleave", () => { $("#tooltip").hidden = true; });
    });
  }
  function move(ev) { const t = $("#tooltip"); t.style.left = Math.min(window.innerWidth - 240, ev.clientX + 16) + "px"; t.style.top = Math.min(window.innerHeight - 330, ev.clientY + 16) + "px"; }
  function fmtEvent(e) {
    const d = Object.entries(e).filter(([k]) => !["kind", "turn"].includes(k)).map(([k, v]) => `${k}=${fmtVal(v)}`).join(" ");
    return `${e.kind}: ${d}`;
  }
  function fmtVal(v) { if (v && v.__t) return "(" + v.__t.map(fmtVal).join(",") + ")"; if (Array.isArray(v)) return "[" + v.map(fmtVal).join(",") + "]"; if (typeof v === "object" && v) return JSON.stringify(v); return String(v); }
  function go(n) { if (!rep) return; frame = Math.max(0, Math.min(rep.frames.length - 1, n)); render(); }
  $("#btn-first").onclick = () => go(0);
  $("#btn-prev").onclick = () => go(frame - 1);
  $("#btn-next").onclick = () => go(frame + 1);
  $("#btn-last").onclick = () => go(1e9);
  $("#frame-slider").oninput = e => go(+e.target.value);
  $("#btn-play").onclick = () => {
    if (timer) { clearInterval(timer); timer = null; $("#btn-play").textContent = "▶ play"; return; }
    $("#btn-play").textContent = "⏸ pause";
    timer = setInterval(() => { if (!rep || frame >= rep.frames.length - 1) { clearInterval(timer); timer = null; $("#btn-play").textContent = "▶ play"; return; } go(frame + 1); }, 900);
  };
  document.addEventListener("keydown", e => { if (e.key === "ArrowRight") go(frame + 1); if (e.key === "ArrowLeft") go(frame - 1); });

  loadDashboard();
  loadReplayList();
})();
