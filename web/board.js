/* Shared board renderer for the replay viewer and the play page. Needs the DOM ids of index.html / play.html. */
window.RiftBoard = (function () {
  const $ = (s, el) => (el || document).querySelector(s);
  let CARDS = {};
  const setCards = j => { CARDS = j; };
  const imgOf = o => (CARDS[o.card] || {}).image || "";
  function card(o, cls) {
    const im = imgOf(o);
    const img = im ? `background-image:url('${im}')` : "";
    const ex = o.exhausted ? " exhausted" : "", st = o.stunned ? " stunned" : "";
    const m = o.might != null ? `<span class="m">${o.might}</span>` : "";
    const d = o.damage ? `<span class="d">-${o.damage}</span>` : "";
    const b = (o.buffs || o.empowered) ? `<span class="b">${o.buffs ? "+1" : ""}${o.empowered ? "E" : ""}</span>` : "";
    return `<div class="card p${o.controller}${ex}${st} ${cls || ""}" style="${img}" data-img="${im}" data-uid="${o.uid != null ? o.uid : ""}" title="${o.name}">${m}${d}${b}<span class="n">${o.name}</span></div>`;
  }
  function renderState(st) {
    for (const p of st.players) {
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
  }
  function move(ev) { const t = $("#tooltip"); t.style.left = Math.min(window.innerWidth - 240, ev.clientX + 16) + "px"; t.style.top = Math.min(window.innerHeight - 330, ev.clientY + 16) + "px"; }
  function bindTooltips() {
    document.querySelectorAll("[data-img]").forEach(el => {
      el.addEventListener("mouseenter", ev => { const img = el.dataset.img; if (!img) return; const t = $("#tooltip"); t.innerHTML = `<img src="${img}">`; t.hidden = false; move(ev); });
      el.addEventListener("mousemove", move);
      el.addEventListener("mouseleave", () => { $("#tooltip").hidden = true; });
    });
  }
  function fmtVal(v) { if (v && v.__t) return "(" + v.__t.map(fmtVal).join(",") + ")"; if (Array.isArray(v)) return "[" + v.map(fmtVal).join(",") + "]"; if (typeof v === "object" && v) return JSON.stringify(v); return String(v); }
  function fmtEvent(e) {
    const d = Object.entries(e).filter(([k]) => !["kind", "turn"].includes(k)).map(([k, v]) => `${k}=${fmtVal(v)}`).join(" ");
    return `${e.kind}: ${d}`;
  }
  return { setCards, card, renderState, bindTooltips, fmtEvent, fmtVal };
})();
