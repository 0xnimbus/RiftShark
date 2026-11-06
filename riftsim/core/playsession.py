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
        self._ev_seen = 0      # index into game.events already sent to the page
        self._to_grade = None  # (game clone before the move, chosen option, log entry) waiting for grade()

    def playable(self, decks):
        """Keep only decks the engine can run exactly as printed (deck entries: {path, name, data})."""
        out = []
        for d in decks:
            try:
                errs = Deck.from_dict(d["data"], self.db).validate(self.db)
            except Exception as e:  # malformed deck file
                errs = [str(e)]
            if not errs:
                out.append({"path": d["path"], "name": d["name"]})
        return out

    # ------------------------------------------------------------------ lifecycle
    def new(self, deck0, deck1, human=0, seed=None, ai="mcts:100", analysis=150):
        # deck0 is the human's deck and deck1 the AI's; the human sits in seat `human` and seat 0 goes first
        mine = Deck.from_dict(deck0, self.db) if isinstance(deck0, dict) else deck0
        theirs = Deck.from_dict(deck1, self.db) if isinstance(deck1, dict) else deck1
        decks = [mine, theirs] if int(human) == 0 else [theirs, mine]
        for d in decks:
            d.validate(self.db, raise_on_error=True)
        if seed is None or seed == "" or seed == "random":
            import random as _random
            seed = _random.SystemRandom().randrange(2**31)   # a fresh shuffle every game
        self.seed = int(seed)
        self.human, self.ai_spec, self.analysis = int(human), ai, int(analysis)
        self.ai = make_policy(ai, seed=int(seed) + 1)
        g = Game(self.db, decks, seed=int(seed), log=True, first_player=0)
        g.max_turns = 60
        self.game, self.reviews, self.log = g, [], []
        self._ev_seen, self._to_grade = 0, None
        moves = self._run_ai()
        self.log.extend(moves)
        return self.payload({"ai_moves": moves})

    def _run_ai(self):
        g, moves = self.game, []
        while True:
            d = g.run()
            if d is None or d.player == self.human:
                return moves
            moves.append(self._ai_move(d))

    def _ai_move(self, d):
        g = self.game
        ch = self.ai.choose(g, d)
        mv = {"player": d.player, "kind": d.kind, "label": d.labels[d.options.index(ch)], "turn": g.turn,
              "prompt": self._prompt(d)}
        g.choose(ch)
        return mv

    # ------------------------------------------------------------------ views
    def masked_snapshot(self):
        st = _jsonable(self.game.snapshot())
        g = self.game
        for p in st["players"]:
            if p["idx"] != self.human:
                p["hand"] = [h if g.knows(self.human, h["uid"]) else
                             {"uid": None, "card": None, "name": "?", "controller": p["idx"], "hidden": True} for h in p["hand"]]
        for b in st["battlefields"]:          # facedown cards the human may see (own, or Scuttle Crab's look this turn)
            b["facedown_known"] = {k: {"uid": u, "card": g.objects[u].defn.id, "name": g.objects[u].defn.name,
                                       "image": g.objects[u].defn.image}
                                   for k, u in b["facedown"].items() if u in g.objects and g.knows(self.human, u)}
        for it, view in zip(self.game.chain, st["chain"]):
            view["targets"] = self._chain_targets(it)
            ev = it.ctx.vars.get("ev") if getattr(it, "ctx", None) is not None else None
            if it.kind in ("trigger", "reflexive") and isinstance(ev, dict) and ev.get("kind"):
                o = self.game.objects.get(ev.get("uid"))
                view["cause"] = {"event": str(ev["kind"]), "name": o.defn.name if o is not None and o.zone != "hand" else None}
        return st

    def _chain_targets(self, it):
        """Public objects a chain item has chosen so far (its targets), read from its context variables."""
        g, out = self.game, []
        ctx = getattr(it, "ctx", None)
        if ctx is None:
            return out
        def add(v):
            if isinstance(v, bool) or not isinstance(v, int) or v == it.uid or v in seen:
                return
            o = g.objects.get(v)
            hidden = any(v in b.facedown.values() for b in g.battlefields) and not g.knows(self.human, v)
            if o is not None and o.zone in ("board", "champion") and not hidden:
                seen.add(v)
                out.append({"uid": v, "name": o.defn.name, "controller": o.controller})
        seen = set()
        for k, v in list(ctx.vars.items()):
            if str(k).startswith("__") or k in ("self", "ev"):
                continue
            for x in (v if isinstance(v, (tuple, list)) else (v,)):
                add(x)
        return out[:6]

    def summary(self):
        rs = [r for r in self.reviews if r.get("grade") not in (None, "only move")]
        if not rs:
            return {"moves": 0}
        counts = {}
        for r in rs:
            counts[r["grade"]] = counts.get(r["grade"], 0) + 1
        avg_loss = sum(r["loss_pct"] for r in rs) / len(rs)
        return {"moves": len(rs), "counts": counts, "avg_loss": round(avg_loss, 1), "accuracy": round(max(0.0, 100.0 - 2.5 * avg_loss), 1)}

    @staticmethod
    def _prompt(d):
        info = d.info or {}
        return str(info.get("label") or info.get("cost") or "")

    def decision_view(self, d):
        """What the page needs to explain a decision: who decides, what kind, the options, and which card asks."""
        if d is None:
            return None
        g, info = self.game, d.info or {}
        dv = {"player": d.player, "kind": d.kind, "labels": list(d.labels), "n": len(d.options), "prompt": self._prompt(d),
              "showdown": bool(info.get("showdown")), "chain": bool(info.get("chain"))}
        if d.kind == "mulligan":   # which hand cards each option sets aside, so the page can show a pick-up-to-two hand
            dv["option_uids"] = [list(o) for o in d.options]
        src = None
        if not info.get("handler") and getattr(g, "vm_frames", None):
            src = g.vm_frames[-1].ctx.source
        if src is not None and src in g.objects:
            o = g.objects[src]
            dv["source"] = {"uid": src, "card": o.defn.id, "name": o.defn.name, "image": o.defn.image,
                            "text": o.defn.text}       # shown under the prompt so the player sees why it is asked
        return dv

    def new_events(self):
        """Engine log entries since the last call (internal 'event:*' mirrors dropped), for the plain-language log."""
        g = self.game
        evs = g.events[self._ev_seen:]
        self._ev_seen = len(g.events)
        out = [e for e in evs if not e["kind"].startswith("event:")]
        hidden = {u for p in g.players if p.idx != self.human for u in p.hand}
        for e in out:  # never leak the name of a card the opponent drew or holds
            if e.get("kind") == "draw" and e.get("player") != self.human:
                e.pop("uid", None)
            elif e.get("uid") in hidden and "name" in e:
                e.pop("name", None)
        return _jsonable(out[-300:])

    def payload(self, extra=None):
        g = self.game
        out = {"ok": True, "started": g is not None, "seed": getattr(self, "seed", None)}
        if g is not None:
            d = g.run()
            out.update({"state": self.masked_snapshot(), "decision": self.decision_view(d), "over": g.over, "winner": g.winner,
                        "reason": g.reason, "turn": g.turn, "human": self.human, "victory": g.cfg.get("victory", 8),
                        "reviews": self.reviews[-200:], "log": self.log[-60:], "summary": self.summary(),
                        "events": self.new_events(), "grading": self._to_grade is not None})
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

    # Step API used by the page so it can show each move as soon as it happens:
    #   apply(i) -> your move is played at once; ai_step() -> one opponent decision at a time; grade() -> coach verdict.
    def apply(self, index):
        g = self.game
        d = g.run() if g else None
        if d is None or d.player != self.human:
            return {"ok": False, "error": "not your decision"}
        i = int(index)
        if not 0 <= i < len(d.options):
            return {"ok": False, "error": "bad option"}
        ch = d.options[i]
        before = g.clone() if len(d.options) > 1 else None
        entry = {"player": self.human, "kind": d.kind, "label": d.labels[i], "turn": g.turn, "grade": None, "prompt": self._prompt(d)}
        review = {"turn": g.turn, "kind": d.kind, "label": d.labels[i], "n": len(d.options)}
        g.choose(ch)
        self.log.append(entry)
        if before is None:
            review.update({"grade": "only move", "loss_pct": 0.0, "win_pct": None})
            entry["grade"] = "only move"
            self.reviews.append(review)
        else:
            self._to_grade = (before, ch, entry, review)
        return self.payload({"applied": entry})

    def ai_step(self):
        g = self.game
        d = g.run() if g else None
        if d is None or d.player == self.human:
            return self.payload({"ai_done": True})
        mv = self._ai_move(d)
        self.log.append(mv)
        nd = g.run()
        return self.payload({"ai_move": mv, "ai_done": nd is None or nd.player == self.human})

    def grade(self):
        if self._to_grade is None:
            return {"ok": True, "review": None, "summary": self.summary()}
        before, ch, entry, review = self._to_grade
        self._to_grade = None
        d = before.run()
        an = analyze(before, d, iterations=self.analysis, seed=len(self.reviews))
        review.update(grade_choice(an, ch))
        review["alternatives"] = [{"label": o["label"], "win_pct": o["win_pct"]} for o in an["options"][:5]]
        entry["grade"] = review["grade"]
        self.reviews.append(review)
        return {"ok": True, "review": review, "summary": self.summary(), "log": self.log[-60:]}

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
