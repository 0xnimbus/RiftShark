"""Play a deck against the AI in the browser with chess-style move grading.

usage: python tools/play_server.py [--port 8765] [--ai mcts:100] [--analysis 150]
then open http://localhost:8765/play.html

Single local game session (no auth; local use only). The engine and the move analysis run in Python, so this
page cannot work from GitHub Pages: it needs this server running on your machine.
"""
import json
import os
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from riftsim.core.analysis import analyze, grade_choice  # noqa: E402
from riftsim.core.cards import CardDB  # noqa: E402
from riftsim.core.deck import Deck  # noqa: E402
from riftsim.core.game import Game  # noqa: E402
from riftsim.core.policies import make_policy  # noqa: E402
from riftsim.core.replay import _jsonable  # noqa: E402
from riftsim.core.scripts import script_all  # noqa: E402

DB = script_all(CardDB.load(os.path.join(ROOT, "data", "cards", "riftbound.json")))
LOCK = threading.Lock()
S = {"game": None, "human": 0, "ai": None, "analysis": 150, "reviews": [], "log": [], "decks": [], "seed": 0, "ai_spec": "mcts:100"}


def list_decks():
    out = []
    for d in ("data/decks/tournament", "data/decks"):
        p = os.path.join(ROOT, d)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):
            if f.endswith(".json"):
                try:
                    name = json.load(open(os.path.join(p, f)))["name"]
                except Exception:
                    continue
                out.append({"path": os.path.join(d, f), "name": name})
    return out


def masked_snapshot(g, human):
    st = _jsonable(g.snapshot())
    for p in st["players"]:
        if p["idx"] != human:
            p["hand"] = [{"uid": None, "card": None, "name": "?", "controller": p["idx"], "hidden": True} for _ in p["hand"]]
    return st


def decision_view(d):
    if d is None:
        return None
    return {"player": d.player, "kind": d.kind, "labels": list(d.labels), "n": len(d.options)}


def run_ai_until_human():
    """Let the AI take its decisions until the human must decide or the game ends. Returns list of AI move labels."""
    g, moves = S["game"], []
    while True:
        d = g.run()
        if d is None:
            return moves
        if d.player == S["human"]:
            return moves
        ch = S["ai"].choose(g, d)
        moves.append({"player": d.player, "kind": d.kind, "label": d.labels[d.options.index(ch)], "turn": g.turn})
        g.choose(ch)


def state_payload(extra=None):
    g = S["game"]
    d = g.run() if g is not None else None
    out = {"ok": True, "started": g is not None}
    if g is not None:
        out.update({"state": masked_snapshot(g, S["human"]), "decision": decision_view(d), "over": g.over, "winner": g.winner,
                    "reason": g.reason, "turn": g.turn, "human": S["human"], "reviews": S["reviews"][-200:], "log": S["log"][-60:],
                    "summary": summary()})
    if extra:
        out.update(extra)
    return out


def summary():
    rs = [r for r in S["reviews"] if r.get("grade") not in (None, "only move")]
    if not rs:
        return {"moves": 0}
    counts = {}
    for r in rs:
        counts[r["grade"]] = counts.get(r["grade"], 0) + 1
    avg_loss = sum(r["loss_pct"] for r in rs) / len(rs)
    # chess-like accuracy: 100 at zero loss, dropping with average loss
    accuracy = max(0.0, 100.0 - 2.5 * avg_loss)
    return {"moves": len(rs), "counts": counts, "avg_loss": round(avg_loss, 1), "accuracy": round(accuracy, 1)}


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(ROOT, "web"), **k)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/decks"):
            return self._json({"decks": list_decks()})
        if self.path.startswith("/api/state"):
            with LOCK:
                return self._json(state_payload())
        if self.path.startswith("/api/hint"):
            with LOCK:
                g = S["game"]
                d = g.run() if g else None
                if d is None or d.player != S["human"]:
                    return self._json({"ok": False, "error": "no decision pending"})
                an = analyze(g, d, iterations=S["analysis"], seed=len(S["reviews"]))
                return self._json({"ok": True, "options": [{"label": o["label"], "win_pct": o["win_pct"], "index": o["index"]} for o in an["options"][:8]]})
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path.startswith("/api/new"):
            with LOCK:
                decks = [Deck.load(os.path.join(ROOT, body.get("deck0", "data/decks/tournament/kaisa_void.json")), DB),
                         Deck.load(os.path.join(ROOT, body.get("deck1", "data/decks/tournament/riven_exile.json")), DB)]
                for d in decks:
                    d.validate(DB, raise_on_error=True)
                S["human"] = int(body.get("human", 0))
                S["seed"] = int(body.get("seed", 0))
                S["ai_spec"] = body.get("ai", S["ai_spec"])
                S["analysis"] = int(body.get("analysis", S["analysis"]))
                S["ai"] = make_policy(S["ai_spec"], seed=S["seed"] + 1)
                g = Game(DB, decks, seed=S["seed"], log=True)
                g.max_turns = 60
                S["game"], S["reviews"], S["log"], S["decks"] = g, [], [], [d.name for d in decks]
                moves = run_ai_until_human()
                S["log"].extend(moves)
                return self._json(state_payload({"ai_moves": moves}))
        if self.path.startswith("/api/choose"):
            with LOCK:
                g = S["game"]
                d = g.run() if g else None
                if d is None or d.player != S["human"]:
                    return self._json({"ok": False, "error": "not your decision"})
                i = int(body.get("index"))
                if not 0 <= i < len(d.options):
                    return self._json({"ok": False, "error": "bad option"})
                ch = d.options[i]
                review = {"turn": g.turn, "kind": d.kind, "label": d.labels[i], "n": len(d.options)}
                if len(d.options) > 1:
                    an = analyze(g, d, iterations=S["analysis"], seed=len(S["reviews"]))
                    review.update(grade_choice(an, ch))
                    review["alternatives"] = [{"label": o["label"], "win_pct": o["win_pct"]} for o in an["options"][:5]]
                else:
                    review.update({"grade": "only move", "loss_pct": 0.0, "win_pct": None})
                g.choose(ch)
                S["reviews"].append(review)
                S["log"].append({"player": S["human"], "kind": d.kind, "label": d.labels[i], "turn": review["turn"], "grade": review["grade"]})
                moves = run_ai_until_human()
                S["log"].extend(moves)
                return self._json(state_payload({"review": review, "ai_moves": moves}))
        return self._json({"ok": False, "error": "unknown endpoint"}, 404)


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    if "--ai" in sys.argv:
        S["ai_spec"] = sys.argv[sys.argv.index("--ai") + 1]
    if "--analysis" in sys.argv:
        S["analysis"] = int(sys.argv[sys.argv.index("--analysis") + 1])
    print(f"RiftShark play server: http://localhost:{port}/play.html  (AI {S['ai_spec']}, analysis {S['analysis']} iterations/move)")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main()
