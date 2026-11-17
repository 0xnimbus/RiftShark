"""Rules audit: play games and check, at every decision, that the offered options are the full set the Core Rules
allow (and nothing more), plus board invariants between decisions.

usage: python tools/rules_audit.py [games] [seed] [policy]     policy: random (default) | greedy | expert

Checks are written from the Core Rules (docs/rules/core_rules_2026-10-09.txt), independently of flow.legal_actions
where practical. Every problem is printed with the game seed, turn and a description; the exit code is the number of
distinct problem kinds found."""
import collections
import itertools
import os
import random
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from riftsim.core import CardDB, Deck, Game          # noqa: E402
from riftsim.core.scripts import script_all          # noqa: E402
from riftsim.core import payment                     # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Audit:
    def __init__(self):
        self.problems = collections.Counter()
        self.examples = {}
        self.notes = collections.Counter()
        self.samples = {}

    def bad(self, kind, msg):
        self.problems[kind] += 1
        self.examples.setdefault(kind, msg)
        self.samples.setdefault(kind, set())
        if len(self.samples[kind]) < 12:
            self.samples[kind].add(msg.split(": ", 1)[1])

    def note(self, kind, msg):
        self.notes[kind] += 1


def card_timing(g, p, u, zone):
    """CR 349/355 + keywords: may player p play this card now (timing only)?"""
    o = g.objects[u]
    d = o.base_defn()
    kw = d.keywords
    reaction = bool(kw.get("reaction")) or bool(kw.get("quick_draw"))
    if zone == "facedown":
        reaction = o.facedown_turn is not None and g.turn > o.facedown_turn
    action = bool(kw.get("action"))
    if g.closed:
        return "reaction" if p == g.priority else None, reaction
    if g.showdown is not None or g.combat is not None:
        return ("showdown" if p == g.focus else None), (reaction or action)
    return ("main" if p == g.turn_player and g.phase == "main" else None), True


def expected_moves(g, p):
    """CR 144: any non-empty group of ready units p controls, same destination, origins may differ (144.3.b).
    Destinations: base -> battlefield, battlefield -> base, battlefield -> battlefield only with Ganking (144.4).
    Stunned units may move (424.1.b). A battlefield with units of two other players is not a destination (144.4.a.1)."""
    out = {}
    ready = [u for u, o in g.objects.items() if o.zone == "board" and o.controller == p and not o.exhausted
             and o.location is not None and "unit" in g.chars(u).types]
    dests = [("bf", b.idx) for b in g.battlefields] + [("base", p)]
    for dest in dests:
        ok = []
        for u in ready:
            o = g.objects[u]
            if o.location == dest or g.cant_move(u) or p in (g.keyword_value(u, "cant_move_by") or ()):
                continue          # Vex, Apathetic: "They can't move it this turn"
            if dest[0] == "base":
                good = o.location[0] == "bf"
            else:
                others = {g.objects[x].controller for x in g.units_at(dest)} - {p}
                good = len(others) < 2 and (o.location[0] == "base" or g.has_keyword(u, "ganking")
                                            or any(g.objects[s].place == dest for s, _ in g.rules("move_here_from_anywhere")))
                if any(g.objects[s].location == dest and v is True for s, v in g.rules("cant_move_here")):
                    good = False
            if dest[0] == "base" and (any(v == "all" or g.objects[s].place == o.location for s, v in g.rules("cant_move_to_base"))
                                      or any(s == u for s, _ in g.rules("i_cant_move_to_base"))):
                good = False
            if good:
                ok.append(u)
        if ok:
            out[dest] = ok
    return out


def check_action(g, d, a, seed):
    p = d.player
    opts = d.options
    kinds = collections.Counter(o[0] for o in opts)
    where = f"seed {seed} turn {g.turn} P{p} phase {g.phase}"
    main_open = (not g.closed) and g.showdown is None and g.combat is None and g.phase == "main" and p == g.turn_player
    # pass / end turn
    if main_open:
        if kinds["end_turn"] != 1 or kinds["pass"]:
            a.bad("end_turn/pass", f"{where}: neutral open main phase must offer exactly 'end turn' (got {dict(kinds)})")
    else:
        if kinds["pass"] != 1 or kinds["end_turn"]:
            a.bad("end_turn/pass", f"{where}: closed state or showdown must offer exactly 'pass' (got {dict(kinds)})")
    # moves
    exp = expected_moves(g, p) if main_open else {}
    got = collections.defaultdict(set)
    select = set()
    for o in opts:
        if o[0] == "move":
            got[o[2]].add(frozenset(o[1]))
        elif o[0] == "move_select":
            select.add(o[1])
    if not main_open and (got or select):
        a.bad("move timing", f"{where}: moves offered outside the neutral open main phase (CR 144.1)")
    for dest, units in exp.items():
        if dest in select:
            continue
        want = {frozenset(c) for k in range(1, len(units) + 1) for c in itertools.combinations(units, k)}
        miss = want - got.get(dest, set())
        if miss:
            m = next(iter(miss))
            a.bad("move missing", f"{where}: move of {[g.label(u) for u in m]} to {dest} not offered (CR 144)")
    for dest, combos in got.items():
        units = set(exp.get(dest, ()))
        for c in combos:
            if not c <= units:
                a.bad("move illegal", f"{where}: illegal move offered: {[g.label(u) for u in c]} to {dest}")
    # plays: every card the player could play now (timing, a location, a payable cost) must be offered
    played = collections.defaultdict(set)
    for o in opts:
        if o[0] == "play":
            played[o[1]].add(o[2] if len(o) > 2 else None)
    ps = g.players[p]
    for u in list(ps.hand):
        state, ok = card_timing(g, p, u, "hand")
        if state is None or not ok:
            if u in played and not g.objects[u].base_defn().keywords.get("ambush") and not any(
                    getattr(ab, "perm", None) in ("reaction", "action") for ab in g._abilities_of(u, g.objects[u])) \
                    and not g.rules("hand_equipment_quick_draw", player=p) and not g.rules("deploy_gear_action", player=p):
                a.bad("play timing", f"{where}: {g.label(u)} offered with the wrong timing ({state or 'not this player'})")
            continue
    for u, locs in played.items():
        o = g.objects[u]
        d0 = o.base_defn()
        if "unit" in d0.types and o.zone == "hand":
            for loc in locs:
                if loc is None:
                    a.bad("play location", f"{where}: unit {g.label(u)} offered without a location")
                elif loc[0] == "base" and loc != ("base", p):
                    a.bad("play location", f"{where}: {g.label(u)} offered to another player's base")
    check_missing(g, d, a, where, main_open, played)


def has_priority(g, p):
    """CR 312-313: who may take Discretionary Actions now."""
    if g.closed:
        return p == g.priority
    if g.showdown is not None or g.combat is not None:
        return p == g.focus
    return p == g.turn_player and g.phase == "main"


def check_missing(g, d, a, where, main_open, played):
    """Options the rules give the player that must be on the list (and a few that must not)."""
    p = d.player
    opts = d.options
    # the decision goes to the player with Priority (CR 312.2), Focus in a showdown (313.2)
    if not has_priority(g, p):
        a.bad("decision holder", f"{where}: action decision given to P{p} who has no priority/focus")
        return
    # CR 164.2 + 312: every rune's '[Reaction] [E]: Add' / '[Reaction] Recycle this: Add' at every window with
    # priority, i.e. the player may always float, or leave runes untapped and pass
    rune_keys = {(g.objects[o[2]].domain, g.objects[o[2]].exhausted, o[1]) for o in opts if o[0] == "rune"}
    for u in g.players[p].runes:
        ro = g.objects[u]
        need = [("recycle")] + ([] if ro.exhausted else ["exhaust"])
        for k in need:
            if (ro.domain, ro.exhausted, k) not in rune_keys:
                a.bad("rune action missing", f"{where}: rune {g.label(u)} has no '{k}' action (CR 164.2)")
    # CR 811.1.b: hide while the card is in hand / champion zone, on your turn, in an Open State (with Focus in a
    # showdown), at a battlefield you control with no facedown card of yours, paying [A]
    open_own = (not g.closed) and p == g.turn_player and g.phase == "main"
    hides = {(o[1], o[2]) for o in opts if o[0] == "hide"}
    for u, b in hides:
        if not open_own:
            a.bad("hide timing", f"{where}: hide offered outside your turn's open state (CR 811.1.b)")
        if g.battlefields[b].controller != p:
            a.bad("hide location", f"{where}: hide offered at a battlefield P{p} doesn't control")
    if open_own:
        ps = g.players[p]
        cards = list(ps.hand) + ([ps.champion] if ps.champion is not None else [])
        bfs = [b.idx for b in g.battlefields if b.controller == p and g.can_hide_at(p, b.idx)]
        payable = g.can_pay(p, 0, ["any"], purpose={"kind": "hide"}) or (
            g.rules("hide_for_1_energy", player=p) and g.can_pay(p, 1, [], purpose={"kind": "hide"}))
        if bfs and payable:
            for u in cards:
                if g.objects[u].defn.keywords.get("hidden"):
                    for b in bfs:
                        if (u, b) not in hides:
                            a.bad("hide missing", f"{where}: hiding {g.label(u)} at battlefield {b} not offered (CR 811.1.b) [{g._state_name()}]")
    # plays: a card with legal timing, a legal location and a payable cost must be offered
    ps = g.players[p]
    srcs = [(u, "hand") for u in ps.hand] + ([(ps.champion, "champion")] if ps.champion is not None else [])
    for b in g.battlefields:
        srcs += [(u, "facedown") for u in g.facedown_cards(b.idx, p)]
    for u, z in srcs:
        o = g.objects[u]
        dd = o.base_defn()
        state, ok = card_timing(g, p, u, z)
        if z == "facedown" and not (o.facedown_turn is not None and g.turn > o.facedown_turn):
            continue                          # CR 811.1.b: playable from facedown beginning on the next turn
        if state is None or not ok or not g._play_restrictions_ok(p, u, z):
            continue
        locs = expected_locations(g, p, u, z)
        offered = played.get(u, set())
        for loc in locs:
            e, pw = g.card_cost(p, u, z, loc)
            if not g.can_pay(p, e, pw, purpose=payment.purpose_of_card(g, u)):
                continue
            direct = not g._variable_reduce_perm(u) and not g._exhaust_reducers(p)
            if loc is None and not g._spell_has_targets(p, u, z, cost=(e, list(pw), payment.purpose_of_card(g, u)) if direct else None):
                continue                      # CR 355.16: a Deflect tax must be payable on top of the cost
            if loc not in offered:
                a.bad("play missing", f"{where}: {g.label(u)} from {z} to {loc} not offered ({state})")
        for loc in offered:
            if "gear" in dd.types and "unit" not in dd.types and dd.keywords.get("deploy") and loc is not None and loc[0] == "base":
                a.bad("play location", f"{where}: Deploy gear {g.label(u)} offered to base (CR 830.1.b: only to a battlefield)")
    # activated abilities: timing per CR 376 / 806 / 813 (Equip has no timing keyword of its own, CR 818.1.c.2)
    for o in opts:
        if o[0] != "activate":
            continue
        ab = g.abilities(o[1])[o[2]]
        if getattr(ab, "is_equip", False) and ab.timing == "reaction" and not main_open:
            a.bad("equip timing", f"{where}: Equip of {g.label(o[1])} offered at reaction timing (CR 818.1.c.2, 819.1.d)")
        if ab.timing == "main" and not main_open:
            a.bad("activate timing", f"{where}: {g.label(o[1])} ability {o[2]} has no [Action]/[Reaction] but is offered outside the main phase")
        if ab.timing == "action" and g.closed:
            a.bad("activate timing", f"{where}: [Action] ability of {g.label(o[1])} offered in a closed state")


def expected_locations(g, p, u, z):
    """CR 355.2 / 811.1.d.1 / 830.1.b / 822: where this card may be played now."""
    o = g.objects[u]
    dd = o.base_defn()
    if "spell" in dd.types:
        return [None]
    if z == "facedown":
        blocked = {g.objects[s].place for s, _ in g.rules("cant_play_here")}
        return [] if ("unit" in dd.types and o.hidden_at in blocked) else [o.hidden_at]     # Rockfall Path
    if "unit" in dd.types:
        locs = [("base", p)] + [("bf", b.idx) for b in g.battlefields if b.controller == p]
        blocked = {g.objects[s].place for s, _ in g.rules("cant_play_here")}
        if any(g.objects[s].controller != p and (g.objects[s].location or ("",))[0] == "bf" for s, _ in g.rules("opp_units_base_only")):
            return [("base", p)]
        if any(getattr(ab, "perm", None) == "only_to" for ab in g._abilities_of(u, o)):
            return []                         # "play me only to ...": checked by the card's own tests
        return [l for l in locs if l[0] == "base" or l not in blocked]
    if dd.keywords.get("deploy"):
        return []                             # any battlefield: checked separately
    return [("base", p)]


def check_invariants(g, a, seed, last):
    where = f"seed {seed} turn {g.turn} phase {g.phase}"
    zone_lists = {}
    for p, ps in enumerate(g.players):
        for z in ("hand", "deck", "trash", "banish", "rune_deck", "runes"):
            for u in getattr(ps, z):
                if u in zone_lists:
                    a.bad("zones", f"{where}: object {u} listed in two zones")
                zone_lists[u] = (p, z)
        if len(ps.runes) + len(ps.rune_deck) > 12:
            a.bad("runes", f"{where}: P{p} has more than 12 runes in total")
    for u, (p, z) in zone_lists.items():
        o = g.objects[u]
        want = {"runes": "board"}.get(z, z)
        if o.zone != want:
            a.bad("zones", f"{where}: {g.label(u)} is listed in {z} but its zone is {o.zone}")
    # state-based checks only when nothing is pending (no chain, combat or showdown)
    if not g.chain and g.combat is None and g.showdown is None and g.phase == "main":
        waiting_replacement = g.pending is not None and g.pending.kind in ("optional_replacement", "order_replacement")
        for u, o in g.objects.items():
            # a unit waiting on an optional 'die' replacement (Sett, The Boss) stays on the board until it is answered
            if o.zone == "board" and "unit" in g.chars(u).types and g.lethal_damage(u) and not waiting_replacement:
                a.bad("lethal", f"{where}: {g.label(u)} has lethal damage on the board (CR 323 cleanup)")
        for b in g.battlefields:
            ctl = {g.objects[x].controller for x in g.units_at(("bf", b.idx))}
            if len(ctl) > 1 and not (getattr(b, "staged_combat", False) or getattr(b, "staged_showdown", False)):
                # a staged combat waits for the turn player to pick which contested battlefield goes first
                a.bad("contested", f"{where}: units of two players at battlefield {b.idx} outside combat/showdown")
            if len(ctl) == 1 and b.controller not in ctl and not getattr(b, "staged_showdown", False):
                a.bad("control", f"{where}: battlefield {b.idx} held only by P{next(iter(ctl))} but controlled by {b.controller}")
    for p, ps in enumerate(g.players):
        if ps.points >= g.victory_score() and not g.over:
            a.bad("victory", f"{where}: P{p} has {ps.points} points (victory {g.victory_score()}) but the game goes on")
        if last is not None and ps.points < last[p] and not any(e["kind"] == "points" and e.get("reason") == "lose" for e in g.events[-40:]):
            a.bad("points", f"{where}: P{p} lost points without a 'lose points' effect")


def check_turns(g, a, seed):
    """Channel 2 runes (3 in the second player's first Channel Phase, CR 487.7), draw 1, at most 2 mulligans."""
    by_turn = collections.defaultdict(list)
    for e in g.events:
        by_turn[e.get("turn")].append(e)
    seen = collections.Counter()
    for t in sorted(k for k in by_turn if k):
        evs = by_turn[t]
        tp = next((e["player"] for e in evs if e["kind"] == "turn"), None)
        if tp is None:
            continue
        seen[tp] += 1
        # the Channel Phase itself (battlefields and triggers may channel more at other times)
        cp = next((e for e in evs if e["kind"] == "channel_phase"), None)
        draws = sum(1 for e in evs if e["kind"] == "draw" and e.get("player") == tp)
        if cp is None:
            continue                 # the game ended before this turn's Channel Phase
        want = 3 if (tp != g.first_player and seen[tp] == 1) else 2
        chimera = cp["n"] == 1
        if cp["n"] != want and not chimera:
            a.bad("channel", f"seed {seed} turn {t}: Channel Phase channeled {cp['n']} runes, expected {want}")
        extra = sum(e.get("n", 0) for e in evs if e["kind"] == "channel_extra")
        short = any(e["kind"] == "channel_short" for e in evs)
        if cp["made"] > cp["n"] + extra or (cp["made"] < cp["n"] and not short):
            a.bad("channel", f"seed {seed} turn {t}: P{tp} channel phase made {cp['made']} runes for {cp['n']}+{extra}")
        if chimera:
            a.note("chimera", f"seed {seed} turn {t}: Sandstone Chimera limited channel to 1")
        if draws < 1 and not g.over:
            a.bad("draw", f"seed {seed} turn {t}: P{tp} did not draw in the Draw Phase")


def deck_paths():
    d = os.path.join(ROOT, "data/decks/tournament")
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json"))


def run(n, seed0, policy):
    db = script_all(CardDB.load(os.path.join(ROOT, "data/cards/riftbound.json")))
    paths = deck_paths()
    a = Audit()
    pol = None
    if policy != "random":
        from riftsim.core import policies
        pol = policies.make_policy(policy, seed0)          # was policies.make (missing): silently fell back to random
    for s in range(seed0, seed0 + n):
        rng = random.Random(s)
        pa, pb = rng.sample(paths, 2)
        decks = [Deck.load(pa, db), Deck.load(pb, db)]
        g = Game(db, decks, seed=s)
        steps = 0
        last = None
        try:
            while True:
                d = g.run()
                if d is None:
                    break
                steps += 1
                if steps > 30000:
                    a.bad("stuck", f"seed {s}: more than 30000 decisions")
                    break
                if d.kind == "action":
                    check_action(g, d, a, s)
                if d.kind == "mulligan":
                    if any(len(o) > 2 for o in d.options if isinstance(o, tuple)):
                        a.bad("mulligan", f"seed {s}: mulligan offers more than 2 cards (CR 117.1)")
                check_invariants(g, a, s, last)
                last = [ps.points for ps in g.players]
                if pol is not None:
                    ch = pol.choose(g, d)
                else:
                    opts = d.options
                    if d.kind == "action" and len(opts) > 1 and rng.random() < 0.6:
                        opts = [o for o in opts if o[0] not in ("pass", "end_turn")] or opts
                    ch = rng.choice(opts)
                g.choose(ch)
            check_turns(g, a, s)
        except Exception:
            a.bad("crash", f"seed {s}: {traceback.format_exc()[-1500:]}")
        print(f"seed {s}: {os.path.basename(pa)} vs {os.path.basename(pb)} winner P{g.winner} turns {g.turn} decisions {steps}",
              flush=True)
    print("\n== problems ==")
    for k, v in a.problems.most_common():
        print(f"{k}: {v}  e.g. {a.examples[k]}")
        if os.environ.get("AUDIT_VERBOSE"):
            for m in sorted(a.samples.get(k, ())):
                print("    ", m)
    return len(a.problems)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    s0 = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    policy = sys.argv[3] if len(sys.argv) > 3 else "random"
    sys.exit(min(run(n, s0, policy), 100))
