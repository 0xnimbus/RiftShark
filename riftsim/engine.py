"""Rules engine: setup, legal actions, and applying actions.

This is a simplified model of Riftbound 1v1. See RULES.md for exactly what is and is not modeled.
The engine is deterministic given (decks, seed, action list), which is what makes replays work.

Actions are plain tuples so they are hashable and JSON-serialisable:
    ("end",)                                   end the turn
    ("play", uid, target_uid|None, accelerate) play a card from hand
    ("champ", accelerate)                      play the chosen champion from the champion zone
    ("move", (uid, ...), dest)                 move units; dest = battlefield index, or -1 for base
"""
from __future__ import annotations

import random

from .state import Battlefield, GameState, PlayerState, Rune, Unit

DEFAULT_CONFIG = {
    "victory_points": 8,
    "opening_hand": 4,
    "runes_per_turn": 2,
    "second_player_extra_rune": True,
    "final_point_rule": True,      # last point can't come from conquering unless every battlefield was scored this turn
    "max_turns": 60,               # half-turns before the game is declared a draw
    "max_actions_per_turn": 40,
}


class IllegalAction(Exception):
    pass


# ---------------------------------------------------------------- setup
def new_game(reg, deck_a, deck_b, seed=0, config=None, log=True) -> GameState:
    s = GameState()
    s.reg = reg
    s.config = {**DEFAULT_CONFIG, **(config or {})}
    s.rng = random.Random(seed)
    s.next_uid = 1
    s.log = [] if log else None
    s.winner, s.done, s.turn, s.actions_this_turn = None, False, 0, 0
    s.players = []
    for i, deck in enumerate((deck_a, deck_b)):
        p = PlayerState(i)
        p.deck_name, p.legend = deck.name, deck.legend
        p.deck = list(deck.main)
        s.rng.shuffle(p.deck)
        p.rune_deck = list(deck.runes)
        s.rng.shuffle(p.rune_deck)
        p.champion = (_uid(s), deck.champion)
        s.players.append(p)
    s.battlefields = [Battlefield(s.rng.choice(d.battlefields), i) for i, d in enumerate((deck_a, deck_b))]
    s.first = s.rng.randrange(2)
    s.active = s.first
    for p in s.players:
        for _ in range(s.config["opening_hand"]):
            _draw(s, p, quiet=True)
    _event(s, "setup", first=s.first, battlefields=[b.name for b in s.battlefields])
    _start_turn(s)
    return s


def _uid(s):
    s.next_uid += 1
    return s.next_uid - 1


def _event(s, kind, **data):
    if s.log is not None:
        s.log.append({"turn": s.turn, "kind": kind, **data})


# ---------------------------------------------------------------- turn structure
def _start_turn(s):
    p = s.players[s.active]
    p.scored = set()
    p.legend_used = False
    s.actions_this_turn = 0
    # Awaken: ready everything we control.
    for r in p.runes:
        r.exhausted = False
    for u in _my_units(s, p.idx):
        u.exhausted = False
    _event(s, "turn_start", player=p.idx)
    # Beginning phase: score every battlefield we hold.
    for i, bf in enumerate(s.battlefields):
        if bf.controller == p.idx:
            _score(s, p, i, "hold")
            if s.done:
                return
    # Channel runes.
    n = s.config["runes_per_turn"]
    if s.config["second_player_extra_rune"] and s.turn == 1:
        n += 1
    for _ in range(n):
        if p.rune_deck:
            p.runes.append(Rune(p.rune_deck.pop(0)))
    # Draw.
    _draw(s, p)


def _end_turn(s):
    for u, _ in s.all_units():
        u.damage = 0
        u.temp_might = 0
    _event(s, "turn_end", player=s.active)
    s.active = 1 - s.active
    s.turn += 1
    if s.turn >= s.config["max_turns"]:
        s.done = True
        _event(s, "draw_game", reason="turn limit")
        return
    _start_turn(s)


def _draw(s, p, quiet=False):
    if not p.deck:
        # Burn out: shuffle the trash back in, opponent gains a point.
        p.deck = p.trash
        p.trash = []
        s.rng.shuffle(p.deck)
        _event(s, "burn_out", player=p.idx)
        _gain_point(s, s.players[1 - p.idx], "burn out")
        if s.done or not p.deck:
            return
    cid = p.deck.pop(0)
    p.hand.append((_uid(s), cid))
    if not quiet:
        _event(s, "draw", player=p.idx, card=cid)


# ---------------------------------------------------------------- scoring
def _gain_point(s, p, reason):
    p.points += 1
    _event(s, "point", player=p.idx, reason=reason, total=p.points)
    if p.points >= s.config["victory_points"] and not s.done:
        s.winner, s.done = p.idx, True
        _event(s, "win", player=p.idx)


def _score(s, p, bf_idx, how):
    if bf_idx in p.scored:
        return
    p.scored.add(bf_idx)
    final = p.points + 1 >= s.config["victory_points"]
    if (how == "conquer" and final and s.config["final_point_rule"]
            and len(p.scored) < len(s.battlefields)):
        _event(s, "final_point_denied", player=p.idx, battlefield=bf_idx)
        _draw(s, p)
        return
    _gain_point(s, p, f"{how} {s.battlefields[bf_idx].name}")


def _conquer(s, pidx, bf_idx):
    bf = s.battlefields[bf_idx]
    bf.controller = pidx
    p = s.players[pidx]
    _event(s, "conquer", player=pidx, battlefield=bf_idx)
    _score(s, p, bf_idx, "conquer")
    ab = s.reg.legends[p.legend].ability or {}
    if ab.get("type") == "conquer_draw" and not p.legend_used and not s.done:
        p.legend_used = True
        _event(s, "legend", player=pidx, ability="conquer_draw")
        _draw(s, p)


def _update_control(s, bf_idx):
    bf = s.battlefields[bf_idx]
    if bf.controller is not None and not bf.units[bf.controller]:
        bf.controller = None


# ---------------------------------------------------------------- costs
def _plan_payment(runes, energy, power):
    """Return (recycle_idx, exhaust_idx) or None. Power is paid first, preferring already-exhausted runes."""
    used, recycle = set(), []
    for dom in power:
        cands = [i for i, r in enumerate(runes) if i not in used and (dom == "any" or r.domain == dom)]
        if not cands:
            return None
        cands.sort(key=lambda i: not runes[i].exhausted)
        used.add(cands[0])
        recycle.append(cands[0])
    ready = [i for i, r in enumerate(runes) if i not in used and not r.exhausted]
    if len(ready) < energy:
        return None
    return recycle, ready[:energy]


def card_cost(s, cid, accelerate):
    c = s.card(cid)
    energy, power = c.energy, list(c.power)
    if accelerate:
        energy += 1
        power.append(c.domains[0] if c.domains else "any")
    return energy, power


def _pay(s, p, energy, power):
    plan = _plan_payment(p.runes, energy, power)
    if plan is None:
        raise IllegalAction("cannot pay cost")
    recycle, exhaust = plan
    for i in exhaust:
        p.runes[i].exhausted = True
    for i in sorted(recycle, reverse=True):
        p.rune_deck.append(p.runes.pop(i).domain)


# ---------------------------------------------------------------- units / combat
def _my_units(s, pidx):
    out = list(s.players[pidx].base)
    for bf in s.battlefields:
        out += bf.units[pidx]
    return out


def might(s, u, role=None):
    c = s.card(u.card_id)
    m = c.might + u.temp_might
    if role == "attack":
        m += int(c.keywords.get("assault", 0))
        ab = s.reg.legends[s.players[u.owner].legend].ability or {}
        if ab.get("type") == "attack_bonus" and ab.get("domain") in c.domains:
            m += ab.get("amount", 1)
    elif role == "defend":
        m += int(c.keywords.get("shield", 0))
    return max(m, 0)


def _assign_damage(s, total, units, role):
    """Assign damage to kill as many units as possible; Tank units must be assigned lethal damage first."""
    order = sorted(units, key=lambda u: (not s.card(u.card_id).keywords.get("tank", False),
                                         might(s, u, role) - u.damage))
    for u in order:
        if total <= 0:
            break
        need = max(might(s, u, role) - u.damage, 0)
        give = min(need, total)
        u.damage += give
        total -= give


def _remove_dead(s, bf_idx, roles):
    bf = s.battlefields[bf_idx]
    dead = []
    for side in (0, 1):
        alive = []
        for u in bf.units[side]:
            if u.damage >= might(s, u, roles[side]) or might(s, u, roles[side]) == 0:
                dead.append(u)
                s.players[u.owner].trash.append(u.card_id)
            else:
                alive.append(u)
        bf.units[side][:] = alive
    return dead


def _combat(s, attacker, bf_idx):
    bf = s.battlefields[bf_idx]
    defender = 1 - attacker
    roles = {attacker: "attack", defender: "defend"}
    att_power = sum(might(s, u, "attack") for u in bf.units[attacker])
    def_power = sum(might(s, u, "defend") for u in bf.units[defender])
    _event(s, "combat", attacker=attacker, battlefield=bf_idx,
           attackers=[u.card_id for u in bf.units[attacker]], defenders=[u.card_id for u in bf.units[defender]],
           attack_might=att_power, defend_might=def_power)
    _assign_damage(s, att_power, bf.units[defender], "defend")
    _assign_damage(s, def_power, bf.units[attacker], "attack")
    dead = _remove_dead(s, bf_idx, roles)
    _event(s, "combat_result", battlefield=bf_idx, died=[u.card_id for u in dead])
    if bf.units[attacker] and not bf.units[defender]:
        _conquer(s, attacker, bf_idx)
    elif bf.units[attacker] and bf.units[defender]:
        # Nobody was wiped out: attackers are recalled to base.
        s.players[attacker].base.extend(bf.units[attacker])
        bf.units[attacker].clear()
        _event(s, "recall", player=attacker, battlefield=bf_idx)
    _update_control(s, bf_idx)


def _arrive(s, pidx, bf_idx):
    bf = s.battlefields[bf_idx]
    if bf.units[1 - pidx]:
        _combat(s, pidx, bf_idx)
    elif bf.controller != pidx:
        _conquer(s, pidx, bf_idx)


# ---------------------------------------------------------------- effects
def effect_targets(s, eff, pidx):
    """None = no target needed; otherwise list of unit uids that are legal targets."""
    tgt = (eff or {}).get("target")
    if not tgt:
        return None
    out = []
    for u, _ in s.all_units():
        if tgt == "enemy_unit" and u.owner != pidx:
            out.append(u.uid)
        elif tgt == "friendly_unit" and u.owner == pidx:
            out.append(u.uid)
        elif tgt == "any_unit":
            out.append(u.uid)
    return out


def _resolve_effect(s, eff, pidx, target_uid):
    t = eff["type"]
    p = s.players[pidx]
    if t == "draw":
        for _ in range(eff.get("amount", 1)):
            _draw(s, p)
    elif t == "damage":
        u, loc = s.find_unit(target_uid)
        u.damage += eff["amount"]
        if u.damage >= might(s, u):
            _destroy(s, u, loc)
    elif t == "buff":
        u, _ = s.find_unit(target_uid)
        u.temp_might += eff["amount"]
    elif t == "kill_if_might_le":
        u, loc = s.find_unit(target_uid)
        if might(s, u) <= eff["amount"]:
            _destroy(s, u, loc)
    elif t == "ready_runes":
        n = eff.get("amount", 1)
        for r in p.runes:
            if n and r.exhausted:
                r.exhausted, n = False, n - 1
    else:
        raise ValueError(f"unknown effect type {t}")


def _destroy(s, u, loc):
    if loc == -1:
        s.players[u.owner].base.remove(u)
    else:
        s.battlefields[loc].units[u.owner].remove(u)
        _update_control(s, loc)
    s.players[u.owner].trash.append(u.card_id)
    _event(s, "destroyed", card=u.card_id, owner=u.owner)


# ---------------------------------------------------------------- legal actions
def legal_actions(s):
    if s.done:
        return []
    p = s.players[s.active]
    acts = [("end",)]
    if s.actions_this_turn >= s.config["max_actions_per_turn"]:
        return acts
    seen = set()
    for uid, cid in p.hand:
        if cid in seen:            # identical copies give identical actions; only offer the first copy
            continue
        seen.add(cid)
        c = s.card(cid)
        if c.is_unit:
            for accel in (False, True) if c.keywords.get("accelerate") else (False,):
                if _plan_payment(p.runes, *card_cost(s, cid, accel)) is not None:
                    acts.append(("play", uid, None, accel))
        else:
            if _plan_payment(p.runes, *card_cost(s, cid, False)) is None:
                continue
            targets = effect_targets(s, c.effect, p.idx)
            if targets is None:
                acts.append(("play", uid, None, False))
            else:
                acts += [("play", uid, t, False) for t in targets]
    if p.champion:
        cid = p.champion[1]
        for accel in (False, True) if s.card(cid).keywords.get("accelerate") else (False,):
            if _plan_payment(p.runes, *card_cost(s, cid, accel)) is not None:
                acts.append(("champ", accel))
    # Moves: each ready unit alone, plus all ready base units together.
    ready_base = [u for u in p.base if not u.exhausted]
    for i in range(len(s.battlefields)):
        for u in ready_base:
            acts.append(("move", (u.uid,), i))
        if len(ready_base) > 1:
            acts.append(("move", tuple(u.uid for u in ready_base), i))
    for i, bf in enumerate(s.battlefields):
        for u in bf.units[p.idx]:
            if u.exhausted:
                continue
            acts.append(("move", (u.uid,), -1))
            if s.card(u.card_id).keywords.get("ganking"):
                acts += [("move", (u.uid,), j) for j in range(len(s.battlefields)) if j != i]
    return acts


# ---------------------------------------------------------------- apply
def apply(s, action):
    """Apply an action in place. Raises IllegalAction if it is not legal."""
    if s.done:
        raise IllegalAction("game is over")
    p = s.players[s.active]
    kind = action[0]
    if s.log is not None:
        s.log.append({"turn": s.turn, "kind": "action", "player": p.idx, "action": list(action),
                      "text": describe(s, action)})
    if kind == "end":
        _end_turn(s)
        return
    if s.actions_this_turn >= s.config["max_actions_per_turn"]:
        raise IllegalAction("action limit reached for this turn")
    s.actions_this_turn += 1
    if kind == "play":
        _, uid, target, accel = action
        entry = next((h for h in p.hand if h[0] == uid), None)
        if entry is None:
            raise IllegalAction("card not in hand")
        cid = entry[1]
        c = s.card(cid)
        if accel and not c.keywords.get("accelerate"):
            raise IllegalAction("card has no Accelerate")
        if not c.is_unit:
            targets = effect_targets(s, c.effect, p.idx)
            if (targets is None) != (target is None) or (targets is not None and target not in targets):
                raise IllegalAction("illegal target")
        _pay(s, p, *card_cost(s, cid, accel))
        p.hand.remove(entry)
        if c.is_unit:
            p.base.append(Unit(uid, cid, p.idx, exhausted=not accel))
            if c.effect and c.effect.get("trigger") == "play":
                tg = None
                if effect_targets(s, c.effect, p.idx):
                    tg = effect_targets(s, c.effect, p.idx)[0]
                if c.effect.get("target") is None or tg is not None:
                    _resolve_effect(s, c.effect, p.idx, tg)
        else:
            _resolve_effect(s, c.effect, p.idx, target)
            p.trash.append(cid)
    elif kind == "champ":
        accel = action[1]
        if not p.champion:
            raise IllegalAction("champion already played")
        uid, cid = p.champion
        if accel and not s.card(cid).keywords.get("accelerate"):
            raise IllegalAction("champion has no Accelerate")
        _pay(s, p, *card_cost(s, cid, accel))
        p.champion = None
        p.base.append(Unit(uid, cid, p.idx, exhausted=not accel))
    elif kind == "move":
        _, uids, dest = action
        units = []
        origins = set()
        for uid in uids:
            u, loc = s.find_unit(uid)
            if u is None or u.owner != p.idx or u.exhausted:
                raise IllegalAction("unit cannot move")
            if loc == dest:
                raise IllegalAction("unit is already there")
            if loc != -1 and dest != -1 and not s.card(u.card_id).keywords.get("ganking"):
                raise IllegalAction("moving between battlefields needs Ganking")
            units.append((u, loc))
            origins.add(loc)
        for u, loc in units:
            (p.base if loc == -1 else s.battlefields[loc].units[p.idx]).remove(u)
            u.exhausted = True
            (p.base if dest == -1 else s.battlefields[dest].units[p.idx]).append(u)
        for loc in origins:
            if loc != -1:
                _update_control(s, loc)
        if dest != -1:
            _arrive(s, p.idx, dest)
    else:
        raise IllegalAction(f"unknown action {kind}")


def describe(s, action):
    p = s.players[s.active]
    kind = action[0]
    if kind == "end":
        return "End turn"
    if kind == "champ":
        return f"Play champion {s.card(p.champion[1]).name}" + (" (accelerated)" if action[1] else "") if p.champion else "Play champion"
    if kind == "play":
        cid = next((c for u, c in p.hand if u == action[1]), "?")
        txt = f"Play {s.card(cid).name if cid != '?' else cid}"
        if action[2] is not None:
            u, _ = s.find_unit(action[2])
            txt += f" targeting {s.card(u.card_id).name}#{u.uid}" if u else ""
        return txt + (" (accelerated)" if action[3] else "")
    if kind == "move":
        names = []
        for uid in action[1]:
            u, _ = s.find_unit(uid)
            names.append(f"{s.card(u.card_id).name}#{uid}" if u else str(uid))
        dest = "base" if action[2] == -1 else s.battlefields[action[2]].name
        return f"Move {', '.join(names)} to {dest}"
    return str(action)


def action_from_json(a):
    """Rebuild an action tuple from its JSON list form."""
    if a[0] == "move":
        return ("move", tuple(a[1]), a[2])
    return tuple(a)
