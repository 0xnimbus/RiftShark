"""Replays: every game is saved as (decks, seed, config, actions). A replay can be
re-simulated step by step, printed as a readable transcript, and verified: each recorded
action is checked against the engine's own legal_actions() before it is applied, so any
rule violation (or engine bug that lets one through) is reported with the turn it happened on.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import engine
from .cards import Registry


def save(path, s, deck_paths, seed, policies, result):
    actions = [e["action"] for e in (s.log or []) if e["kind"] == "action"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({
        "version": 1, "decks": list(deck_paths), "seed": seed, "config": s.config,
        "policies": list(policies), "actions": actions, "result": result,
    }))


def load(path):
    return json.loads(Path(path).read_text())


def resimulate(rep, reg: Registry, card_set, verify=True):
    """Yield (step, action_text, state_snapshot, events) for each recorded action.
    Raises engine.IllegalAction (with step info) if verification fails."""
    decks = [reg.load_deck(p) for p in rep["decks"]]
    s = engine.new_game(reg, decks[0], decks[1], seed=rep["seed"], config=rep["config"])
    yield 0, "Game start", s.snapshot(), list(s.log)
    for i, a in enumerate(rep["actions"], 1):
        act = engine.action_from_json(a)
        if verify and act not in engine.legal_actions(s):
            raise engine.IllegalAction(f"step {i} (turn {s.turn}, player {s.active}): {act} is not legal")
        text = engine.describe(s, act)
        before = len(s.log)
        engine.apply(s, act)
        yield i, text, s.snapshot(), s.log[before:]
    if rep.get("result") and rep["result"].get("winner") != s.winner:
        raise engine.IllegalAction(f"recorded winner {rep['result'].get('winner')} but replay ends with {s.winner}")


def verify(rep, reg, card_set):
    try:
        for _ in resimulate(rep, reg, card_set, verify=True):
            pass
        return True, "ok"
    except engine.IllegalAction as e:
        return False, str(e)


def _fmt_units(reg, units):
    return ", ".join(f"{reg.cards[u['card']].name}{'(ex)' if u['exhausted'] else ''}"
                     + (f"[-{u['damage']}]" if u["damage"] else "") for u in units) or "-"


def transcript(rep, reg, card_set, show_hands=True):
    """Human-readable transcript of a replay."""
    lines = []
    for step, text, snap, events in resimulate(rep, reg, card_set, verify=False):
        p = snap["active"]
        lines.append(f"\n=== Step {step} | Turn {snap['turn']} | P{p} ({snap['players'][p]['deck']}) : {text}")
        for e in events:
            if e["kind"] in ("action",):
                continue
            desc = {k: v for k, v in e.items() if k not in ("turn", "kind")}
            lines.append(f"    · {e['kind']}: {desc}")
        for i, pl in enumerate(snap["players"]):
            runes = "".join(("x" if r["exhausted"] else r["domain"][0].upper()) for r in pl["runes"])
            hand = f" hand={[reg.cards[c].name for c in pl['hand']]}" if show_hands else f" hand={len(pl['hand'])}"
            lines.append(f"  P{i} pts={pl['points']} runes={runes} deck={pl['deck_size']}"
                         f" champ={'in zone' if pl['champion_zone'] else 'played'}{hand}")
            lines.append(f"     base: {_fmt_units(reg, pl['base'])}")
        for bi, bf in enumerate(snap["battlefields"]):
            ctrl = "nobody" if bf["controller"] is None else f"P{bf['controller']}"
            lines.append(f"  BF{bi} {bf['name']} (held by {ctrl}): P0 [{_fmt_units(reg, bf['units'][0])}] "
                         f"P1 [{_fmt_units(reg, bf['units'][1])}]")
        if snap["winner"] is not None:
            lines.append(f"\n*** P{snap['winner']} ({snap['players'][snap['winner']]['deck']}) WINS ***")
    return "\n".join(lines)
