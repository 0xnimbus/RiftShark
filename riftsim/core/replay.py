"""Replays: a game is fully determined by (decks, seed, list of choices). A replay stores the choices
plus the event log and per-decision snapshots so it can be watched back, and `verify` re-simulates it
from scratch, checking that every recorded choice was among the legal options at that point and that the
outcome matches. That is the rules audit: the engine itself enumerates legality, so a replay that
re-simulates identically never contained an illegal action under the engine's rules."""
from __future__ import annotations

import gzip
import json

from .deck import Deck
from .game import Game


def _jsonable(x):
    if isinstance(x, tuple):
        return {"__t": [_jsonable(v) for v in x]}
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (int, float, str, bool)) or x is None:
        return x
    if isinstance(x, set):
        return [_jsonable(v) for v in sorted(x, key=str)]
    return str(x)


def _unjson(x):
    if isinstance(x, dict):
        if "__t" in x and len(x) == 1:
            return tuple(_unjson(v) for v in x["__t"])
        return {k: _unjson(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_unjson(v) for v in x]
    return x


class Recorder:
    """Collects decisions and snapshots while a game is played."""

    def __init__(self, game, snapshots=True):
        self.game = game
        self.choices = []
        self.frames = []
        self.snapshots = snapshots

    def record(self, d, choice):
        self.choices.append(choice)
        if self.snapshots:
            self.frames.append({"decision": {"player": d.player, "kind": d.kind, "label": d.labels[d.options.index(choice)],
                                             "n_options": len(d.options), "options": d.labels[:60]},
                                "event_index": len(self.game.events),
                                "state": _jsonable(self.game.snapshot())})

    def to_replay(self, decks, seed, policies=None):
        g = self.game
        return {
            "version": 2,
            "seed": seed,
            "decks": [d.to_dict() for d in decks],
            "policies": policies or [],
            "choices": _jsonable(self.choices),
            "frames": self.frames,
            "events": _jsonable(g.events),
            "result": {"winner": g.winner, "reason": g.reason, "turns": g.turn, "points": [p.points for p in g.players]},
            "final": _jsonable(g.snapshot()),
        }


def play_game(db, decks, seed, policies, record=True, snapshots=False, max_turns=60, log=True):
    """Play one game to completion. Returns (game, replay_dict or None)."""
    g = Game(db, decks, seed=seed, log=log)
    g.max_turns = max_turns
    rec = Recorder(g, snapshots=snapshots) if record else None
    while True:
        d = g.run()
        if d is None:
            break
        choice = policies[d.player].choose(g, d)
        if rec is not None:
            rec.record(d, choice)
        g.choose(choice)
    rep = rec.to_replay(decks, seed, [getattr(p, "name", "?") for p in policies]) if rec is not None else None
    return g, rep


def save_replay(rep, path):
    data = json.dumps(rep).encode()
    if str(path).endswith(".gz"):
        with gzip.open(path, "wb") as f:
            f.write(data)
    else:
        with open(path, "wb") as f:
            f.write(data)


def load_replay(path):
    if str(path).endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode())
    with open(path) as f:
        return json.load(f)


def verify(db, rep):
    """Re-simulate the replay. Returns (ok, report)."""
    decks = [Deck.from_dict(d, db) for d in rep["decks"]]
    g = Game(db, decks, seed=rep["seed"])
    choices = _unjson(rep["choices"])
    problems = []
    for i, ch in enumerate(choices):
        d = g.run()
        if d is None:
            problems.append(f"game ended before choice {i}")
            break
        if ch not in d.options:
            problems.append(f"choice {i} ({ch!r}) not legal for {d}")
            break
        g.choose(ch)
    else:
        d = g.run()
        if d is not None:
            problems.append("game did not end after the last recorded choice")
    res = rep.get("result", {})
    if not problems:
        if g.winner != res.get("winner") or [p.points for p in g.players] != res.get("points"):
            problems.append(f"outcome differs: winner {g.winner} points {[p.points for p in g.players]} vs recorded {res}")
    return (not problems), {"problems": problems, "choices": len(choices), "turns": g.turn, "winner": g.winner}


def transcript(rep, db=None):
    """Human readable account of a replay from its event log."""
    lines = []
    skip = {"event:exhaust", "event:ready", "event:pay", "event:add", "event:channel", "event:draw", "event:awaken", "pay",
            "event:leave_loc", "event:arrive", "event:enter", "event:play", "event:resolve", "finalized", "resolve",
            "event:gain_points", "event:score", "event:main_phase", "event:beginning_phase", "event:ending_phase",
            "event:move", "event:recycle", "event:leave", "event:hold", "event:conquer", "event:combat_start",
            "event:showdown_start", "event:combat_end", "event:combat_result", "event:attack", "event:defend",
            "event:damage", "event:stun", "event:buff", "event:die", "event:hide", "event:attach", "event:recall",
            "event:target", "event:discard", "event:burn", "event:xp"}
    turn = None
    for e in _unjson(rep["events"]):
        k = e["kind"]
        if k in skip:
            continue
        if e.get("turn") != turn:
            turn = e.get("turn")
        d = {a: b for a, b in e.items() if a not in ("kind", "turn")}
        if k == "turn":
            lines.append(f"\n=== Turn {turn}: P{d['player']} ===")
        elif k == "decision":
            lines.append(f"  P{d['player']} {d['dkind']}: {d['choice']}")
        else:
            lines.append(f"    {k}: " + ", ".join(f"{a}={b}" for a, b in d.items()))
    r = rep.get("result", {})
    lines.append(f"\nResult: winner P{r.get('winner')} ({r.get('reason')}) after {r.get('turns')} turns, points {r.get('points')}")
    return "\n".join(lines)
