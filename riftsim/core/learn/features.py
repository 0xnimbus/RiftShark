"""Position features for the learned value network.

encode(g, p) describes the game from player p's seat using only what p may know: public zones, counts of hidden
zones, and p's own hand. The opponent's hand contents and both deck orders are never read (Derrick's hidden-info rule),
so the same function is safe inside search and on the real game. Pure Python: it also runs in the browser build.
"""
from __future__ import annotations

import math
import zlib

LEGEND_BUCKETS = 16
MAX_BF = 3
# card identity (feature version 2, appended so version-1 models still read their own prefix): hashed counts of the
# cards in p's own hand, on p's board and on the opponent's board (public, face-up cards only), so the value model can
# learn what each card is worth in each place
CARD_BUCKETS = 64
# held interaction (feature version 3, appended again): reaction-speed cards in p's own hand and whether p's ready runes
# can pay for them, so the value model can learn what open energy with a counter or trick in hand is worth on the
# opponent's turn (self-play labels those positions by playing the opponent's turn while p may respond)
FEATURE_VERSION = 5
# turn structure: the same board is worth different amounts before and after the turn player's Awaken/Channel/Draw,
# so the net must know where in the turn it is (without this, gen 1 rated "end my turn" above every attack because
# the next own decision came in the opponent's Beginning phase with their runes and units still exhausted)
PHASES = ("beginning", "main", "ending", "other")
H_INDEX = 11 + len(PHASES)     # position of tanh(heuristic / 150) in the vector (the net's residual base)


def _bucket(name):
    return zlib.crc32(name.encode()) % LEGEND_BUCKETS


def _side(g, p, out):
    ps = g.players[p]
    units_base = units_bf = might_base = might_bf = ready_might = gear = attach = buffs = dmg = 0
    for u, o in g.objects.items():
        if o.zone != "board" or o.controller != p:
            continue
        c = g.chars(u)
        if "unit" in c.types:
            m = c.might or 0
            if o.location is not None and o.location[0] == "bf":
                units_bf += 1
                might_bf += m
            else:
                units_base += 1
                might_base += m
            if not o.exhausted:
                ready_might += m
            buffs += o.buffs
            dmg += 1 if o.damage else 0
            attach += len(o.attachments)
        elif "gear" in c.types:
            gear += 1
    runes = len(ps.runes)
    ready_runes = sum(1 for u in ps.runes if not g.objects[u].exhausted)
    champ_waiting = 1.0 if ps.champion is not None and g.objects[ps.champion].zone == "champion" else 0.0
    legend_ready = 1.0 if ps.legend is not None and not g.objects[ps.legend].exhausted else 0.0
    facedown = sum(1 for bf in g.battlefields for u in bf.facedown.values() if g.objects[u].controller == p)
    held = sum(1 for bf in g.battlefields if bf.controller == p)
    out += [units_base / 4, units_bf / 4, might_base / 10, might_bf / 10, ready_might / 10, gear / 3, attach / 3,
            buffs / 3, dmg / 3, len(ps.hand) / 7, len(ps.deck) / 40, len(ps.trash) / 20, runes / 12,
            ready_runes / 12, ps.xp / 5, champ_waiting, legend_ready, facedown / 2, held / 2]


def _hand(g, p, out):
    """Own hand: p may look at it."""
    ps = g.players[p]
    runes = len(ps.runes)
    units = spells = gear = affordable = 0
    cost = 0
    for u in ps.hand:
        d = g.objects[u].defn
        cost += d.energy or 0
        if "unit" in d.types:
            units += 1
        elif "spell" in d.types:
            spells += 1
        elif "gear" in d.types:
            gear += 1
        if (d.energy or 0) <= runes:
            affordable += 1
    out += [units / 4, spells / 4, gear / 3, affordable / 5, cost / 25]


def encode(g, p):
    q = g.opponent(p)
    me, opp = g.players[p], g.players[q]
    win = g.victory_score()
    out = [me.points / win, opp.points / win, (me.points - opp.points) / win,
           1.0 if win - me.points <= 2 else 0.0, 1.0 if win - opp.points <= 2 else 0.0,
           min(g.turn, 30) / 20, 1.0 if g.turn_player == p else 0.0,
           min(len(g.chain), 5) / 5, 1.0 if g.chain and g.chain[-1].controller == p else 0.0,
           1.0 if g.combat is not None else 0.0, 1.0 if getattr(g, "showdown", None) is not None else 0.0]
    ph = g.phase if g.phase in PHASES else "other"
    out += [1.0 if ph == x else 0.0 for x in PHASES]
    from ..policies import heuristic        # hand-written score as one input (reads public info and own hand only)
    out.append(math.tanh(heuristic(g, p) / 150.0))
    _side(g, p, out)
    _side(g, q, out)
    _hand(g, p, out)
    for k in range(MAX_BF):
        if k < len(g.battlefields):
            bf = g.battlefields[k]
            mine = theirs = 0
            for u, o in g.objects.items():
                if o.zone == "board" and o.location is not None and o.location[0] == "bf" and o.location[1] == bf.idx:
                    c = g.chars(u)
                    if "unit" in c.types:
                        if o.controller == p:
                            mine += c.might or 0
                        else:
                            theirs += c.might or 0
            out += [1.0 if bf.controller == p else 0.0, 1.0 if bf.controller == q else 0.0,
                    mine / 8, theirs / 8, 1.0 if bf.contested_by is not None else 0.0]
        else:
            out += [0.0] * 5
    legends = [0.0] * (2 * LEGEND_BUCKETS)
    if me.legend is not None:
        legends[_bucket(g.objects[me.legend].defn.id)] = 1.0
    if opp.legend is not None:
        legends[LEGEND_BUCKETS + _bucket(g.objects[opp.legend].defn.id)] = 1.0
    out += legends
    cards = [0.0] * (3 * CARD_BUCKETS)
    for u in me.hand:
        cards[_card_bucket(g.objects[u].defn.id)] += 0.5
    for o in g.objects.values():
        if o.zone == "board" and ("unit" in o.defn.types or "gear" in o.defn.types):
            base = CARD_BUCKETS if o.controller == p else 2 * CARD_BUCKETS
            cards[base + _card_bucket(o.defn.id)] += 0.5
    return out + cards + _interaction(g, p) + _held_answers(g, p) + _decks(g, p)


def _interaction(g, p):
    """Own hand only: reaction cards held, how many the ready runes pay for now, and how many of those are counters."""
    ps = g.players[p]
    ready = sum(1 for u in ps.runes if not g.objects[u].exhausted)
    held = affordable = counters = 0
    for u in ps.hand:
        d = g.objects[u].defn
        if not d.keywords.get("reaction"):
            continue
        held += 1
        if (d.energy or 0) <= ready:
            affordable += 1
            if "counter" in (d.text or "").lower():
                counters += 1
    return [held / 3, affordable / 3, counters / 2]


def _held_answers(g, p):
    """Version 4 (2026-11-09): what the cards in p's own hand can answer with, and Equipment left lying unattached.
    Kennen and Riven win by holding bounce, removal and fast spells; v3 only counted reactions, and the AI played
    Edge of Night to an empty base. Removal and bounce count when all p's runes could pay for them (next turn they
    are ready); fast spells when the ready runes pay for them now."""
    ps = g.players[p]
    runes = len(ps.runes)
    ready = sum(1 for u in ps.runes if not g.objects[u].exhausted)
    removal = bounce = fast = 0
    for u in ps.hand:
        d = g.objects[u].defn
        if d.type != "spell":
            continue
        t = (d.text or "").lower()
        e = d.energy or 0
        if e <= runes and ("kill" in t or "deal " in t):
            removal += 1
        if e <= runes and ("owner's hand" in t or "owners' hands" in t):
            bounce += 1
        if e <= ready and (d.keywords.get("reaction") or d.keywords.get("action")):
            fast += 1
    loose = sum(1 for o in g.objects.values() if o.zone == "board" and o.controller == p and o.defn.is_equipment
                and o.attached_to is None)
    return [removal / 3, bounce / 3, fast / 3, loose / 2]


def _kinds(d, ready):
    """(reaction, counter, removal, bounce, fast-and-payable, unit) flags of one card definition."""
    t = (d.text or "").lower()
    spell = d.type == "spell"
    reaction = bool(d.keywords.get("reaction"))
    return (reaction, reaction and "counter" in t, spell and ("kill" in t or "deal " in t),
            spell and ("owner's hand" in t or "owners' hands" in t),
            spell and (reaction or bool(d.keywords.get("action"))) and (d.energy or 0) <= ready, "unit" in d.types)


def _decks(g, p):
    """Version 5 (2026-11-26): what is left in each deck. The opponent's decklist is public (Derrick, 2026-11-09), so
    decklist minus every card p has seen is public too: the opponent's unseen pool is their hidden hand + deck +
    facedown cards p can't look at (exactly what `policies.determinize` shuffles), and each pool card is in their hand
    with probability hidden-hand size / pool size. From that: how many reactions, counters, removal, bounce and payable
    fast spells they are expected to hold now. For p's own deck (composition known, order not): the share of units,
    removal and reactions still to draw, and the remaining units' average Might."""
    q = g.opponent(p)
    qs = g.players[q]
    ready_q = sum(1 for u in qs.runes if not g.objects[u].exhausted)
    hidden_hand = [u for u in qs.hand if not g.knows(p, u)]
    pool = hidden_hand + list(qs.deck) + [u for bf in g.battlefields for u in bf.facedown.values()
                                         if g.objects[u].controller == q and not g.knows(p, u)]
    exp = [0.0] * 5
    if pool:
        ph = len(hidden_hand) / len(pool)
        for u in pool:
            k = _kinds(g.objects[u].base_defn(), ready_q)
            for i in range(5):
                if k[i]:
                    exp[i] += ph
    known = [0.0] * 5                              # opponent hand cards p has seen (returned to hand, revealed)
    for u in qs.hand:
        if g.knows(p, u):
            k = _kinds(g.objects[u].base_defn(), ready_q)
            for i in range(5):
                if k[i]:
                    known[i] += 1
    opp = [(exp[i] + known[i]) / 2 for i in range(5)]
    ps = g.players[p]
    n = len(ps.deck)
    units = removal = reactions = might = 0
    for u in ps.deck:                              # composition only: the same for any order of p's deck
        d = g.objects[u].base_defn()
        k = _kinds(d, 0)
        reactions += k[0]
        removal += k[2]
        if k[5]:
            units += 1
            might += d.might or 0
    mine = [units / n, removal / n, reactions / n, (might / units) / 5 if units else 0.0] if n else [0.0] * 4
    return opp + mine


def _card_bucket(card_id):
    return zlib.crc32(b"card:" + card_id.encode()) % CARD_BUCKETS


def size_v1():
    return 11 + len(PHASES) + 1 + 2 * 19 + 5 + 5 * MAX_BF + 2 * LEGEND_BUCKETS


def size_v2():
    return size_v1() + 3 * CARD_BUCKETS


def size_v3():
    return size_v2() + 3


def size_v4():
    return size_v3() + 4


def size():
    return size_v4() + 9
