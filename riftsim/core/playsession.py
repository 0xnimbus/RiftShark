"""A single human-vs-AI game with move grading. Used by tools/play_server.py (local HTTP) and by the in-browser
build (Pyodide, see web/engine_worker.js). Everything returned is plain JSON-able data."""
from __future__ import annotations

from .analysis import analyze, grade_choice
from .deck import Deck
from .game import Game
from .policies import make_policy
from .replay import _jsonable


class PlaySession:
    def __init__(self, db):
        self.db = db
        self.game = None
        self.human = 0
        self.ai = None
        self.ai_spec = "mcts:100"
        self.analysis = 150
        self.reviews = []
        self.log = []

    # ------------------------------------------------------------------ lifecycle
    def new(self, deck0, deck1, human=0, seed=0, ai="mcts:100", analysis=150):
        decks = [Deck.from_dict(deck0, self.db) if isinstance(deck0, dict) else deck0,
                 Deck.from_dict(deck1, self.db) if isinstance(deck1, dict) else deck1]
        for d in decks:
            d.validate(self.db, raise_on_error=True)
        self.human, self.ai_spec, self.analysis = int(human), ai, int(analysis)
        self.ai = make_policy(ai, seed=int(seed) + 1)
        g = Game(self.db, decks, seed=int(seed), log=True)
        g.max_turns = 60
        self.game, self.reviews, self.log = g, [], []
        moves = self._run_ai()
        self.log.extend(moves)
        return self.payload({"ai_moves": moves})

    def _run_ai(self):
        g, moves = self.game, []
        while True:
            d = g.run()
            if d is None or d.player == self.human:
                return moves
            ch = self.ai.choose(g, d)
            moves.append({"player": d.player, "kind": d.kind, "label": d.labels[d.options.index(ch)], "turn": g.turn})
            g.choose(ch)

    # ------------------------------------------------------------------ views
    def masked_snapshot(self):
        st = _jsonable(self.game.snapshot())
        for p in st["players"]:
            if p["idx"] != self.human:
                p["hand"] = [{"uid": None, "card": None, "name": "?", "controller": p["idx"], "hidden": True} for _ in p["hand"]]
        return st

    def summary(self):
        rs = [r for r in self.reviews if r.get("grade") not in (None, "only move")]
        if not rs:
            return {"moves": 0}
        counts = {}
        for r in rs:
            counts[r["grade"]] = counts.get(r["grade"], 0) + 1
        avg_loss = sum(r["loss_pct"] for r in rs) / len(rs)
        return {"moves": len(rs), "counts": counts, "avg_loss": round(avg_loss, 1), "accuracy": round(max(0.0, 100.0 - 2.5 * avg_loss), 1)}

    def payload(self, extra=None):
        g = self.game
        out = {"ok": True, "started": g is not None}
        if g is not None:
            d = g.run()
            dv = None if d is None else {"player": d.player, "kind": d.kind, "labels": list(d.labels), "n": len(d.options)}
            out.update({"state": self.masked_snapshot(), "decision": dv, "over": g.over, "winner": g.winner, "reason": g.reason,
                        "turn": g.turn, "human": self.human, "reviews": self.reviews[-200:], "log": self.log[-60:], "summary": self.summary()})
        if extra:
            out.update(extra)
        return out

    # ------------------------------------------------------------------ actions
    def hint(self):
        g = self.game
        d = g.run() if g else None
        if d is None or d.player != self.human:
            return {"ok": False, "error": "no decision pending"}
        an = analyze(g, d, iterations=self.analysis, seed=len(self.reviews))
        return {"ok": True, "options": [{"label": o["label"], "win_pct": o["win_pct"], "index": o["index"]} for o in an["options"][:8]]}

    def choose(self, index):
        g = self.game
        d = g.run() if g else None
        if d is None or d.player != self.human:
            return {"ok": False, "error": "not your decision"}
        i = int(index)
        if not 0 <= i < len(d.options):
            return {"ok": False, "error": "bad option"}
        ch = d.options[i]
        review = {"turn": g.turn, "kind": d.kind, "label": d.labels[i], "n": len(d.options)}
        if len(d.options) > 1:
            an = analyze(g, d, iterations=self.analysis, seed=len(self.reviews))
            review.update(grade_choice(an, ch))
            review["alternatives"] = [{"label": o["label"], "win_pct": o["win_pct"]} for o in an["options"][:5]]
        else:
            review.update({"grade": "only move", "loss_pct": 0.0, "win_pct": None})
        g.choose(ch)
        self.reviews.append(review)
        self.log.append({"player": self.human, "kind": d.kind, "label": d.labels[i], "turn": review["turn"], "grade": review["grade"]})
        moves = self._run_ai()
        self.log.extend(moves)
        return self.payload({"review": review, "ai_moves": moves})
