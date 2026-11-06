/* Shared board renderer for the replay viewer (index.html) and the play page (play.html).
   RiftBoard.render(container, state, opts) draws a playmat: opponent on top, you at the bottom, battlefields in the middle.
   RiftBoard.say(label) and RiftBoard.describe(event) turn engine labels and log entries into plain English. */
window.RiftBoard = (function () {
  const $ = (s, el) => (el || document).querySelector(s);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let CARDS = {};            // card id -> {name, image, type, energy, power, domains, text} (web/data/cards.json)
  const OBJ = {};            // uid -> last seen object (for names and images in the log)
  let BFN = [];              // battlefield index -> name
  let ME = 0;                // seat shown at the bottom ("you")
  let NEUTRAL = false;       // replays: say "P0"/"P1" instead of "you"/"opponent"
  const setCards = j => { CARDS = j || {}; };
  const defOf = o => CARDS[o && o.card] || {};
  const imgOf = o => (o && o.image) || defOf(o).image || "";
  const DOMAINS = ["fury", "calm", "mind", "body", "chaos", "order"];
  const PHASES = [["awaken", "Awaken"], ["beginning", "Beginning"], ["scoring", "Beginning"], ["channel", "Channel"], ["draw", "Draw"],
                  ["main", "Main"], ["ending", "End"], ["expiration", "End"]];
  const PHASE_STEPS = ["Awaken", "Beginning", "Channel", "Draw", "Main", "End"];

  // ------------------------------------------------------------------ words
  const who = p => p == null ? "nobody" : NEUTRAL ? "P" + p : (p === ME ? "You" : "Opponent");
  const third = v => v.replace(/^(\w+)/, m => /(s|sh|ch)$/.test(m) ? m + "es" : m + "s");
  const whoS = (p, verb) => p === ME && !NEUTRAL ? `You ${verb}` : `${p == null ? "Someone" : NEUTRAL ? "P" + p : "Opponent"} ${third(verb)}`;
  const yours = p => NEUTRAL ? `P${p}'s` : (p === ME ? "your" : "the opponent's");
  const seatName = p => NEUTRAL ? "P" + p : (p === ME ? "You" : "Opponent");
  const bfName = i => BFN[i] || `battlefield ${i + 1}`;
  function locName(loc) {
    if (!loc) return "";
    const t = loc.__t || loc;
    if (t[0] === "base") return yours(t[1]) + " base";
    if (t[0] === "bf") return bfName(t[1]);
    return String(t[0]);
  }
  const nameOf = uid => (OBJ[uid] && OBJ[uid].name && OBJ[uid].name !== "?") ? OBJ[uid].name : "a card";
  /* Rift text tokens like [T], [A], [M], [Reaction] as small chips. */
  function chips(s) {
    return esc(s).replace(/\[(T)\]/g, '<i class="tok" title="exhaust this">⟳</i>')
      .replace(/\[(A)\]/g, '<i class="tok any" title="power of any domain">◆</i>')
      .replace(/\[(M)\]/g, '<i class="tok" title="Might">⚔</i>')
      .replace(/\[(E|1|2|3|4|5|6|7|8|9)\]/g, '<i class="tok en" title="energy">$1</i>')
      .replace(/\[([A-Z][A-Za-z ]+)\]/g, '<i class="kw">$1</i>');
  }
  /* Engine option label -> short plain sentence (HTML). */
  function say(label) {
    let s = String(label || "");
    s = s.replace(/base P(\d)/g, (_, p) => yours(+p) + " base")
      .replace(/\bBF(\d) /g, "").replace(/\bP(\d)\b/g, (_, p) => NEUTRAL ? "P" + p : (+p === ME ? "you" : "the opponent"));
    let m;
    if (s === "end turn") return "End your turn";
    if (s === "pass") return "Pass";
    if ((m = s.match(/^play (.+?)#\d+(?: to (.+))?$/))) return `Play <b>${esc(m[1])}</b>${m[2] ? " to " + esc(m[2]) : ""}`;
    if ((m = s.match(/^move (.+) to (.+)$/))) return `Move <b>${esc(m[1].replace(/#\d+/g, ""))}</b> to ${esc(m[2])}`;
    if ((m = s.match(/^hide (.+?)#\d+ at (.+)$/))) return `Hide <b>${esc(m[1])}</b> face down at ${esc(m[2])}`;
    if ((m = s.match(/^activate (.+?)#\d+: (.*)$/))) return `Use <b>${esc(m[1])}</b>: ${chips(m[2])}`;
    if ((m = s.match(/^exhaust an? (\w+) rune: add 1 energy$/))) return `Exhaust a ${esc(m[1])} rune for 1 energy`;
    if ((m = s.match(/^recycle an? (\w+) rune: add (\w+) power$/))) return `Recycle a ${esc(m[1])} rune for 1 ${esc(m[2])} power`;
    if ((m = s.match(/^pay: (.*?);? ?spend (.*)$/))) return `${m[1] ? esc(m[1].replace(/;\s*/g, ", ").replace(/^\w/, c => c.toUpperCase())) : "Use your pool"} <span class="muted">(${esc(m[2])})</span>`;
    if ((m = s.match(/^yes: (.*)$/))) return `Yes, ${chips(m[1])}`;
    if ((m = s.match(/^recycle: (.*)$/))) return `Recycle ${esc(m[1].replace(/#\d+/g, ""))}`;
    return chips(s.replace(/#\d+/g, ""));
  }
  const uidsIn = label => Array.from(String(label || "").matchAll(/#(\d+)/g)).map(m => +m[1]);

  /* What a decision is asking, in plain words. d = {kind, player, prompt, showdown, chain, source}. */
  function explain(d, st) {
    const r = explainBase(d, st);
    if (d.kind !== "action" && d.source && d.source.text)     // quote the card so it is clear why this is asked
      r[1] += `<div class="src-text"><b>${esc(d.source.name)}</b>: ${chips(String(d.source.text).replace(/\n/g, " / "))}</div>`;
    return r;
  }
  function explainBase(d, st) {
    const src = d.source ? `<b>${esc(d.source.name)}</b>` : "An effect";
    const pr = d.prompt ? chips(d.prompt.replace(/#\d+/g, "")) : "";
    const sd = st && st.showdown ? bfName(st.showdown.bf) : "";
    switch (d.kind) {
      case "action":
        if (d.chain) return ["Respond?", "Something is on the chain. You may answer with a Reaction, or pass to let it resolve (the newest item resolves first)." +
          (st && (st.phase === "beginning" || st.phase === "scoring") ? " This is a start-of-turn trigger: it resolves before Channel and Draw, so this turn's runes and card haven't arrived yet." : "")];
        if (d.showdown) return [`Showdown at ${esc(sd)}`, "You have focus. Play an Action or Reaction, or pass. When both players pass in a row, the showdown ends (and combat happens if both sides have units)."];
        return ["Your turn", "Play cards, move ready units to a battlefield to contest it, use abilities, or end your turn. Glowing cards in your hand can be played right now."];
      case "choose": return ["Choose a target", `${src} needs a target${pr ? ": " + pr : "."}`];
      case "choose_many": return ["Choose targets", `${src} lets you pick several${pr ? ": " + pr : "."}`];
      case "pick": case "pick_many": return ["Pick", `${src}: ${pr || "pick from the options."}`];
      case "choose_location": return ["Choose a place", `${src}: ${pr || "choose a location."}`];
      case "choose_showdown": return ["Which showdown first?", "You moved into more than one battlefield. Pick where the first showdown happens."];
      case "choose_player": return ["Choose a player", `${src}: ${pr || "choose a player."}`];
      case "mode": return ["Choose a mode", `${src} has several modes. Pick one.`];
      case "yesno": return ["Optional effect", `${src} offers an optional effect. Do you want it?`];
      case "additional_cost": return ["Additional cost", `Pay the optional additional cost${d.prompt ? " (" + esc(d.prompt) + ")" : ""}? Paying it turns on the extra text of the card.`];
      case "assign_damage": return ["Assign combat damage", "Your side's total Might is dealt as damage to the enemy units (CR 467.2.c): Tanks first, Backline last, and each unit must get lethal damage before the next gets any; extra can only be spread once all have lethal. Each option shows where the damage goes and who dies."];
      case "pay_amount": return ["How much?", `${src}: choose how much to pay.`];
      case "discard": return ["Discard", `${src}: choose what to discard.`];
      case "recycle": return ["Recycle", `${src}: choose what to put on the bottom of its deck.`];
      case "predict": return ["Predict", `${src}: look at the top of your deck and choose what to recycle (send to the bottom).`];
      case "show_off": return ["Show Off?", `${src} has <i class="kw">Show Off</i>: you may reveal or pick a card to turn on its extra effect, or don't show off.`];
      case "pay": return ["Pay with runes", "Choose which runes pay. Exhausting a rune adds 1 energy; recycling a rune adds 1 power of its domain."];
      case "order_triggers": return ["Order your triggers", "Several of your abilities triggered at the same time (CR 383). Pick " +
        (/next/i.test(d.prompt || "") ? "which of the rest resolves next." : "which one resolves first; you'll then order the rest one at a time.")];
      case "mulligan": return ["Mulligan", "Your opening hand. Click up to two cards to set aside, then confirm: you draw that many new cards and the set-aside cards go to the bottom of your deck (CR 117). Or keep your hand."];
      default: return [esc(d.kind), pr || ""];
    }
  }

  /* Engine log entry -> one plain sentence (HTML), or null to skip it. */
  function describe(e) {
    const p = e.player;
    const n = e.uid != null ? (e.name || nameOf(e.uid)) : (e.name || "");
    switch (e.kind) {
      case "turn": return null;
      case "draw": return e.uid != null && (p === ME || NEUTRAL) ? `${whoS(p, "draw")} <b>${esc(nameOf(e.uid))}</b>.` : `${whoS(p, "draw")} a card.`;
      case "play": return `${whoS(p, "play")} <b>${esc(n)}</b>${e.loc ? " to " + locName(e.loc) : ""}.`;
      case "show_off": return ["Show Off?", `${src} has <i class="kw">Show Off</i>: you may reveal or pick a card to turn on its extra effect, or don't show off.`];
      case "pay": return (e.energy || (e.power && e.power.length)) ? `${whoS(p, "pay")} ${e.energy || 0} energy${e.power && e.power.length ? " and " + e.power.length + " power" : ""}.` : null;
      case "mulligan": return e.count ? `${whoS(p, "mulligan")} ${e.count} card${e.count === 1 ? "" : "s"}.` : `${whoS(p, "keep")} their opening hand.`.replace("You keep their", "You keep your");
      case "trigger_order": return `${whoS(p, "order")} simultaneous triggers.`;
      case "channel_phase": return `${whoS(p, "channel")} ${e.made != null ? e.made : e.n} rune${(e.made != null ? e.made : e.n) === 1 ? "" : "s"}.`;
      case "token": return `${whoS(p, "create")} a <b>${esc(e.name || "token")}</b> token${e.loc ? " at " + locName(e.loc) : ""}.`;
      case "rune": return e.how === "recycle" ? `${whoS(p, "recycle")} a ${esc(nameOf(e.uid))} for power.` : `${whoS(p, "exhaust")} a ${esc(nameOf(e.uid))} for energy.`;
      case "trigger": return `<b>${chips(e.label)}</b> triggers.`;
      case "resolve": return `<b>${chips(e.label)}</b> resolves.`;
      case "enter": return e.ready === false && OBJ[e.uid] && OBJ[e.uid].might != null ? `<b>${esc(n)}</b> enters exhausted (it can't move this turn).` : null;
      case "move": return `<b>${esc(n)}</b> moves to ${locName(e.to)}.`;
      case "damage": return `<b>${esc(nameOf(e.uid))}</b> takes ${e.amount} damage${e.source != null ? " from " + esc(nameOf(e.source)) : ""}.`;
      case "die": return `<b>${esc(n)}</b> dies.`;
      case "contest": return `${whoS(p, "contest")} ${esc(bfName(e.bf))}.`;
      case "showdown": return `Showdown at ${esc(bfName(e.bf))}.`;
      case "control": return `${whoS(p, "take")} control of ${esc(bfName(e.bf))}.`;
      case "lose_control": return `${whoS(p, "lose")} control of ${esc(bfName(e.bf))}.`;
      case "points": return `<span class="pts-ev">${whoS(p, "score")} ${e.points} point${e.points === 1 ? "" : "s"}</span> (${esc(e.reason || "")}).`;
      case "combat": return `Combat at ${esc(bfName(e.bf))}: ${whoS(e.attacker, "attack")}.`;
      case "combat_damage": return "Combat damage: " + (e.assignments || []).map(a => {
        const t = a.__t || a, m = String(t[0]).match(/#(\d+)/), o = m ? OBJ[m[1]] : null;
        const dead = o && o.might != null && t[1] >= o.might - (o.damage || 0);
        return `<b class="${o ? (o.controller === ME ? "me" : "op") : ""}">${esc(String(t[0]).replace(/#\d+/, ""))}</b> takes ${t[1]}${dead ? " ☠" : ""}`;
      }).join(", ") + ".";
      case "combat_result": return e.winner == null ? "Nobody wins the combat." : `${whoS(e.winner, "win")} the combat.`;
      case "activate": return `${whoS(p, "use")} <b>${esc(n)}</b>: ${chips(e.label || "")}`;
      case "hide": return `${whoS(p, "hide")} a card face down at ${esc(bfName(e.bf))}.`;
      case "attach": return `<b>${esc(nameOf(e.gear))}</b> is attached to <b>${esc(nameOf(e.unit))}</b>.`;
      case "counter": return `<b>${esc(e.label)}</b> is countered.`;
      case "burn_out": return `${whoS(p, "burn")} out (deck empty).`;
      case "game_over": return `<b>Game over: ${e.winner == null ? "draw" : whoS(e.winner, "win")}</b> (${esc(e.reason)}).`;
      case "replace": return `<b>${esc(e.label || "")}</b> replaces ${esc(e.event || "an event")}.`;
      case "decision": case "finalized": case "score": case "showdown_close": case "combat_end": return null;
      default:
        if (e.kind.startsWith("event:")) return null;
        return `<span class="muted">${esc(e.kind.replace(/_/g, " "))}</span>`;
    }
  }

  // ------------------------------------------------------------------ pieces
  const STATUS_HELP = {
    exhausted: "Exhausted: it can't make a standard move (moving costs exhausting it) or pay [T] costs. It readies in its controller's next Awaken phase. Units enter the board exhausted (CR 359.2.c).",
    stunned: "Stunned: it adds no Might to combat damage. Stun wears off in the end-of-turn cleanup (CR 424).",
  };
  function card(o, cls, extra) {
    if (!o) return "";
    if (o.hidden || o.card == null) return `<div class="card back ${cls || ""}" title="hidden card"></div>`;
    remember(o);
    const im = imgOf(o);
    const def = defOf(o);
    const unit = o.might != null && (def.type === "unit" || def.type === "token" || o.zone === "board" || o.zone === "champion");
    const flags = [];
    if (o.exhausted) flags.push(`<span class="flag ex">EXHAUSTED</span>`);
    if (o.stunned) flags.push(`<span class="flag st">STUNNED</span>`);
    const role = o.designation === "attacker" ? `<span class="role atk" title="attacking">⚔ ATK</span>` : o.designation === "defender" ? `<span class="role def" title="defending">🛡 DEF</span>` : "";
    const pend = o.pending_damage ? `<span class="pend" title="combat damage assigned to it">-${o.pending_damage}${o.pending_damage >= o.might - (o.damage || 0) ? " ☠" : ""}</span>` : "";
    const m = unit ? `<span class="m${o.damage ? " hurt" : ""}">${o.damage ? (o.might - o.damage) + "/" : ""}${o.might}</span>` : "";
    const b = (o.buffs || o.empowered) ? `<span class="b">${o.buffs ? "+" + o.buffs : ""}${o.empowered ? " E" : ""}</span>` : "";
    const cost = (cls || "").includes("inhand") && def.energy != null ? `<span class="cost">${def.energy}${def.power ? "+" + def.power : ""}</span>` : "";
    const cl = ["card", "p" + (o.controller === ME ? "me" : "op"), o.exhausted ? "exhausted" : "", o.stunned ? "stunned" : "", o.token ? "token" : "", cls || ""].join(" ");
    return `<div class="${cl}" data-uid="${o.uid}" ${extra || ""}>
      ${im ? `<img src="${esc(im)}" loading="lazy" alt="">` : `<div class="noimg">${esc(o.name)}</div>`}
      ${cost}${m}${b}${role}${pend}${flags.join("")}<span class="n">${esc(o.name)}</span></div>`;
  }
  function remember(o) { if (o && o.uid != null && o.name && o.name !== "?") OBJ[o.uid] = o; }
  function runeDomain(r) { const d = (r.name || "").split(" ")[0].toLowerCase(); return DOMAINS.includes(d) ? d : "any"; }
  function runes(p) {
    const ready = p.runes.filter(r => !r.exhausted).length;
    const list = p.runes.map(r => `<span class="rune ${runeDomain(r)}${r.exhausted ? " ex" : ""}" title="${esc(r.name)}${r.exhausted ? " (exhausted)" : " (ready)"}"></span>`).join("");
    const pool = (p.energy || p.power.length) ? `<span class="pool" title="unspent energy and power in your pool">pool ${p.energy}⚡${p.power.length ? " · " + p.power.map(x => `<span class="rune mini ${x}"></span>`).join("") : ""}</span>` : "";
    return `<div class="runes" title="Runes: exhaust one for 1 energy, recycle one for 1 power of its domain">
      <span class="lbl">Runes ${ready}/${p.runes.length} ready</span><div class="rlist">${list || '<span class="muted">none yet</span>'}</div>${pool}</div>`;
  }
  function scorePips(p, victory) {
    let s = "";
    for (let i = 1; i <= victory; i++) s += `<i class="${i <= p.points ? "on" : ""}"></i>`;
    return `<div class="score" title="${p.points} of ${victory} points to win"><b>${p.points}</b><span class="pips">${s}</span></div>`;
  }

  function seat(p, st, o, top) {
    const mine = p.idx === ME;
    const hand = p.hand.map(c => {
      if (!mine || !o.playable) return card(c, top ? "tiny" : "inhand");
      const opts = o.playable[c.uid] || [];
      const extra = opts.length ? `data-opts="${opts.join(",")}"` : `data-why="${esc(whyNot(c, p, st, o))}"`;
      return card(c, "inhand" + (opts.length ? " playable" : ""), extra);
    }).join("");
    const champ = p.champion ? (() => {
      const opts = mine && o.playable ? (o.playable[p.champion.uid] || []) : [];
      const extra = opts.length ? `data-opts="${opts.join(",")}"` : (mine && o.playable ? `data-why="${esc(whyNot(p.champion, p, st, o))}"` : "");
      return card(p.champion, "zone" + (opts.length ? " playable" : ""), extra);
    })() : `<div class="card empty zone">played</div>`;
    const thinking = !mine && o.thinking ? `<div class="think"><span></span><span></span><span></span> thinking</div>` : "";
    const handZone = `<div data-zone="hand${p.idx}" class="zone-box hand-box${!mine && o.thinking ? " thinking" : ""}"><div class="zl">${NEUTRAL ? seatName(p.idx) + "'s hand" : mine ? "Your hand" : "Opponent's hand"} · ${p.hand_size != null ? p.hand_size : p.hand.length}</div>
        <div class="hand">${hand || '<span class="muted">empty</span>'}</div>${thinking}</div>`;
    const info = `<div class="seat-info">
        <div class="who ${mine ? "me" : "op"}">${seatName(p.idx)}${st.turn_player === p.idx ? ' <span class="turnflag">turn</span>' : ""}${st.showdown && st.focus === p.idx ? ' <span class="focusflag" title="has Focus in the showdown">◉ focus</span>' : ""}</div>
        <div class="deckname" title="${esc(p.deck)}">${esc(p.legend)}</div>
        ${scorePips(p, o.victory || 8)}
        <div class="counts"><span title="cards left in main deck">Deck ${p.deck_size}</span><span title="trash (discard pile)">Trash ${p.trash.length}</span><span title="cards left in rune deck">Rune deck ${p.rune_deck}</span>${p.xp ? `<span>XP ${p.xp}</span>` : ""}</div>
      </div>`;
    const zones = `<div data-zone="legend${p.idx}" class="zone-box"><div class="zl">Legend</div>${card(p.legend_obj, "zone")}</div>
      <div data-zone="champ${p.idx}" class="zone-box"><div class="zl" title="Your Chosen Champion waits here until you play it">Champion</div>${champ}</div>`;
    const rn = `<div class="zone-box rune-box">${runes(p)}</div>`;
    return `<div class="seat ${mine ? "me" : "op"}">${info}${zones}${rn}${mine && o.playable ? "" : handZone}</div>` +
      (mine && o.playable ? `<div class="my-hand">${handZone}</div>` : "");
  }

  /* Why a card in hand / champion zone can't be played right now (best effort; the engine's option list is the authority). */
  function whyNot(c, p, st, o) {
    const def = defOf(c);
    if (o.decisionKind && o.decisionKind !== "action") return "Finish the current choice first.";
    if (o.decisionKind == null) return "Wait for your turn.";
    const ready = p.runes.filter(r => !r.exhausted).length + (p.energy || 0);
    const parts = [];
    if (def.energy != null && def.energy > ready) parts.push(`costs ${def.energy} energy, you can make ${ready} (ready runes + pool)`);
    if (def.power) {
      const doms = (def.domains || []).filter(x => DOMAINS.includes(x));
      const have = p.runes.filter(r => doms.includes(runeDomain(r))).length + p.power.filter(x => doms.includes(x) || x === "any").length;
      if (have < def.power) parts.push(`needs ${def.power} ${doms.join("/")} power, you have ${have} matching rune${have === 1 ? "" : "s"}`);
    }
    if (parts.length) return "Not playable yet: " + parts.join("; ") + ".";
    if (st.turn_player !== ME || st.showdown || (st.chain && st.chain.length))
      return "Not playable now: only cards with [Action] or [Reaction] can be played outside your own open main phase.";
    return "Not playable now (timing, power or no legal target).";
  }

  function battlefield(b, st, o) {
    const mine = b.units.filter(u => u.controller === ME), theirs = b.units.filter(u => u.controller !== ME);
    const ctrl = b.controller == null ? `<span class="ctl none">uncontrolled</span>` : `<span class="ctl ${b.controller === ME ? "me" : "op"}">held by ${seatName(b.controller).toLowerCase().replace(/^p/, "P")}</span>`;
    const con = b.contested_by != null ? `<span class="tag warn">contested by ${seatName(b.contested_by).toLowerCase().replace(/^p/, "P")}</span>` : "";
    const here = st.combat && st.combat.bf === b.idx ? `<span class="tag hot">combat</span>` : (st.showdown && st.showdown.bf === b.idx ? `<span class="tag hot">showdown</span>` : "");
    const known = b.facedown_known || {};
    const fd = Object.keys(b.facedown || {}).map(k => known[k]
      ? `<span class="fd-known" title="face down: only ${NEUTRAL ? "its owner" : "you"} can see it">${card(Object.assign({ controller: +k, zone: "facedown" }, known[k]), "tiny")}<span class="tag">${yours(+k)} hidden card</span></span>`
      : `<span class="tag" title="a face-down card is hidden here">${yours(+k)} hidden card</span>`).join("");
    const im = imgOf(b);
    const hot = here ? " hot" : "";
    return `<div data-zone="bf${b.idx}" class="bf ${b.controller == null ? "" : (b.controller === ME ? "c-me" : "c-op")}${hot}">
      ${im ? `<div class="bf-art" style="background-image:url('${esc(im)}')"></div>` : ""}
      <div class="bf-head"><span class="bf-name" data-uid="bf${b.idx}">${esc(b.name)}</span>${ctrl}${con}${here}${fd}</div>
      <div class="side op">${theirs.map(u => card(u, "unit")).join("")}</div>
      ${fightStrip(b, st)}
      <div class="side me">${mine.map(u => card(u, "unit")).join("")}</div>
    </div>`;
  }
  function base(p) {
    const mine = p.idx === ME;
    return `<div data-zone="base${p.idx}" class="base ${mine ? "me" : "op"}"><div class="zl">${NEUTRAL ? seatName(p.idx) + "'s base" : mine ? "Your base" : "Opponent's base"}</div>
      <div class="row">${p.base.map(c => card(c, "unit")).join("")}</div></div>`;
  }
  const T = v => (v && v.__t) ? v.__t : v;
  /* Showdown / combat strip between the two sides of the battlefield where it happens:
     who has Focus, how many passes in a row, Might totals and where the damage goes. */
  function fightStrip(b, st) {
    const sd = st.showdown, cb = st.combat;
    if (!(sd && sd.bf === b.idx) && !(cb && cb.bf === b.idx)) return "";
    const nm = p => NEUTRAL ? "P" + p : p === ME ? "You" : "Opponent";
    const parts = [];
    if (sd && sd.bf === b.idx) {
      const f = st.focus;
      const passes = sd.passes || 0;
      parts.push(`<div class="focus ${f === ME ? "me" : "op"}"><span class="orb"></span><b>Focus: ${f == null ? "nobody" : nm(f)}</b>
        <span class="muted">${passes ? `${passes} pass${passes === 1 ? "" : "es"} in a row (2 in a row ends the showdown${sd.combat ? " and combat damage follows" : ""})` :
          `${f === ME && !NEUTRAL ? "you may" : "they may"} play an Action or Reaction, or pass Focus`}</span></div>`);
    }
    if (cb && cb.bf === b.idx) {
      const tot = T(cb.totals);
      const att = b.units.filter(u => u.designation === "attacker"), dfn = b.units.filter(u => u.designation === "defender");
      const sum = us => us.filter(u => !u.stunned).reduce((a, u) => a + (u.might || 0), 0);
      const aT = tot ? tot[0] : sum(att), dT = tot ? tot[1] : sum(dfn);
      const step = cb.step === "damage" ? "assigning damage" : "showdown before damage";
      parts.push(`<div class="clash"><span class="side-a ${cb.attacker === ME ? "me" : "op"}">⚔ ${nm(cb.attacker)} attack: <b>${aT}</b> Might</span>
        <span class="vs">vs</span><span class="side-d ${cb.defender === ME ? "me" : "op"}">🛡 ${nm(cb.defender)} defend: <b>${dT}</b> Might</span>
        <span class="muted">· ${step}</span></div>`);
    }
    return `<div class="fight">${parts.join("")}</div>`;
  }
  /* Annotate units with the damage already assigned to them this combat (combat.assign + assign_targets_P). */
  function markPending(st) {
    const cb = st.combat;
    if (!cb || !cb.assign) return;
    const per = {};
    for (const [p, plan] of Object.entries(cb.assign)) {
      const tg = T(cb["assign_targets_" + p]) || [];
      (T(plan) || []).forEach((a, i) => { if (a && tg[i] != null) per[tg[i]] = (per[tg[i]] || 0) + a; });
    }
    st.battlefields.forEach(b => b.units.forEach(u => { u.pending_damage = per[u.uid] || 0; }));
  }
  /* A damage-assignment option as bars: each target, its health left, the damage it gets, and whether that kills it. */
  function damagePlan(label) {
    const items = String(label).split(/,\s*/).map(x => x.match(/^(.*?)#(\d+):(\d+)$/)).filter(Boolean);
    if (!items.length) return null;
    return `<div class="dmg-plan">${items.map(m => {
      const o = OBJ[m[2]] || {}, amt = +m[3];
      const hp = Math.max(1, (o.might || amt) - (o.damage || 0));
      const pct = Math.min(100, Math.round(100 * amt / hp));
      const dead = amt >= hp;
      return `<div class="dp" data-uid="${m[2]}"><span class="dp-n">${esc(m[1])}</span><span class="dp-bar"><i style="width:${pct}%"></i></span>
        <span class="dp-a">${amt}/${hp}${dead ? ' <b class="kill">☠ dies</b>' : ""}</span></div>`;
    }).join("")}</div>`;
  }
  function turnBar(st, o) {
    const cur = (PHASES.find(x => x[0] === st.phase) || [null, ""])[1];
    const steps = PHASE_STEPS.map(s => `<span class="ph${s === cur ? " on" : ""}">${s}</span>`).join("");
    const special = st.phase === "mulligan" ? `<span class="tag hot">Mulligan</span>` : st.combat ? `<span class="tag hot">Combat at ${esc(bfName(st.combat.bf))}</span>` :
      st.showdown ? `<span class="tag hot">Showdown at ${esc(bfName(st.showdown.bf))}</span>` : "";
    const whose = NEUTRAL ? `P${st.turn_player}'s turn` : st.turn_player === ME ? "Your turn" : "Opponent's turn";
    return `<div class="turnbar"><span class="tn">Turn ${st.turn}</span><span class="whose ${st.turn_player === ME ? "me" : "op"}">${whose}</span>
      <span class="phases">${steps}</span>${special}</div>`;
  }
  const KIND = { spell: "Spell", unit: "Unit", gear: "Gear", trigger: "Triggered ability", reflexive: "Triggered ability",
                 activated: "Activated ability", ability: "Activated ability", add: "Add (resolves at once)" };
  const CAUSE = { play: "was played", enter: "entered", die: "died", move: "moved", attack: "attacked", defend: "defended",
                  conquer: "conquered", hold: "held", damage: "took damage", draw: "drew", score: "scored", showdown_start: "a showdown began",
                  combat_start: "combat began", beginning_phase: "the turn began", ending_phase: "the turn ended", stun: "was stunned" };
  /* The chain as a lane in the middle of the board: oldest on the left, the one that resolves next on the right. */
  function chainBox(st) {
    if (!st.chain || !st.chain.length) return "";
    const n = st.chain.length;
    const items = st.chain.map((it, i) => {
      const def = CARDS[it.card] || {};
      const top = i === n - 1;
      const owner = NEUTRAL ? "P" + it.controller : it.controller === ME ? "Yours" : "Opponent's";
      const tg = (it.targets || []).length ? `<div class="ci-tg">→ ${it.targets.map(t => `<b class="${t.controller === ME ? "me" : "op"}" data-uid="${t.uid}">${esc(t.name)}</b>`).join(", ")}</div>` : "";
      const cause = it.cause ? `<div class="ci-cause">because ${it.cause.name ? esc(it.cause.name) + " " : ""}${esc(CAUSE[it.cause.event] || it.cause.event.replace(/_/g, " "))}</div>` : "";
      const resp = i > 0 ? `<div class="ci-arrow" title="responds to the item on its left">⟵ responds</div>` : "";
      return `${resp}<div class="chain-item ${it.controller === ME ? "me" : "op"}${top ? " next" : ""}" ${it.card ? `data-card="${esc(it.card)}"` : ""}>
        <div class="ci-pos">${top ? "RESOLVES NEXT" : "#" + (i + 1)}</div>
        ${def.image ? `<img src="${esc(def.image)}" alt="">` : `<div class="ci-noimg">⛓</div>`}
        <div class="ci-body"><div class="ci-kind">${esc(KIND[it.kind] || it.kind || "")}${it.finalized ? "" : " · being played"}</div>
          <b>${chips(it.label)}</b><div class="ci-own">${owner}</div>${tg}${cause}</div></div>`;
    }).join("");
    let wait = "";
    const playing = st.chain.find(it => !it.finalized);
    if (playing) wait = `${NEUTRAL ? "P" + playing.controller + " is" : playing.controller === ME ? "You are" : "Opponent is"} still playing <b>${esc(playing.label)}</b> (choosing targets and paying)`;
    else if (st.priority != null) {
      const p = st.priority;
      wait = NEUTRAL ? `P${p} may respond or pass` : p === ME ? "<b>Your priority:</b> respond with a Reaction or pass" : "<b>Opponent</b> may respond or pass";
    }
    return `<div class="chain-lane"><div class="chain-head"><span class="ch-title">⛓ Chain · ${n} item${n === 1 ? "" : "s"}</span>
        <span class="ch-wait">${wait}</span>
        <span class="ch-rule" title="While anything is on the chain, only Reaction-speed cards and abilities can be played. When both players pass in a row, the item on the right resolves.">ⓘ</span></div>
      <div class="chain-row">${items}</div></div>`;
  }

  /* Track chain depth through the log: items go on (play / trigger) and come off (resolve / counter). */
  function chainStep(e, open) {
    let depth = open.size, note = "";
    if ((e.kind === "finalized" || e.kind === "trigger") && e.item != null && !open.has(e.item)) {
      if (open.size) note = ` <span class="resp">responding (chain ${open.size + 1})</span>`;
      open.add(e.item); depth = open.size;
    } else if ((e.kind === "resolve" || e.kind === "counter") && e.item != null) {
      depth = open.size; open.delete(e.item);
    }
    return { depth: Math.max(0, depth - 1), note };
  }

  /* opts: {me, thinking, playable: {uid: [option indexes]}, victory, decisionKind, banner} */
  function render(el, st, o) {
    o = o || {};
    ME = o.me != null ? o.me : 0;
    NEUTRAL = !!o.neutral;
    BFN = st.battlefields.map(b => b.name);
    markPending(st);
    st.players.forEach(p => { p.hand.forEach(remember); p.base.forEach(remember); p.runes.forEach(remember); p.trash.forEach(remember); remember(p.champion); remember(p.legend_obj); });
    st.battlefields.forEach(b => b.units.forEach(remember));
    const me = st.players.find(p => p.idx === ME), op = st.players.find(p => p.idx !== ME);
    const before = o.animate === false ? null : snapRects(el);
    el.innerHTML = `${turnBar(st, o)}
      <div class="mat">
        ${seat(op, st, o, true)}
        ${base(op)}
        <div class="bfs">${st.battlefields.map(b => battlefield(b, st, o)).join("")}</div>
        ${chainBox(st)}
        ${base(me)}
        ${seat(me, st, o, false)}
        ${o.banner ? `<div class="banner ${o.banner.me ? "me" : "op"}">${o.banner.html}</div>` : ""}
      </div>`;
    if (before) slide(el, before);
  }

  // ------------------------------------------------------------------ card movement (FLIP: first, last, invert, play)
  const REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function snapRects(el) {
    const r = { cards: {}, opHand: null, meHand: null };
    el.querySelectorAll(".mat .card[data-uid]").forEach(c => { r.cards[c.dataset.uid] = { rect: c.getBoundingClientRect(), zone: zoneOf(c) }; });
    const oh = el.querySelector(".seat.op .hand-box"), mh = el.querySelector(".seat.me .hand-box, .my-hand .hand-box");
    if (oh) r.opHand = oh.getBoundingClientRect();
    if (mh) r.meHand = mh.getBoundingClientRect();
    return Object.keys(r.cards).length || r.opHand ? r : null;
  }
  const zoneOf = c => { const z = c.closest("[data-zone]"); return z ? z.dataset.zone : ""; };
  function slide(el, before) {
    if (REDUCED || !el.animate && !Element.prototype.animate) return;
    el.querySelectorAll(".mat .card[data-uid]").forEach(c => {
      const now = c.getBoundingClientRect();
      const was = before.cards[c.dataset.uid];
      if (was && was.zone === zoneOf(c)) return;   // same zone: only the layout shifted, don't animate
      let from = was && was.rect;
      let fresh = false;
      if (!from) {
        // a card that just appeared: the opponent's came out of their hidden hand, a new one of yours from your hand area
        if (c.closest(".hand")) return;
        from = c.classList.contains("pop") ? before.opHand : before.meHand;
        fresh = true;
        if (!from) { c.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 300 }); return; }
      }
      const dx = (from.left + from.width / 2) - (now.left + now.width / 2), dy = (from.top + from.height / 2) - (now.top + now.height / 2);
      if (Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
      const base = getComputedStyle(c).transform;
      const end = base === "none" ? "none" : base;
      const start = `translate(${dx}px, ${dy}px) ${base === "none" ? "" : base}`;
      c.animate([{ transform: start, opacity: fresh ? 0.2 : 1, zIndex: 4 }, { transform: end, opacity: 1, zIndex: 4 }],
                { duration: 450, easing: "cubic-bezier(.2,.8,.2,1)" });
    });
  }

  // ------------------------------------------------------------------ tooltip (card preview)
  function tipHtml(el) {
    let o = null, def = {}, im = "";
    if (el.dataset.card) { def = CARDS[el.dataset.card] || {}; im = def.image; o = { name: def.name }; }
    else {
      const u = el.dataset.uid;
      if (u == null || u === "" || u === "undefined") return "";
      o = OBJ[u];
      if (!o) return "";
      def = defOf(o); im = imgOf(o);
    }
    const lines = [];
    if (def.type) lines.push(`<div class="tt-type">${esc(def.type)}${def.energy != null ? ` · cost ${def.energy}${def.power ? " + " + def.power + " power" : ""}` : ""}${(def.domains || []).length ? " · " + esc(def.domains.join(", ")) : ""}</div>`);
    if (def.text) lines.push(`<div class="tt-text">${chips(def.text).replace(/\n/g, "<br>")}</div>`);
    if (o.exhausted) lines.push(`<div class="tt-st ex">${chips(STATUS_HELP.exhausted)}</div>`);
    if (o.stunned) lines.push(`<div class="tt-st st">${STATUS_HELP.stunned}</div>`);
    if (o.damage) lines.push(`<div class="tt-st">${o.damage} damage marked (dies at ${o.might}).</div>`);
    if (el.dataset.why) lines.push(`<div class="tt-st why">${chips(el.dataset.why)}</div>`);
    if (el.dataset.opts) lines.push(`<div class="tt-st ok">Playable now: click to see the options.</div>`);
    return `${im ? `<img src="${esc(im)}" alt="">` : ""}<div class="tt-body"><b>${esc(o.name || def.name || "")}</b>${lines.join("")}</div>`;
  }
  function bindTooltips(root) {
    const t = $("#tooltip");
    if (!t || (root || document).__tipBound) return;
    (root || document).__tipBound = true;
    const move = ev => {
      const w = 300, h = t.offsetHeight || 420;
      let x = ev.clientX + 18, y = ev.clientY + 12;
      if (x + w > window.innerWidth) x = ev.clientX - w - 18;
      if (y + h > window.innerHeight) y = Math.max(8, window.innerHeight - h - 8);
      t.style.left = x + "px"; t.style.top = y + "px";
    };
    (root || document).addEventListener("mouseover", ev => {
      const el = ev.target.closest("[data-uid],[data-card]");
      if (!el) { t.hidden = true; return; }
      const h = tipHtml(el);
      if (!h) { t.hidden = true; return; }
      t.innerHTML = h; t.hidden = false; move(ev);
    });
    (root || document).addEventListener("mousemove", ev => { if (!t.hidden) move(ev); });
    (root || document).addEventListener("mouseleave", () => { t.hidden = true; });
  }

  /* Small card thumbnails for the objects an option refers to (by #uid in its label). */
  function thumbs(label) {
    return uidsIn(label).map(u => OBJ[u]).filter(Boolean).slice(0, 3).map(o => {
      const im = imgOf(o);
      return im ? `<img class="th" src="${esc(im)}" data-uid="${o.uid}" alt="">` : "";
    }).join("");
  }
  const getMe = () => ME;
  return { setCards, render, bindTooltips, say, explain, describe, chainStep, damagePlan, thumbs, uidsIn, chips, esc, getMe };
})();
